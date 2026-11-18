"""점수·공부 순서 계산. LLM 없이 순수 함수로 — 같은 입력이면 항상 같은 결과."""
from datetime import date


REQUIRED_WEIGHT = 2  # 필수 기술 1개 = 우대 기술 2개만큼의 비중
PREFERRED_WEIGHT = 1


def calc_match_score(required: list[bool], preferred: list[bool]) -> float | None:
    """각 리스트는 기술별 보유 여부. 가중 평균을 0~100점으로. 기술이 하나도 없으면 None."""
    total = REQUIRED_WEIGHT * len(required) + PREFERRED_WEIGHT * len(preferred)
    if total == 0:
        return None
    got = REQUIRED_WEIGHT * sum(required) + PREFERRED_WEIGHT * sum(preferred)
    return round(got / total * 100, 1)


def study_order(required_missing: list[str], preferred_missing: list[str]) -> list[str]:
    """필수 먼저, 그다음 우대. 같은 그룹 안에서는 공고에 나온 순서(보통 중요한 것부터 적음)."""
    return required_missing + [s for s in preferred_missing if s not in required_missing]


def calc_dday(deadline: date, today: date) -> int:
    """마감까지 남은 날 수. 0이면 오늘 마감, 음수면 지남. (D-3 알림은 Phase 5에서 이 함수로)"""
    return (deadline - today).days
