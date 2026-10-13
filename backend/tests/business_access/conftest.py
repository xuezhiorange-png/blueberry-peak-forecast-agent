"""Reuse isolated S1 PostgreSQL fixtures; never production credentials."""

from backend.tests.local_auth.conftest import pg_auth, synthetic_authority  # noqa: F401
