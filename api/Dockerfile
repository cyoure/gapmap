FROM python:3.12-slim

# 로그가 버퍼링 없이 바로 docker compose logs에 찍히도록
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# requirements를 먼저 복사 → 코드만 바뀌면 pip install 레이어는 캐시 재사용
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
