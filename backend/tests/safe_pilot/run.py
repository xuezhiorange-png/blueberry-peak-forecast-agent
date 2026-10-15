"""Create and stop ONLY a new private SYNTHETIC PostgreSQL cluster.

Run from repository root with the locked Python 3.12 environment and PostgreSQL
tools on PATH. No deployment, Docker, existing DB cleanup, or real provisioning.
"""

import argparse
import hashlib
import json
import os
import secrets
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import time
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


class Cancellation:
    """Signal handlers request cancellation; they never interrupt finalization."""

    def __init__(self):
        self.signum = None
        self.count = 0
        self.business_cancelled = False

    def request(self, signum, frame):
        del frame
        if self.signum is None:
            self.signum = signum
        self.count += 1

    @property
    def exit_code(self):
        return 128 + self.signum if self.signum is not None else 0


class RunCancelled(Exception):
    """Control flow only; cleanup determines the final observable exit code."""


def command(arguments, environment, log, *, cwd=ROOT, cancellation=None, cancellable=True):
    if cancellable and cancellation is not None and cancellation.signum is not None:
        return cancellation.exit_code
    with log.open("ab") as output:
        with subprocess.Popen(
            arguments,
            cwd=cwd,
            env=environment,
            stdout=output,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        ) as process:
            terminated_at = None
            while True:
                if (
                    cancellable
                    and cancellation is not None
                    and cancellation.signum is not None
                    and terminated_at is None
                ):
                    # Only this command's newly created process group, never a
                    # port/process-name search. PostgreSQL control is NOT cancelled:
                    # settle startup first, then stop via verified data directory.
                    cancellation.business_cancelled = True
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    terminated_at = time.monotonic()
                try:
                    result = process.wait(timeout=0.1)
                    return cancellation.exit_code if terminated_at is not None else result
                except subprocess.TimeoutExpired:
                    if terminated_at is not None and time.monotonic() - terminated_at > 5:
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass


class OwnedPostgres:
    """Exclusive directory identity survives cancellation before pg_ctl returns."""

    def __init__(self, root, data, port):
        self.root, self.data, self.port = root.resolve(), data.resolve(), port
        self.root_identity = self._identity(self.root)
        self.data_identity = self._identity(self.data)
        self.version = (self.data / "PG_VERSION").read_bytes()

    @staticmethod
    def _identity(directory):
        if directory.is_symlink():
            raise RuntimeError("OWNED_DIRECTORY_REPLACED")
        info = directory.stat()
        if not directory.is_dir() or info.st_uid != os.getuid():
            raise RuntimeError("OWNED_DIRECTORY_INVALID")
        return info.st_dev, info.st_ino

    def verify(self):
        if (
            self._identity(self.root) != self.root_identity
            or self._identity(self.data) != self.data_identity
            or (self.data / "PG_VERSION").is_symlink()
            or (self.data / "PG_VERSION").read_bytes() != self.version
        ):
            raise RuntimeError("OWNED_DIRECTORY_REPLACED")
        pid_file = self.data / "postmaster.pid"
        if pid_file.is_symlink():
            raise RuntimeError("POSTMASTER_IDENTITY_INVALID")
        if pid_file.exists():
            lines = pid_file.read_text().splitlines()
            if (
                len(lines) < 2
                or not lines[0].isdigit()
                or int(lines[0]) <= 1
                or Path(lines[1]).resolve() != self.data
                # Startup appends listener/socket lines after the PID/directory.
                # Their absence must not hide a verifiable owned postmaster.
                or (len(lines) > 3 and lines[3] and lines[3] != str(self.port))
                or (len(lines) > 4 and lines[4] and Path(lines[4]).resolve() != self.root)
                or (len(lines) > 5 and lines[5] and lines[5] != "127.0.0.1")
            ):
                raise RuntimeError("POSTMASTER_IDENTITY_INVALID")
            return int(lines[0])
        return None

    def verify_process(self, pid):
        observed = subprocess.run(
            ["ps", "-ww", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            check=False,
            start_new_session=True,
        )
        arguments = shlex.split(observed.stdout.strip())
        # A stale PID file must never turn PID reuse into an unrelated stop.
        if (
            observed.returncode
            or not arguments
            or Path(arguments[0]).name not in {"postgres", "postmaster"}
            or "-D" not in arguments
            or arguments.index("-D") + 1 >= len(arguments)
            or Path(arguments[arguments.index("-D") + 1]).resolve() != self.data
        ):
            raise RuntimeError("POSTMASTER_PROCESS_UNVERIFIED")

    def cleanup(self, environment, log, cancellation):
        pid = self.verify()
        state = command(
            ["pg_ctl", "-D", str(self.data), "status"],
            environment,
            log,
            cancellation=cancellation,
            cancellable=False,
        )
        if state not in (0, 3) or (state == 0 and pid is None):
            raise RuntimeError("POSTMASTER_STATUS_UNVERIFIED")
        stopped = 0
        if pid is not None:
            self.verify()  # do not trust a stale in-memory 'started' flag
            self.verify_process(pid)
            stopped = command(
                ["pg_ctl", "-D", str(self.data), "-m", "fast", "-t", "60", "-w", "stop"],
                environment,
                log,
                cancellation=cancellation,
                cancellable=False,
            )
        self.verify()
        remaining = command(
            ["pg_ctl", "-D", str(self.data), "status"],
            environment,
            log,
            cancellation=cancellation,
            cancellable=False,
        )
        with socket.socket() as probe:
            probe.settimeout(2)
            closed = probe.connect_ex(("127.0.0.1", self.port)) != 0
        absent = not (self.data / "postmaster.pid").exists() and remaining == 3
        verified = stopped == 0 and absent and closed
        return {
            "state": "STOPPED" if verified else "FAILED",
            "directory_identity_verified": True,
            "root_device_inode": self.root_identity,
            "data_device_inode": self.data_identity,
            "postmaster_pid": pid,
            "postmaster_absent": absent,
            "listener_closed": closed,
            "stop_exit": stopped,
        }, 0 if verified else 1


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
    owned = OwnedPostgres(root, data, port)
    report["ownership"] = {
        "root_device_inode": owned.root_identity,
        "data_device_inode": owned.data_identity,
        "pg_version_sha256": hashlib.sha256(owned.version).hexdigest(),
    }
    # This manifest identifies exact owned resources before starting any listener.
    manifest = root / "owned-resources.json"
    manifest.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    cancellation = Cancellation()
    status = 1
    old_handlers = {
        number: signal.signal(number, cancellation.request)
        for number in (signal.SIGTERM, signal.SIGINT)
    }
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
                "-t",
                "60",
                "-w",
                "start",
            ],
            environment,
            log,
            cancellation=cancellation,
            cancellable=False,
        )
        if status:
            raise RuntimeError("ISOLATED_POSTGRES_START_FAILED")
        if cancellation.signum is not None:
            status = cancellation.exit_code
            raise RunCancelled
        status = 1
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
            cancellation=cancellation,
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
                cancellation=cancellation,
            )
            report["browser_exit"] = status
    except RunCancelled:
        status = cancellation.exit_code
    except Exception as error:
        report["run_error_type"] = type(error).__name__
        status = 1
    finally:
        try:
            try:
                report["cleanup"], stopped = owned.cleanup(environment, log, cancellation)
                report["shutdown_exit"] = stopped
                if stopped:
                    status = stopped
            except Exception as error:
                # Persist the failure, never silently kill an unverified process.
                report["cleanup"] = {"state": "FAILED", "error_type": type(error).__name__}
                report["shutdown_exit"] = status = 1
            if cancellation.signum is not None and report["shutdown_exit"] == 0:
                status = cancellation.exit_code
            report["cancel_signal"] = cancellation.signum
            report["signal_count"] = cancellation.count
            report["business_cancelled"] = cancellation.business_cancelled
            # Redaction failure also gets an honest manifest/exit result, AFTER
            # resource cleanup. Never remove logs to conceal a failed check.
            from backend.tests.safe_pilot.operations import assert_redacted

            try:
                assert_redacted(log.read_text(), [password])
                report["execution_secret_scan"] = "PASS"
            except AssertionError:
                report["execution_secret_scan"] = "FAIL"
                status = 1
            report["execution_sha256"] = hashlib.sha256(log.read_bytes()).hexdigest()
            report["exit"] = status
            report["finished_at_utc"] = datetime.now(UTC).isoformat()
            manifest.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
            # Preserve private cluster/dump/log evidence. No recursive deletion.
        finally:
            for number, handler in old_handlers.items():
                signal.signal(number, handler)
    raise SystemExit(status)


if __name__ == "__main__":
    main()
