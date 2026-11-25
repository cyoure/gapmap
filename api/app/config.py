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
# 코드 근거 검색에서 뺄 내 저장소 (이 프로젝트는 기술 사전 때문에 모든 기술이 검색됨)
GITHUB_EXCLUDE_REPOS = [r.strip() for r in os.environ.get("GITHUB_EXCLUDE_REPOS", "").split(",") if r.strip()]
# 코드 근거로 함께 볼 팀 저장소 (owner/repo). org 전체가 아니라 내가 참여한 저장소만
GITHUB_TEAM_REPOS = [r.strip() for r in os.environ.get("GITHUB_TEAM_REPOS", "").split(",") if r.strip()]

# 이미지 공고 OCR — Tesseract 언어 (한국어+영어: 기술명은 대부분 영어)
OCR_LANG = os.environ.get("OCR_LANG", "kor+eng")
