FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8012 \
    WEB_CONCURRENCY=2 \
    LOG_LEVEL=info

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY scripts ./scripts
COPY examples ./examples
COPY init_api_db.py ./
COPY .env.example ./.env.example

RUN mkdir -p /app/data && \
    adduser --disabled-password --gecos "" govup && \
    chown -R govup:govup /app

USER govup

EXPOSE 8012

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.getenv(\"PORT\", \"8012\")}/health', timeout=3)"

CMD ["sh", "-c", "python -m uvicorn src.main:app --host 0.0.0.0 --port ${PORT} --workers ${WEB_CONCURRENCY} --log-level ${LOG_LEVEL}"]
