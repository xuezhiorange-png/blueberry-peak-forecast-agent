"""Real owned PostgreSQL processes, deterministic command-boundary barriers.

The probe replaces only the downstream test command, never PostgreSQL, its
status/stop commands, or the runner's signal handlers. No business DB is used.
"""

import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import types
from pathlib import Path

import pytest

from backend.tests.safe_pilot import run

pytestmark = pytest.mark.integration
MODULE = "backend.tests.safe_pilot.test_runner_cleanup"
BASELINE = "97eb4417344f5950927cd65cf77ea3fdfa6f7d44"


def exchange(configuration, phase):
    with socket.create_connection(tuple(configuration["control"]), timeout=40) as stream:
        stream.sendall((phase + "\n").encode())
        assert stream.recv(1) == b"G", "PROBE_BARRIER_NOT_RELEASED"


def probe():
    global run
    mode, config_path, *arguments = sys.argv[1:]
    configuration = json.loads(Path(config_path).read_text())
    if mode == "driver":
        executed = {
            "kind": "CURRENT_RUNTIME_SOURCE",
            "sha256": hashlib.sha256(Path(run.__file__).read_bytes()).hexdigest(),
        }
        if configuration["baseline"]:
            source = subprocess.check_output(
                ["git", "show", BASELINE + ":backend/tests/safe_pilot/run.py"], cwd=run.ROOT
            )
            module = types.ModuleType("s5_reviewed_baseline")
            module.__file__ = run.__file__
            exec(compile(source, run.__file__, "exec"), module.__dict__)
            run = module
            executed = {
                "kind": "FIXED_GIT_BASELINE_REPRO_ONLY",
                "commit": BASELINE,
                "sha256": hashlib.sha256(source).hexdigest(),
                "old_runner_manifest_inventories_current_worktree_not_executed_blob": True,
            }
        (Path(config_path).parent / "executed-source.json").write_text(
            json.dumps(executed, sort_keys=True, indent=2) + "\n"
        )
        original = run.command

        def instrumented(arguments, environment, log, **options):
            phase = None
            if arguments[0] == "pg_ctl" and arguments[-1] == "start":
                phase = "startup"
            elif arguments[0] == "pg_ctl" and arguments[-1] == "stop":
                phase = "cleanup"
            elif arguments[1:3] == ["-m", "pytest"]:
                phase = "business"
            if phase:
                arguments = [
                    sys.executable,
                    "-m",
                    MODULE,
                    phase,
                    config_path,
                    *arguments,
                ]
            return original(arguments, environment, log, **options)

        run.command = instrumented
        sys.argv = [sys.argv[0], "--output", configuration["output"]]
        run.main()
    elif mode == "startup":
        arguments[0] = configuration["pg_ctl"]
        result = subprocess.run(arguments, check=False).returncode
        if result == 0:
            # Postmaster exists, but the pg_ctl command has NOT returned to main.
            exchange(configuration, mode)
        raise SystemExit(result or configuration["startup_exit"])
    elif mode == "cleanup":
        exchange(configuration, mode)
        arguments[0] = configuration["pg_ctl"]
        raise SystemExit(subprocess.run(arguments, check=False).returncode)
    elif mode == "business":
        exchange(configuration, mode)
        raise SystemExit(configuration["business_exit"])
    else:
        raise AssertionError("UNKNOWN_TEST_PROBE")


class Runner:
    def __init__(self, directory, *, business_exit=0, startup_exit=0, baseline=False):
        self.directory = directory
        directory.mkdir()
        self.output = directory / "SYNTHETIC-owned"
        self.control = socket.socket()
        self.control.bind(("127.0.0.1", 0))
        self.control.listen()
        self.control.settimeout(40)
        self.streams = []
        self.pg_ctl = shutil.which("pg_ctl")
        if self.pg_ctl is None:
            # Ubuntu's installed server binaries are outside the default PATH.
            binary_directory = subprocess.check_output(["pg_config", "--bindir"]).decode().strip()
            self.pg_ctl = str(Path(binary_directory) / "pg_ctl")
        assert Path(self.pg_ctl).is_file(), "REAL_POSTGRESQL_TOOLS_REQUIRED"
        config = directory / "probe.json"
        config.write_text(
            json.dumps(
                {
                    "control": self.control.getsockname(),
                    "output": str(self.output),
                    "pg_ctl": self.pg_ctl,
                    "business_exit": business_exit,
                    "startup_exit": startup_exit,
                    "baseline": baseline,
                }
            )
        )
        with (directory / "runner.log").open("wb") as output:
            self.process = subprocess.Popen(
                [sys.executable, "-m", MODULE, "driver", str(config)],
                cwd=run.ROOT,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                env=dict(
                    os.environ, PATH=str(Path(self.pg_ctl).parent) + os.pathsep + os.environ["PATH"]
                ),
            )

    def barrier(self, expected):
        try:
            stream, _ = self.control.accept()
        except TimeoutError:
            raise AssertionError(
                f"PROBE_BARRIER_MISSING: {expected}\n" + (self.directory / "runner.log").read_text()
            ) from None
        stream.settimeout(40)
        self.streams.append(stream)
        received = b""
        while not received.endswith(b"\n"):
            part = stream.recv(100)
            assert part, (self.directory / "runner.log").read_text()
            received += part
        assert received.decode().strip() == expected
        return stream

    def release(self, stream):
        stream.sendall(b"G")
        stream.close()
        self.streams.remove(stream)

    def postgres(self):
        return subprocess.run(
            [self.pg_ctl, "-D", str(self.output / "data"), "status"],
            capture_output=True,
            check=False,
        ).returncode

    def assert_finished(self, expected):
        assert self.process.wait(timeout=40) == expected, (
            self.directory / "runner.log"
        ).read_text()
        report = json.loads((self.output / "owned-resources.json").read_text())
        assert report["exit"] == expected
        assert report["shutdown_exit"] == 0
        assert report["cleanup"]["state"] == "STOPPED"
        assert report["cleanup"]["directory_identity_verified"] is True
        for key in ("root_device_inode", "data_device_inode"):
            assert report["ownership"][key] == report["cleanup"][key]
        assert report["cleanup"]["postmaster_absent"] is True
        assert report["cleanup"]["listener_closed"] is True
        assert self.postgres() == 3
        assert not (self.output / "data/postmaster.pid").exists()
        process_state = subprocess.run(
            ["ps", "-p", str(report["cleanup"]["postmaster_pid"]), "-o", "stat="],
            capture_output=True,
            text=True,
            check=False,
        )
        assert process_state.returncode != 0 or process_state.stdout.strip().startswith("Z")
        with socket.socket() as check:
            check.settimeout(2)
            assert check.connect_ex(("127.0.0.1", report["port"])) != 0
        assert (
            report["execution_sha256"]
            == hashlib.sha256((self.output / "execution.log").read_bytes()).hexdigest()
        )
        assert (self.output / "postgres.log").exists()
        assert (self.output / "private-password").exists()  # preserve, never publish
        return report

    def close(self):
        # Failure-path teardown is exact-directory only, including pre-fix repro.
        for stream in self.streams:
            try:
                stream.sendall(b"G")
            except OSError:
                pass
            stream.close()
        self.control.close()
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=10)
        data = self.output / "data"
        pid_file = data / "postmaster.pid"
        teardown = {
            "postmaster_existed_before_fixture_cleanup": pid_file.exists(),
            "runner_process_exit": self.process.returncode,
        }
        if pid_file.exists():
            lines = pid_file.read_text().splitlines()
            assert Path(lines[1]).resolve() == data.resolve()
            subprocess.run(
                [self.pg_ctl, "-D", str(data), "-m", "fast", "-w", "stop"],
                check=True,
                capture_output=True,
            )
        teardown["postgres_status_after_fixture_cleanup"] = self.postgres()
        teardown["postmaster_absent_after_fixture_cleanup"] = not pid_file.exists()
        (self.directory / "fixture-cleanup.json").write_text(
            json.dumps(teardown, sort_keys=True, indent=2) + "\n"
        )


@pytest.fixture
def runners(record_property):
    instances = []
    # PostgreSQL's Unix socket path limit also applies on macOS (long TMPDIR).
    evidence_root = Path(tempfile.mkdtemp(prefix="SYNTHETIC-s5-cancel-", dir="/tmp"))
    record_property("owned_resource_evidence", str(evidence_root))

    def create(**options):
        instance = Runner(evidence_root / str(len(instances)), **options)
        instances.append(instance)
        return instance

    try:
        yield create
    finally:
        for instance in reversed(instances):
            instance.close()


def test_sigterm_during_pg_ctl_start_cleans_postmaster(runners):
    instance = runners()
    startup = instance.barrier("startup")
    assert instance.postgres() == 0
    instance.process.send_signal(signal.SIGTERM)
    instance.release(startup)
    cleanup = instance.barrier("cleanup")
    instance.release(cleanup)
    report = instance.assert_finished(143)
    assert report["cancel_signal"] == signal.SIGTERM
    assert "backend_exit" not in report


def test_sigterm_running_and_repeated_during_cleanup_preserves_other_cluster(runners):
    independent = runners()
    independent.release(independent.barrier("startup"))
    other_work = independent.barrier("business")
    instance = runners()
    instance.release(instance.barrier("startup"))
    instance.barrier("business")
    instance.process.send_signal(signal.SIGTERM)
    cleanup = instance.barrier("cleanup")
    # Barriers, not sleeps: every signal is delivered while cleanup is held.
    instance.process.send_signal(signal.SIGTERM)
    instance.process.send_signal(signal.SIGINT)
    instance.release(cleanup)
    report = instance.assert_finished(143)
    assert report["cancel_signal"] == signal.SIGTERM
    assert report["business_cancelled"] is True
    assert independent.postgres() == 0
    assert independent.process.poll() is None
    independent.release(other_work)
    independent.release(independent.barrier("cleanup"))
    independent.assert_finished(0)


def test_failed_test_exit_still_cleans_postgres_and_preserves_failure(runners):
    instance = runners(business_exit=7)
    instance.release(instance.barrier("startup"))
    instance.release(instance.barrier("business"))
    instance.release(instance.barrier("cleanup"))
    report = instance.assert_finished(7)
    assert report["backend_exit"] == 7


def test_start_command_failure_after_postmaster_spawn_still_cleans(runners):
    instance = runners(startup_exit=7)
    instance.release(instance.barrier("startup"))
    instance.release(instance.barrier("cleanup"))
    report = instance.assert_finished(1)
    assert report["run_error_type"] == "RuntimeError"
    assert "backend_exit" not in report


def test_reviewed_baseline_reproduces_startup_leak_before_fixture_cleanup(runners, record_property):
    instance = runners(baseline=True)
    startup = instance.barrier("startup")
    assert instance.postgres() == 0
    instance.process.send_signal(signal.SIGTERM)
    instance.release(startup)
    assert instance.process.wait(timeout=10) != 0
    assert instance.postgres() == 0  # actual pre-fix leak, NOT a fixed-run PASS
    manifest = json.loads((instance.output / "owned-resources.json").read_text())
    assert "shutdown_exit" not in manifest
    executed = json.loads((instance.directory / "executed-source.json").read_text())
    assert executed["commit"] == BASELINE
    source = subprocess.check_output(
        ["git", "show", BASELINE + ":backend/tests/safe_pilot/run.py"], cwd=run.ROOT
    )
    assert executed["sha256"] == hashlib.sha256(source).hexdigest()
    record_property("executed_baseline_source_sha256", executed["sha256"])
    record_property("reproduced_unfixed_source_commit", BASELINE)
    record_property("pre_fix_result", "POSTMASTER_LEFT_RUNNING_CONFIRMED_THEN_TEARDOWN_STOPPED")


@pytest.mark.parametrize("tamper", ["directory", "pid_identity"])
def test_unverified_owned_resource_never_invokes_stop(tmp_path, monkeypatch, tamper):
    root = tmp_path / "SYNTHETIC-owned"
    root.mkdir()
    data = root / "data"
    data.mkdir()
    (data / "PG_VERSION").write_text("15\n")
    owned = run.OwnedPostgres(root, data, 56789)
    if tamper == "directory":
        data.rename(root / "preserved-data")
        data.symlink_to(root / "preserved-data", target_is_directory=True)
    else:
        (data / "postmaster.pid").write_text("12345\n/another/cluster\n1\n56789\n/tmp\n127.0.0.1\n")

    def forbidden(*arguments, **options):
        raise AssertionError("UNVERIFIED_RESOURCE_CONTROL_ATTEMPTED")

    monkeypatch.setattr(run, "command", forbidden)
    with pytest.raises(
        RuntimeError, match="(OWNED_DIRECTORY_REPLACED|POSTMASTER_IDENTITY_INVALID)"
    ):
        owned.cleanup({}, root / "execution.log", run.Cancellation())


def test_reused_pid_cannot_stop_an_unrelated_process(tmp_path, monkeypatch):
    root = tmp_path / "SYNTHETIC-owned"
    root.mkdir()
    data = root / "data"
    data.mkdir()
    (data / "PG_VERSION").write_text("15\n")
    owned = run.OwnedPostgres(root, data, 56789)
    # The initial two-line startup identity is sufficient only WITH live process
    # verification; unfinished listener fields must not mask a reused PID.
    (data / "postmaster.pid").write_text(f"{os.getpid()}\n{data.resolve()}\n")
    calls = []

    def status_only(arguments, *other, **options):
        calls.append(arguments)
        assert arguments[-1] == "status", "UNRELATED_PROCESS_STOP_ATTEMPTED"
        return 0  # stale PID looks alive to pg_ctl, but is NOT a postmaster

    monkeypatch.setattr(run, "command", status_only)
    with pytest.raises(RuntimeError, match="POSTMASTER_PROCESS_UNVERIFIED"):
        owned.cleanup({}, root / "execution.log", run.Cancellation())
    assert len(calls) == 1
    os.kill(os.getpid(), 0)  # observer remains alive; no signal was sent


if __name__ == "__main__":
    probe()
