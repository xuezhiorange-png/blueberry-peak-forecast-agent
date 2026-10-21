"""SYNTHETIC-only adapter tests; never open project private artifacts."""

from __future__ import annotations

import inspect
from copy import deepcopy
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from backend.research import v019_real_phase_a_adapter as adapter
from backend.research.v019_daily_curve import canonical_bytes
from backend.research.v019_retrospective_entry import CandidateScope

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def test_real_execution_never_opens_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> bytes:
        raise AssertionError("INPUT_OR_LABEL_OPENED")

    monkeypatch.setattr(Path, "read_bytes", forbidden)
    for forged in (None, True, {"owner_authorized": True}, "APPROVED"):
        with pytest.raises(PermissionError, match="REAL_PHASE_A_EXECUTION_DISABLED"):
            adapter.generate_real_predictions(forged, input_path="/not/opened")


def test_synthetic_phase_a_repeat_without_labels(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.research import v019_replay_preparation, v019_retrospective_entry

    def forbidden(*args: object, **kwargs: object) -> Any:
        raise AssertionError("LABEL_OR_SCORE_OPENED")

    monkeypatch.setattr(v019_retrospective_entry, "demo_labels", forbidden)
    monkeypatch.setattr(v019_replay_preparation, "demo_labels", forbidden)
    monkeypatch.setattr(v019_retrospective_entry, "score_synthetic", forbidden)
    read_bytes = Path.read_bytes
    source_names = {
        "v019_real_phase_a_adapter.py",
        "v019_daily_curve.py",
        "v019_retrospective_entry.py",
        "v019_replay_preparation.py",
        "v019_synthetic_validation.py",
    }

    def source_only(path: Path) -> bytes:
        assert path.name in source_names and path.parent.name == "research"
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", source_only)
    one = adapter.rehearse_synthetic()
    assert one == adapter.rehearse_synthetic()
    assert one["data_class"] == "SYNTHETIC"
    assert one["labels_read"] is False
    assert one["real_prediction_generated"] is False
    assert len(one["members"]) == 4
    for member in one["members"]:
        assert member["computed_at"] == member["issued_at"]
        assert member["computed_at"] > member["origin"]
        assert len(member["baseline_daily"]) == len(member["candidate_daily"])
        assert member["full_support_start"] == "2000-01-02"
        assert member["full_support_end"] == "2000-01-22"
        assert len(member["daily_dates"]) in (7, 15)
        assert member["baseline_source_hash"] == member["candidate_source_hash"]


@pytest.mark.parametrize("fixture", ["MISSING_INPUT", "UNVERIFIED_PHYSICAL_BASIS"])
def test_registered_failures_are_retained(fixture: str) -> None:
    result = adapter.rehearse_synthetic(fixture=fixture)
    assert len(result["members"]) == 4
    assert any(member["failure"] for member in result["members"])


@pytest.mark.parametrize("fixture", ["REAL", "SOURCE_002", "../private", ""])
def test_synthetic_entry_rejects_external_inputs(fixture: str) -> None:
    with pytest.raises((ValueError, PermissionError)):
        adapter.rehearse_synthetic(fixture=fixture)


def test_hash_rejection_precedes_schema(tmp_path: Path) -> None:
    path = tmp_path / "reference-B.json"
    path.write_bytes(b'{"labels": "SYNTHETIC-NOT-A-REAL-ARTIFACT"}')
    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        adapter._read_pinned(path, adapter.PROFILE_SHA256, "reference-B.json")


def test_paths_are_explicit_and_symlinks_rejected(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.write_bytes(b"SYNTHETIC")
    link = tmp_path / "reference-B.json"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="SYMLINK"):
        adapter._read_pinned(link, adapter.PROFILE_SHA256, "reference-B.json")
    with pytest.raises(ValueError, match="ABSOLUTE"):
        adapter._read_pinned(Path("reference-B.json"), adapter.PROFILE_SHA256, "reference-B.json")


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}', b'{"a":NaN}', b"[]"])
def test_strict_json(raw: bytes) -> None:
    with pytest.raises(ValueError):
        adapter._object(raw)


def test_candidate_metadata_validation_and_negative_controls() -> None:
    # One actual-shaped but wholly SYNTHETIC base, never the private 39-base roster.
    meta = {
        "SYNTHETIC-BASE": {
            "accepted_member_identity_sha256": "1" * 64,
            "historical_area_authority_row_sha256": "2" * 64,
        }
    }
    row = {
        "base_id": "SYNTHETIC-BASE",
        "season": "2025-2026",
        "window": "H7_PREFIX",
        "origin_date": "2025-08-04",
        "target_start": "2025-08-05",
        "target_end": "2025-08-11",
        "day_authority_sha256": "3" * 64,
        "target_dates_sha256": adapter._hash(
            canonical_bytes([f"2025-08-{d:02d}" for d in range(5, 12)])
        ),
        "status": "C0_CANDIDATE_ONLY",
    }
    row["candidate_id"] = adapter._candidate_hash(row, meta[row["base_id"]])
    support = adapter.SupportProposal(date(2025, 7, 1), date(2025, 8, 5), date(2026, 4, 15))
    adapter._validate_member(row, meta, 7, support)
    for field, bad in (
        ("candidate_id", "0" * 64),
        ("target_end", "2025-08-12"),
        ("base_id", "UNKNOWN"),
        ("status", "APPROVED"),
        ("target_dates_sha256", "0" * 64),
        ("window", "FULL_SEASON"),
        ("origin_date", "2025-08-04T00:00:00Z"),
        ("season", "2024-2025"),
    ):
        with pytest.raises(ValueError):
            adapter._validate_member({**row, field: bad}, meta, 7, support)


def test_support_is_explicit_complete_not_a_window_renormalization() -> None:
    valid = adapter.SupportProposal(date(2025, 7, 1), date(2025, 8, 5), date(2026, 4, 15))
    valid.validate()
    for bad in (
        replace(valid, season_start=date(2025, 8, 5)),
        replace(valid, end=date(2026, 4, 14)),
        replace(valid, start=date(2025, 8, 6)),
        replace(valid, status="APPROVED"),
    ):
        with pytest.raises(ValueError):
            bad.validate()


def test_csv_forbids_labels_duplicate_headers_and_extra_values() -> None:
    for raw in (b"base_id,harvest_kg\nSYNTHETIC,2\n", b"base_id,base_id\na,a\n", b"base_id\na,b\n"):
        with pytest.raises(ValueError):
            adapter._candidate_rows(raw)


def test_scope_remains_blocked_and_constants_are_pinned() -> None:
    boundary = adapter.boundary()
    assert boundary["formally_admitted_c0_count"] == 0
    assert boundary["unresolved_farms"] == 9
    assert boundary["strict_pit"] is False
    assert boundary["protocol_status"] == "PROPOSED_NOT_EFFECTIVE"
    assert (
        adapter.PROFILE_SHA256 == "a0a5cbc3c3ca5bd2b0b8860328eee73840499b38da89c11a104f83d02fd77c5b"
    )
    assert "labels" not in inspect.signature(adapter.rehearse_synthetic).parameters


def test_environment_cannot_enable_real_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("REAL_PREDICTION_EXECUTION_AUTHORIZED", "OWNER_AUTHORIZED", "PROTOCOL_EFFECTIVE"):
        monkeypatch.setenv(key, "true")
    with pytest.raises(PermissionError, match="REAL_PHASE_A_EXECUTION_DISABLED"):
        adapter.generate_real_predictions(owner_authorized=True, protocol_effective=True)


@pytest.fixture(scope="module")
def documents() -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    list[dict[str, str]],
    list[dict[str, str]],
    adapter.SupportProposal,
]:
    """Full-size entirely fictional roster; no private names/areas/profile values."""
    profile: dict[str, Any] = {
        "available_bins": list(range(42)),
        "fold_id": "B",
        "missing_bin_policy": "NEAREST_AVAILABLE_TRAIN_BIN_EARLIER_TIE",
        "profile_kg_per_mu_by_7_day_bin": {str(i): "1" for i in range(42)},
        "reference_id": "AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1",
        "train_row_set_hash": "c8b2da43696071648ac8280569fc2e28d7fa4b987f0a63b9edaae22122cc717e",
        "validation_labels_used": False,
    }
    bases = [
        {
            "base_id": f"SYNTHETIC-{i:02d}",
            "canonical_base_name": f"SYNTHETIC-{i:02d}",
            "productive_area_mu": "1",
            "active": True,
        }
        for i in range(39)
    ]
    registry: dict[str, Any] = {
        "version": "BASE_REGISTRY_V1",
        "bases": bases,
        "enrichment_hashes": {},
        "source_hash": adapter.SOURCE_AREA_SHA256,
    }
    registry["hash"] = adapter._compact_hash(registry)
    metadata = [
        {
            "base_id": b["base_id"],
            "base_name": b["canonical_base_name"],
            "accepted_member_identity_sha256": "1" * 64,
            "historical_area_authority_row_sha256": "2" * 64,
            "accepted_source_farm_count": 2 if i < 36 else 1,
            "area_unit": "mu",
            "season": "2025-2026",
            "eligible_days": 254,
            "historical_area_known_at": "NOT_PROVEN",
            "historical_area_structurally_valid": True,
            "full_admission_status": "BLOCKED",
            "residual_unresolved_farm_impact": "NOT_PROVEN_UNAFFECTED_NOT_LOCALLY_ATTRIBUTABLE",
        }
        for i, b in enumerate(bases)
    ]
    sidecar: dict[str, Any] = {
        "base_metadata": metadata,
        "status": "C0_CANDIDATE_ONLY",
        "source_id": "SOURCE_002",
        "source_sha256": CandidateScope().source_sha256,
        "global_blockers": ["UNRESOLVED_NINE_FARMS_SCOPE_NOT_PROVEN"],
        "origin_time_status": "NOT_REGISTERED_DATE_ONLY_NOT_HISTORICAL_ISSUANCE",
        "physical_basis": "SOURCE002_RECORDED_MARKETABLE_NET_WEIGHT_PROFILE_EQUIVALENCE_NOT_PROVEN",
    }
    windows: list[list[dict[str, str]]] = []
    for n in (7, 15):
        rows = []
        for base in metadata:
            for i in range(254 - n + 1):
                start = adapter.START + timedelta(days=i)
                row: dict[str, str] = {
                    "base_id": str(base["base_id"]),
                    "season": "2025-2026",
                    "window": "H7_PREFIX" if n == 7 else "H15_LOCAL",
                    "origin_date": (start - timedelta(days=1)).isoformat(),
                    "target_start": start.isoformat(),
                    "target_end": (start + timedelta(days=n - 1)).isoformat(),
                    "target_dates_sha256": adapter._hash(
                        canonical_bytes([(start + timedelta(days=k)).isoformat() for k in range(n)])
                    ),
                    "day_authority_sha256": "3" * 64,
                    "status": "C0_CANDIDATE_ONLY",
                }
                row["candidate_id"] = adapter._candidate_hash(row, base)
                rows.append(row)
        windows.append(rows)
    return (
        profile,
        registry,
        sidecar,
        windows[0],
        windows[1],
        adapter.SupportProposal(date(2025, 7, 1), adapter.START, adapter.END),
    )


def test_full_size_synthetic_structure_is_not_formal_c0(documents: Any) -> None:
    result = adapter._validate_documents(*documents)
    assert result == {
        "h7_candidate_count": 9672,
        "h15_candidate_count": 9360,
        "base_count": 39,
        "status": "VALIDATED_CANDIDATE_ONLY_EXECUTION_BLOCKED",
    }
    # This fixture's bytes must NOT be accepted as the real Registry.
    assert documents[1]["hash"] != adapter.REGISTRY_PAYLOAD_HASH


@pytest.mark.parametrize(
    "defect",
    [
        "missing",
        "duplicate",
        "reorder",
        "scope",
        "physical",
        "area",
        "base",
        "fold",
        "profile_negative",
        "future_known_at",
        "false_area_authority",
        "extra_label_field",
    ],
)
def test_complete_set_negative_controls(documents: Any, defect: str) -> None:
    p, r, m, h7, h15, s = deepcopy(documents)
    if defect == "missing":
        h7.pop()
    elif defect == "duplicate":
        h7[-1] = h7[0]
    elif defect == "reorder":
        h7[0], h7[1] = h7[1], h7[0]
    elif defect == "scope":
        m["global_blockers"] = []
    elif defect == "physical":
        m["physical_basis"] = "PROVEN_EQUIVALENT"
    elif defect == "area":
        r["bases"][0]["productive_area_mu"] = "0"
        r["hash"] = adapter._compact_hash({k: v for k, v in r.items() if k != "hash"})
    elif defect == "base":
        m["base_metadata"][0]["base_id"] = "UNKNOWN"
    elif defect == "fold":
        p["fold_id"] = "A"
    elif defect == "profile_negative":
        p["profile_kg_per_mu_by_7_day_bin"]["0"] = "-1"
    elif defect == "future_known_at":
        m["base_metadata"][0]["historical_area_known_at"] = "PROVEN"
    elif defect == "false_area_authority":
        m["base_metadata"][0]["historical_area_structurally_valid"] = False
    else:
        m["harvest_kg"] = "SYNTHETIC-LABEL-NOT-ALLOWED"
    with pytest.raises(ValueError):
        adapter._validate_documents(p, r, m, h7, h15, s)


def test_window_values_are_slices_of_one_full_support() -> None:
    result = adapter.rehearse_synthetic()
    for member in result["members"]:
        n = len(member["daily_dates"])
        assert member["baseline_daily"] == [r["kg"] for r in member["full_baseline_daily"][:n]]
        assert member["candidate_daily"] == [r["kg"] for r in member["full_candidate_daily"][:n]]
        assert len(member["full_baseline_daily"]) == len(member["full_candidate_daily"]) == 21
    grouped: dict[str, list[dict[str, Any]]] = {}
    for member in result["members"]:
        grouped.setdefault(member["base_id"], []).append(member)
    for members in grouped.values():
        assert members[0]["full_candidate_daily"] == members[1]["full_candidate_daily"]


def test_real_file_review_is_read_only_and_has_no_auth_override(tmp_path: Path) -> None:
    paths = adapter.FrozenInputPaths(
        *(
            tmp_path / n
            for n in (
                "reference-B.json",
                "base-registry-v1.json",
                "h7-candidates.csv",
                "h15-candidates.csv",
                "base-admission-metadata.json",
            )
        )
    )
    paths.profile.write_bytes(b"SYNTHETIC-NOT-THE-PINNED-PROFILE")
    before = paths.profile.read_bytes()
    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        adapter.validate_frozen_inputs(
            paths, support=adapter.SupportProposal(date(2025, 7, 1), adapter.START, adapter.END)
        )
    assert paths.profile.read_bytes() == before
    assert set(inspect.signature(adapter.validate_frozen_inputs).parameters) == {"paths", "support"}


def test_synthetic_seal_detects_algorithm_source_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    first = adapter.rehearse_synthetic()
    read_bytes = Path.read_bytes

    def changed_source(path: Path) -> bytes:
        raw = read_bytes(path)
        return (
            raw + b"\n# SYNTHETIC source drift probe\n"
            if path.name == "v019_daily_curve.py"
            else raw
        )

    monkeypatch.setattr(Path, "read_bytes", changed_source)
    assert adapter.rehearse_synthetic()["seal_sha256"] != first["seal_sha256"]
    with pytest.raises(ValueError, match="SEAL_MISMATCH"):
        adapter.verify_synthetic_seal(first)


@pytest.mark.parametrize("field", ["c0_sha256", "members", "formally_admitted_c0_count"])
def test_rehashed_forgery_is_not_an_accepted_seal(field: str) -> None:
    result = adapter.rehearse_synthetic()
    adapter.verify_synthetic_seal(result)
    result[field] = [] if field == "members" else "SYNTHETIC-TAMPERING"
    result["seal_sha256"] = adapter._hash(
        canonical_bytes({k: v for k, v in result.items() if k != "seal_sha256"})
    )
    with pytest.raises(ValueError, match="SEAL_MISMATCH"):
        adapter.verify_synthetic_seal(result)
