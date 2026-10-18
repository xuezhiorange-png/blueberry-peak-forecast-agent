"""Run the unchanged probe plus fix regressions with S5 owned resource cleanup."""

import sys

from backend.tests.safe_pilot import run as owned

if __name__ == "__main__":
    owned.TESTS = ["backend/tests/preauth_repro_r1"]
    if "--related" in sys.argv:
        sys.argv.remove("--related")
        owned.TESTS += [
            "backend/tests/safe_pilot",
            "backend/tests/local_auth",
            "backend/tests/business_access",
            "backend/tests/revoke_read_race",
            "backend/tests/mcp/test_v0_18_s3_policy.py",
            "backend/tests/mcp/test_v0_18_s3_postgres.py",
        ]
    owned.main()
