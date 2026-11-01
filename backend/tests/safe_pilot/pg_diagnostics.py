"""Allowlisted diagnostics for the owned synthetic backup/restore subprocesses.

No subprocess text, SQL, paths, identifiers or environment values are exported.
An unrecognized error remains unknown; these classes never authorize a retry.
"""

import json
import re


def version_number(output, executable):
    if executable not in {"pg_dump", "pg_restore"}:
        return None
    match = re.match(
        re.escape(executable) + r" \(PostgreSQL\) ([0-9]+\.[0-9]+(?:\.[0-9]+)?)\b",
        output.decode("ascii", errors="replace"),
    )
    return match[1] if match else None


def _version(value):
    return (
        value
        if isinstance(value, str) and re.fullmatch(r"[0-9]+\.[0-9]+(?:\.[0-9]+)?", value)
        else None
    )


def _category(raw, dump_version, restore_version, server):
    message = raw.decode("utf-8", errors="replace")
    if re.search(r"pg_dump: error: aborting because of server version mismatch", message):
        return "VERSION_INCOMPATIBILITY"
    if re.search(r"pg_restore: error: unsupported version .* in file header", message):
        return "VERSION_INCOMPATIBILITY"
    # This setting was introduced in PostgreSQL 17. Require actual client and
    # server version evidence as well as the specific server error.
    if (
        server is not None
        and server < 170000
        and restore_version is not None
        and int(restore_version.split(".")[0]) >= 17
        and re.search(
            r'ERROR:\s+unrecognized configuration parameter "transaction_timeout"', message
        )
    ):
        return "VERSION_INCOMPATIBILITY"
    patterns = (
        (
            r"ERROR:\s+extension .+ (?:is not available|cannot be loaded)",
            "EXTENSION_OR_SCHEMA_CONFLICT",
        ),
        (
            r"ERROR:\s+(?:encoding|collation) .+ (?:does not match|is incompatible)",
            "ENCODING_OR_COLLATION_CONFLICT",
        ),
        (r"ERROR:\s+permission denied\b", "PERMISSION_DENIED"),
        (
            r"ERROR:\s+(?:relation|schema|type|function|constraint|index) .+ already exists",
            "OBJECT_ALREADY_EXISTS",
        ),
        (
            r"ERROR:\s+(?:relation|schema|type|function|constraint|index) .+ does not exist",
            "OBJECT_MISSING",
        ),
        (
            r"pg_(?:dump|restore): error: connection to server .*(?:failed|refused)",
            "CONNECTION_FAILURE",
        ),
        (
            r"pg_restore: error: (?:input file is too short|"
            r"did not find magic string in file header|could not read from input file|"
            r"input file does not appear to be a valid archive)",
            "INVALID_ARCHIVE",
        ),
    )
    for pattern, category in patterns:
        if re.search(pattern, message):
            return category
    return "UNKNOWN_UNCLASSIFIED"


class PostgresOperationFailure(RuntimeError):
    def __init__(self, diagnostic):
        self.diagnostic = diagnostic
        super().__init__(
            "SYNTHETIC_POSTGRES_OPERATION_FAILED "
            + json.dumps(diagnostic, sort_keys=True, separators=(",", ":"))
        )


def failure(completed, operation, dump_version, restore_version, server, validation):
    if operation not in {"PG_DUMP", "PG_RESTORE"}:
        raise ValueError("SYNTHETIC_POSTGRES_OPERATION_REQUIRED")
    dump_version, restore_version = _version(dump_version), _version(restore_version)
    server = server if type(server) is int and 100000 <= server < 1000000 else None
    category = _category(completed.stderr, dump_version, restore_version, server)
    diagnostic = {
        "operation": operation,
        "phase": "RESTORE_INTO_NEW_SYNTHETIC_DATABASE",
        "exit_code": int(completed.returncode),
        "client_pg_dump_version": dump_version,
        "client_pg_restore_version": restore_version,
        "server_version_num": server,
        "archive_format": "CUSTOM" if validation == "PASS" else "NOT_PROVEN",
        "archive_validation_status": validation if validation in {"PASS", "FAIL"} else "NOT_PROVEN",
        "error_class": category,
        # Default pg_restore stderr has no reliably encoded SQLSTATE. Do not
        # infer one from English text or a value embedded in an identifier.
        "sqlstate_if_reliably_available": None,
        "diagnostic_evidence_status": (
            "EXPLICIT_STDERR_CLASSIFIED"
            if category != "UNKNOWN_UNCLASSIFIED"
            else "UNKNOWN_UNCLASSIFIED"
        ),
    }
    # Also sanitize the CompletedProcess left in the caller's traceback frame.
    completed.args = [operation]
    completed.stdout = completed.stderr = b""
    return PostgresOperationFailure(diagnostic)
