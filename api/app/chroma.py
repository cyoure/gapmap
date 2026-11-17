"""Chroma 접속 (rag·jobs 공용)."""
import logging
from urllib.parse import urlparse

import chromadb

from app import config

# chromadb-client 1.0.0 버그: 텔레메트리를 꺼도 posthog 호출을 시도하다 실패 로그를 남김
# (실제 전송은 실패하므로 외부로 나가는 데이터는 없음) → 해당 로거만 조용히
logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)


def client() -> chromadb.HttpClient:
    url = urlparse(config.CHROMA_URL)  # compose 서비스 이름(chroma)으로 접속
    return chromadb.HttpClient(
        host=url.hostname,
        port=url.port,
        settings=chromadb.Settings(anonymized_telemetry=False),  # 외부로 사용통계 전송 안 함
    )
