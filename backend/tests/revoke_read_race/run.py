"""Reuse the unchanged S5 task-owned PostgreSQL/SIGTERM lifecycle."""

from backend.tests.safe_pilot import run as owned

if __name__ == "__main__":
    owned.TESTS = ["backend/tests/revoke_read_race"]
    owned.main()
