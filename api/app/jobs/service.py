"""공고 분석 전체 흐름: 추출(LLM) → 정규화(사전·임베딩) → 마감일(함수)."""
import logging
import re
from datetime import date, datetime, timedelta, timezone

from app.jobs.deadline import parse_deadline
from app.jobs.extract import extract
from app.jobs.normalize import normalize
from app.jobs.schema import JobAnalysis

log = logging.getLogger("uvicorn.error")

KST = timezone(timedelta(hours=9))  # 컨테이너 시계는 UTC → 한국 날짜 기준으로 계산


def today_kst() -> date:
    return datetime.now(KST).date()


def _in_text(phrase: str | None, text: str) -> bool:
    """공백을 무시하고 phrase가 원문에 실제로 있는지."""
    squash = lambda s: re.sub(r"\s+", "", s)  # noqa: E731
    return bool(phrase) and squash(phrase) in squash(text)


def analyze(text: str) -> JobAnalysis:
    ext, attempts = extract(text)
    if ext.deadline_raw and not _in_text(ext.deadline_raw, text):
        # LLM이 원문에 없는 날짜를 지어낸 경우 → 틀린 날짜보다 "모름"이 낫다
        log.warning("job analyze: deadline_raw not found in posting, discarded")
        ext.deadline_raw = None

    required = normalize(ext.required)
    required_names = {s.name for s in required}
    # 필수와 우대에 같은 기술이 있으면 필수로만 친다
    preferred = [s for s in normalize(ext.preferred) if s.name not in required_names]

    return JobAnalysis(
        company=ext.company,
        required=required,
        preferred=preferred,
        deadline=parse_deadline(ext.deadline_raw, today_kst()),
        deadline_raw=ext.deadline_raw,
        attempts=attempts,
    )
