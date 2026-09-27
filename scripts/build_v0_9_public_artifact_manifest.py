"""Build the deterministic public artifact manifest for the V0.9 closeout."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_RELATIVE_PATH = "docs/v0-9/evidence/v0.9.0-public-artifact-manifest.json"
S0_PINS = dict(
    [
        (
            "docs/v0-9/s0/global-protected-blueberry-biology-and-management-authority-review-r1.md",
            "827725a44094e5e15643186fe8f82095adbff0bfc2b2ac549aca6600d06a4c13",
        ),
        (
            "docs/v0-9/evidence/"
            "s0-global-protected-blueberry-biology-and-management-authority-review-r1.json",
            "530106f7291ab3d92fe4b0a0d682efc0fc154149218acda71369f76e785449cf",
        ),
        (
            "docs/v0-9/s0/scientific-authority-matrix-r1.csv",
            "1fecd24c4aa537d5617a960e15ab74ace260ad35e30e63d9fdbe89e59bf88294",
        ),
        (
            "docs/v0-9/s0/biological-causal-claim-register-r1.csv",
            "0ee8959db03f1ac28b226df06c00bf08c2427949b2f1e9de69a772bbd805d55a",
        ),
        (
            "docs/v0-9/s0/evidence-conflict-and-uncertainty-register-r1.csv",
            "e5c17df1d33e3ef9dcc1d5d149598fa6a602a5c65a09f99d47e8040d42d94a91",
        ),
        (
            "docs/v0-9/s0/literature-parameter-candidate-register-r1.csv",
            "2d28f90e42eafeea14f252e96ed0c26e2bc6b78b1c8273263b5d2d32b1410325",
        ),
    ]
)
S1_MANIFEST_PATH = "docs/v0-9/evidence/s1-biological-contract-artifact-manifest-r1.json"
S1_MANIFEST_SHA256 = "8ea4d508010e55c4996142ec96c389a91a356f78966e8f5d4fb4e449ef611381"
S2_EVIDENCE_PATH = "docs/v0-9/evidence/s2-existing-data-observability-and-gap-audit-r1.json"
S2_EVIDENCE_SHA256 = "18133476e96cb33308762bb7466dd05d1aa51dacde31f6c2924d5435db347cad"
S3_EVIDENCE_PATH = "docs/v0-9/evidence/s3-theoretical-blueberry-growth-model-r1.json"
S3_EVIDENCE_SHA256 = "c74c956650f4e5751083ffed3d40e9cbff68c3f53fc8e1ad661c234003d3e441"
S4_EVIDENCE_PATH = "docs/v0-9/evidence/s4-theoretical-model-validation-and-identifiability-r1.json"
S4_EVIDENCE_SHA256 = "04aa371419b08856ee6b363e67590fb7ebcb038b5a75e563200c4fe1401f0a17"
S4_REPORT_PATH = "docs/v0-9/s4/theoretical-model-structural-validation-r1.md"
S4_REPORT_SHA256 = "b846bc24f32872a117b7d72b0fcd1356dc36ab7976f3019f7e39f01384bc8367"
S3_PRE_S4_CORRECTIONS = dict(
    [
        (
            "backend/app/biological_growth/parameters.py",
            "b50bc862aa3e2b8cef847e0213d97f55bf71cd70463c55390c78618ea203d2be",
        ),
        (
            "backend/app/biological_growth/fruit_development.py",
            "437b65642ebeba5b04bd843f784804db6e8c085c46c13a16f487a77b66efde84",
        ),
        (
            "backend/app/biological_growth/dormancy.py",
            "bc5860e71df33fd24f18b62ee92498021e6f54edbf94e20f65a1392698229017",
        ),
        (
            "backend/app/biological_growth/engine.py",
            "124b7a4a27c789b21982cdf168fe9097f3b69cac7159d229756f5a1c6bdce5a7",
        ),
    ]
)
AREA_YIELD_V09_TESTS = {
    "backend/tests/area_yield/test_v09_s1_contract_integrity.py",
    "backend/tests/area_yield/test_v09_s2_data_observability.py",
}
EXPLICIT_SCRIPTS = {
    "scripts/audit_v0_9_s2_data_observability.py",
    "scripts/run_v0_9_s4_validation.py",
    "scripts/build_v0_9_public_artifact_manifest.py",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(relative_path: str) -> dict[str, Any]:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def require_hash(relative_path: str, expected: str) -> None:
    actual = sha256_file(ROOT / relative_path)
    if actual != expected:
        raise ValueError(f"Artifact pin mismatch: {relative_path}: {actual}")


def verify_stage_lineage() -> None:
    for path, expected in S0_PINS.items():
        require_hash(path, expected)

    version_plan = read_json("docs/v0-9/evidence/v0.9.0-version-plan-and-scope-freeze.json")
    if version_plan["result"] != "PASS_V0_9_VERSION_SCOPE_FROZEN":
        raise ValueError("V0.9 version-plan result mismatch")
    if version_plan["primary_goal"] != (
        "ESTABLISH_A_SCIENTIFICALLY_GROUNDED_AND_AUDITABLE_BLUEBERRY_BIOLOGICAL_FORECAST_FOUNDATION"
    ):
        raise ValueError("V0.9 primary goal drift")

    s0_evidence = read_json(
        "docs/v0-9/evidence/s0-global-protected-blueberry-biology-and-management-authority-review-r1.json"
    )
    if s0_evidence["result"] != "PASS_V0_9_S0_SCIENTIFIC_AUTHORITY_REVIEW_COMPLETED":
        raise ValueError("S0 result mismatch")
    if s0_evidence["research_scope"]["scientific_source_count"] != 47:
        raise ValueError("S0 scientific source count drift")
    if s0_evidence["research_scope"]["peer_reviewed_source_count_minimum_verified"] != 41:
        raise ValueError("S0 peer-reviewed source count drift")

    require_hash(S1_MANIFEST_PATH, S1_MANIFEST_SHA256)
    s1_manifest = read_json(S1_MANIFEST_PATH)
    for item in s1_manifest["files"]:
        require_hash(item["path"], item["sha256"])
    s1_evidence = read_json(
        "docs/v0-9/evidence/s1-biological-state-and-management-event-contract-r1.json"
    )
    if s1_evidence["result"] != "PASS_V0_9_S1_BIOLOGICAL_CONTRACT_FROZEN":
        raise ValueError("S1 result mismatch")
    if s1_evidence["mechanism_admission"]["unauthorized_mechanism_promotion_count"] != 0:
        raise ValueError("S1 unauthorized mechanism promotion detected")

    require_hash(S2_EVIDENCE_PATH, S2_EVIDENCE_SHA256)
    s2_evidence = read_json(S2_EVIDENCE_PATH)
    if s2_evidence["task_id"] != "V0_9_S2_EXISTING_DATA_OBSERVABILITY_AND_GAP_AUDIT_R1":
        raise ValueError("S2 task identity mismatch")
    if s2_evidence["coverage"]["total_contract_variables_audited"] != 213:
        raise ValueError("S2 coverage count drift")
    if s2_evidence["scope"]["live_database_queried"] or s2_evidence["scope"]["model_trained"]:
        raise ValueError("S2 scope boundary mismatch")

    require_hash(S3_EVIDENCE_PATH, S3_EVIDENCE_SHA256)
    s3_evidence = read_json(S3_EVIDENCE_PATH)
    require_hash(S4_EVIDENCE_PATH, S4_EVIDENCE_SHA256)
    s4_evidence = read_json(S4_EVIDENCE_PATH)
    require_hash(S4_REPORT_PATH, S4_REPORT_SHA256)

    s4_current_hashes = {item["path"]: item["sha256"] for item in s4_evidence["artifact_manifest"]}
    s3_mismatches: dict[str, str] = {}
    for item in s3_evidence["artifact_manifest"]:
        path = item["path"]
        actual = sha256_file(ROOT / path)
        if actual == item["sha256"]:
            continue
        if path not in S3_PRE_S4_CORRECTIONS or item["sha256"] != S3_PRE_S4_CORRECTIONS[path]:
            raise ValueError(f"Unexpected S3 artifact drift: {path}")
        if s4_current_hashes.get(path) != actual:
            raise ValueError(f"S4 does not pin the current declared correction: {path}")
        s3_mismatches[path] = actual
    if set(s3_mismatches) != set(S3_PRE_S4_CORRECTIONS):
        raise ValueError("S3-to-S4 correction set is incomplete")

    for item in s4_evidence["artifact_manifest"]:
        require_hash(item["path"], item["sha256"])

    if s0_tier_count() != {"A": 37, "A2": 4, "B": 1, "C": 5, "D": 0, "X": 0}:
        raise ValueError("S0 source authority counts differ from the frozen closeout facts")
    if s3_evidence["result"] != "PASS_V0_9_S3_THEORETICAL_GROWTH_MODEL_IMPLEMENTED":
        raise ValueError("S3 result mismatch")
    if s3_evidence["model"]["equation_count"] != 30:
        raise ValueError("S3 equation count drift")
    if s3_evidence["scope_and_authorization"]["historical_harvest_parameter_fitting"]:
        raise ValueError("S3 historical-harvest fitting boundary mismatch")
    if s4_evidence["result"] != "PASS_V0_9_S4_THEORETICAL_MODEL_VALIDATED_AND_PROSPECTIVE_READY":
        raise ValueError("S4 result mismatch")
    if s4_evidence["equation_count_reviewed"] != 30:
        raise ValueError("S4 reviewed equation count drift")
    if s4_evidence["untraceable_equation_count"] != 0:
        raise ValueError("S4 contains an untraceable equation")


def s0_tier_count() -> dict[str, int]:
    import csv

    path = ROOT / "docs/v0-9/s0/scientific-authority-matrix-r1.csv"
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    counts = {tier: 0 for tier in ("A", "A2", "B", "C", "D", "X")}
    for row in rows:
        tier = row["authority_tier"]
        if tier not in counts:
            raise ValueError(f"Unknown S0 authority tier: {tier}")
        counts[tier] += 1
    return counts


def collect_public_paths() -> list[str]:
    paths: set[str] = set()
    for root_name in (
        "docs/v0-9",
        "backend/app/biological_growth",
        "backend/tests/biological_growth",
    ):
        base = ROOT / root_name
        for path in base.rglob("*"):
            if path.is_file() and path.suffix in {".csv", ".json", ".md", ".py"}:
                relative = path.relative_to(ROOT).as_posix()
                if relative != MANIFEST_RELATIVE_PATH:
                    paths.add(relative)
    paths.update(AREA_YIELD_V09_TESTS)
    paths.update(EXPLICIT_SCRIPTS)
    missing = sorted(path for path in paths if not (ROOT / path).is_file())
    if missing:
        raise ValueError(f"Expected public artifacts missing: {missing}")
    return sorted(paths)


def classify(path: str) -> tuple[str, str]:
    if path.startswith("docs/v0-9/evidence/v0.9.0-biological-forecast-foundation-closeout"):
        return "VERSION_CLOSEOUT", "FINAL_CLOSEOUT"
    if path.startswith("docs/v0-9/evidence/v0.9.0-version-plan") or path.endswith(
        "v0.9.0-version-plan-and-scope-freeze.md"
    ):
        return "VERSION_SCOPE", "VERSION_PLAN_FROZEN"
    for stage, role, lifecycle in (
        ("s0", "SOURCE_AUTHORITY", "SCIENTIFIC_AUTHORITY_REVIEW"),
        ("s1", "BIOLOGICAL_CONTRACT", "CONTRACT_FROZEN"),
        ("s2", "DATA_OBSERVABILITY", "CURRENT_DATA_AUDIT"),
        ("s3", "THEORETICAL_MODEL", "SYNTHETIC_RESEARCH_MODEL"),
        ("s4", "STRUCTURAL_VALIDATION", "THEORETICAL_VALIDATION"),
    ):
        stage_directory = f"/{stage}/"
        evidence_prefix = f"/evidence/{stage}-"
        if stage_directory in path or evidence_prefix in path:
            return role, lifecycle
    if path.startswith("backend/app/biological_growth/"):
        return "MODEL_IMPLEMENTATION", "S3_IMPLEMENTED_S4_VALIDATED"
    if path.startswith("backend/tests/"):
        return "TESTS_AND_SYNTHETIC_GOLDENS", "FOCUSED_VALIDATION"
    return "AUDIT_OR_VALIDATION_TOOL", "REPRODUCIBILITY_SUPPORT"


def build_manifest() -> dict[str, Any]:
    entries = []
    for relative in collect_public_paths():
        role, lifecycle = classify(relative)
        entries.append(
            {
                "path": relative,
                "sha256": sha256_file(ROOT / relative),
                "role": role,
                "lifecycle": lifecycle,
            }
        )
    return {
        "schema_version": "V0_9_PUBLIC_ARTIFACT_MANIFEST_R1",
        "version": "0.9.0",
        "task_id": "V0_9_VERSION_CLOSEOUT_AND_DRAFT_PR_R1",
        "manifest_self_sha256_excluded": True,
        "private_row_level_artifacts_included": False,
        "machine_specific_private_paths_included": False,
        "artifact_count": len(entries),
        "entries": entries,
    }


def main() -> int:
    verify_stage_lineage()
    manifest = build_manifest()
    encoded = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    output = ROOT / MANIFEST_RELATIVE_PATH
    if "--check" in sys.argv:
        if not output.is_file() or output.read_text(encoding="utf-8") != encoded:
            raise SystemExit("Public artifact manifest is missing or stale")
        print(f"manifest PASS: {manifest['artifact_count']} artifacts")
        return 0
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(encoded, encoding="utf-8")
    print(f"wrote {MANIFEST_RELATIVE_PATH}: {manifest['artifact_count']} artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
