"""공고 분석 스키마. LLM 출력은 반드시 이 형식으로 검증한다 (자유 텍스트 파싱 금지)."""
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class JobExtraction(BaseModel):
    """LLM이 채우는 형식. JSON Schema로 바꿔 Ollama `format`에 넘겨 출력 자체를 제한한다."""

    company: str | None = Field(description="회사명. 공고에 없으면 null")
    required: list[str] = Field(description="자격요건(필수)에 나온 기술 이름 목록")
    preferred: list[str] = Field(description="우대사항에 나온 기술 이름 목록")
    # 기술이 아닌 요건을 넣을 칸 — 칸이 없으면 작은 모델은 이런 항목을 기술 목록에 억지로 넣는다
    others: list[str] = Field(description="기술이 아닌 요건: 경력 연차, 도메인·서비스 경험, 자격증, 학력, 직무명")
    deadline_raw: str | None = Field(description="마감일 관련 문구 원문 그대로. 없으면 null")


class Skill(BaseModel):
    name: str  # 정규화된 이름 (예: Spring Boot)
    raw: str  # 공고 원문 표기 (예: 스프링부트)
    match: Literal["dict", "spelling", "embedding", "none"]  # 어떻게 정규화됐는지
    score: float | None = None  # 임베딩 유사도 (dict 매칭이면 null)


class JobAnalysis(BaseModel):
    """API 응답 형식. 날짜는 LLM이 아니라 함수(parse_deadline)가 계산한다."""

    company: str | None
    required: list[Skill]
    preferred: list[Skill]
    # 사전에도 없고 비슷한 철자·의미도 없는 항목 (OCR 잡음, "자격증 소지" 같은 비기술, 사전에 없는 새 기술).
    # 점수·공부 순서·통계에서 빼고 "확인 필요"로만 보여준다 — 실제 기술이면 skills.yaml에 추가하면 다음부터 반영
    unverified: list[Skill] = []
    # 기술이 아닌 요건 (경력·도메인 경험·자격증 등). 이력서·GitHub로 판단할 수 없어 근거 판정·점수에서 뺀다
    others: list[str] = []
    deadline: date | None
    deadline_raw: str | None
    attempts: int  # LLM 호출 횟수 (1이면 한 번에 성공, 최대 3)


class AnalyzeRequest(BaseModel):
    text: str = Field(min_length=20, description="사용자가 붙여넣은 채용공고 원문")
