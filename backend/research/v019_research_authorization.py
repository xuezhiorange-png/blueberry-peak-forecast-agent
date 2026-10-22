"""Signed, subject-bound decisions with explicitly pinned real enrollment.

Synthetic roots never authorize REAL. A real context must name the exact
Owner-authorized enrollment bytes. Enrollment does not grant any operation.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from backend.research import v019_real_phase_a_adapter as io
from backend.research.v019_daily_curve import canonical_bytes
from backend.research.v019_synthetic_validation import digest

# Deliberately empty. Current development permission does not install trust or
# grant any real study operation. Synthetic roots are a separate test namespace.
REAL_TRUST_ANCHORS: dict[str, dict[str, str]] = {}
REAL_TRUST_CONFIG_SHA256 = "45a28a1879c17cb770896b8d9389bbad8adca708aef0b031b18a241bb710a0d6"
REAL_ENROLLMENT_DECISIONS = {
    "OWNER": frozenset({"PROTOCOL", "FORMAL_C0", "A_INPUT_READ"}),
    "REVIEWER": frozenset({"IMPLEMENTATION_REVIEW", "A_SEAL_REVIEW"}),
}
DECISIONS = frozenset(
    {
        "PROTOCOL",
        "FORMAL_C0",
        "A_INPUT_READ",
        "A_EXECUTION",
        "A_SEAL_REVIEW",
        "B_LABEL_READ",
        "B_SCORING",
        "IMPLEMENTATION_REVIEW",
    }
)


@dataclass(frozen=True)
class Context:
    mode: str
    synthetic_roots: dict[str, dict[str, str]] = field(default_factory=dict)
    real_trust_config: Path | None = None


def now() -> str:
    return datetime.now(UTC).isoformat()


def aware(value: str) -> datetime:
    t = datetime.fromisoformat(value)
    if t.utcoffset() is None:
        raise ValueError("TIMEZONE_REQUIRED")
    return t


def _real_roots(path: Path) -> dict[str, Any]:
    raw = io._read_pinned(path, REAL_TRUST_CONFIG_SHA256, "real-trust-config.json")
    config = io._object(raw)
    if (
        set(config)
        != {
            "version",
            "mode",
            "task_id",
            "issued_at",
            "expires_at",
            "scope",
            "keys",
            "custody",
            "authorization_source",
        }
        or type(config["version"]) is not int
        or config["version"] != 1
        or config["mode"] != "REAL"
        or config["task_id"] != "V0_19_S3_FORMAL_C0_AND_TRUST_PROVISIONING_R1"
        or config["scope"] != "V0_19_SOURCE002_OWNER_RESEARCH_SCOPE_R1"
        or type(config["keys"]) is not dict
        or len(config["keys"]) != 2
    ):
        raise PermissionError("REAL_TRUST_ENROLLMENT_SCHEMA_OR_SCOPE")
    if not aware(config["issued_at"]) <= aware(now()) < aware(config["expires_at"]):
        raise PermissionError("REAL_TRUST_ENROLLMENT_EXPIRED_OR_FUTURE")
    result = config["keys"]
    roles = []
    for key_id, key in result.items():
        if (
            type(key_id) is not str
            or not key_id
            or type(key) is not dict
            or set(key) != {"role", "public_key_hex", "allowed_decisions"}
            or key["role"] not in REAL_ENROLLMENT_DECISIONS
            or type(key["allowed_decisions"]) is not list
            or frozenset(key["allowed_decisions"]) != REAL_ENROLLMENT_DECISIONS[key["role"]]
            or not io.HEX.fullmatch(key["public_key_hex"])
        ):
            raise PermissionError("REAL_TRUST_ROLE_OR_CAPABILITY_INVALID")
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(key["public_key_hex"]))
        roles.append(key["role"])
    if sorted(roles) != ["OWNER", "REVIEWER"]:
        raise PermissionError("OWNER_AND_REVIEWER_ROOTS_REQUIRED")
    return result


def roots(ctx: Context) -> dict[str, Any]:
    if type(ctx) is not Context or ctx.mode not in {"REAL", "SYNTHETIC"}:
        raise PermissionError("EXPLICIT_DATA_CLASS_REQUIRED")
    if ctx.mode == "REAL":
        if ctx.real_trust_config is None or ctx.synthetic_roots:
            raise PermissionError("TRUST_ANCHOR_NOT_PROVISIONED_REAL_EXECUTION_BLOCKED")
        result = _real_roots(ctx.real_trust_config)
    else:
        if ctx.real_trust_config is not None:
            raise PermissionError("TRUST_NAMESPACES_MUST_BE_SEPARATE")
        result = ctx.synthetic_roots
    if not result:
        raise PermissionError("TRUST_ANCHOR_NOT_PROVISIONED_REAL_EXECUTION_BLOCKED")
    owner_keys = {k["public_key_hex"] for k in result.values() if k["role"] == "OWNER"}
    reviewer_keys = {k["public_key_hex"] for k in result.values() if k["role"] == "REVIEWER"}
    if owner_keys & reviewer_keys:
        raise PermissionError("OWNER_REVIEWER_TRUST_KEYS_MUST_BE_DISTINCT")
    return result


def require(
    ctx: Context, grants: object, kind: str, subject: str, *, at: str | None = None
) -> dict[str, Any]:
    trusted = roots(ctx)  # fail before any business/seal/label I/O
    if type(grants) is not dict or kind not in DECISIONS or kind not in grants:
        raise PermissionError("INDEPENDENT_SIGNED_DECISION_REQUIRED:" + kind)
    g = grants[kind]
    if type(g) is not dict or set(g) != {"payload", "signature"} or type(g["payload"]) is not dict:
        raise PermissionError("SIGNED_DECISION_SCHEMA")
    p = g["payload"]
    if set(p) != {
        "version",
        "mode",
        "kind",
        "subject",
        "code_sha256",
        "key_id",
        "issued_at",
        "expires_at",
        "decision_id",
        "restrictions",
    }:
        raise PermissionError("SIGNED_DECISION_SCHEMA")
    if (
        type(p["version"]) is not int
        or type(g["signature"]) is not str
        or any(
            type(p[k]) is not str
            for k in (
                "mode",
                "kind",
                "subject",
                "code_sha256",
                "key_id",
                "issued_at",
                "expires_at",
                "decision_id",
            )
        )
    ):
        raise PermissionError("SIGNED_DECISION_TYPES")
    key = trusted.get(p["key_id"])
    role = "REVIEWER" if kind in {"A_SEAL_REVIEW", "IMPLEMENTATION_REVIEW"} else "OWNER"
    if (
        not key
        or key["role"] != role
        or (ctx.mode == "REAL" and kind not in key["allowed_decisions"])
        or p["version"] != 1
        or p["mode"] != ctx.mode
        or p["kind"] != kind
        or p["subject"] != subject
        or p["code_sha256"] != code_identity()
        or not p["decision_id"]
        or canonical_bytes(p["restrictions"]) != canonical_bytes(restrictions())
    ):
        raise PermissionError("DECISION_SCOPE_ROLE_OR_CODE_MISMATCH")
    try:
        clock = aware(at or now())
        if not aware(p["issued_at"]) <= clock < aware(p["expires_at"]):
            raise PermissionError("DECISION_EXPIRED_OR_FUTURE")
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(key["public_key_hex"])).verify(
            base64.b64decode(g["signature"], validate=True), canonical_bytes(p)
        )
    except (InvalidSignature, ValueError, TypeError) as exc:
        raise PermissionError("INVALID_DECISION_SIGNATURE_OR_TIME") from exc
    return p


def restrictions() -> dict[str, Any]:
    return {
        "experiment_type": "RETROSPECTIVE_REPLAY",
        "strict_pit": False,
        "historical_status": "EXPOSED_HISTORICAL_BENCHMARK",
        "training": False,
        "production_eligible": False,
        "full_season_admitted": False,
        "physical_basis_equivalence": "NOT_PROVEN",
        "historical_area_known_at": "NOT_PROVEN",
    }


def code_identity() -> str:
    root = Path(__file__).resolve().parents[2]
    names = (
        "v019_research_authorization",
        "v019_research_cohort",
        "v019_research_execution",
        "v019_research_evaluation",
        "v019_research_cli",
        "v019_owner_scope_adapter",
        "v019_real_phase_a_adapter",
        "v019_retrospective_engine",
        "v019_retrospective_scoring",
        "v019_daily_curve",
        "v019_synthetic_validation",
    )
    paths = [f"backend/research/{n}.py" for n in names]
    paths += ["backend/app/forecast_quality/operational_peak.py"]
    return digest({p: io._hash((root / p).read_bytes()) for p in paths})


def read_json(path: Path, *, limit: int = 150_000_000) -> dict[str, Any]:
    """Explicit, bounded, no-follow read. Caller must check access beforehand."""
    import os
    import stat

    if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("ABSOLUTE_NON_SYMLINK_PATH_REQUIRED")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as f:
        before = os.fstat(f.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= limit:
            raise ValueError("BOUNDED_REGULAR_FILE_REQUIRED")
        raw = f.read(limit + 1)
        after = os.fstat(f.fileno())
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ) or len(raw) != before.st_size:
        raise ValueError("INPUT_CHANGED_DURING_READ")
    return io._object(raw)


def sealed(payload: dict[str, Any]) -> dict[str, Any]:
    return {"payload": payload, "sha256": digest(payload)}


def unseal(value: dict[str, Any]) -> dict[str, Any]:
    if set(value) != {"payload", "sha256"} or digest(value["payload"]) != value["sha256"]:
        raise ValueError("SEALED_PAYLOAD_HASH_MISMATCH")
    payload: dict[str, Any] = value["payload"]
    return payload
