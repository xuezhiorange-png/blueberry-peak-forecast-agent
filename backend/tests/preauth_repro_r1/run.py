"""Local reproduction only; reuse verified S5 owned-PostgreSQL cleanup."""

from backend.tests.safe_pilot import run as owned

if __name__ == "__main__":
    owned.TESTS = ["backend/tests/preauth_repro_r1/test_concurrent_login.py"]
    owned.main()
