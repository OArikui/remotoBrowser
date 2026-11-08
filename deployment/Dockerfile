# syntax=docker/dockerfile:1
# Phase 0-3 の試作用: API と Browser Runtime(Xvfb + x11vnc + Chromium)を1コンテナに同居させる。
# 外部公開時はブラウザ実行環境を別コンテナへ分離すること(docs/architecture.md 参照)。
FROM python:3.13-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      xvfb x11vnc novnc tini ca-certificates fonts-noto-cjk fonts-liberation \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install . \
 && playwright install --with-deps chromium \
 && python -m pip install --no-cache-dir --upgrade \
      "setuptools>=78.1.1" \
      "msgpack>=1.2.3" \
      "urllib3>=2.8.0" \
 && python -m pip check \
 && rm -rf /var/lib/apt/lists/* \
 && chmod -R a+rX /ms-playwright

COPY run.py ./
COPY frontend ./frontend

RUN useradd --create-home --uid 10001 app \
 && mkdir -p /app/data \
 && chown app:app /app/data
USER app

ENV BROWSER_RUNTIME=process \
    NOVNC_DIR=/usr/share/novnc \
    FRONTEND_DIR=/app/frontend \
    DATABASE_PATH=/app/data/app.db \
    BIND_HOST=0.0.0.0 \
    PORT=8080

EXPOSE 8080
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "run.py"]
