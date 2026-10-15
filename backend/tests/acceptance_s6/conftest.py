"""Reuse the existing real PostgreSQL fixture without replacing authentication."""

from backend.tests.local_auth.conftest import pg_auth  # noqa: F401
