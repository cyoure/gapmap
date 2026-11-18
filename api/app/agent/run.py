"""에이전트 실행 + 스트리밍: 도구 호출 과정(🔧)과 최종 답변 토큰을 흘려보낸다."""
import json
import logging
import uuid
from collections.abc import AsyncIterator

from langchain_core.messages import HumanMessage
from langgraph.errors import GraphRecursionError
from starlette.concurrency import run_in_threadpool

from app.agent.graph import build
from app.agent.mcp import load_github_tools
from app.agent.tools import CONTEXT, LOCAL_TOOLS
from app.db import store as db
from app.gap.report import Prepared, prepare

log = logging.getLogger("uvicorn.error")

RECURSION_LIMIT = 16  # agent↔tools 왕복 상한 (무한 반복 방지)
_graph = None


async def init() -> None:
    """서버 시작 시 1회: GitHub MCP 도구를 불러와 그래프를 만든다."""
    global _graph
    tools = LOCAL_TOOLS + await load_github_tools()
    _graph = build(tools)
    log.info("agent ready: tools=%s", [t.name for t in tools])


def _task(p: Prepared, posting: str) -> str:
    """계산이 끝난 결과를 에이전트에게 넘긴다. 공고 원문도 함께 (회사 정보 판단용)."""
    facts = {
        "company": p.a.company,
        "deadline": str(p.a.deadline) if p.a.deadline else None,
        "required": {g.name: g.status for g in p.gaps if g.kind == "required"},
        "preferred": {g.name: g.status for g in p.gaps if g.kind == "preferred"},
        "score": p.score,
    }
    return f"""다음은 채용공고와, 함수로 계산한 분석 결과입니다.

[분석 결과]
{json.dumps(facts, ensure_ascii=False)}

[공고 원문]
{posting}

할 일 (필요한 도구를 스스로 골라 쓰세요):
1. 공고에 회사 설명이 부족하면 web_search로 회사가 무엇을 하는 곳인지 찾아 2줄로 요약
2. deadline이 있으면 calc_dday로 남은 날짜 확인
3. '근거 없음'인 필수 기술은 search_resume(그리고 있으면 search_code)로 근거를 한 번 더 찾고,
   새로 찾았을 때만 그 기술 이름을 newly_have에 넣어 calc_match_score로 점수 재계산
4. 마지막에 정리: 회사 요약 / 마감 D-day / 새로 찾은 근거 / 다음에 할 일 3가지"""


async def run(thread_id: str, message: str) -> AsyncIterator[str]:
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": RECURSION_LIMIT}
    try:
        async for mode, data in _graph.astream(
            {"messages": [HumanMessage(message)]}, config, stream_mode=["updates", "messages"]
        ):
            if mode == "messages":  # LLM 토큰 단위 스트리밍 (최종 답변 글자)
                chunk, meta = data
                if meta.get("langgraph_node") == "agent" and chunk.content:
                    yield chunk.content
            elif "agent" in data:  # 에이전트가 도구를 고른 순간
                for call in data["agent"]["messages"][-1].tool_calls:
                    args = json.dumps(call["args"], ensure_ascii=False)
                    log.info("agent tool call: %s(%s)", call["name"], args[:200])  # 도구·인자만 (결과는 X)
                    yield f"\n🔧 {call['name']}({args})\n"
            elif "tools" in data:  # 도구 실행 결과 (짧게만)
                for m in data["tools"]["messages"]:
                    yield f"   ↳ {str(m.content)[:120].replace(chr(10), ' ')}…\n"
    except GraphRecursionError:
        yield f"\n[중단] 도구 호출이 {RECURSION_LIMIT}단계를 넘어 멈췄습니다.\n"
    except Exception as e:
        log.warning("agent failed: %s", type(e).__name__)
        yield f"\n[오류] {type(e).__name__}: {e}\n"


async def stream_agent_report(text: str, thread_id: str) -> AsyncIterator[str]:
    yield "⏳ 공고 분석 중...\n\n"
    p = await prepare(text)
    if isinstance(p, str):
        yield p
        return
    yield p.md + "\n## 에이전트 분석\n"
    CONTEXT[thread_id] = p  # 점수 도구가 이 공고의 판정 결과를 직접 읽도록
    if len(CONTEXT) > 100:  # 오래된 대화는 버린다 (메모리 보호)
        CONTEXT.pop(next(iter(CONTEXT)))
    answer = ""
    async for piece in run(thread_id, _task(p, text)):
        answer += piece
        yield piece
    await run_in_threadpool(db.save_report, p.job_id, p.md + "\n## 에이전트 분석\n" + answer)
    yield f"\n\n---\n💾 저장됨: job #{p.job_id} / 후속 질문: POST /agent/chat (thread_id={thread_id})\n"


def new_thread_id() -> str:
    return uuid.uuid4().hex[:12]
