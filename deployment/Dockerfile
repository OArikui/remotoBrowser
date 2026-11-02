# syntax=docker/dockerfile:1
# OCIの初期構成: APIとBrowser Runtime(Xvfb + x11vnc + Chromium)を同居させる。
# 接続先は完全一致ホスト許可リストで制限し、出口フィルタはdeployment/ociを参照。
FROM python:3.13-slim-bookworm AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# noVNC is only used as static frontend files. Extract its Debian package
# without installing it, avoiding its unused system-Python dependency tree.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      xvfb x11vnc tini ca-certificates fonts-noto-cjk fonts-liberation \
 && mkdir -p /tmp/novnc-package /opt/novnc \
 && (cd /tmp/novnc-package && apt-get download novnc) \
 && dpkg-deb -x /tmp/novnc-package/novnc_*.deb /tmp/novnc-package/extracted \
 && cp -a /tmp/novnc-package/extracted/usr/share/novnc/. /opt/novnc/ \
 && rm -rf /tmp/novnc-package /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src

# Playwright installs Chromium's shared-library dependencies. Keep the
# Python runtime dependencies patched independently of those OS packages.
RUN pip install . \
 && playwright install --with-deps chromium \
 && python -m pip install --no-cache-dir --upgrade --force-reinstall \
      "setuptools>=78.1.1" \
      "msgpack>=1.2.3" \
      "urllib3>=2.8.0" \
 && python -c "from importlib.metadata import version; from pip._vendor.packaging.version import Version; assert Version(version('setuptools')) >= Version('78.1.1'); assert Version(version('msgpack')) >= Version('1.2.3'); assert Version(version('urllib3')) >= Version('2.8.0')" \
 && rm -rf /tmp/pip-* /tmp/build-env-* /root/.cache/pip /var/lib/apt/lists/* \
 && chmod -R a+rX /ms-playwright /opt/novnc

COPY run.py ./
COPY frontend ./frontend

RUN useradd --create-home --uid 10001 app \
 && mkdir -p /app/data \
 && chown app:app /app/data

# Copy the finished runtime filesystem into a fresh image without retaining
# intermediate builder layers or temporary package files.
FROM scratch AS runtime
COPY --from=builder / /

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    BROWSER_RUNTIME=process \
    NOVNC_DIR=/opt/novnc \
    FRONTEND_DIR=/app/frontend \
    DATABASE_PATH=/app/data/app.db \
    BIND_HOST=0.0.0.0 \
    PORT=8080

WORKDIR /app
USER app

EXPOSE 8080
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "run.py"]
