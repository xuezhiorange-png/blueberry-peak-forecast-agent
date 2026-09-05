"""Legacy SOURCE-002 live-session wiring (sync injection only).

Production SOURCE-002 attestation and content obtain execute through
``accepted_s2_train_val_source_002_row_level_read_live_run_sync.py`` using
AsyncSessionMaker → AsyncSession.run_sync(...).

This module remains for explicit unit-test sync-session injection via
``set_source_002_row_level_read_session_provider``. It does not bind a
production default provider.
"""

from __future__ import annotations


def bind_default_source_002_row_level_read_live_session_provider() -> None:
    """No-op: production no longer binds a sync-engine Session bridge."""
