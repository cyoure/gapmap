"""공고 분석 스키마. LLM 출력은 반드시 이 형식으로 검증한다 (자유 텍스트 파싱 금지)."""
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class JobExtraction(BaseModel):
    """LLM이 채우는 형식. JSON Schema로 바꿔 Ollama `format`에 넘겨 출력 자체를 제한한다."""

    company: str | None = Field(description="회사명. 공고에 없으면 null")
    required: list[str] = Field(description="자격요건(필수)에 나온 기술 이름 목록")
    preferred: list[str] = Field(description="우대사항에 나온 기술 이름 목록")
    deadline_raw: str | None = Field(description="마감일 관련 문구 원문 그대로. 없으면 null")


class Skill(BaseModel):
    name: str  # 정규화된 이름 (예: Spring Boot)
    raw: str  # 공고 원문 표기 (예: 스프링부트)
    match: Literal["dict", "embedding", "none"]  # 어떻게 정규화됐는지
    score: float | None = None  # 임베딩 유사도 (dict 매칭이면 null)


class JobAnalysis(BaseModel):
    """API 응답 형식. 날짜는 LLM이 아니라 함수(parse_deadline)가 계산한다."""

    company: str | None
    required: list[Skill]
    preferred: list[Skill]
    deadline: date | None
    deadline_raw: str | None
    attempts: int  # LLM 호출 횟수 (1이면 한 번에 성공, 최대 3)


class AnalyzeRequest(BaseModel):
    text: str = Field(min_length=20, description="사용자가 붙여넣은 채용공고 원문")
