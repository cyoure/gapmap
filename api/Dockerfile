FROM python:3.12-slim

# 로그가 버퍼링 없이 바로 docker compose logs에 찍히도록
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# 이미지 공고 OCR — Tesseract 엔진 + 한국어 학습 데이터 (OS 패키지라 pip이 아니라 apt로 설치)
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-kor     && rm -rf /var/lib/apt/lists/*

# requirements를 먼저 복사 → 코드만 바뀌면 pip install 레이어는 캐시 재사용
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
