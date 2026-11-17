"""FastAPI 라우터만 둔다. 로직은 다른 모듈에."""
import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse

from app import config
from app.jobs.extract import ExtractionError
from app.jobs.schema import AnalyzeRequest, JobAnalysis
from app.jobs.service import analyze
from app.llm import stream_answer
from app.rag import store

app = FastAPI(title="GapMap")


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
