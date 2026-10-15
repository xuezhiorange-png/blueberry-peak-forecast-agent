"""Create and stop ONLY a new private SYNTHETIC PostgreSQL cluster.

Run from repository root with the locked Python 3.12 environment and PostgreSQL
tools on PATH. No deployment, Docker, existing DB cleanup, or real provisioning.
"""

import argparse
import hashlib
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TESTS = [
    "backend/tests/safe_pilot",
    "backend/tests/local_auth",
    "backend/tests/business_access",
    "backend/tests/mcp/test_v0_18_s3_policy.py",
    "backend/tests/mcp/test_v0_18_s3_postgres.py",
]


def command(arguments, environment, log, *, cwd=ROOT):
    with log.open("ab") as output:
        return subprocess.run(
            arguments,
            cwd=cwd,
            env=environment,
            stdout=output,
            stderr=subprocess.STDOUT,
            check=False,
        ).returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="New, nonexisting private SYNTHETIC evidence directory",
    )
    parser.add_argument(
        "--browser", action="store_true", help="Also rerun actual S4 TLS/PG browser flow"
    )
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 12):
        raise SystemExit("PYTHON_312_REQUIRED")
    for executable in ("initdb", "pg_ctl", "pg_dump", "pg_restore", "openssl"):
        if shutil.which(executable) is None:
            raise SystemExit("REQUIRED_TEST_EXECUTABLE_MISSING: " + executable)
    if args.browser and shutil.which("npx") is None:
        raise SystemExit("BROWSER_EXECUTABLE_MISSING")
    root = args.output.absolute()
    if root.exists() or not root.name.startswith("SYNTHETIC-") or root.is_symlink():
        raise SystemExit("NEW_SYNTHETIC_DIRECTORY_REQUIRED")
    root.mkdir(mode=0o700)
    temporary = root / "temporary"
    temporary.mkdir(mode=0o700)
    password = secrets.token_urlsafe(40)
    password_file = root / "private-password"
    with password_file.open("x") as output:
        password_file.chmod(0o600)
        output.write(password + "\n")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    environment = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(
            ("POSTGRES_", "PG", "LOCAL_AUTH_", "BUSINESS_ACCESS_", "FORECAST_INTELLIGENCE_MCP_")
        )
        and k not in {"DATABASE_URL", "S4_HTTPS_URL"}
    }
    environment.update(
        APP_ENV="test",
        POSTGRES_HOST="127.0.0.1",
        POSTGRES_PORT=str(port),
        POSTGRES_USER="SYNTHETIC_s5",
        POSTGRES_PASSWORD=password,
        POSTGRES_DB="blueberry_peak_test",
        TZ="UTC",
        PYTHONPATH=str(ROOT),
        DASHBOARD_TEST_PYTHON=sys.executable,
        TMPDIR=str(temporary),
    )
    data, log = root / "data", root / "execution.log"
    initialized = command(
        [
            "initdb",
            "-D",
            str(data),
            "--username=SYNTHETIC_s5",
            "--auth-host=scram-sha-256",
            "--auth-local=scram-sha-256",
            "--pwfile",
            str(password_file),
        ],
        environment,
        log,
    )
    if initialized:
        raise SystemExit("ISOLATED_INIT_FAILED")
    report = {
        "SYNTHETIC": True,
        "root": str(root),
        "port": port,
        "host": "127.0.0.1",
        "production_deployed": False,
        "password_published": False,
        "tests": TESTS,
    }
    source_files = list((ROOT / "backend/tests/safe_pilot").glob("*.py"))
    source_files += [
        ROOT / p
        for p in (
            "frontend/e2e/dashboard-business-flow.spec.ts",
            "frontend/e2e/support/business_pg.py",
            "backend/app/main.py",
            "backend/app/mcp/forecast_intelligence_http.py",
            "backend/app/mcp/forecast_intelligence_policy.py",
        )
    ]
    report["source_sha256"] = {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(source_files)
    }
    report["started_at_utc"] = datetime.now(UTC).isoformat()
    report["python"] = sys.version
    # This manifest identifies exact owned resources before starting any listener.
    manifest = root / "owned-resources.json"
    manifest.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    started = False
    status = 1

    def terminate(signum, frame):
        del signum, frame
        raise KeyboardInterrupt("SYNTHETIC_RUN_CANCELLED")

    signal.signal(signal.SIGTERM, terminate)
    try:
        status = command(
            [
                "pg_ctl",
                "-D",
                str(data),
                "-l",
                str(root / "postgres.log"),
                "-o",
                f"-h 127.0.0.1 -p {port} -k {root}",
                "-w",
                "start",
            ],
            environment,
            log,
        )
        started = status == 0
        if not started:
            raise RuntimeError("ISOLATED_POSTGRES_START_FAILED")
        status = command(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                *TESTS,
                "--basetemp=" + str(root / "pytest"),
                "--junitxml=" + str(root / "backend.xml"),
            ],
            environment,
            log,
        )
        report["backend_exit"] = status
        if status == 0 and args.browser:
            environment["PLAYWRIGHT_BASE_URL"] = f"http://127.0.0.1:{port + 1}"
            status = command(
                [
                    "npx",
                    "playwright",
                    "test",
                    "dashboard-business-flow.spec.ts",
                    "--workers=1",
                    "--output=" + str(root / "browser"),
                ],
                environment,
                root / "browser.log",
                cwd=ROOT / "frontend",
            )
            report["browser_exit"] = status
    finally:
        if started:
            stopped = command(
                ["pg_ctl", "-D", str(data), "-m", "fast", "-w", "stop"], environment, log
            )
            report["shutdown_exit"] = stopped
            if stopped:
                status = stopped
        report["execution_sha256"] = hashlib.sha256(log.read_bytes()).hexdigest()
        report["exit"] = status
        report["finished_at_utc"] = datetime.now(UTC).isoformat()
        manifest.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
        # Preserve private cluster/dump/log evidence. No recursive deletion.
        from backend.tests.safe_pilot.operations import assert_redacted

        assert_redacted(log.read_text(), [password])
    raise SystemExit(status)


if __name__ == "__main__":
    main()
