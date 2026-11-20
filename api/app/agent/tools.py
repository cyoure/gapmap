"""에이전트 로컬 도구. 계산은 LLM이 아니라 여기 함수가 한다 (Function Calling)."""
from datetime import date
from typing import Annotated

from ddgs import DDGS
from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from app.gap.evidence import _pattern
from app.gap.schema import HAVE
from app.gap.score import calc_dday as _dday
from app.gap.score import calc_match_score as _score
from app.jobs.normalize import canonical
from app.jobs.service import today_kst
from app.rag import store

# thread_id → 그 대화에서 분석한 공고 (Prepared). 도구가 상태 목록을 LLM에게서 받지 않고 여기서 직접 읽는다
CONTEXT: dict = {}
EVIDENCE_TOOLS = {"search_resume", "search_my_code"}


@tool
def search_resume(query: str) -> str:
    """내 이력서에서 query와 관련된 문단을 찾는다. 기술 경험의 근거를 확인할 때 사용."""
    hits = store.search(query, k=3)
    return "\n\n".join(f"[{h['source']}, 유사도 {h['score']}] {h['text'][:300]}" for h in hits) or "결과 없음"


@tool
def web_search(query: str) -> str:
    """인터넷 검색(DuckDuckGo). 회사가 무엇을 하는 곳인지 등 공고에 없는 정보를 찾을 때 사용.
    이력서 내용은 절대 검색어에 넣지 않는다."""
    # ddgs(구 duckduckgo-search) 기본(auto) 백엔드: DuckDuckGo가 봇 확인(202)으로 막으면 다른 엔진으로 넘어감.
    # region="kr-kr"은 결과 0건이 잦아서 전 세계(wt-wt) — 한글 검색어도 결과가 나옴 (2026-11-18 확인)
    try:
        results = DDGS().text(query[:100], region="wt-wt", max_results=5)  # 외부로 나가는 건 검색어뿐
    except Exception as e:
        return f"검색 실패({type(e).__name__}). 다른 검색어로 다시 시도하거나 모른다고 답하세요."
    return "\n".join(f"- {r['title']}: {r['body'][:200]}" for r in results) or "결과 없음"


@tool
def calc_match_score(
    newly_have: list[str], state: Annotated[dict, InjectedState], config: RunnableConfig
) -> str:
    """이 공고의 매칭 점수(0~100)를 다시 계산한다. 직접 계산하지 말고 반드시 이 도구를 쓴다.
    newly_have: search_resume이나 search_my_code 결과에서 '새로' 근거를 찾은 '근거 없음' 기술 이름 목록 (없으면 [])."""
    # state·config는 LangGraph가 넣어준다 (LLM에게 보이는 인자는 newly_have 하나뿐)
    p = CONTEXT.get(config["configurable"]["thread_id"])
    if p is None:
        return "이 대화에는 분석된 공고가 없습니다."
    # 근거 도구들이 실제로 돌려준 내용 — LLM의 주장만으로는 반영하지 않는다
    seen = "\n".join(str(m.content) for m in state["messages"]
                     if isinstance(m, ToolMessage) and m.name in EVIDENCE_TOOLS)
    missing = {g.name for g in p.gaps if g.status != HAVE}
    accepted, rejected = [], []
    for name in {canonical(n) for n in newly_have}:
        (accepted if name in missing and _pattern(name).search(seen) else rejected).append(name)

    have = lambda g: g.status == HAVE or g.name in accepted  # noqa: E731
    s = _score([have(g) for g in p.gaps if g.kind == "required"], [have(g) for g in p.gaps if g.kind == "preferred"])
    out = f"{s}점 (원래 {p.score}점)"
    if accepted:
        out += f" / 새 근거 반영: {', '.join(accepted)}"
    if rejected:
        out += f" / 반영 안 함(근거 도구 결과에서 확인 안 됨 또는 이미 보유): {', '.join(rejected)}"
    return out


@tool
def calc_dday(deadline: str) -> str:
    """마감일(YYYY-MM-DD)까지 오늘 기준 남은 날 수를 계산한다. 날짜 계산은 반드시 이 도구를 쓴다."""
    try:
        d = _dday(date.fromisoformat(deadline), today_kst())
    except ValueError:
        return "날짜 형식이 잘못됐습니다. YYYY-MM-DD로 주세요."
    return f"D-{d}" if d > 0 else ("오늘 마감 (D-day)" if d == 0 else f"마감 {-d}일 지남")


LOCAL_TOOLS = [search_resume, web_search, calc_match_score, calc_dday]
