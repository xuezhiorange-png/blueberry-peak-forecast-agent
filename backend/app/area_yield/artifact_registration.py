"""Read-only frozen R1 verification and create-only E1 registry publication.

The CLI accepts no authority overrides. Tests replace the pinned public file
identity in process, never requiring private artifact bytes in CI.
"""

from __future__ import annotations

import math
import os
import tempfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from backend.app.area_yield import area_size_r1
from backend.app.area_yield import prospective_validation as e1
from backend.app.area_yield.data import calendar, digest
from backend.app.area_yield.research_records import file_hash, read
from backend.app.area_yield.research_records_r2 import sha256

Record = dict[str, Any]
EXECUTION = "NEXT_AREA_SIZE_20261002_R1"
CODE_SHA = "8e886b45984a358125d00e80f4f5d662fab3d8e9"
CODE_FILE_HASH = "cb3b8d2043b1b932c207b4011151cf0744872cc5c8605edc0f61c5746d238a8f"
CONFIG_FILE_HASH = "eee3bc94ff6f9f3598fc320f00ea9ff5117a9384d336bc47855a162508ccfed5"
SOURCE_SCOPE = "NONSEALED_PRIOR_TRAINING_POOL;2025_2026_NOT_OPENED"
PUBLIC_FILE_HASH = "fa348381ea1f20e8ff535099d5b70272225e69dd9b679da8e5d848981aeb4508"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def verify_pair(candidate: Path, baseline: Path, public_path: Path) -> tuple[list[Record], Record]:
    """Only read explicit artifacts and pinned public provenance; no source discovery."""
    _require(file_hash(public_path) == PUBLIC_FILE_HASH, "PUBLIC_EVIDENCE_IDENTITY_MISMATCH")
    public = read(public_path)
    _require(
        public["execution_id"] == EXECUTION and public["base_sha"] == CODE_SHA,
        "EXECUTION_IDENTITY_MISMATCH",
    )
    fold = public["fold"]
    _require(
        fold["train_seasons"] == ["2023-2024"]
        and fold["train_sample_count"] == 15
        and fold["test_season"] == "2024-2025"
        and fold["test_sample_count"] == 22,
        "PUBLIC_TRAINING_SCOPE_MISMATCH",
    )
    models = []
    entries = []
    snapshots = []
    for kind, path in (("candidate", candidate), ("baseline", baseline)):
        before = (file_hash(path), path.stat().st_size, path.stat().st_mtime_ns)
        _require(
            before[0] == sha256(fold["artifact_file_hashes"][kind]), f"{kind}_FILE_HASH_MISMATCH"
        )
        model = read(path)
        _require(
            model.get("artifact_hash")
            == digest({k: v for k, v in model.items() if k != "artifact_hash"}),
            f"{kind}_CONTENT_HASH_MISMATCH",
        )
        if kind == "candidate":
            _require(
                model["artifact_hash"] == public["example"]["artifact_hash"],
                "CANDIDATE_PUBLIC_CONTENT_HASH_MISMATCH",
            )
        _require(
            model["model_id"] == f"{EXECUTION}_{kind.upper()}"
            and model["model_family"] == kind
            and model["model_version"] == "1"
            and model["model_role"] == "RESEARCH_CANDIDATE",
            "LEGACY_MODEL_IDENTITY_MISMATCH",
        )
        _require(
            model["training_seasons"] == ["2023-2024"]
            and model["training_sample_count"] == 15
            and model["training_area_range_mu"] == ["216", "2548"],
            "TRAINING_SCOPE_MISMATCH",
        )
        _require(
            model["features"] == (["log_area_mu"] if kind == "candidate" else [])
            and model["weather_used"] is False
            and model["holdout_used_for_fit"] is False
            and model["target_definition"] == e1.SPEC["window"]
            and model["quantity_precision"] == "0.000001kg_HALF_EVEN",
            "MODEL_CONFIG_MISMATCH",
        )
        _require(model["created_at"] == fold["created_at"], "CREATED_AT_MISMATCH")
        _require(
            datetime.fromisoformat(model["created_at"]).tzinfo is not None,
            "AWARE_CREATED_AT_REQUIRED",
        )
        identity = model["training_identity"]
        _require(
            set(identity)
            == {
                "base_sha",
                "training_source",
                "daily_source",
                "configuration_hash",
                "code_hash",
                "scope",
            },
            "TRAINING_IDENTITY_SCHEMA_MISMATCH",
        )
        _require(
            identity["base_sha"] == CODE_SHA
            and identity["scope"] == SOURCE_SCOPE
            and identity["code_hash"] == CODE_FILE_HASH
            and identity["configuration_hash"] == CONFIG_FILE_HASH,
            "TRAINING_CODE_PROVENANCE_MISMATCH",
        )
        for key in ("training_source", "daily_source"):
            _require(
                identity[key] == public["coverage"]["source_hashes"][key],
                "SOURCE_HASH_PROVENANCE_MISMATCH",
            )
        for key in ("training_source", "daily_source", "configuration_hash", "code_hash"):
            sha256(identity[key])
        params = model["parameters"]
        _require(
            set(params) == {"pooled_yield", "mean_log_area", "alpha", "beta", "penalty"}
            and params["penalty"] == 1.0,
            "PARAMETER_CONTRACT_MISMATCH",
        )
        pooled = Decimal(params["pooled_yield"])
        _require(pooled.is_finite() and pooled > 0, "POSITIVE_POOLED_YIELD_REQUIRED")
        _require(
            all(
                type(params[k]) in (int, float) and math.isfinite(params[k])
                for k in ("mean_log_area", "alpha", "beta", "penalty")
            ),
            "FINITE_PARAMETERS_REQUIRED",
        )
        profile = model["curve_parameters"]
        # Frozen leap-year training calendar; no filling or shape reconstruction.
        dates = {d.strftime("%m-%d") for d in calendar(date(2023, 7, 1), date(2024, 4, 15))}
        _require(
            set(profile) == dates
            and all(
                type(v) in (int, float) and math.isfinite(v) and v >= 0 for v in profile.values()
            )
            and math.fsum(profile.values()) > 0,
            "CURVE_CONTRACT_MISMATCH",
        )
        entries.append(
            e1.register_artifact(
                path,
                {
                    "registry_id": model["model_id"]
                    if kind == "candidate"
                    else "V0_12_COMPARATOR_BASELINE",
                    "model_role": "RESEARCH_CANDIDATE"
                    if kind == "candidate"
                    else "COMPARATOR_BASELINE",
                    "training_manifest_hash": digest(identity),
                    "training_cutoff": "2024-04-15",
                    "code_sha": identity["base_sha"],
                    "source_execution_id": EXECUTION,
                    "synthetic": False,
                    "active_for_research": True,
                },
            )
        )
        _require(
            before == (file_hash(path), path.stat().st_size, path.stat().st_mtime_ns),
            "ARTIFACT_CHANGED_DURING_VERIFICATION",
        )
        snapshots.append(before)
        models.append(model)
    c, b = models
    for key in (
        "training_identity",
        "training_seasons",
        "training_sample_count",
        "training_area_range_mu",
        "training_bases",
        "curve_parameters",
        "parameters",
    ):
        _require(c[key] == b[key], f"PAIR_{key.upper()}_MISMATCH")
    evidence = {
        "schema": "V0_12_E2_IMMUTABLE_R1_VERIFICATION_R2",
        "source_execution_id": EXECUTION,
        "candidate_file_hash": snapshots[0][0],
        "comparator_file_hash": snapshots[1][0],
        "candidate_content_hash": c["artifact_hash"],
        "comparator_content_hash": b["artifact_hash"],
        "comparator_public_content_hash_previously_frozen": False,
        "training_identity_parity": "PASS",
        "cohort_parity": "PASS",
        "training_base_identity_parity": "PASS",
        "temporal_shape_shared": True,
        "legacy_baseline_internal_role": b["model_role"],
        "runtime_baseline_role": "COMPARATOR_BASELINE",
        "role_mapping_type": "EXTERNAL_GOVERNED_ROLE_MAPPING_WITHOUT_ARTIFACT_REWRITE",
        "training_cutoff_basis": "DERIVED_FROM_FROZEN_TRAINING_SEASON_BUSINESS_WINDOW",
        "metadata_derivation": "CONFIG_AND_TRAINING_MANIFEST_DERIVED_FROM_IMMUTABLE_ARTIFACT",
        "candidate_training_manifest_hash": entries[0]["training_manifest_hash"],
        "comparator_training_manifest_hash": entries[1]["training_manifest_hash"],
        "candidate_config_hash": entries[0]["config_hash"],
        "comparator_config_hash": entries[1]["config_hash"],
        "training_seasons": c["training_seasons"],
        "training_sample_count": 15,
        "training_area_range_mu": c["training_area_range_mu"],
        "artifact_bytes_unchanged": True,
        "production_approved": False,
        "scientific_score_role": "NONE",
    }
    return entries, evidence


def register_pair(candidate: Path, baseline: Path, public_path: Path, output: Path) -> Record:
    """Validate both, publish one complete registry atomically without overwrite."""
    if output.exists():
        raise FileExistsError("RUNTIME_REGISTRY_ALREADY_EXISTS")
    _require(
        output.resolve() not in {candidate.resolve(), baseline.resolve(), public_path.resolve()},
        "OUTPUT_INPUT_ALIAS_REJECTED",
    )
    entries, evidence = verify_pair(candidate, baseline, public_path)
    # Same-filesystem link is atomic and exclusive, unlike replace(). Both
    # artifacts are validated before any official registry becomes visible.
    with tempfile.TemporaryDirectory(prefix=".e2-registration-", dir=output.parent) as staging:
        staged = Path(staging) / "registry.json"
        e1.save_registry(staged, entries)
        staged.chmod(0o600)
        with staged.open("rb") as stream:
            os.fsync(stream.fileno())
        os.link(staged, output)
    return {
        **evidence,
        "runtime_registry_created": True,
        "runtime_registry_file_hash": file_hash(output),
    }


def guarded_predict(artifact: Path) -> Record:
    """Fixed TEST_ONLY inference; actively disable fit in this fresh process."""

    def reject_fit(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("MODEL_TRAINING_FORBIDDEN")

    area_size_r1.fit = reject_fit
    return area_size_r1.predict(read(artifact), "736.000000", 2026, "TEST_ONLY_UNSEEN_BASE")
