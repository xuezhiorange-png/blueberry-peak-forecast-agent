"""Hermetic Owner-scope R2 regression; no private records or quantities."""

from __future__ import annotations

import inspect
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from backend.research import v019_owner_scope_adapter as adapter
from backend.research import v019_real_phase_a_adapter as r1
from backend.research.v019_daily_curve import canonical_bytes
from backend.tests.area_yield import test_v0_19_real_phase_a_adapter as old_tests

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def test_versioned_scope_does_not_rewrite_r1() -> None:
    assert adapter.boundary()["matched_farms"] == 80
    assert adapter.boundary()["research_excluded_farms"] == 4
    assert adapter.boundary()["unresolved_in_research_scope"] == 0
    assert r1.boundary()["unresolved_farms"] == 9
    assert r1.H7_SHA256 != adapter.H7_SHA256
    assert adapter.boundary()["formally_admitted_c0_count"] == 0


@pytest.mark.parametrize("approval", [None, True, {"owner_authorized": True}, "APPROVED"])
def test_real_generation_always_rejected(approval: object) -> None:
    with pytest.raises(PermissionError, match="REAL_PHASE_A_EXECUTION_DISABLED"):
        adapter.generate_real_predictions(approval)


@pytest.fixture(scope="module")
def documents() -> tuple[Any, ...]:
    profile, registry, *_ = inspect.unwrap(old_tests.documents)()
    special = list(adapter.ZERO_CHANGES)
    names = {bid: name for bid, name in adapter.BINDINGS.values()}
    for i, bid in enumerate(special):
        registry["bases"][i].update(base_id=bid, canonical_base_name=names[bid])
    registry["hash"] = r1._compact_hash({k: v for k, v in registry.items() if k != "hash"})
    mapping = []

    def member(name: str, bid: str, new: bool = False, excluded: bool = False) -> None:
        mapping.append(
            {
                "season": "2025-2026",
                "source_farm_label": name,
                "source_identity_sha256": r1._hash(name.encode()),
                "original_global_status": "UNRESOLVED" if new or excluded else "EXACT",
                "original_base_id": "" if new or excluded else bid,
                "research_status": "OWNER_RESEARCH_EXCLUDE_ONLY"
                if excluded
                else "OWNER_RESEARCH_INCLUDE"
                if new
                else "REUSE_FROZEN_ACCEPTED_IDENTITY",
                "research_base_id": bid,
                "research_base_name": names.get(bid, bid),
                "owner_decision_sha256": adapter.DECISION_SHA256,
                "source_sha256": adapter.SOURCE_SHA256,
            }
        )

    for i, b in enumerate(registry["bases"]):
        for j in range(1 if i < 3 else 2):
            member(f"SYNTHETIC-FARM-{i}-{j}", b["base_id"])
    for name, (bid, _) in adapter.BINDINGS.items():
        member(name, bid, new=True)
    for name in sorted(adapter.EXCLUDED):
        member(name, "", excluded=True)
    bases = []
    for b in registry["bases"]:
        mm = sorted(
            (r for r in mapping if r["research_base_id"] == b["base_id"]),
            key=lambda r: r["source_identity_sha256"],
        )
        bases.append(
            {
                "base_id": b["base_id"],
                "base_name": b["canonical_base_name"],
                "member_count": len(mm),
                "member_identity_sha256": r1._hash(canonical_bytes(mm)),
                "historical_area_authority_row_sha256": "2" * 64,
                "area_unit": "mu",
                "historical_area_known_at": "NOT_PROVEN",
                "area_parity": True,
            }
        )
    days, previous = [], []
    zeros = 3490
    for b in bases:
        for i in range(254):
            changed = i < adapter.ZERO_CHANGES.get(b["base_id"], 0)
            zero = not changed and zeros > 0
            zeros -= int(zero)
            day = str(r1.START + timedelta(days=i))
            status = "CONFIRMED_ZERO" if zero else "KNOWN_MAPPED_SUBTOTAL"
            days.append(
                {
                    "base_id": b["base_id"],
                    "date": day,
                    "new_quantity_status": status,
                    "new_completeness_status": "AUTHORIZED_ZERO"
                    if zero
                    else "COMPLETE_MAPPED_MEMBERS",
                    "zero_applied": str(zero).lower(),
                    "partial_resolved": str(not zero and b["member_count"] > 1).lower(),
                    "source_row_count": "0" if zero else "1",
                    "member_expected_count": str(b["member_count"]),
                    "member_observed_count": "0" if zero else "1",
                    "identity_unresolved_conflict": "false",
                    "authority_eligible_daily": "true",
                    "source_coverage_status": "VERIFIED_SEASON_SOURCE_HASH",
                }
            )
            previous.append(
                {
                    "base_id": b["base_id"],
                    "date": day,
                    "old_status": "CONFIRMED_ZERO" if changed else status,
                }
            )
    meta = {
        "scope_version": adapter.SCOPE_VERSION,
        "source_sha256": adapter.SOURCE_SHA256,
        "decision": adapter._decision(),
        "decision_sha256": adapter.DECISION_SHA256,
        "mapping": mapping,
        "bases": bases,
        "days": days,
        "previous_day_statuses": previous,
        "source_counts": dict(adapter.COUNTS),
        "limitations": dict(adapter.LIMITATIONS),
    }
    byday = {(r["base_id"], r["date"]): r for r in days}
    windows = []
    for n in (7, 15):
        rr = []
        for b in sorted(bases, key=lambda b: b["base_id"]):
            for i in range(255 - n):
                start = r1.START + timedelta(days=i)
                dates = [str(start + timedelta(days=j)) for j in range(n)]
                r = {
                    "base_id": b["base_id"],
                    "season": "2025-2026",
                    "window": "H7_PREFIX" if n == 7 else "H15_LOCAL",
                    "origin_date": str(start - timedelta(days=1)),
                    "target_start": str(start),
                    "target_end": dates[-1],
                    "target_dates_sha256": r1._hash(canonical_bytes(dates)),
                    "day_authority_sha256": r1._hash(
                        canonical_bytes([byday[b["base_id"], d] for d in dates])
                    ),
                    "status": "C0_CANDIDATE_ONLY",
                }
                # Construct independent expected serialization, not a call to the validator.
                r["candidate_id"] = r1._hash(
                    canonical_bytes(
                        {
                            **r,
                            "source_sha256": adapter.SOURCE_SHA256,
                            "research_scope_decision_sha256": adapter.DECISION_SHA256,
                            "base_members_sha256": b["member_identity_sha256"],
                            "area_authority_row_sha256": b["historical_area_authority_row_sha256"],
                        }
                    )
                )
                rr.append(r)
        windows.append(rr)
    return (
        profile,
        registry,
        meta,
        *windows,
        r1.SupportProposal(date(2025, 7, 1), date(2025, 7, 1), r1.END),
    )


def test_full_synthetic_owner_set_and_repeat(documents: Any) -> None:
    first = adapter._review(*documents)
    assert first == adapter._review(*documents)
    assert first["base_day_count"] == 9906
    assert first["observed_base_days"] == 6416
    assert first["authorized_zero_base_days"] == 3490
    assert first["zero_changes_by_base"] == adapter.ZERO_CHANGES
    assert (first["h7_candidate_count"], first["h15_candidate_count"]) == (9672, 9360)
    assert first["real_execution_available"] is False


@pytest.mark.parametrize(
    "defect",
    [
        "mapping",
        "exclusion",
        "global_identity",
        "member_hash",
        "count_75",
        "area_known_at",
        "physical",
        "formal_c0",
        "protocol",
        "label_column",
        "missing_day",
        "duplicate_day",
        "unresolved_day",
        "missing_coverage",
        "zero_change",
        "missing_candidate",
        "duplicate_candidate",
        "reorder",
        "day_hash",
        "source_hash",
        "candidate_status",
        "target_date",
        "fold",
    ],
)
def test_owner_set_rejects_drift(documents: Any, defect: str) -> None:
    p, r, m, h7, h15, s = deepcopy(documents)
    if defect == "mapping":
        next(x for x in m["mapping"] if x["source_farm_label"] in adapter.BINDINGS)[
            "research_base_name"
        ] = "盘龙基地"
    elif defect == "exclusion":
        next(x for x in m["mapping"] if x["source_farm_label"] in adapter.EXCLUDED)[
            "research_status"
        ] = "OWNER_RESEARCH_INCLUDE"
    elif defect == "global_identity":
        next(x for x in m["mapping"] if x["source_farm_label"] in adapter.EXCLUDED)[
            "original_global_status"
        ] = "EXCLUDED"
    elif defect == "member_hash":
        m["bases"][0]["member_identity_sha256"] = "0" * 64
    elif defect == "count_75":
        m["source_counts"]["matched_farms"] = 75
    elif defect == "area_known_at":
        m["bases"][0]["historical_area_known_at"] = "PROVEN"
    elif defect in ("physical", "formal_c0", "protocol"):
        key = {
            "physical": "physical_basis_equivalence",
            "formal_c0": "formally_admitted_c0_count",
            "protocol": "retrospective_protocol_effective",
        }[defect]
        m["limitations"][key] = True
    elif defect == "label_column":
        m["days"][0]["harvest_kg"] = "SYNTHETIC-NOT-A-LABEL-INPUT"
    elif defect == "missing_day":
        m["days"].pop()
    elif defect == "duplicate_day":
        m["days"][-1] = m["days"][0]
    elif defect == "unresolved_day":
        m["days"][0]["identity_unresolved_conflict"] = "true"
    elif defect == "missing_coverage":
        m["days"][0]["source_coverage_status"] = "CANONICAL_ROW_MISSING"
    elif defect == "zero_change":
        next(x for x in m["previous_day_statuses"] if x["base_id"] in adapter.ZERO_CHANGES)[
            "old_status"
        ] = "KNOWN_MAPPED_SUBTOTAL"
    elif defect == "missing_candidate":
        h7.pop()
    elif defect == "duplicate_candidate":
        h7[-1] = h7[0]
    elif defect == "reorder":
        h7[0], h7[1] = h7[1], h7[0]
    elif defect == "day_hash":
        h15[0]["day_authority_sha256"] = "0" * 64
    elif defect == "source_hash":
        m["source_sha256"] = "0" * 64
    elif defect == "candidate_status":
        h7[0]["status"] = "APPROVED"
    elif defect == "target_date":
        h7[0]["target_end"] = "2025-08-12"
    else:
        p["fold_id"] = "A"
    with pytest.raises(ValueError):
        adapter._review(p, r, m, h7, h15, s)


def test_public_entry_rejects_unpinned_files_before_schema(tmp_path: Path) -> None:
    p = tmp_path / "reference-B.json"
    p.write_bytes(b"SYNTHETIC-NOT-A-PINNED-FILE")
    paths = adapter.OwnerScopeInputPaths(
        p,
        *(
            tmp_path / name
            for name in (
                "base-registry-v1.json",
                "h7-candidates.csv",
                "h15-candidates.csv",
                "owner-scope-metadata-r2.json",
            )
        ),
    )
    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        adapter.validate_owner_scope_inputs(
            paths, support=r1.SupportProposal(date(2025, 7, 1), r1.START, r1.END)
        )
    assert p.read_bytes() == b"SYNTHETIC-NOT-A-PINNED-FILE"


def test_refusal_does_not_open_data_or_call_prediction(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("DATA_OR_PREDICTION_TOUCHED")

    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(r1, "generate_candidate", forbidden)
    monkeypatch.setenv("REAL_PREDICTION_EXECUTION_AUTHORIZED", "true")
    with pytest.raises(PermissionError):
        adapter.generate_real_predictions(owner_authorized=True, formal_c0=True)


@pytest.mark.parametrize(
    "filename,expected",
    [
        ("reference-B.json", r1.PROFILE_SHA256),
        ("base-registry-v1.json", r1.REGISTRY_SHA256),
        ("h7-candidates.csv", adapter.H7_SHA256),
        ("h15-candidates.csv", adapter.H15_SHA256),
        ("owner-scope-metadata-r2.json", adapter.METADATA_SHA256),
    ],
)
def test_each_fixed_object_rejects_hash_drift(tmp_path: Path, filename: str, expected: str) -> None:
    path = tmp_path / filename
    path.write_bytes(b"SYNTHETIC-HASH-DRIFT")
    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        r1._read_pinned(path, expected, filename)


def test_review_cannot_generate_or_score(documents: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.research import v019_replay_preparation, v019_retrospective_entry

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("PREDICTION_OR_LABEL_ACCESS")

    for module, names in (
        (r1, ("generate_candidate", "generate_synthetic", "register_synthetic")),
        (v019_retrospective_entry, ("score_synthetic", "demo_labels")),
        (v019_replay_preparation, ("demo_labels",)),
    ):
        for name in names:
            monkeypatch.setattr(module, name, forbidden)
    result = adapter._review(*documents)
    assert result["real_execution_available"] is False
