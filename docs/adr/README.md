# 기술 결정 기록 (ADR) · 트러블슈팅

ADR(Architecture Decision Record): **왜 이렇게 만들었는지**를 결정 하나당 한 장으로 남긴다.
형식은 `배경 → 결정 → 결과(좋은 점·치른 비용)`.

| 번호 | 결정 |
|---|---|
| [0001](0001-local-llm.md) | LLM은 로컬 Ollama로만 — 이력서를 외부로 보내지 않는다 |
| [0002](0002-llm-output-validation.md) | LLM 출력은 스키마로 강제하고, 원문에 없는 값은 버린다 |
| [0003](0003-calculation-in-functions.md) | 점수·D-day·공부 순서는 순수 함수로 계산한다 |
| [0004](0004-no-evidence-not-lacking.md) | "부족"이 아니라 "근거 없음" — 사용자가 직접 고칠 수 있게 |
| [0005](0005-github-mcp-wrapper.md) | GitHub MCP 도구를 그대로 주지 않고 검색 범위를 고정한 래퍼로 |
| [0006](0006-n8n-calls-api.md) | n8n은 DB를 직접 읽지 않고 api를 호출한다 |

[트러블슈팅 기록](troubleshooting.md) — 실제로 겪은 문제와 해결 과정.
