"""공고 원문 → LLM → JobExtraction (스키마 검증 + 실패 시 재시도)."""
import logging

from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate
from pydantic import ValidationError

from app.jobs.schema import JobExtraction
from app.llm import get_chat_model

log = logging.getLogger("uvicorn.error")

MAX_RETRIES = 2  # 첫 시도 + 재시도 2회 = 최대 3번 호출

SYSTEM = """당신은 채용공고에서 정보를 뽑아 JSON으로만 답하는 추출기입니다.

규칙:
1. 공고에 적힌 내용만 추출합니다. 추측하거나 지어내지 않습니다. 없으면 null 또는 빈 배열.
2. required에는 자격요건·필수요건에 나온 기술, preferred에는 우대사항에 나온 기술을 넣습니다.
3. 기술 이름만 짧게 씁니다. 예: "Spring Boot 기반 개발 경험 3년 이상" → "Spring Boot"
4. 하나의 항목에 기술이 여러 개면 나눕니다. 예: "JPA/Hibernate" → "JPA", "Hibernate"
5. 기술이 아닌 것은 넣지 않습니다: 학력, 경력 연차, 협업·커뮤니케이션 능력, 어학, 병역.
6. deadline_raw에는 공고 본문의 마감일 관련 문구를 한 글자도 바꾸지 말고 그대로 복사합니다. 날짜·연도를 만들어내지 않습니다. 없으면 null.
7. company에는 회사 이름만 넣습니다."""

# 프롬프트 템플릿: 지시(system)는 고정, 공고(text)만 바꿔 끼운다
PROMPT = ChatPromptTemplate.from_messages(
    [("system", SYSTEM), ("human", "다음 채용공고에서 정보를 추출하세요.\n\n<공고>\n{text}\n</공고>")]
)


class ExtractionError(Exception):
    pass


def extract(text: str) -> tuple[JobExtraction, int]:
    """(추출 결과, 시도 횟수)를 돌려준다."""
    llm = get_chat_model(
        temperature=0,  # 같은 공고 → 같은 결과
        num_ctx=8192,  # Ollama 기본 컨텍스트(2048)로는 긴 공고가 잘림
        num_predict=1024,  # 출력 상한: 무한 생성되면 잘린 JSON → 검증 실패 → 재시도로 처리
        format=JobExtraction.model_json_schema(),  # 출력 형식 자체를 스키마로 제한
    )
    messages = PROMPT.format_messages(text=text)

    for attempt in range(1, MAX_RETRIES + 2):
        reply = llm.invoke(messages)
        try:
            return JobExtraction.model_validate_json(reply.content), attempt
        except ValidationError as e:
            log.warning("job extract: attempt %d failed (%d errors)", attempt, e.error_count())
            # 무엇이 틀렸는지 알려주고 다시 요청
            messages = [
                *messages,
                reply,
                HumanMessage(f"출력이 스키마 검증에 실패했습니다: {str(e)[:300]}\n스키마에 맞는 JSON만 다시 출력하세요."),
            ]

    raise ExtractionError(f"{MAX_RETRIES + 1}번 시도했지만 스키마에 맞는 출력을 얻지 못했습니다.")
