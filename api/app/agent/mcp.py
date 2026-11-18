"""GitHub MCP 도구 불러오기 (langchain-mcp-adapters). 토큰이 없거나 연결에 실패하면 빈 목록."""
import logging

from langchain_mcp_adapters.client import MultiServerMCPClient

from app import config

log = logging.getLogger("uvicorn.error")

# 작은 모델은 도구가 많으면 헷갈린다 → 내 코드를 확인하는 데 필요한 것만
ALLOWED = {"search_code", "get_file_contents"}


async def load_github_tools() -> list:
    if not config.GITHUB_TOKEN:
        log.warning("GitHub MCP: GITHUB_TOKEN이 비어 있어 GitHub 도구 없이 시작")
        return []
    client = MultiServerMCPClient({
        "github": {
            "transport": "streamable_http",
            "url": config.GITHUB_MCP_URL,
            "headers": {
                "Authorization": f"Bearer {config.GITHUB_TOKEN}",
                "X-MCP-Toolsets": "repos",  # 저장소 관련 도구만 받기
                "X-MCP-Readonly": "true",  # 쓰기 도구는 아예 받지 않기
            },
        }
    })
    try:
        tools = await client.get_tools()
    except Exception as e:  # 네트워크·토큰 문제로 서버 전체가 죽지 않게
        log.warning("GitHub MCP 연결 실패: %s", type(e).__name__)
        return []
    picked = [t for t in tools if t.name in ALLOWED]
    log.info("GitHub MCP: %d개 중 %s 사용", len(tools), [t.name for t in picked])
    return picked
