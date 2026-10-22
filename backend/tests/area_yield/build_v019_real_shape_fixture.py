"""Full real-shaped SYNTHETIC files; never opens private source or model paths."""

from __future__ import annotations

import base64
import csv
import inspect
import io as text_io
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from backend.research import v019_owner_scope_adapter as scope
from backend.research import v019_real_phase_a_adapter as io
from backend.research import v019_research_authorization as auth
from backend.research import v019_research_cohort as cohort
from backend.research.v019_daily_curve import canonical_bytes
from backend.research.v019_synthetic_validation import digest
from backend.tests.area_yield.test_v0_19_owner_scope_adapter import documents


class Signer:
    """Ephemeral test keys, not real Owner decisions or independent acceptance."""

    def __init__(self) -> None:
        self.keys = {r: Ed25519PrivateKey.generate() for r in ("OWNER", "REVIEWER")}
        self.context = auth.Context(
            "SYNTHETIC",
            {
                r: {
                    "role": r,
                    "public_key_hex": k.public_key()
                    .public_bytes(Encoding.Raw, PublicFormat.Raw)
                    .hex(),
                }
                for r, k in self.keys.items()
            },
        )

    def decision(self, kind: str, subject: str) -> dict[str, Any]:
        role = "REVIEWER" if kind in {"A_SEAL_REVIEW", "IMPLEMENTATION_REVIEW"} else "OWNER"
        t = datetime.now(UTC)
        p = {
            "version": 1,
            "mode": "SYNTHETIC",
            "kind": kind,
            "subject": subject,
            "code_sha256": auth.code_identity(),
            "key_id": role,
            "issued_at": (t - timedelta(minutes=1)).isoformat(),
            "expires_at": (t + timedelta(hours=2)).isoformat(),
            "decision_id": "SYNTHETIC-ONLY-" + kind,
            "restrictions": auth.restrictions(),
        }
        return {
            "payload": p,
            "signature": base64.b64encode(self.keys[role].sign(canonical_bytes(p))).decode(),
        }


def write(path: Path, value: object) -> str:
    import os

    raw = canonical_bytes(value)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(raw)
    return io._hash(raw)


def build(
    directory: Path, *, label_variant: str = "DEFAULT"
) -> tuple[Path, str, Path, str, Signer, dict[str, Any]]:
    directory.mkdir(mode=0o700)
    # Reuse the already validated 39-base/84-farm fixture, not a second schema.
    profile, registry, meta, h7, h15, _ = inspect.unwrap(documents)()
    profile["profile_kg_per_mu_by_7_day_bin"] = {str(i): str(1 + i % 6) for i in range(42)}
    for i, b in enumerate(registry["bases"]):
        b["productive_area_mu"] = str(1 + i % 4)
    registry["hash"] = io._compact_hash({k: v for k, v in registry.items() if k != "hash"})
    files = {}
    for key, val in (("profile", profile), ("registry", registry), ("metadata", meta)):
        path = directory / cohort.FILES[key]
        files[key] = {"path": str(path), "sha256": write(path, val)}
    for key, rr in (("h7", h7), ("h15", h15)):
        text = text_io.StringIO(newline="")
        writer = csv.DictWriter(text, fieldnames=io.FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rr)
        path = directory / cohort.FILES[key]
        raw = text.getvalue().encode()
        path.touch(mode=0o600)
        with path.open("wb") as f:
            f.write(raw)
        files[key] = {"path": str(path), "sha256": io._hash(raw)}
    manifest = {
        "version": 1,
        "data_class": "SYNTHETIC",
        "scope_version": scope.SCOPE_VERSION,
        "files": files,
        "support": ["2025-07-01", "2026-04-15"],
    }
    manifest_path = directory / "input-manifest.json"
    mh = write(manifest_path, manifest)
    # Labels are a SEPARATE file: zero metadata is honored explicitly, no A
    # function imports or loads this generator or label data.
    ordered = sorted(b["base_id"] for b in registry["bases"])
    labels = []
    for day in meta["days"]:
        i = ordered.index(day["base_id"])
        # Whole-base zero, changing peaks, and different scales, all fictional.
        kg = (
            "0"
            if day["zero_applied"] == "true" or i == 38
            else str(1 + (i * 3 + int(day["date"][-2:])) % 19)
        )
        labels.append(
            {
                "base_id": day["base_id"],
                "date": day["date"],
                "kg": kg,
                "day_authority_sha256": digest(day),
            }
        )
    lp = directory / "labels.json"
    if label_variant == "MISSING_END":
        labels.pop()
    elif label_variant != "DEFAULT":
        raise ValueError("REVIEWED_SYNTHETIC_FIXTURE_ONLY")
    lh = write(
        lp,
        {
            "data_class": "SYNTHETIC",
            "source_hash": scope.SOURCE_SHA256,
            "physical_basis": "RECORDED_MARKETABLE_NET_WEIGHT",
            "unit": "kg",
            "mature_at": "2026-04-16T00:00:00+08:00",
            "rows": labels,
        },
    )
    signer = Signer()
    grants = {
        "A_INPUT_READ": signer.decision(
            "A_INPUT_READ", digest({"manifest_path": str(manifest_path), "sha256": mh})
        )
    }
    return manifest_path, mh, lp, lh, signer, grants
