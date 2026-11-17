"""Chroma `resume` 컬렉션: 적재(ingest)와 검색(search)."""
import logging

from app import config
from app.chroma import client
from app.llm import embedder
from app.rag.loader import load_chunks

log = logging.getLogger("uvicorn.error")

COLLECTION = "resume"


def ingest() -> dict:
    """폴더 전체를 다시 적재한다. 컬렉션을 지우고 새로 만들어서 삭제된 파일의 청크가 남지 않게."""
    chunks = load_chunks(config.RESUME_DIR)
    c = client()
    if COLLECTION in [x if isinstance(x, str) else x.name for x in c.list_collections()]:
        c.delete_collection(COLLECTION)
    col = c.create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})

    if chunks:
        # 임베딩은 Ollama(bge-m3)가 만들고, Chroma에는 벡터만 넘긴다
        vectors = embedder.embed_documents([ch["text"] for ch in chunks])
        col.add(
            ids=[ch["id"] for ch in chunks],
            documents=[ch["text"] for ch in chunks],
            embeddings=vectors,
            metadatas=[{"source": ch["source"]} for ch in chunks],
        )

    sources = sorted({ch["source"] for ch in chunks})
    # 개인정보 보호: 내용은 찍지 않고 파일명·개수만 로그에 남긴다
    log.info("resume ingest: %d files, %d chunks", len(sources), len(chunks))
    return {"files": sources, "chunks": len(chunks)}


def search(query: str, k: int = 3) -> list[dict]:
    col = client().get_collection(COLLECTION)
    res = col.query(query_embeddings=[embedder.embed_query(query)], n_results=k)
    return [
        {"text": doc, "source": meta["source"], "score": round(1 - dist, 3)}
        for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0])
    ]
