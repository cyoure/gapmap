# 트러블슈팅 기록

형식: **증상 → 원인 → 해결 → 배운 점**. 에러가 나면 추측으로 고치기 전에 `docker compose logs <서비스>`부터 본다.

---

## 1. 웹 검색이 결과 0건 / 202 응답
- **증상**: 에이전트의 `web_search`가 회사 정보를 하나도 못 가져옴.
- **원인**: DuckDuckGo가 자동화된 요청을 봇으로 판단해서 `202`(봇 확인 페이지)를 돌려줌. `region="kr-kr"`도 결과 0건이 잦았음.
- **해결**: `duckduckgo-search` → 후속 라이브러리 `ddgs`로 교체. 기본(auto) 백엔드는 DuckDuckGo가 막히면 다른 엔진으로 넘어간다. region은 `wt-wt`(전 세계)로 바꿈 (한글 검색어도 결과 나옴).
- **배운 점**: 외부 서비스는 언제든 막힐 수 있다 → 검색이 실패해도 리포트는 나오도록 도구 실패를 에이전트가 받아들이게 했다.

## 2. LLM이 공고에 없는 기술을 지어내서 100점
- **증상**: 기술 스택이 적혀 있지 않은 공고인데 리포트에 필수 기술 `Java`가 나오고 매칭 점수가 100점.
- **원인**: 3b 모델이 "백엔드 공고니까 Java겠지"라고 추측해서 채움. 출력 **형식**은 스키마를 통과했으니 형식 검증만으로는 못 잡는다.
- **해결**: 추출한 기술명이 원문 표기·정규화 이름·동의어 중 하나로 원문에 실제로 나오는지 함수로 확인하고, 없으면 버림 (마감일에 쓰던 방식과 같음). → [ADR-0002](0002-llm-output-validation.md)
- **배운 점**: 스키마 검증은 "형식"만 보장한다. "내용"은 원문과 대조하는 검증이 따로 필요하다.

## 3. GitHub 코드 근거가 엉뚱하게 "보유"
- **증상**: 써 본 적 없는 기술이 코드 근거로 "보유" 처리됨.
- **원인 ①**: 이 프로젝트 저장소에 기술 사전(`skills.yaml`)이 있어서 모든 기술 이름이 검색됨.
- **원인 ②**: LLM이 검색어에 `user:apache` 같은 한정자를 붙여 `user:`가 OR로 묶이면서 남의 저장소 코드가 섞임.
- **해결**: `GITHUB_EXCLUDE_REPOS`로 gapmap 제외. MCP 도구를 `search_my_code` 래퍼로 감싸서 LLM은 기술 이름만 넘기고 검색 범위는 코드가 고정. → [ADR-0005](0005-github-mcp-wrapper.md)

## 4. n8n 포트 충돌 (5678)
- **증상**: `docker compose up` 때 n8n 컨테이너가 포트를 못 잡음.
- **원인**: 같은 PC에서 다른 프로젝트의 n8n(`restart: always`)이 이미 호스트 5678을 쓰고 있음.
- **해결**: `"5679:5678"` — 컨테이너 안은 그대로 5678, 호스트에만 5679로 노출.
- **배운 점**: 포트 매핑은 `호스트:컨테이너`. 컨테이너끼리는 호스트 포트와 상관없이 `서비스이름:컨테이너포트`로 통신한다.

## 5. Git Bash에서 n8n import 경로가 깨짐
- **증상**: `docker compose exec n8n n8n import:workflow --input=/workflows`가 경로를 못 찾음.
- **원인**: Git Bash(MSYS)가 `/workflows` 같은 인자를 Windows 경로(`C:/Program Files/Git/workflows`)로 자동 변환함.
- **해결**: 명령 앞에 `MSYS_NO_PATHCONV=1`. (PowerShell에서는 필요 없음)

## 6. n8n 워크플로우를 CLI로 실행할 수 없음
- **증상**: `n8n execute --id=...`로 테스트하려 했는데 실행되지 않음.
- **원인**: CLI 실행은 수동 트리거(Manual Trigger)가 있는 워크플로우만 된다. 우리 워크플로우는 시간 트리거(Schedule)뿐.
- **해결**: n8n 화면에서 `Execute workflow` 버튼으로 테스트. 알림 내용 자체는 `curl http://localhost:8000/alerts/deadlines?days=3`로 api만 따로 확인 가능 (ADR-0006 덕분).

## 7. n8n 화면이 안 열림
- **증상**: http://localhost:5679 에 접속이 안 됨.
- **원인**: Docker Desktop이 꺼져 있었음. `docker info`가 `open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified` 에러.
- **해결**: Docker Desktop 실행 → `docker compose up -d`. 데이터는 볼륨에 있어서 그대로 남아 있었음.
- **배운 점**: 시연 전 체크리스트 1번 = Docker Desktop 실행 확인.

## 8. n8n 로그인 비밀번호 분실
- **증상**: 예전에 만든 n8n 계정 비밀번호가 기억나지 않음. 로컬 n8n이라 메일 재설정도 안 됨.
- **해결**: `docker compose exec n8n n8n user-management:reset` → 재시작 → 회원가입 화면에서 새로 만듦.
- **배운 점**: 계정만 초기화되고 워크플로우·실행 기록은 남는다. 워크플로우는 계정이 아니라 프로젝트에 속하고, 데이터는 `n8n_data` 볼륨에 있기 때문.
