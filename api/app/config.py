"""환경변수 → 설정값. 모델명·URL은 코드에 하드코딩하지 않는다."""
import os

OLLAMA_BASE_URL = os.environ["OLLAMA_BASE_URL"]
OLLAMA_MODEL = os.environ["OLLAMA_MODEL"]
EMBED_MODEL = os.environ["EMBED_MODEL"]
CHROMA_URL = os.environ["CHROMA_URL"]
RESUME_DIR = os.environ["RESUME_DIR"]
