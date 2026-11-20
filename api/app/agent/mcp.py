"""GitHub MCP 도구 (langchain-mcp-adapters). 토큰이 없거나 연결에 실패하면 빈 목록."""
import json
import logging
import re

from langchain_core.tools import tool
from langchain_mcp_adapters.client import MultiServerMCPClient

from app import config

log = logging.getLogger("uvicorn.error")


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
        tools = {t.name: t for t in await client.get_tools()}
        raw_search = tools["search_code"]
    except Exception as e:  # 네트워크·토큰 문제로 서버 전체가 죽지 않게
        log.warning("GitHub MCP 연결 실패: %s", type(e).__name__)
        return []
    log.info("GitHub MCP: %d개 도구 중 search_code를 감싸서 사용", len(tools))
    return [_wrap_search(raw_search)]


def _clean(skill: str) -> str:
    """LLM이 넘긴 기술 이름에서 GitHub 검색 문법을 지운다.
    'Kafka user:apache'를 그대로 넣으면 user:가 두 개(OR)가 되어 남의 코드가 '내 근거'로 둔갑한다."""
    s = re.sub(r"\S*:\S*", " ", skill)  # user:, repo:, org:, path: … 같은 한정자 제거
    s = re.sub(r"(^|\s)-\S*", " ", s)  # -repo:… 같은 제외 문법 제거
    s = re.sub(r'["()]|\b(AND|OR|NOT)\b', " ", s)  # 따옴표·괄호·논리 연산자 제거
    return " ".join(s.split())[:40]


def _wrap_search(raw_search):
    """MCP search_code를 그대로 주지 않고 감싼다.
    - 작은 모델이 'user:' 같은 검색 문법을 틀리지 않게: LLM은 기술 이름만 넘긴다
    - 이 프로젝트(gapmap) 저장소 제외: 기술 사전(skills.yaml)에 모든 기술 이름이 있어 거짓 근거가 된다
    - 팀 저장소는 org 전체가 아니라 내가 참여한 저장소만 (org에는 다른 사람 프로젝트가 많다)
    - 2,000자가 넘는 원본 JSON 대신 '저장소/파일: 코드 조각'만 돌려준다 (컨텍스트 절약)"""
    user = config.GITHUB_USER
    exclude = " ".join(f"-repo:{user}/{r}" for r in config.GITHUB_EXCLUDE_REPOS)
    team = " ".join(f"repo:{r}" for r in config.GITHUB_TEAM_REPOS)  # repo: 여러 개는 OR로 동작

    async def search(query: str, label: str) -> list[str]:
        res = await raw_search.ainvoke({"query": query, "perPage": 5})
        try:
            data = json.loads(res[0]["text"] if isinstance(res, list) else str(res))
        except (ValueError, KeyError, IndexError):  # GitHub가 오류 문구 등 JSON이 아닌 응답을 준 경우
            return [f"[{label}] 검색 실패"]
        lines = []
        for it in data.get("items", []):
            repo = it["repository"]["full_name"] if isinstance(it["repository"], dict) else it["repository"]
            frag = ((it.get("text_matches") or [{}])[0].get("fragment") or "").replace("\r", "")
            lines.append(f"- [{label}] {repo}/{it['path']}: {' '.join(frag.split())[:150]}")
        return lines

    @tool
    async def search_my_code(skill: str) -> str:
        """내 GitHub 저장소와 내가 참여한 팀 프로젝트 코드에서 skill(기술 이름 하나, 예: "Kafka")을 쓴 흔적을 찾는다.
        이력서에 근거가 없는 기술의 코드 근거를 확인할 때 사용. [팀 프로젝트] 코드는 다른 팀원이 썼을 수도 있다."""
        name = _clean(skill)
        if not name:
            return "기술 이름만 넣어 주세요 (예: Kafka)."
        # 따옴표로 묶어 '단어'로만 검색. user:와 repo:는 한 질의에 섞으면 파싱 오류 → 따로 검색해서 합친다
        lines = await search(f'"{name}" user:{user} {exclude}', "내 저장소")
        if team:
            lines += await search(f'"{name}" {team}', "팀 프로젝트")
        return "\n".join(lines) if lines else f"내 저장소·팀 프로젝트에서 {name}을(를) 쓴 코드를 찾지 못했습니다."

    return search_my_code
