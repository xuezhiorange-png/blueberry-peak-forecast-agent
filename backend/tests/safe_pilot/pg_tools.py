"""Select same-major clients for an already guarded synthetic server only."""

import shutil
import subprocess
from pathlib import Path

from backend.tests.safe_pilot.pg_diagnostics import version_number


class PostgresClientUnavailable(RuntimeError):
    def __init__(self):
        super().__init__("SYNTHETIC_POSTGRES_MATCHING_CLIENT_REQUIRED")


def client_for_server(name, server_version_num, environment, extra_candidates=None):
    if name not in {"pg_dump", "pg_restore"} or not 100000 <= server_version_num < 1000000:
        raise ValueError("SYNTHETIC_POSTGRES_CLIENT_IDENTITY_REQUIRED")
    major = server_version_num // 10000
    default = shutil.which(name, path=environment.get("PATH"))
    candidates = [Path(default)] if default else []
    if extra_candidates is None:
        # These are exact tool locations, not a directory or private-data scan.
        # The owned runner's local server tools also identify a client bindir.
        extra_candidates = []
        for control in ("pg_ctl", "initdb"):
            executable = shutil.which(control, path=environment.get("PATH"))
            if executable:
                extra_candidates.append(Path(executable).parent / name)
        # Debian/Ubuntu's pg_wrapper otherwise selects its newest installed
        # client, independently of the PostgreSQL 16 service under test.
        extra_candidates.append(Path(f"/usr/lib/postgresql/{major}/bin") / name)
    candidates.extend(extra_candidates)
    visited = set()
    for candidate in candidates:
        candidate = Path(candidate)
        if candidate in visited or not candidate.is_file():
            continue
        visited.add(candidate)
        try:
            result = subprocess.run(
                [str(candidate), "--version"],
                env=environment,
                capture_output=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue  # Unavailable metadata never authorizes an executable.
        version = version_number(result.stdout, name) if result.returncode == 0 else None
        if version is not None and int(version.split(".")[0]) == major:
            return str(candidate), version
    # A traceback formatter may show arguments/locals even though the error
    # message is constant. Discard lookup inputs and captured version output.
    environment, extra_candidates, candidates, visited = {}, (), [], set()
    default = candidate = executable = result = None
    raise PostgresClientUnavailable()


def toolchain(server_version_num, environment):
    return {
        name: client_for_server(name, server_version_num, environment)
        for name in ("pg_dump", "pg_restore")
    }
