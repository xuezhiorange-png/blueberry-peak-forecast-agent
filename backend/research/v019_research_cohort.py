"""Actual Owner-scope file adapters and exact, separately signed C0 review."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from backend.research import v019_owner_scope_adapter as scope
from backend.research import v019_real_phase_a_adapter as io
from backend.research import v019_research_authorization as auth
from backend.research.v019_synthetic_validation import digest

SUPPORT = io.SupportProposal(date(2025, 7, 1), date(2025, 7, 1), io.END)
FILES = {
    "profile": "reference-B.json",
    "registry": "base-registry-v1.json",
    "metadata": "owner-scope-metadata-r2.json",
    "h7": "h7-candidates.csv",
    "h15": "h15-candidates.csv",
}
REAL_HASHES = {
    "profile": io.PROFILE_SHA256,
    "registry": io.REGISTRY_SHA256,
    "metadata": scope.METADATA_SHA256,
    "h7": scope.H7_SHA256,
    "h15": scope.H15_SHA256,
}
# Reviewed full-size fictional fixture identities, NOT historical expected
# hashes. Extending synthetic fixtures requires a reviewed new identity; merely
# labeling an actual private object SYNTHETIC must never enable calculation.
SYNTHETIC_HASHES = {
    "profile": "48b1c611801b4bb810ada46affba21213806b876947cb91db973534288a93c07",
    "registry": "7dc6c92b005cc4d4c9d321cfb338e17cd24a923f2571b626e1e47e690567cfb1",
    "metadata": "4cb1f87fdd7c02af425ee442e4b0580029a5f6c00c4a540b883aa22fa3a5f4a6",
    "h7": "41327c1becefbf9a9bfd5aa0185cf5ea609bbe574fda1038919e4da36b8c5081",
    "h15": "23311e96451d140fd7c85735ee93238b095fceb5d64ddd768e580cba1f92da0c",
}


@dataclass(frozen=True)
class Inputs:
    manifest: dict[str, Any]
    profile: dict[str, Any]
    registry: dict[str, Any]
    metadata: dict[str, Any]
    rows: list[dict[str, str]]
    review: dict[str, Any]
    raw_files: dict[str, str]
    manifest_utf8: str


def numerical_inputs(inputs: Inputs) -> tuple[dict[str, Any], dict[str, Any]]:
    # Historical payload-identity checking above retains the existing adapter's
    # JSON semantics. Mathematical values are separately decoded from EXACT
    # original tokens, never from an intermediate binary float.
    profile: dict[str, Any] = json.loads(inputs.raw_files["profile"], parse_float=str)
    registry: dict[str, Any] = json.loads(inputs.raw_files["registry"], parse_float=str)
    return profile, registry


def load_inputs(
    manifest_path: Path, ctx: auth.Context, grants: object, manifest_sha256: str = ""
) -> Inputs:
    # The signed subject includes the exact absolute manifest path. It permits
    # opening only that metadata manifest and its individually pinned inputs.
    auth.require(
        ctx,
        grants,
        "A_INPUT_READ",
        digest({"manifest_path": str(manifest_path), "sha256": manifest_sha256}),
    )
    manifest_raw = io._read_pinned(manifest_path, manifest_sha256, "input-manifest.json")
    m = io._object(manifest_raw)
    if (
        set(m) != {"version", "data_class", "scope_version", "files", "support"}
        or m["version"] != 1
        or m["data_class"] != ctx.mode
        or m["scope_version"] != scope.SCOPE_VERSION
        or set(m["files"]) != set(FILES)
        or m["support"] != ["2025-07-01", "2026-04-15"]
    ):
        raise ValueError("INPUT_MANIFEST_SCHEMA_OR_DATA_CLASS")
    # Validate the entire identity/path set before any of the five data reads.
    for key in FILES:
        spec = m["files"][key]
        if set(spec) != {"path", "sha256"} or not io.HEX.fullmatch(spec["sha256"]):
            raise ValueError("EXPLICIT_PINNED_FILE_SCHEMA")
        if ctx.mode == "REAL" and spec["sha256"] != REAL_HASHES[key]:
            raise ValueError("FROZEN_REAL_OBJECT_IDENTITY_CHANGED")
        if ctx.mode == "SYNTHETIC" and (
            spec["sha256"] != SYNTHETIC_HASHES[key]
            or Path(spec["path"]).parent != manifest_path.parent
        ):
            raise PermissionError("SYNTHETIC_REVIEWED_IDENTITY_AND_OWNED_PATH_REQUIRED")
    if len({s["path"] for s in m["files"].values()}) != 5:
        raise ValueError("INPUT_PATHS_NOT_DISTINCT")
    raw = {
        key: io._read_pinned(Path(m["files"][key]["path"]), m["files"][key]["sha256"], name)
        for key, name in FILES.items()
    }
    return from_snapshot(
        m,
        {k: b.decode("utf-8") for k, b in raw.items()},
        ctx,
        manifest_raw.decode("utf-8"),
        manifest_sha256,
    )


def from_snapshot(
    m: dict[str, Any],
    snapshots: dict[str, str],
    ctx: auth.Context,
    manifest_utf8: str,
    manifest_sha256: str,
) -> Inputs:
    """No I/O: revalidate the exact A input bytes inside an approved A seal."""
    if (
        io._hash(manifest_utf8.encode("utf-8")) != manifest_sha256
        or io._object(manifest_utf8.encode("utf-8")) != m
        or set(snapshots) != set(FILES)
        or set(m["files"]) != set(FILES)
        or m["data_class"] != ctx.mode
        or m["scope_version"] != scope.SCOPE_VERSION
        or m["support"] != ["2025-07-01", "2026-04-15"]
    ):
        raise ValueError("A_INPUT_SNAPSHOT_SCHEMA")
    raw = {k: v.encode("utf-8") for k, v in snapshots.items()}
    for k in FILES:
        if ctx.mode == "SYNTHETIC" and m["files"][k]["sha256"] != SYNTHETIC_HASHES[k]:
            raise PermissionError("SYNTHETIC_REVIEWED_SNAPSHOT_IDENTITY_REQUIRED")
        if io._hash(raw[k]) != m["files"][k]["sha256"]:
            raise ValueError("A_INPUT_SNAPSHOT_HASH_MISMATCH")
        if ctx.mode == "REAL" and m["files"][k]["sha256"] != REAL_HASHES[k]:
            raise ValueError("A_FROZEN_REAL_SNAPSHOT_CHANGED")
    profile, registry, meta = [io._object(raw[k]) for k in ("profile", "registry", "metadata")]
    if ctx.mode == "REAL" and registry["hash"] != io.REGISTRY_PAYLOAD_HASH:
        raise ValueError("FROZEN_REGISTRY_PAYLOAD_CHANGED")
    h7, h15 = io._candidate_rows(raw["h7"]), io._candidate_rows(raw["h15"])
    review = scope._review(profile, registry, meta, h7, h15, SUPPORT)
    return Inputs(m, profile, registry, meta, h7 + h15, review, snapshots, manifest_utf8)


def candidates(inputs: Inputs, ctx: auth.Context) -> dict[str, Any]:
    bmeta = {b["base_id"]: b for b in inputs.metadata["bases"]}
    rows = []
    for r in inputs.rows:
        b = bmeta[r["base_id"]]
        rows.append(
            {
                "candidate_id": r["candidate_id"],
                "base_id": r["base_id"],
                "origin": r["origin_date"] + "T23:59:59+08:00",
                "cutoff": r["origin_date"] + "T23:59:59+08:00",
                "target_start": r["target_start"],
                "target_end": r["target_end"],
                "window": r["window"],
                "source_hash": scope.SOURCE_SHA256,
                "member_hash": b["member_identity_sha256"],
                "area_authority_hash": b["historical_area_authority_row_sha256"],
                "day_authority_hash": r["day_authority_sha256"],
                "admission_status": "CANDIDATE",
                "failure_reason": None,
            }
        )
    rows.sort(key=lambda r: r["candidate_id"])
    # File locations are access-control identities, not numerical input content.
    identities = {k: s["sha256"] for k, s in inputs.manifest["files"].items()}
    body = {
        "data_class": ctx.mode,
        "scope_version": scope.SCOPE_VERSION,
        "source_hash": scope.SOURCE_SHA256,
        "inputs": identities,
        "support": inputs.manifest["support"],
        "members": rows,
        "code_sha256": auth.code_identity(),
        "restrictions": auth.restrictions(),
    }
    return auth.sealed(body)


def review_candidates(
    candidate: dict[str, Any], dispositions: dict[str, dict[str, str]]
) -> dict[str, Any]:
    c = auth.unseal(candidate)
    if set(dispositions) != {r["candidate_id"] for r in c["members"]}:
        raise ValueError("ALL_CANDIDATES_REQUIRE_EXPLICIT_REVIEW_NO_SHRINKING")
    rows = []
    for r in c["members"]:
        d = dispositions[r["candidate_id"]]
        if (
            set(d) != {"status", "reason"}
            or d["status"] not in {"ADMIT", "REJECT"}
            or (d["status"] == "REJECT" and not d["reason"].strip())
            or (d["status"] == "ADMIT" and d["reason"] != "")
        ):
            raise ValueError("EXPLICIT_PRE_LABEL_DISPOSITION_REQUIRED")
        rows.append({**r, "admission_status": d["status"], "failure_reason": d["reason"] or None})
    return auth.sealed(
        {
            "candidate_sha256": candidate["sha256"],
            "data_class": c["data_class"],
            "members": rows,
            "inputs": c["inputs"],
            "support": c["support"],
            "code_sha256": c["code_sha256"],
            "restrictions": c["restrictions"],
        }
    )


def formalize(
    candidate: dict[str, Any], review: dict[str, Any], ctx: auth.Context, grants: object
) -> dict[str, Any]:
    c, r = auth.unseal(candidate), auth.unseal(review)
    auth.require(ctx, grants, "PROTOCOL", digest(auth.restrictions()))
    decision = auth.require(ctx, grants, "FORMAL_C0", review["sha256"])
    if c["data_class"] != ctx.mode or r["data_class"] != ctx.mode:
        raise PermissionError("C0_DATA_CLASS_MISMATCH")
    if r["candidate_sha256"] != candidate["sha256"]:
        raise ValueError("C0_CANDIDATE_MISMATCH")
    dispositions = {
        x["candidate_id"]: {"status": x["admission_status"], "reason": x["failure_reason"] or ""}
        for x in r["members"]
    }
    if review_candidates(candidate, dispositions) != review:
        raise ValueError("C0_REVIEW_TAMPERING")
    approved = {
        w: sorted(
            x["candidate_id"]
            for x in r["members"]
            if x["window"] == w and x["admission_status"] == "ADMIT"
        )
        for w in ("H7_PREFIX", "H15_LOCAL")
    }
    return auth.sealed(
        {
            "candidate": candidate,
            "review": review,
            "approved": approved,
            "approved_members_sha256": digest(approved),
            "decision_id": decision["decision_id"],
            "data_class": ctx.mode,
        }
    )
