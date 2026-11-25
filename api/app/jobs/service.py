"""공고 분석 전체 흐름: 추출(LLM) → 정규화(사전·임베딩) → 마감일(함수)."""
import logging
import re
from datetime import date, datetime, timedelta, timezone

from app.jobs.deadline import parse_deadline
from app.jobs.extract import extract
from app.gap.evidence import _pattern
from app.jobs.normalize import dictionary, normalize, spelled_in
from app.jobs.schema import JobAnalysis, Skill

log = logging.getLogger("uvicorn.error")

KST = timezone(timedelta(hours=9))  # 컨테이너 시계는 UTC → 한국 날짜 기준으로 계산


def today_kst() -> date:
    return datetime.now(KST).date()


def _in_text(phrase: str | None, text: str) -> bool:
    """공백을 무시하고 phrase가 원문에 실제로 있는지."""
    squash = lambda s: re.sub(r"\s+", "", s)  # noqa: E731
    return bool(phrase) and squash(phrase) in squash(text)


# 기술이 아닌 요건의 표현 — 사전에 없는 항목(match="none")에만 적용. 3b 모델이 프롬프트 규칙을 놓쳐도 함수로 한 번 더 거른다
_NOT_TECH = re.compile(
    r"경력|경험|자격증|자격|소지|기사$|학위|학력|전공|업무|분야|직무|개발자|엔지니어|능력|역량|이상$"
    r"|^(back|front)[\s-]?end$|^백엔드$|^프론트엔드$|^풀스택$|^full[\s-]?stack$", re.I)


def _split_not_tech(skills: list[Skill]) -> tuple[list[Skill], list[str]]:
    """(기술, 기술이 아닌 요건 원문). 사전·철자·임베딩으로 확인된 기술은 건드리지 않는다."""
    tech, others = [], []
    for s in skills:
        (others.append(s.raw) if s.match == "none" and _NOT_TECH.search(s.raw.strip()) else tech.append(s))
    return tech, others


def _grounded(skills: list[Skill], text: str) -> list[Skill]:
    """원문에 실제로 나온 기술만 남긴다 (LLM이 지어낸 기술 제거).
    LLM이 표기를 바꿨을 수 있어(스프링부트 → Spring Boot) 원문 표기·정규화 이름·동의어 중 하나만 있으면 인정.
    OCR 오타를 LLM이 고쳐 뽑은 경우(Sprlng Boot → Spring Boot)도 철자가 비슷하면 인정."""
    aliases = dictionary()
    kept = []
    for s in skills:
        if any(_pattern(n).search(text) for n in [s.raw, s.name, *aliases.get(s.name, [])]) or spelled_in(s.name, text):
            kept.append(s)
        else:
            log.warning("job analyze: skill not found in posting, discarded: %s", s.raw)
    return kept


def analyze(text: str) -> JobAnalysis:
    ext, attempts = extract(text)
    if ext.deadline_raw and not _in_text(ext.deadline_raw, text):
        # LLM이 원문에 없는 날짜를 지어낸 경우 → 틀린 날짜보다 "모름"이 낫다
        log.warning("job analyze: deadline_raw not found in posting, discarded")
        ext.deadline_raw = None

    required = _grounded(normalize(ext.required), text)
    required_names = {s.name for s in required}
    # 필수와 우대에 같은 기술이 있으면 필수로만 친다
    preferred = [s for s in _grounded(normalize(ext.preferred), text) if s.name not in required_names]
    required, others_r = _split_not_tech(required)
    preferred, others_p = _split_not_tech(preferred)
    others = list(dict.fromkeys([*ext.others, *others_r, *others_p]))  # 순서 유지 중복 제거
    verified = lambda skills: [s for s in skills if s.match != "none"]  # noqa: E731
    unverified = [s for s in required + preferred if s.match == "none"]

    return JobAnalysis(
        company=ext.company,
        required=verified(required),
        preferred=verified(preferred),
        unverified=unverified,
        others=others,
        deadline=parse_deadline(ext.deadline_raw, today_kst()),
        deadline_raw=ext.deadline_raw,
        attempts=attempts,
    )
