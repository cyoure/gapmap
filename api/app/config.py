"""환경변수 → 설정값. 모델명·URL은 코드에 하드코딩하지 않는다."""
import os

OLLAMA_BASE_URL = os.environ["OLLAMA_BASE_URL"]
OLLAMA_MODEL = os.environ["OLLAMA_MODEL"]
EMBED_MODEL = os.environ["EMBED_MODEL"]
CHROMA_URL = os.environ["CHROMA_URL"]
RESUME_DIR = os.environ["RESUME_DIR"]
DATABASE_URL = os.environ["DATABASE_URL"]  # compose가 POSTGRES_* 값으로 조립해서 넣어줌

# GitHub MCP — 토큰이 비어 있으면 GitHub 도구 없이 동작
GITHUB_MCP_URL = os.environ["GITHUB_MCP_URL"]
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_USER = os.environ.get("GITHUB_USER", "")
