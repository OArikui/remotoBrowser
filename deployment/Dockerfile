# syntax=docker/dockerfile:1
# OCIの初期構成: APIとBrowser Runtime(Xvfb + x11vnc + Chromium)を同居させる。
# 接続先は完全一致ホスト許可リストで制限し、出口フィルタはdeployment/ociを参照。
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

# Playwright's Debian dependencies bring in an additional system Python runtime.
# Keep noVNC's static UI, then purge unused Python 3.11 packages and temp build
# environments. The application itself runs on the Python 3.13 base interpreter.
RUN pip install . \
 && playwright install --with-deps chromium \
 && mkdir -p /opt/novnc \
 && cp -a /usr/share/novnc/. /opt/novnc/ \
 && apt-get purge -y python3-msgpack python3-setuptools python3-urllib3 \
 && apt-get autoremove --purge -y \
 && python -m pip install --no-cache-dir --upgrade --force-reinstall \
      "setuptools>=78.1.1" \
      "msgpack>=1.2.3" \
      "urllib3>=2.8.0" \
 && python -c "from importlib.metadata import version; from pip._vendor.packaging.version import Version; assert Version(version('setuptools')) >= Version('78.1.1'); assert Version(version('msgpack')) >= Version('1.2.3'); assert Version(version('urllib3')) >= Version('2.8.0')" \
 && rm -rf /tmp/pip-* /tmp/build-env-* /root/.cache/pip /var/lib/apt/lists/* \
 && find /usr /opt /root /tmp /app -type f \( -name METADATA -o -name PKG-INFO \) -exec sh -c ' \
      for file do \
        if grep -qE "^Name: (msgpack|setuptools|urllib3)$" "$file"; then \
          printf "%s " "$file"; \
          grep -E "^(Name|Version):" "$file" | tr "\n" " "; \
          printf "\n"; \
        fi; \
      done' sh {} + 2>/dev/null \
 && chmod -R a+rX /ms-playwright /opt/novnc

COPY run.py ./
COPY frontend ./frontend

RUN useradd --create-home --uid 10001 app \
 && mkdir -p /app/data \
 && chown app:app /app/data
USER app

ENV BROWSER_RUNTIME=process \
    NOVNC_DIR=/opt/novnc \
    FRONTEND_DIR=/app/frontend \
    DATABASE_PATH=/app/data/app.db \
    BIND_HOST=0.0.0.0 \
    PORT=8080

EXPOSE 8080
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "run.py"]
