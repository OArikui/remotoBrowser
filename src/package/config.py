"""設定の一元管理。環境変数(または .env)から読み込む。"""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from package.browser.policies import normalize_hostname, parse_allowed_hosts


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- アプリ全般 ---
    app_env: Literal["development", "production"] = "development"
    app_secret_key: str = Field(default="", validate_default=True)
    base_url: str = "http://localhost:8000"
    bind_host: str = "0.0.0.0"
    port: int = 8000
    trust_proxy_headers: bool = False
    log_level: str = "INFO"
    enable_docs: bool = False

    # --- Discord OAuth2 ---
    discord_client_id: str = ""
    discord_client_secret: str = ""
    # カンマ区切り。空なら全員許可。
    allowed_discord_ids: str = ""

    # --- 管理対象ブラウザサイト ---
    # 完全一致ホスト名をカンマ区切りで指定。ワイルドカード・IPアドレスは不可。
    browser_allowed_hosts: str = ""

    # --- データベース ---
    database_path: str = "data/app.db"

    # --- ブラウザ実行環境 ---
    browser_runtime: Literal["process", "fake"] = "process"
    novnc_dir: str = "/usr/share/novnc"
    frontend_dir: str = "frontend"
    screen_width: int = Field(default=1280, ge=320, le=3840)
    screen_height: int = Field(default=720, ge=240, le=2160)
    default_start_url: str = "https://example.com"

    # --- 運営制限(計画書 5章の初期値) ---
    max_concurrent_sessions: int = Field(default=1, ge=1)
    session_max_seconds: int = Field(default=1800, ge=60)
    idle_timeout_seconds: int = Field(default=300, ge=30)
    login_ttl_seconds: int = Field(default=43200, ge=300)
    sweep_interval_seconds: float = Field(default=15.0, gt=0)

    # --- レート制限(1分あたり) ---
    rate_limit_login_per_minute: int = Field(default=20, ge=1)
    rate_limit_start_per_minute: int = Field(default=10, ge=1)

    @field_validator("app_secret_key")
    @classmethod
    def _check_secret(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError(
                "APP_SECRET_KEY must be set and at least 32 characters long "
                '(generate: python -c "import secrets; print(secrets.token_urlsafe(48))")'
            )
        return value

    @field_validator("browser_allowed_hosts")
    @classmethod
    def _check_browser_allowed_hosts(cls, value: str) -> str:
        hosts = parse_allowed_hosts(value)
        return ",".join(sorted(hosts))

    @field_validator("base_url")
    @classmethod
    def _check_base_url(cls, value: str) -> str:
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError("BASE_URL must look like https://example.com")
        return value.rstrip("/")

    @model_validator(mode="after")
    def _check_production_settings(self) -> Settings:
        if self.app_env == "production":
            if not self.base_url.startswith("https://"):
                raise ValueError("production BASE_URL must use HTTPS")
            if not self.discord_client_id or not self.discord_client_secret:
                raise ValueError("production requires Discord OAuth2 client credentials")
            if not self.allowed_ids:
                raise ValueError("production requires ALLOWED_DISCORD_IDS")
            if not self.browser_hosts:
                raise ValueError("production requires BROWSER_ALLOWED_HOSTS")
            if self.browser_runtime != "process":
                raise ValueError("production requires BROWSER_RUNTIME=process")
            if self.enable_docs:
                raise ValueError("ENABLE_DOCS must be false in production")
            start_host = urlsplit(self.default_start_url).hostname
            try:
                normalized_start_host = normalize_hostname(start_host or "")
            except ValueError as exc:
                raise ValueError("DEFAULT_START_URL must use an allowlisted DNS hostname") from exc
            if normalized_start_host not in self.browser_hosts:
                raise ValueError("DEFAULT_START_URL host must be in BROWSER_ALLOWED_HOSTS")
        return self

    @property
    def browser_hosts(self) -> frozenset[str]:
        return parse_allowed_hosts(self.browser_allowed_hosts)

    @property
    def origin(self) -> str:
        parts = urlsplit(self.base_url)
        return f"{parts.scheme}://{parts.netloc}"

    @property
    def ws_origin(self) -> str:
        parts = urlsplit(self.base_url)
        scheme = "wss" if parts.scheme == "https" else "ws"
        return f"{scheme}://{parts.netloc}"

    @property
    def redirect_uri(self) -> str:
        return f"{self.base_url}/auth/callback"

    @property
    def cookie_secure(self) -> bool:
        return self.base_url.startswith("https://")

    @property
    def allowed_ids(self) -> frozenset[str]:
        return frozenset(
            part.strip() for part in self.allowed_discord_ids.split(",") if part.strip()
        )
