"""복사가 안 되는 공고(이미지·PDF) → 텍스트. 사용자가 직접 올린 파일만 처리한다 (크롤링 아님).

결과는 바로 분석하지 않고 화면 입력창에 채워서 사용자가 확인·수정하게 한다.
OCR은 오타가 잦아서("Spring" → "Sprlng"), 기술명이 틀리면 갭 분석 전체가 틀어지기 때문.
"""
import io
import re

import pytesseract
from PIL import Image, ImageOps
from pypdf import PdfReader

from app import config

MAX_BYTES = 10 * 1024 * 1024  # 10MB
MAX_PDF_PAGES = 10
MIN_WIDTH = 2400  # 이보다 작은 이미지는 키워서 인식 — Tesseract는 글자가 작으면 한글을 많이 틀림 (1600·2400·3000 비교 결과)
IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}


class OcrError(ValueError):
    pass


def _ocr_image(img: Image.Image) -> str:
    img = ImageOps.exif_transpose(img).convert("L")  # 회색조
    if img.width < MIN_WIDTH:
        scale = MIN_WIDTH / img.width
        img = img.resize((MIN_WIDTH, int(img.height * scale)), Image.LANCZOS)
    # 흑백 이진화 — 연한 색 배경·회색 글씨 공고에서 글자 경계가 또렷해짐
    img = ImageOps.autocontrast(img).point(lambda p: 255 if p > 160 else 0)
    # psm 4: "크기가 다른 글줄이 세로로 이어진 한 단" — 제목·목록이 위아래로 이어진 공고 형태에 맞음
    return pytesseract.image_to_string(img, lang=config.OCR_LANG, config="--psm 4")


def _clean(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _from_pdf(data: bytes) -> tuple[str, str]:
    """글자가 들어 있는 PDF는 그대로 추출, 스캔본(이미지만 있음)이면 페이지 이미지를 OCR."""
    pages = PdfReader(io.BytesIO(data)).pages[:MAX_PDF_PAGES]
    text = "\n\n".join(p.extract_text() or "" for p in pages)
    if len(text.strip()) >= 50:
        return text, "pdf-text"
    images = [im.image for p in pages for im in p.images]
    if not images:
        raise OcrError("PDF에서 글자도 이미지도 찾지 못했습니다.")
    return "\n\n".join(_ocr_image(im) for im in images), "ocr"


def extract_text(filename: str, data: bytes) -> dict:
    if len(data) > MAX_BYTES:
        raise OcrError(f"파일이 너무 큽니다 (최대 {MAX_BYTES // 1024 // 1024}MB).")
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if ext == ".pdf":
        text, method = _from_pdf(data)
    elif ext in IMAGE_TYPES or not ext:  # 클립보드에서 붙여넣은 캡처는 이름이 image.png
        try:
            img = Image.open(io.BytesIO(data))
        except Exception:
            raise OcrError("이미지 파일을 열 수 없습니다.")
        text, method = _ocr_image(img), "ocr"
    else:
        raise OcrError(f"지원하지 않는 형식입니다: {ext} (이미지 또는 PDF)")
    text = _clean(text)
    if not text:
        raise OcrError("글자를 찾지 못했습니다. 더 크게 캡처해 보세요.")
    return {"text": text, "method": method, "chars": len(text)}
