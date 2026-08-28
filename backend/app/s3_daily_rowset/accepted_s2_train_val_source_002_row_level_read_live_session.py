"""Bind the landed SOURCE_002 row-level reader to the existing live engine.

Does not invent a connection string or call create_engine. Uses the
application AsyncEngine already configured in ``backend.app.db.session``.
Binding a session that then fail-closes is not SOURCE_002_ROW_LEVEL_READ.
"""

from __future__ import annotations

from sqlalchemy.orm import Session


def source_002_row_level_read_live_session_provider() -> Session | None:
    try:
        from backend.app.db.session import engine as async_engine

        bind = async_engine.sync_engine
        if bind is None:
            return None
        return Session(bind)
    except Exception:
        return None


def bind_default_source_002_row_level_read_live_session_provider() -> None:
    from backend.app.s3_daily_rowset.accepted_s2_train_val_source_002_row_level_read import (
        set_source_002_row_level_read_session_provider,
    )

    set_source_002_row_level_read_session_provider(source_002_row_level_read_live_session_provider)
