"""LangGraph ReAct: agent(생각·도구 선택) ⇄ tools(실행)를 도구 호출이 없을 때까지 반복."""
from langchain_core.messages import SystemMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from app.llm import get_chat_model

SYSTEM = """당신은 취업 준비생의 채용공고 분석을 돕는 에이전트입니다. 반드시 한국어로만 답합니다.
도구 사용 규칙:
- 점수 계산은 calc_match_score, 날짜 계산은 calc_dday 도구로만 합니다. 직접 계산하지 않습니다.
- 공고에 회사 설명이 거의 없으면 web_search로 그 회사가 무슨 일을 하는지 찾습니다.
- 이력서 근거가 필요하면 search_resume을 씁니다. 이력서 내용을 web_search 검색어에 넣지 않습니다.
- 도구 결과에 없는 사실은 지어내지 않습니다. 모르면 모른다고 씁니다.
- 도구가 필요하면 "확인하겠습니다"라고 말하거나 도구 이름을 글자로 쓰지 말고, 그 자리에서 바로 도구를 호출합니다.
- 할 일을 모두 마친 뒤에만 최종 답변을 씁니다."""

GITHUB_RULE = """- '근거 없음'인 필수 기술은 search_my_code 도구로 내 GitHub 코드에 쓴 흔적이 있는지 기술 이름 하나씩 확인합니다."""


def build(tools: list):
    system = SYSTEM
    if any(t.name == "search_my_code" for t in tools):
        system += "\n" + GITHUB_RULE

    llm = get_chat_model(temperature=0, num_ctx=8192, num_predict=1024).bind_tools(tools)

    async def agent(state: MessagesState):
        # 시스템 지시는 매번 앞에 붙인다 (대화 기록에는 저장하지 않음)
        return {"messages": [await llm.ainvoke([SystemMessage(system), *state["messages"]])]}

    g = StateGraph(MessagesState)
    g.add_node("agent", agent)
    g.add_node("tools", ToolNode(tools))  # 도구 오류는 메시지로 돌려줘서 에이전트가 다시 판단
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", tools_condition)  # 도구 호출이 있으면 tools, 없으면 끝
    g.add_edge("tools", "agent")
    # 메모리: thread_id별 대화 기록 보관 → 후속 질문에서 앞의 공고·결과를 기억
    return g.compile(checkpointer=InMemorySaver())
