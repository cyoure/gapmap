# ADR-0006 n8n은 DB를 직접 읽지 않고 api를 호출한다

## 배경
마감 D-3 알림과 주간 요약은 n8n에서 돌린다. n8n에는 Postgres 노드가 있어서 SQL로 바로 조회할 수도 있다. 하지만 그러면 D-day 계산과 "같은 공고를 여러 번 분석한 경우의 중복 제거" 로직이 api(Python)와 n8n(SQL·JS) 두 곳에 생긴다.

## 결정
- n8n 워크플로우는 `시간 트리거 → HTTP 요청(api) → IF → Discord 웹훅`만 한다.
  - `GET http://api:8000/alerts/deadlines?days=3` (매일 09:00)
  - `GET http://api:8000/alerts/weekly` (매주 월 09:00)
- D-day는 `calc_dday` 함수로 계산하고, Discord 메시지 문구도 api가 만든다. n8n은 **일정 관리와 전달만** 맡는다.
- 컨테이너끼리는 `localhost`가 아니라 compose 서비스 이름(`api`)으로 통신한다.
- 웹훅 URL은 `.env` → n8n 환경변수 → `{{ $env.DISCORD_WEBHOOK_URL }}`로 읽는다. 워크플로우 json에 URL을 넣지 않으니 json은 그대로 커밋할 수 있다.
  - n8n은 기본적으로 노드에서 `$env` 접근을 막아서 `N8N_BLOCK_ENV_ACCESS_IN_NODE=false`로 풀었다.
- 워크플로우는 `n8n/*.json`으로 관리하고 CLI로 import한다.

## 결과
- 👍 계산 로직이 한 곳에만 있다. 알림 내용은 `curl`로 api만 호출해 봐도 확인할 수 있다.
- 👍 postgres 포트를 호스트에 열 필요가 없다.
- 👎 n8n 화면에서 고친 내용은 json 파일에 자동으로 반영되지 않는다 → 고치면 다시 export해야 한다.
- 참고: "D-3"은 "마감이 0~3일 남은 공고"라서 마감 전까지 매일 알림이 간다 (D-3, D-2, D-1, D-day).
