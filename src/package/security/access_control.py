from __future__ import annotations

from package.sessions.manager import SessionManager


def authorize_vnc(sessions: SessionManager, session_id: str, user_id: int) -> int | None:
    """セッションの所有者本人にだけVNCポートを返す。他人のセッションIDを指定しても None。"""
    session = sessions.get_running(session_id)
    if session is None or session.user_id != user_id:
        return None
    return sessions.vnc_port(session_id)
