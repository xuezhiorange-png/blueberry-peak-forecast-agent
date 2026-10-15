"""Reuse the real disposable PostgreSQL/S1 fixture; never a production DB."""

from backend.tests.local_auth.conftest import pg_auth  # noqa: F401
