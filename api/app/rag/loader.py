"""이력서 파일(md/pdf/txt) → 텍스트 → 청크."""
import re
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

SUPPORTED = {".md", ".txt", ".pdf"}

# 긴 섹션만 문단(\n\n) → 줄 → 공백 순으로 다시 자른다
_splitter = RecursiveCharacterTextSplitter(chunk_size=300, chunk_overlap=30)


def read_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        return "\n\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    return path.read_text(encoding="utf-8")


def split_sections(text: str) -> list[str]:
    """마크다운 제목(#~###)마다 무조건 끊는다 → "프로젝트 하나 = 청크 하나".
    (splitter만 쓰면 짧은 섹션끼리 chunk_size까지 다시 합쳐져서 서로 다른 프로젝트가 섞인다)"""
    pieces = []
    for section in re.split(r"\n(?=#{1,3} )", text):
        section = section.strip()
        if "\n" not in section and section.startswith("#"):
            continue  # 본문 없는 제목 줄(예: "## 프로젝트")은 버린다
        pieces.extend(_splitter.split_text(section) if len(section) > 300 else [section])
    return [p for p in pieces if p]


def load_chunks(resume_dir: str) -> list[dict]:
    """폴더의 모든 이력서 파일을 청크 목록으로. 각 청크는 {id, text, source}."""
    chunks = []
    for path in sorted(Path(resume_dir).iterdir()):
        if path.suffix.lower() not in SUPPORTED:
            continue
        for i, text in enumerate(split_sections(read_text(path))):
            chunks.append({"id": f"{path.name}#{i}", "text": text, "source": path.name})
    return chunks
