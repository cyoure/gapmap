"""갭 분석 형식."""
from typing import Literal

from pydantic import BaseModel

HAVE = "보유"
NO_EVIDENCE = "근거 없음"  # "부족"이라고 단정하지 않는다 — 이력서에 안 썼을 뿐일 수 있음

Status = Literal["보유", "근거 없음"]


class SkillGap(BaseModel):
    name: str
    kind: Literal["required", "preferred"]
    status: Status
    source: Literal["resume", "user"]  # 자동 판정(이력서) / 사용자가 직접 수정
    evidence: str | None = None  # 보유 근거: 이력서에서 기술명이 나온 부분
    evidence_file: str | None = None
    hint: str | None = None  # 근거 없음일 때: 의미상 가장 가까운 이력서 문단 (참고용)
    hint_score: float | None = None


class StatusUpdate(BaseModel):
    status: Status
