"""갭 리포트 스트리밍: 계산 결과(표·점수·순서)를 먼저 내보내고, LLM 공부 가이드를 토큰 단위로 이어서."""
import logging
from collections.abc import AsyncIterator

from langchain_core.prompts import ChatPromptTemplate
from starlette.concurrency import run_in_threadpool

from app.db import store as db
from app.gap.evidence import find_gaps
from app.gap.schema import HAVE, SkillGap
from app.gap.score import PREFERRED_WEIGHT, REQUIRED_WEIGHT, calc_match_score, study_order
from app.jobs.schema import JobAnalysis
from app.jobs.service import analyze
from app.llm import get_chat_model

log = logging.getLogger("uvicorn.error")

KIND = {"required": "필수", "preferred": "우대"}

ADVICE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """당신은 백엔드 개발 취업 준비생의 학습 코치입니다. 반드시 한국어로만 답합니다.
규칙:
- 주어진 '공부할 기술'만, 주어진 순서 그대로 번호 목록으로 씁니다. 기술을 추가하거나 순서를 바꾸지 않습니다.
- 기술마다 2~3문장: 이 공고에서 왜 필요한지, 이미 보유한 기술과 연결해서 무엇부터 해보면 좋은지.
- 점수, 날짜, 합격 가능성은 언급하지 않습니다."""),
    ("human", "회사: {company}\n이미 보유한 기술: {have}\n공부할 기술(이 순서대로): {order}"),
])


def _cell(s: str | None) -> str:
    return (s or "").replace("|", "\\|")  # 마크다운 표가 깨지지 않게


def render(a: JobAnalysis, gaps: list[SkillGap], score: float | None, order: list[str]) -> str:
    """계산 결과 → 마크다운. LLM을 쓰지 않는 부분."""
    req = [g for g in gaps if g.kind == "required"]
    pref = [g for g in gaps if g.kind == "preferred"]
    have = lambda gs: sum(g.status == HAVE for g in gs)  # noqa: E731

    lines = [f"# 갭 분석 리포트 — {a.company or '회사명 없음'}", ""]
    lines.append(f"- 마감: {a.deadline or '정보 없음'}" + (f" (원문: {a.deadline_raw})" if a.deadline_raw else ""))
    lines.append(f"- **매칭 점수: {score if score is not None else '-'}점** "
                 f"(필수 {have(req)}/{len(req)} ×{REQUIRED_WEIGHT}, 우대 {have(pref)}/{len(pref)} ×{PREFERRED_WEIGHT})")
    fixed = [s for s in a.required + a.preferred if s.match == "spelling"]
    if fixed:
        lines.append("- 🔤 오타 보정: " + ", ".join(f"{_cell(s.raw)} → {s.name}" for s in fixed))
    lines += ["", "## 기술별 상태", "", "| 구분 | 기술 | 상태 | 근거 |", "|---|---|---|---|"]
    for g in gaps:
        if g.source == "user":
            basis = "사용자가 직접 수정"
        elif g.status == HAVE:
            basis = f"{g.evidence_file}: {g.evidence}"
        elif g.hint:
            basis = f"참고(유사도 {g.hint_score}): {g.hint} — 맞다면 PATCH로 '보유' 처리"
        else:
            basis = ""
        mark = "✅" if g.status == HAVE else "❔"
        lines.append(f"| {KIND[g.kind]} | {_cell(g.name)} | {mark} {g.status} | {_cell(basis)} |")
    if a.others:
        lines += ["", "**📋 기타 요건 (기술 아님 · 점수 제외)**: " + ", ".join(_cell(o) for o in a.others),
                  "— 경력·도메인 경험·자격증은 이력서·코드로 판단할 수 없어 직접 확인하세요."]
    if a.unverified:
        lines += ["", f"⚠️ **확인 필요 {len(a.unverified)}개 (점수 제외)**: "
                  + ", ".join(_cell(s.raw) for s in a.unverified),
                  "— 기술 사전에 없는 항목이에요. OCR 오타나 기술이 아닌 항목(자격증·직무명)일 수 있어요. "
                  "실제 기술이면 `skills.yaml`에 추가하면 다음 분석부터 반영돼요."]

    lines += ["", "## 공부 순서", ""]
    kind_of = {g.name: KIND[g.kind] for g in gaps}
    lines += [f"{i}. {name} ({kind_of[name]})" for i, name in enumerate(order, 1)] or ["모든 기술의 근거가 있습니다. 🎉"]
    return "\n".join(lines) + "\n"


class Prepared:
    """계산까지 끝난 분석 결과 (Phase 3 리포트와 Phase 4 에이전트가 함께 사용)."""

    def __init__(self, a: JobAnalysis, gaps: list[SkillGap], score: float | None, order: list[str], job_id: int):
        self.a, self.gaps, self.score, self.order, self.job_id = a, gaps, score, order, job_id
        self.md = render(a, gaps, score, order)


def _drop_hidden(a: JobAnalysis, hidden: set[str]) -> JobAnalysis:
    """사용자가 통계에서 숨긴 이름(기술 아님)은 다음 분석부터 '확인 필요'로 보내 점수에서 뺀다."""
    keep = lambda skills: [s for s in skills if s.name not in hidden]  # noqa: E731
    dropped = [s for s in a.required + a.preferred if s.name in hidden]
    return a.model_copy(update={"required": keep(a.required), "preferred": keep(a.preferred),
                                "unverified": a.unverified + dropped})


def _prepare(text: str) -> Prepared:
    """공고 분석 → 근거 판정 → 점수·순서 계산 → DB 저장. LLM은 추출에만 쓰고 나머지는 함수."""
    a = _drop_hidden(analyze(text), set(db.hidden_skills()))
    gaps = find_gaps(a, db.get_overrides())
    missing = lambda kind: [g.name for g in gaps if g.kind == kind and g.status != HAVE]  # noqa: E731
    score = calc_match_score([g.status == HAVE for g in gaps if g.kind == "required"],
                             [g.status == HAVE for g in gaps if g.kind == "preferred"])
    order = study_order(missing("required"), missing("preferred"))
    job_id = db.save_job(text, a.model_dump(mode="json"), [g.model_dump() for g in gaps], score)
    return Prepared(a, gaps, score, order, job_id)


async def prepare(text: str) -> Prepared | str:
    """성공하면 Prepared, 실패하면 사용자에게 보여줄 오류 문구."""
    try:
        # analyze·DB·Chroma는 동기(blocking) 함수 → 스레드풀에서 실행해 이벤트 루프를 막지 않는다
        return await run_in_threadpool(_prepare, text)
    except Exception as e:
        log.warning("gap prepare failed: %s", type(e).__name__)
        hint = " (이력서를 먼저 POST /resume/ingest 했는지 확인하세요)" if "NotFound" in type(e).__name__ else ""
        return f"[오류] {type(e).__name__}: {e}{hint}\n"


async def stream_report(text: str) -> AsyncIterator[str]:
    yield "⏳ 공고 분석 중...\n\n"
    p = await prepare(text)
    if isinstance(p, str):
        yield p
        return
    a, gaps, order, job_id, md = p.a, p.gaps, p.order, p.job_id, p.md
    yield md

    advice = ""
    if order:
        yield "\n## 공부 가이드 (AI 작성)\n\n"
        llm = get_chat_model(temperature=0.3, num_predict=1024)
        prompt = ADVICE_PROMPT.format_messages(
            company=a.company or "미상",
            have=", ".join(g.name for g in gaps if g.status == HAVE) or "없음",
            order=", ".join(order),
        )
        try:
            async for chunk in llm.astream(prompt):
                if chunk.content:
                    advice += chunk.content
                    yield chunk.content
        except Exception as e:
            yield f"\n[오류] 공부 가이드 생성 실패: {type(e).__name__}\n"

    await run_in_threadpool(db.save_report, job_id, md + ("\n## 공부 가이드 (AI 작성)\n\n" + advice if advice else ""))
    yield f"\n\n---\n💾 저장됨: job #{job_id}\n"
