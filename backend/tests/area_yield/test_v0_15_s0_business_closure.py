"""Synthetic-only business evidence projection; never connect to a real database."""

from copy import deepcopy

import pytest

from scripts.audit_v0_15_s0_business_closure import (
    PINS,
    build_reports,
    classify_quantity,
    close_identity,
    project_pair,
    validate_business_public,
    validate_season,
    write_reports,
)


def pair() -> tuple[dict, dict]:
    common = {"base_id": "base_test", "season": "2024-2025", "date": "2025-01-01"}
    original = dict(
        common,
        quantity_status="UNKNOWN",
        quantity_completeness_status="UNKNOWN_NOT_ZERO_FILLED",
        mapped_observed_subtotal_kg="null",
        source_sha256="s" * 64,
    )
    overlay = dict(
        common,
        old_quantity_status="UNKNOWN",
        old_completeness_status="UNKNOWN_NOT_ZERO_FILLED",
        old_quantity_kg="null",
        new_quantity_status="UNKNOWN",
        new_completeness_status="UNKNOWN_NOT_ZERO_FILLED",
        new_quantity_kg="null",
        zero_applied="false",
        partial_resolved="false",
        resolution_reason="NO_ACCEPTED_SOURCE_IDENTITY_FOR_BASE_SEASON",
    )
    return original, overlay


@pytest.mark.parametrize("value", [None, "", "null"])
def test_unknown_remains_null(value: object) -> None:
    assert classify_quantity("UNKNOWN", "UNKNOWN_NOT_ZERO_FILLED", value) == ("UNKNOWN", None)


@pytest.mark.parametrize(
    "status,completeness,value,expected",
    [
        ("CONFIRMED_ZERO", "AUTHORIZED_ZERO", "0", "REAL_ZERO"),
        ("KNOWN_MAPPED_SUBTOTAL", "COMPLETE_MAPPED_MEMBERS", "1.234", "VALID_OBSERVED"),
        ("KNOWN_MAPPED_SUBTOTAL", "COMPLETE_MAPPED_MEMBERS", "0", "REAL_ZERO"),
        ("KNOWN_MAPPED_SUBTOTAL", "PARTIAL_KNOWN_SUBTOTAL", "3", "PARTIAL_SUBTOTAL"),
        ("UNKNOWN", "UNKNOWN_NOT_ZERO_FILLED", "0", "INVALID"),
        ("CONFIRMED_ZERO", "AUTHORIZED_ZERO", "3", "INVALID"),
        ("KNOWN_MAPPED_SUBTOTAL", "COMPLETE_MAPPED_MEMBERS", "-1", "INVALID"),
        ("KNOWN_MAPPED_SUBTOTAL", "COMPLETE_MAPPED_MEMBERS", "NaN", "INVALID"),
        ("KNOWN_MAPPED_SUBTOTAL", "COMPLETE_MAPPED_MEMBERS", "Infinity", "INVALID"),
        ("UNKNOWN", "wrong", "null", "INVALID"),
    ],
)
def test_state_not_coerced(status: str, completeness: str, value: str, expected: str) -> None:
    assert classify_quantity(status, completeness, value)[0] == expected


def test_pair_checked_not_count_divided_and_inputs_immutable() -> None:
    original, overlay = pair()
    before = deepcopy((original, overlay))
    row = project_pair(original, overlay, ["e1", "e2"], ["a", "b"])
    assert row["record_state"] == "UNKNOWN" and row["quantity_kg"] is None
    assert row["source_evidence_ids"] == ["e1", "e2"]
    assert (original, overlay) == before


@pytest.mark.parametrize(
    "field", ["old_quantity_status", "old_completeness_status", "old_quantity_kg"]
)
def test_overlay_lineage_conflict(field: str) -> None:
    original, overlay = pair()
    overlay[field] = "tampered"
    assert project_pair(original, overlay, [], [])["record_state"] == "CONFLICTING"


def test_authorized_zero_transition_only() -> None:
    original, overlay = pair()
    overlay.update(
        new_quantity_status="CONFIRMED_ZERO",
        new_completeness_status="AUTHORIZED_ZERO",
        new_quantity_kg="0",
        zero_applied="true",
        resolution_reason="VERIFIED_SEASON_SOURCE_HAS_NO_BASE_DAY_HARVEST_ROW",
    )
    assert project_pair(original, overlay, [], [])["record_state"] == "REAL_ZERO"
    overlay["zero_applied"] = "false"
    assert project_pair(original, overlay, [], [])["record_state"] == "CONFLICTING"


def test_nonzero_quantity_change_is_conflict() -> None:
    original, overlay = pair()
    original.update(
        quantity_status="KNOWN_MAPPED_SUBTOTAL",
        quantity_completeness_status="PARTIAL_KNOWN_SUBTOTAL",
        mapped_observed_subtotal_kg="10",
    )
    overlay.update(
        old_quantity_status="KNOWN_MAPPED_SUBTOTAL",
        old_completeness_status="PARTIAL_KNOWN_SUBTOTAL",
        old_quantity_kg="10",
        new_quantity_status="KNOWN_MAPPED_SUBTOTAL",
        new_completeness_status="COMPLETE_MAPPED_MEMBERS",
        new_quantity_kg="11",
        partial_resolved="true",
        resolution_reason="KNOWN_MISSING_MEMBERS_HAVE_NO_HARVEST_ROWS",
    )
    assert project_pair(original, overlay, [], [])["record_state"] == "CONFLICTING"


def test_missing_version_is_not_zero() -> None:
    original, _ = pair()
    assert project_pair(original, None, ["e1"], ["a"])["record_state"] == "MISSING"


def test_no_fuzzy_or_candidate_parent_resolution() -> None:
    row = {"season": "2024-2025", "source_farm_label": "Alias", "mapping_status": "UNRESOLVED"}
    proposed = [
        {
            "season": "2024-2025",
            "source_farm_label": "Alias",
            "candidate_base_id": "base_test",
            "match_type": "EXACT",
        }
    ]
    assert close_identity(row, proposed, [], [])["closure_status"] == "UNRESOLVED"


@pytest.mark.parametrize("season", ["2026-2027", "2022-2023", ""])
def test_unauthorized_season_rejected(season: str) -> None:
    with pytest.raises(ValueError, match="UNAUTHORIZED_SEASON"):
        validate_season(season)


@pytest.mark.parametrize(
    "field", ["quantity_kg", "actual_quantity_kg", "credentials", "coordinates"]
)
def test_public_sensitive_field_rejected(field: str) -> None:
    with pytest.raises(ValueError, match="PUBLIC_"):
        validate_business_public({"nested": [{field: "private"}]})


def test_public_private_path_rejected() -> None:
    with pytest.raises(ValueError, match="PUBLIC_PRIVATE_PATH"):
        validate_business_public({"source": "/Users/operator/private-input"})


def test_new_explicit_identity_cannot_be_ignored() -> None:
    row = {"season": "2024-2025", "source_farm_label": "Alias", "mapping_status": "UNRESOLVED"}
    newer = [
        {
            "season": "2024-2025",
            "source_label": "Alias",
            "proposed_base_id": "base_test",
            "proposed_resolution_status": "RESOLVED",
        }
    ]
    with pytest.raises(ValueError, match="NEW_EXPLICIT_IDENTITY_EVIDENCE"):
        close_identity(row, [], [], newer)


def snapshot_fixture() -> tuple[dict, dict]:
    original, overlay = pair()

    def envelope(source: str, payload: dict) -> dict:
        return dict(
            source=source,
            source_hash=PINS[source],
            source_row_number=2,
            season="2024-2025",
            base_id="base_test",
            payload=payload,
            imported_at="2026-10-05T00:00:00Z",
        )

    area = dict(
        area_authority_id="area_test",
        business_confirmation_id="retrospective",
        original_area_source_sha256="a" * 64,
        business_confirmation_sha256="b" * 64,
    )
    identity = dict(
        season="2024-2025",
        source_farm_label="Base",
        mapping_status="EXACT",
        canonical_base_id="base_test",
    )
    snapshot = dict(
        transaction_read_only="on",
        transaction_end="ROLLBACK",
        records={
            "audit.source_manifest": [dict(source=k, source_hash=v) for k, v in PINS.items()],
            "label_vault.harvest_records": [
                envelope("canonical_daily", original),
                envelope("zero_overlay", overlay),
            ],
            "authority.area_records": [envelope("season_area", area)],
            "authority.identity_records": [envelope("identity", identity)],
            "authority.subfarm_parent_records": [],
        },
    )
    supplementary = dict(
        db_local_source_payload_parity=True,
        s6_policy={"input_authorities": {"s1_daily_ledger_sha256": PINS["canonical_daily"]}},
        supplementary_sources={"closure_overlay": {"row_count": 0}},
        area_metadata={"base_test:2024-2025": dict(available_at=None, historical_known_at=None)},
        historical_mapping=[],
        identity_resolutions=[],
        area_commit="synthetic retrospective",
        area_search_source_ids=["synthetic"],
        identity_search_source_hashes={},
    )
    return snapshot, supplementary


def test_full_projection_is_evidence_bound_and_deterministic(tmp_path) -> None:
    snapshot, supplementary = snapshot_fixture()
    reports, logical = build_reports(snapshot, supplementary, [])
    assert len(logical) == 1  # Not a prefilled production count.
    assert reports["area-pit-evidence-reclassification"]["tier_c_count"] == 1
    assert reports["identity-authority-closure-report"]["strict_count"] == 0
    assert reports["base-season-training-readiness-matrix"]["training_candidate_count"] == 0
    validate_business_public(reports)
    write_reports(tmp_path / "a", reports, logical)
    write_reports(tmp_path / "b", reports, logical)
    for p in (tmp_path / "a").iterdir():
        assert p.read_bytes() == (tmp_path / "b" / p.name).read_bytes()
    with pytest.raises(ValueError, match="OUTPUT_EXISTS_IMMUTABLE"):
        write_reports(tmp_path / "a", reports, logical)


@pytest.mark.parametrize("mutation", ["read_write", "bad_hash", "bad_season", "bad_envelope"])
def test_snapshot_failure_closed(mutation: str) -> None:
    snapshot, supplementary = snapshot_fixture()
    if mutation == "read_write":
        snapshot["transaction_read_only"] = "off"
    elif mutation == "bad_hash":
        snapshot["records"]["audit.source_manifest"][0]["source_hash"] = "tampered"
    elif mutation == "bad_season":
        snapshot["records"]["label_vault.harvest_records"][0]["season"] = "2026-2027"
    else:
        snapshot["records"]["label_vault.harvest_records"][0]["base_id"] = "wrong"
    with pytest.raises(ValueError):
        build_reports(snapshot, supplementary, [])
