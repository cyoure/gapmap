"""Ollama 연결: 대화 모델 + 임베딩 모델."""
from collections.abc import AsyncIterator

from langchain_ollama import ChatOllama, OllamaEmbeddings

from app import config


def get_chat_model(**kwargs) -> ChatOllama:
    """kwargs: temperature, num_ctx, format(JSON Schema) 등 용도별 옵션."""
    return ChatOllama(base_url=config.OLLAMA_BASE_URL, model=config.OLLAMA_MODEL, **kwargs)


embedder = OllamaEmbeddings(base_url=config.OLLAMA_BASE_URL, model=config.EMBED_MODEL)


async def stream_answer(question: str) -> AsyncIterator[str]:
    llm = get_chat_model()
    try:
        async for chunk in llm.astream(question):
            if chunk.content:
                yield chunk.content
    except Exception as e:
        # 스트리밍이 시작된 뒤에는 HTTP 상태코드를 바꿀 수 없으므로 본문으로 알린다
        yield f"\n[오류] {type(e).__name__}: {e}\n"
