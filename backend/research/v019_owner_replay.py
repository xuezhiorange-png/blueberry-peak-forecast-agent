"""Explicit local Owner-operated research, not signatures or production authority.

The OS operator invoking this dedicated command is the authorization boundary.
No service imports this module. The signed CLI and strict PIT evaluator are unchanged.
"""

from __future__ import annotations

import argparse
import csv
import io as text_io
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

from backend.research import v019_owner_scope_adapter as scope
from backend.research import v019_real_phase_a_adapter as io
from backend.research import v019_research_authorization as auth
from backend.research import v019_research_cohort as cohort
from backend.research import v019_research_evaluation as scoring
from backend.research import v019_research_execution as execution
from backend.research.v019_daily_curve import canonical_bytes, method_config
from backend.research.v019_synthetic_validation import digest

MODE = "OWNER_CONTROLLED_RETROSPECTIVE"
TASK = "V0_19_S3_OWNER_CONTROLLED_REAL_REPLAY_R1"
OLD_C0 = "d5dc13b119357934ddcbcf3abd5fbef413ffbfecc87035734ba4f2fcf93d4b2a"
MEMBERS = "50a2dd0ae913920fb32515c5a1fb41c0c62cc90217bd66bd5a9686c912a9df13"
MANIFEST = "5897df46d8071b038ccf38dada0d2b2733c9669f1b893a2e51796a17f0588770"
DAILY = "27a8274448223aa0018cbc6f02e7769f493982bb66bfbb541fb9cf62718bd714"


def code_identity() -> str:
    return digest(
        {"engine": auth.code_identity(), "owner_entry": io._hash(Path(__file__).read_bytes())}
    )


def read_bytes(path: Path, expected: str) -> bytes:
    if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("EXPLICIT_NON_SYMLINK_PATH_REQUIRED")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as f:
        before = os.fstat(f.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= 150_000_000:
            raise ValueError("BOUNDED_REGULAR_FILE_REQUIRED")
        raw = f.read(150_000_001)
        after = os.fstat(f.fileno())
    if (
        (before.st_size, before.st_mtime_ns, before.st_ino)
        != (after.st_size, after.st_mtime_ns, after.st_ino)
        or len(raw) != before.st_size
        or io._hash(raw) != expected
    ):
        raise ValueError("INPUT_HASH_OR_STABILITY_MISMATCH")
    return raw


def load_inputs(path: Path, expected: str, data_class: str) -> cohort.Inputs:
    if data_class not in {"REAL", "SYNTHETIC"}:
        raise ValueError("DATA_CLASS")
    if data_class == "REAL" and expected != MANIFEST:
        raise PermissionError("FROZEN_MANIFEST_REQUIRED")
    raw = read_bytes(path, expected)
    m = io._object(raw)
    if (
        set(m) != {"version", "data_class", "scope_version", "files", "support"}
        or m["version"] != 1
    ):
        raise ValueError("MANIFEST_SCHEMA")
    pins = cohort.REAL_HASHES if data_class == "REAL" else cohort.SYNTHETIC_HASHES
    if m["data_class"] != data_class or set(m["files"]) != set(pins):
        raise ValueError("MANIFEST_DATA_CLASS")
    for k, s in m["files"].items():
        if set(s) != {"path", "sha256"} or s["sha256"] != pins[k]:
            raise ValueError("FROZEN_IDENTITY_REQUIRED")
        if data_class == "SYNTHETIC" and Path(s["path"]).parent != path.parent:
            raise ValueError("SYNTHETIC_OWNED_DIRECTORY_REQUIRED")
    snapshots = {
        k: io._read_pinned(Path(s["path"]), s["sha256"], cohort.FILES[k]).decode()
        for k, s in m["files"].items()
    }
    return cohort.from_snapshot(m, snapshots, auth.Context(data_class), raw.decode(), expected)


def rebind(inputs: cohort.Inputs, old: dict[str, Any], data_class: str) -> dict[str, Any]:
    f = auth.unseal(old)
    original = auth.unseal(f["candidate"])
    review = auth.unseal(f["review"])
    candidate = cohort.candidates(inputs, auth.Context(data_class))
    current = candidate["payload"]
    if {k: v for k, v in original.items() if k != "code_sha256"} != {
        k: v for k, v in current.items() if k != "code_sha256"
    }:
        raise ValueError("EXACT_HISTORICAL_MEMBERS_OR_INPUTS_CHANGED")
    dispositions = {
        m["candidate_id"]: {"status": m["admission_status"], "reason": m["failure_reason"] or ""}
        for m in review["members"]
    }
    if cohort.review_candidates(f["candidate"], dispositions) != f["review"]:
        raise ValueError("HISTORICAL_REVIEW_DRIFT")
    approved = {
        w: sorted(
            m["candidate_id"]
            for m in review["members"]
            if m["window"] == w and m["admission_status"] == "ADMIT"
        )
        for w in ("H7_PREFIX", "H15_LOCAL")
    }
    if approved != f["approved"] or digest(approved) != f["approved_members_sha256"]:
        raise ValueError("APPROVED_MEMBERS_DRIFT")
    if data_class == "REAL" and (
        old["sha256"] != OLD_C0
        or digest(approved) != MEMBERS
        or len(review["members"]) != 19032
        or any(m["admission_status"] != "ADMIT" for m in review["members"])
    ):
        raise PermissionError("EXACT_OWNER_APPROVED_C0_REQUIRED")
    return auth.sealed(
        {
            "candidate": candidate,
            "review": cohort.review_candidates(candidate, dispositions),
            "approved": approved,
            "approved_members_sha256": digest(approved),
            "decision_id": TASK,
            "data_class": data_class,
            "owner_mode": MODE,
            "historical_c0_sha256": old["sha256"],
            "owner_code_sha256": code_identity(),
        }
    )


def stage_a(inputs: cohort.Inputs, old: dict[str, Any], data_class: str) -> dict[str, Any]:
    formal = rebind(inputs, old, data_class)
    profile, registry = cohort.numerical_inputs(inputs)
    content = {
        "data_class": data_class,
        "formal_c0": formal,
        "historical_c0": old,
        "input_manifest": inputs.manifest,
        "input_manifest_utf8": inputs.manifest_utf8,
        "input_snapshots_utf8": inputs.raw_files,
        "day_authorities": inputs.metadata["days"],
        "input_identities": formal["payload"]["candidate"]["payload"]["inputs"],
        "profile": profile,
        "registry": registry,
        "support": inputs.manifest["support"],
        "config": method_config(),
        "code_sha256": auth.code_identity(),
        "owner_code_sha256": code_identity(),
        "owner_mode": MODE,
        "restrictions": auth.restrictions(),
        **execution.calculate(
            profile, registry, auth.unseal(formal["payload"]["review"])["members"]
        ),
        "labels_read": False,
        "real_prediction_generated": data_class == "REAL",
    }
    return auth.sealed(
        {
            "content": content,
            "content_sha256": digest(content),
            "prediction_sha256": execution.prediction_hash(content),
            "executed_at": auth.now(),
            "historical_issued_at": None,
            "owner_mode": MODE,
        }
    )


def verify_a(seal: dict[str, Any], data_class: str) -> dict[str, Any]:
    p = auth.unseal(seal)
    c: dict[str, Any] = p["content"]
    if (
        p["owner_mode"] != MODE
        or c["owner_mode"] != MODE
        or c["data_class"] != data_class
        or c["owner_code_sha256"] != code_identity()
        or c["code_sha256"] != auth.code_identity()
        or c["labels_read"] is not False
        or c["restrictions"] != auth.restrictions()
        or c["config"] != method_config()
        or p["historical_issued_at"] is not None
        or auth.aware(p["executed_at"]) > auth.aware(auth.now())
        or p["content_sha256"] != digest(c)
        or p["prediction_sha256"] != execution.prediction_hash(c)
    ):
        raise ValueError("OWNER_A_SCOPE_CODE_OR_SEAL_DRIFT")
    manifest_hash = io._hash(c["input_manifest_utf8"].encode())
    if data_class == "REAL" and manifest_hash != MANIFEST:
        raise ValueError("MANIFEST_DRIFT")
    inputs = cohort.from_snapshot(
        c["input_manifest"],
        c["input_snapshots_utf8"],
        auth.Context(data_class),
        c["input_manifest_utf8"],
        manifest_hash,
    )
    formal = rebind(inputs, c["historical_c0"], data_class)
    profile, registry = cohort.numerical_inputs(inputs)
    if (
        formal != c["formal_c0"]
        or profile != c["profile"]
        or registry != c["registry"]
        or (
            c["day_authorities"] != inputs.metadata["days"]
            or c["support"] != inputs.manifest["support"]
        )
    ):
        raise ValueError("OWNER_A_INPUT_DRIFT")
    recomputed = execution.calculate(
        profile, registry, auth.unseal(formal["payload"]["review"])["members"]
    )
    if any(c[k] != v for k, v in recomputed.items()):
        raise ValueError("OWNER_A_RECOMPUTATION_MISMATCH")
    return c


def real_labels(path: Path, content: dict[str, Any]) -> dict[str, Any]:
    """Only the already sealed SOURCE_002 Owner-scope derived daily artifact.

    Recorded inbound net weight, NOT proof of all field harvest or equivalence.
    No workbook search, imputation, extrapolation or fuzzy identity matching.
    """
    raw = read_bytes(path, DAILY)
    days = {(d["base_id"], d["date"]): d for d in content["day_authorities"]}
    rows, seen = [], set()
    for r in csv.DictReader(text_io.StringIO(raw.decode())):
        key = r["base_id"], r["date"]
        if key in seen or key not in days:
            raise ValueError("LABEL_MEMBER_DUPLICATE_OR_OUTSIDE_SCOPE")
        seen.add(key)
        authority = days[key]
        if any(r[k] != v for k, v in authority.items()):
            raise ValueError("LABEL_DAY_AUTHORITY_MISMATCH")
        if r["authority_eligible_daily"] != "true":
            continue  # Missing row stays explicitly non-computable in scorer.
        rows.append(
            {
                "base_id": key[0],
                "date": key[1],
                "kg": r["new_quantity_kg"],
                "day_authority_sha256": digest(authority),
            }
        )
    if seen != set(days):
        raise ValueError("LABEL_SOURCE_CALENDAR_INCOMPLETE")
    return {
        "data_class": "REAL",
        "source_hash": scope.SOURCE_SHA256,
        "physical_basis": "RECORDED_MARKETABLE_NET_WEIGHT",
        "unit": "kg",
        "mature_at": auth.now(),
        "rows": rows,
    }


def write_bundle(path: Path, files: dict[str, bytes], manifest: dict[str, Any]) -> None:
    if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("PRIVATE_EXPLICIT_OUTPUT_REQUIRED")
    path.mkdir(mode=0o700, exist_ok=False)
    all_files = {
        **files,
        "manifest.json": canonical_bytes(
            {**manifest, "file_sha256": {n: io._hash(b) for n, b in files.items()}}
        ),
    }
    for name, raw in all_files.items():
        if Path(name).name != name:
            raise ValueError("LOCAL_FILENAME_REQUIRED")
        fd = os.open(path / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(raw)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("stage-a", "verify-a", "stage-b"))
    p.add_argument("--owner-command", required=True, choices=(TASK,))
    p.add_argument("--data-class", required=True, choices=("REAL", "SYNTHETIC"))
    p.add_argument("--inputs", type=Path)
    p.add_argument("--inputs-hash")
    p.add_argument("--historical-c0", type=Path)
    p.add_argument("--historical-c0-file-hash")
    p.add_argument("--seal", type=Path)
    p.add_argument("--seal-file-hash")
    p.add_argument("--verification", type=Path)
    p.add_argument("--verification-file-hash")
    p.add_argument("--labels", type=Path)
    p.add_argument("--labels-hash")
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args()
    if a.command != "stage-b" and (a.labels or a.labels_hash):
        p.error("Phase A accepts no label input")
    root = Path(__file__).resolve().parents[2]
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    if (
        a.data_class == "REAL"
        and subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=no"], cwd=root, text=True
        ).strip()
    ):
        p.error("REAL requires tested committed clean source")
    record = {
        "owner_mode": MODE,
        "task_id": TASK,
        "command": sys.argv,
        "recorded_at": auth.now(),
        "code_git_sha": sha,
        "code_sha256": code_identity(),
        "authorization_source": "DIRECT_OWNER_CHAT_CURRENT_TASK_DELEGATED_COMMAND",
        "third_party_review_claimed": False,
        "production_eligible": False,
        "data_class": a.data_class,
        "phase": a.command,
        "pid": os.getpid(),
    }
    if a.command == "stage-a":
        if not all((a.inputs, a.inputs_hash, a.historical_c0, a.historical_c0_file_hash)):
            p.error("explicit pinned inputs and original C0 required")
        inputs = load_inputs(a.inputs, a.inputs_hash, a.data_class)
        old = io._object(read_bytes(a.historical_c0, a.historical_c0_file_hash))
        seal = stage_a(inputs, old, a.data_class)
        files = {
            "phase-a.json": canonical_bytes(seal),
            "formal-c0.json": canonical_bytes(seal["payload"]["content"]["formal_c0"]),
        }
    else:
        if not a.seal or not a.seal_file_hash:
            p.error("explicit pinned A seal required")
        seal = io._object(read_bytes(a.seal, a.seal_file_hash))
        content = verify_a(seal, a.data_class)
        if a.command == "verify-a":
            files = {
                "phase-a-verification.json": canonical_bytes(
                    auth.sealed(
                        {
                            **record,
                            "a_sha256": seal["sha256"],
                            "verified": True,
                            "member_count": len(content["members"]),
                            "failure_count": len(content["failures"]),
                            "prediction_sha256": seal["payload"]["prediction_sha256"],
                            "labels_read": False,
                        }
                    )
                )
            }
        else:
            if not all((a.verification, a.verification_file_hash, a.labels, a.labels_hash)):
                p.error("independent verification and exact label identity required")
            v = auth.unseal(io._object(read_bytes(a.verification, a.verification_file_hash)))
            if (
                v["a_sha256"] != seal["sha256"]
                or v["code_sha256"] != code_identity()
                or v["verified"] is not True
                or v["labels_read"] is not False
                or v["pid"] == os.getpid()
                or v["data_class"] != a.data_class
            ):
                raise ValueError("INDEPENDENT_PROCESS_VERIFICATION_REQUIRED")
            if a.data_class == "REAL":
                if a.labels_hash != DAILY:
                    raise ValueError("FROZEN_DAILY_LABEL_IDENTITY_REQUIRED")
                labels = real_labels(a.labels, content)
            else:
                if a.labels_hash not in scoring.SYNTHETIC_LABEL_HASHES:
                    raise ValueError("REVIEWED_SYNTHETIC_LABEL_REQUIRED")
                labels = io._object(read_bytes(a.labels, a.labels_hash))
            report = scoring.score_verified(
                seal, content, labels, a.labels_hash, auth.Context(a.data_class), clock=auth.now()
            )
            report.pop("report_sha256")
            report.update(
                owner_mode=MODE,
                owner_execution=record,
                label_physical_basis_description=(
                    "SOURCE_002 recorded inbound net weight; not all field harvest"
                ),
                label_adapter_hash=digest(labels),
            )
            report["report_sha256"] = digest(report)
            files = scoring.render(report)
    if record["code_sha256"] != code_identity():
        raise ValueError("SOURCE_CHANGED_DURING_EXECUTION")
    write_bundle(a.output, files, record)
    print(a.output)


if __name__ == "__main__":
    main()
