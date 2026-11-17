"""Chroma `resume` 컬렉션: 적재(ingest)와 검색(search)."""
import logging
from urllib.parse import urlparse

import chromadb
from langchain_ollama import OllamaEmbeddings

from app import config
from app.rag.loader import load_chunks

log = logging.getLogger("uvicorn.error")

# chromadb-client 1.0.0 버그: 텔레메트리를 꺼도 posthog 호출을 시도하다 실패 로그를 남김
# (실제 전송은 실패하므로 외부로 나가는 데이터는 없음) → 해당 로거만 조용히
logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)

COLLECTION = "resume"

_embedder = OllamaEmbeddings(base_url=config.OLLAMA_BASE_URL, model=config.EMBED_MODEL)


def _client() -> chromadb.HttpClient:
    url = urlparse(config.CHROMA_URL)  # compose 서비스 이름(chroma)으로 접속
    return chromadb.HttpClient(
        host=url.hostname,
        port=url.port,
        settings=chromadb.Settings(anonymized_telemetry=False),  # 외부로 사용통계 전송 안 함
    )


def ingest() -> dict:
    """폴더 전체를 다시 적재한다. 컬렉션을 지우고 새로 만들어서 삭제된 파일의 청크가 남지 않게."""
    chunks = load_chunks(config.RESUME_DIR)
    client = _client()
    if COLLECTION in [c if isinstance(c, str) else c.name for c in client.list_collections()]:
        client.delete_collection(COLLECTION)
    col = client.create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})

    if chunks:
        # 임베딩은 Ollama(bge-m3)가 만들고, Chroma에는 벡터만 넘긴다
        vectors = _embedder.embed_documents([c["text"] for c in chunks])
        col.add(
            ids=[c["id"] for c in chunks],
            documents=[c["text"] for c in chunks],
            embeddings=vectors,
            metadatas=[{"source": c["source"]} for c in chunks],
        )

    sources = sorted({c["source"] for c in chunks})
    # 개인정보 보호: 내용은 찍지 않고 파일명·개수만 로그에 남긴다
    log.info("resume ingest: %d files, %d chunks", len(sources), len(chunks))
    return {"files": sources, "chunks": len(chunks)}


def search(query: str, k: int = 3) -> list[dict]:
    col = _client().get_collection(COLLECTION)
    res = col.query(query_embeddings=[_embedder.embed_query(query)], n_results=k)
    return [
        {"text": doc, "source": meta["source"], "score": round(1 - dist, 3)}
        for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0])
    ]
