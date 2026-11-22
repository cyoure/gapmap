# GapMap — 채용공고 갭 분석 에이전트

채용공고를 붙여넣으면 **내 이력서·GitHub 코드와 비교해서 근거가 없는 기술과 공부 순서**를 알려주는 로컬 AI 에이전트입니다.
공고가 쌓일수록 "여러 회사가 공통으로 원하는 기술" 통계를 보여주고, 마감이 다가오면 Discord로 알려줍니다.

- 🔒 **이력서는 밖으로 나가지 않습니다.** LLM·임베딩은 모두 로컬 Ollama에서 실행합니다.
- 🧮 **계산은 LLM이 아니라 함수가 합니다.** 매칭 점수·D-day·공부 순서는 순수 함수라 같은 입력이면 항상 같은 결과가 나옵니다.
- ❔ **"부족" 대신 "근거 없음"** 으로 표시합니다. 이력서에 안 썼을 뿐일 수 있으니 사용자가 직접 고칠 수 있습니다.

## 아키텍처

```
브라우저(localhost:8000) → [api: FastAPI + LangGraph ReAct 에이전트]
                              ├─ ollama     : 대화 모델(qwen2.5) + 임베딩(bge-m3)
                              ├─ chroma     : 이력서 · 기술 사전 벡터
                              ├─ postgres   : 공고 · 분석 결과 · 직접 수정한 상태
                              ├─ GitHub MCP : 내 저장소 코드 근거 (외부, 읽기 전용)
                              └─ DuckDuckGo : 회사 정보 검색 (외부, 검색어만 전송)
[n8n] 매일 09:00 · 매주 월 09:00 → api /alerts/* 호출 → Discord 웹훅
```

모든 서비스는 `docker-compose.yml` 하나로 실행되고, 모델·벡터·DB·n8n 데이터는 **볼륨**에 저장되어 컨테이너를 다시 만들어도 유지됩니다.

## 사용 기술과 쓰인 곳

| 기술 | 쓰인 곳 |
|---|---|
| Docker · Compose · 볼륨 | `docker-compose.yml` — 5개 서비스, 서비스 이름으로 통신, healthcheck로 기동 순서 |
| Ollama (로컬 LLM) | `api/app/llm.py` — 대화·추출 모델, bge-m3 임베딩 |
| FastAPI 스트리밍 | `/chat`, `/gap/report`, `/agent/report` — `StreamingResponse`로 생성되는 대로 출력 |
| 프롬프트 템플릿 · 구조화 출력 | `api/app/jobs/extract.py` — JSON Schema로 출력 제한 + Pydantic 검증, 실패 시 2회 재시도 |
| RAG · ChromaDB | `api/app/rag/` — 이력서 청킹·검색, `api/app/jobs/normalize.py` — 기술명 동의어 매칭 |
| Function Calling | `api/app/agent/tools.py` — `calc_match_score`, `calc_dday`, `search_resume`, `web_search` |
| ReAct · LangGraph · 메모리 | `api/app/agent/` — agent ⇄ tools 그래프, `thread_id`별 대화 기억(후속 질문) |
| MCP | `api/app/agent/mcp.py` — GitHub MCP(langchain-mcp-adapters), 검색 범위를 고정한 래퍼 |
| 웹 검색 | DuckDuckGo(`ddgs`) — 공고에 회사 설명이 부족할 때 에이전트가 스스로 호출 |
| n8n | `n8n/*.json` — 마감 D-3 알림, 주간 요약 → Discord |

## 실행 방법

### 1. 준비
- Docker Desktop (실행 중이어야 함)
- 디스크 여유 10GB 이상 (모델)

```bash
cp .env.example .env          # 값 채우기 (아래 표 참고)
mkdir -p data/resume          # 이력서(.md/.txt/.pdf)를 여기에 — Git에 올라가지 않음
docker compose up -d
docker compose exec ollama ollama pull qwen2.5:3b
docker compose exec ollama ollama pull bge-m3
curl -X POST http://localhost:8000/resume/ingest      # 이력서 → 벡터 적재
```

| `.env` 항목 | 설명 |
|---|---|
| `OLLAMA_MODEL` | 개발 `qwen2.5:3b`(CPU), 시연 `qwen2.5:7b` |
| `POSTGRES_PASSWORD` | 아무 값으로 변경 |
| `GITHUB_TOKEN`, `GITHUB_USER` | Fine-grained 토큰, Public 저장소 읽기 전용. 비우면 GitHub 도구만 빠짐 |
| `DISCORD_WEBHOOK_URL` | Discord 채널 → 연동 → 웹후크 URL. **커밋 금지** |

### 2. 사용
- 웹 화면: **http://localhost:8000** — 공고 붙여넣기 → `빠른 리포트` 또는 `에이전트 분석`
- API 문서: http://localhost:8000/docs

### 3. n8n 알림 (선택)
```bash
# Git Bash에서는 컨테이너 경로가 Windows 경로로 바뀌지 않게 MSYS_NO_PATHCONV=1 필요
MSYS_NO_PATHCONV=1 docker compose exec n8n n8n import:workflow --separate --input=/workflows
```
http://localhost:5679 에서 계정 생성 → 워크플로우 열기 → `Execute workflow`로 테스트 → **Active** 켜기.

## API

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/` | 웹 화면 |
| GET | `/health` | ollama·chroma 연결 상태, 사용 모델 |
| GET | `/chat?q=` | 단순 대화 (스트리밍) |
| POST | `/resume/ingest` | `data/resume/` → Chroma `resume` 컬렉션 |
| GET | `/resume/search?q=` | 이력서 의미 검색 |
| POST | `/jobs/analyze` | 공고 → `{company, required[], preferred[], deadline}` |
| POST | `/gap/report` | 보유/근거 없음 표 + 점수 + 공부 순서 + AI 가이드 (스트리밍, 저장) |
| POST | `/agent/report` | 위 결과 + ReAct 에이전트가 도구로 보충 (스트리밍, `X-Thread-Id` 헤더) |
| POST | `/agent/chat` | `{thread_id, message}` 후속 질문 |
| PATCH / DELETE | `/skills/{name}` | 기술 상태 직접 수정 / 자동 판정으로 되돌리기 |
| GET | `/stats` | 저장된 공고에서 자주 요구되는 기술 순위 |
| GET | `/alerts/deadlines?days=3`, `/alerts/weekly` | n8n용 알림 데이터 + Discord 문구 |

## 폴더 구조

```
api/app/
├── main.py        # 라우터만
├── config.py      # 환경변수 (모델명·URL 하드코딩 금지)
├── llm.py         # Ollama 연결
├── rag/           # 이력서 적재·검색
├── jobs/          # 공고 추출·정규화(skills.yaml)·마감일 파싱
├── gap/           # 근거 판정·점수·리포트
├── agent/         # LangGraph ReAct + 도구 + GitHub MCP
├── db/            # PostgreSQL
├── notify/        # n8n 알림 문구
└── static/        # 웹 화면 (HTML 1장)
n8n/               # 워크플로우 export(json)
docs/adr/          # 기술 결정·트러블슈팅 기록
```

## 원칙

- **크롤링하지 않습니다.** 채용 사이트 약관 문제로, 공고는 사용자가 직접 붙여넣습니다.
- **LLM 출력은 항상 스키마로 검증하고, 원문에 없는 기술·날짜는 버립니다.** ([ADR-0002](docs/adr/0002-llm-output-validation.md))
- `data/`와 `.env`는 커밋하지 않고, 이력서 내용은 로그에 남기지 않습니다.

## 알려진 한계 (qwen2.5:3b 기준)

- 공고 추출에서 "~운영 경험" 같은 표현의 기술(예: Kubernetes)이나 "Git 협업 경험"을 놓칠 때가 있음
- 답변에 중국어가 섞이거나 공부 가이드에서 같은 기술을 반복할 때가 있음 → 7b 비교 예정
- 알림의 매칭 점수는 분석 시점 값이라, 나중에 상태를 직접 고쳐도 점수는 그대로 (근거 없음 목록은 반영됨)
