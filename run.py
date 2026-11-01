"""開発・本番共通の起動スクリプト: `python run.py`"""

from __future__ import annotations

import sys
from pathlib import Path

import uvicorn

# リポジトリ直下から実行しても `main` / `package` を import できるようにする
_SRC = Path(__file__).resolve().parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from package.config import Settings  # noqa: E402


def main() -> None:
    settings = Settings()
    uvicorn.run(
        "main:create_app",
        factory=True,
        host=settings.bind_host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        proxy_headers=settings.trust_proxy_headers,
        forwarded_allow_ips="*" if settings.trust_proxy_headers else None,
    )


if __name__ == "__main__":
    main()
