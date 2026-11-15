"""FastAPI 라우터만 둔다. 로직은 다른 모듈에."""
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse

from app import config
from app.db import store as db
from app.gap.report import stream_report
from app.gap.schema import StatusUpdate
from app.jobs.extract import ExtractionError
from app.jobs.normalize import canonical
from app.jobs.schema import AnalyzeRequest, JobAnalysis
from app.jobs.service import analyze
from app.llm import stream_answer
from app.rag import store


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_schema()  # 테이블이 없으면 생성 (compose healthcheck로 DB 준비 후에 시작됨)
    yield


app = FastAPI(title="GapMap", lifespan=lifespan)


async def _ping(url: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(url)
        return "ok" if r.status_code == 200 else f"http {r.status_code}"
    except httpx.HTTPError as e:
        return f"down ({type(e).__name__})"


@app.get("/health")
async def health():
    return {
        "api": "ok",
        "ollama": await _ping(f"{config.OLLAMA_BASE_URL}/api/tags"),
        "chroma": await _ping(f"{config.CHROMA_URL}/api/v2/heartbeat"),
        "model": config.OLLAMA_MODEL,
    }


@app.get("/chat")
async def chat(q: str = Query(..., min_length=1)):
    return StreamingResponse(stream_answer(q), media_type="text/plain; charset=utf-8")


# chroma 클라이언트·임베딩 호출은 동기(blocking)라서 async가 아닌 def로 선언 →
# FastAPI가 별도 스레드풀에서 실행해 이벤트 루프(스트리밍 등)를 막지 않는다
@app.post("/resume/ingest")
def resume_ingest():
    return store.ingest()


@app.get("/resume/search")
def resume_search(q: str = Query(..., min_length=1), k: int = Query(3, ge=1, le=10)):
    try:
        return {"query": q, "results": store.search(q, k)}
    except Exception as e:  # 컬렉션이 아직 없을 때 (ingest 전)
        raise HTTPException(404, f"resume 컬렉션이 없습니다. 먼저 POST /resume/ingest 하세요. ({type(e).__name__})")


@app.post("/jobs/analyze", response_model=JobAnalysis)
def jobs_analyze(req: AnalyzeRequest):
    """공고는 사용자가 직접 붙여넣는다 (크롤링 금지)."""
    try:
        return analyze(req.text)
    except ExtractionError as e:
        raise HTTPException(502, str(e))


@app.post("/gap/report")
async def gap_report(req: AnalyzeRequest):
    """공고 → 보유/근거 없음 표 + 점수 + 공부 순서 + AI 공부 가이드 (스트리밍, postgres 저장)."""
    return StreamingResponse(stream_report(req.text), media_type="text/plain; charset=utf-8")


# {name:path} — "CI/CD"처럼 이름에 "/"가 들어간 기술도 받기 위해
@app.patch("/skills/{name:path}")
def skill_set(name: str, body: StatusUpdate):
    """자동 판정이 틀렸을 때 사용자가 직접 상태를 고친다. 다음 리포트부터 반영."""
    canon = canonical(name)
    db.set_override(canon, body.status)
    return {"name": canon, "status": body.status, "source": "user"}


@app.delete("/skills/{name:path}")
def skill_reset(name: str):
    """직접 고친 상태를 지우고 자동 판정으로 되돌린다."""
    canon = canonical(name)
    if not db.delete_override(canon):
        raise HTTPException(404, f"{canon}: 직접 수정한 기록이 없습니다.")
    return {"name": canon, "source": "resume"}
