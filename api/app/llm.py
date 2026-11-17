"""Ollama 연결. 토큰이 생성되는 대로 하나씩 내보내는 비동기 제너레이터."""
from collections.abc import AsyncIterator

from langchain_ollama import ChatOllama

from app import config


def get_chat_model() -> ChatOllama:
    return ChatOllama(base_url=config.OLLAMA_BASE_URL, model=config.OLLAMA_MODEL)


async def stream_answer(question: str) -> AsyncIterator[str]:
    llm = get_chat_model()
    try:
        async for chunk in llm.astream(question):
            if chunk.content:
                yield chunk.content
    except Exception as e:
        # 스트리밍이 시작된 뒤에는 HTTP 상태코드를 바꿀 수 없으므로 본문으로 알린다
        yield f"\n[오류] {type(e).__name__}: {e}\n"
