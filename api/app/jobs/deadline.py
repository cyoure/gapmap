"""마감일 문구 → date. 날짜 계산은 LLM이 아니라 이 순수 함수가 한다."""
import re
from datetime import date

# 2026.12.31 / 2026-12-31 / 2026/12/31 / 2026년 12월 31일
_FULL = re.compile(r"(\d{4})\s*[./\-년]\s*(\d{1,2})\s*[./\-월]\s*(\d{1,2})")
# 12/31 / 12.31 / 12월 31일 (연도 없음)
_SHORT = re.compile(r"(\d{1,2})\s*[./월]\s*(\d{1,2})")
# 영어: Dec 15 / December 15, 2026
_MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
_ENGLISH = re.compile(r"\b(" + "|".join(_MONTHS) + r")[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s*(\d{4}))?", re.I)


def _safe_date(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:  # 2월 30일 같은 잘못된 날짜
        return None


def parse_deadline(raw: str | None, today: date) -> date | None:
    """기간이 적혀 있으면("11.1 ~ 12.31") 마지막 날짜가 마감일.
    연도가 없으면 올해로 보되, 이미 지났으면 내년으로 본다. 상시채용 등은 None."""
    if not raw:
        return None

    if full := _FULL.findall(raw):
        return _safe_date(*map(int, full[-1]))

    if eng := _ENGLISH.findall(raw):
        mon, d, y = eng[-1]
        m = _MONTHS.index(mon[:3].lower()) + 1
        return _safe_date(int(y), m, int(d)) if y else _no_year(m, int(d), today)

    if short := _SHORT.findall(raw):
        m, d = map(int, short[-1])
        return _no_year(m, d, today)

    return None


def _no_year(m: int, d: int, today: date) -> date | None:
    """연도가 없으면 올해로 보되, 이미 지났으면 내년."""
    this_year = _safe_date(today.year, m, d)
    if this_year and this_year < today:
        return _safe_date(today.year + 1, m, d)
    return this_year
