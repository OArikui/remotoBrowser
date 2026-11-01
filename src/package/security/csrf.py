from __future__ import annotations

import logging
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from package.auth.dependencies import AuthContext, CurrentUser
from package.state import container

log = logging.getLogger("rb.security")


def require_csrf(request: Request, ctx: CurrentUser) -> AuthContext:
    """状態を変更するAPI用: Originの検査 + セッションに紐づくCSRFトークンのヘッダー検査。"""
    origin = request.headers.get("origin")
    if origin is not None and origin != container(request).settings.origin:
        log.warning("csrf: unexpected origin on %s", request.url.path)
        raise HTTPException(status_code=403, detail="origin not allowed")
    header = request.headers.get("x-csrf-token", "")
    if not secrets.compare_digest(header.encode(), ctx.csrf_token.encode()):
        log.warning("csrf: token mismatch on %s", request.url.path)
        raise HTTPException(status_code=403, detail="invalid csrf token")
    return ctx


CsrfUser = Annotated[AuthContext, Depends(require_csrf)]
