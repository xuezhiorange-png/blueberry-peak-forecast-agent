"""Synthetic acceptance of read-only asset audit, not dataset reconstruction."""

from copy import deepcopy

import pytest

from scripts.audit_v0_15_s0_existing_assets import (
    admit_predictor,
    attach_audit_metadata,
    authorize_label_unlock,
    classify_readiness,
    coverage_matrix,
    digest,
    identity_conflicts,
    owner_gaps,
    validate_archive_claim,
    validate_public,
)


def complete() -> dict[str, str]:
    return dict.fromkeys(
        ("harvest", "area", "weather", "identity", "season", "variety", "management"),
        "AVAILABLE_VALID",
    )


def test_unknown_and_missing_are_not_valid_zero() -> None:
    row = complete()
    row["harvest"] = "UNKNOWN_REQUIRES_REVIEW"
    assert classify_readiness(row) == "BLOCKED_BY_HARVEST"
    row["harvest"] = "MISSING"
    assert classify_readiness(row) == "BLOCKED_BY_HARVEST"


def test_complete_coverage_is_audit_readiness_not_cohort_selection() -> None:
    assert classify_readiness(complete()) == "TRAINING_READY"
    row = complete()
    row["weather"] = "AVAILABLE_PARTIAL"
    assert classify_readiness(row) == "TRAINING_READY_WITH_LIMITATION"


def test_multiple_gates_and_unknown_applicability() -> None:
    row = complete()
    row.update(area="MISSING", identity="CONFLICTING")
    assert classify_readiness(row) == "BLOCKED_BY_MULTIPLE_AUTHORITIES"
    row.update(area="AVAILABLE_VALID", identity="AVAILABLE_VALID", season="MISSING")
    assert classify_readiness(row) == "BLOCKED_BY_SEASON"


def test_no_history_not_silently_new_base() -> None:
    row = complete()
    row["harvest"] = "MISSING"
    assert classify_readiness(row) == "BLOCKED_BY_HARVEST"
    assert classify_readiness(row, new_base_no_history=True) == "NEW_BASE_NO_HISTORY"


def test_dense_universe_includes_unregistered_entities() -> None:
    entities = [{"entity_id": "base_a"}, {"entity_id": "unresolved_b"}]
    facts = {("base_a", "2023-2024"): complete()}
    rows = coverage_matrix(entities, ["2023-2024", "2024-2025"], facts)
    assert len(rows) == 4
    assert {r["entity_id"] for r in rows} == {"base_a", "unresolved_b"}
    assert rows[-1]["harvest"] == "UNKNOWN_REQUIRES_REVIEW"


def test_duplicate_ids_fail_closed() -> None:
    with pytest.raises(ValueError, match="DUPLICATE_ENTITY"):
        coverage_matrix([{"entity_id": "a"}, {"entity_id": "a"}], ["2023-2024"], {})


def test_fact_outside_universe_is_not_silently_dropped() -> None:
    with pytest.raises(ValueError, match="FACT_OUTSIDE_AUDIT_UNIVERSE"):
        coverage_matrix([{"entity_id": "a"}], ["2023-2024"], {("b", "2023-2024"): complete()})


def test_unknown_domain_is_rejected() -> None:
    with pytest.raises(ValueError, match="UNKNOWN_ASSET_DOMAIN"):
        coverage_matrix(
            [{"entity_id": "a"}], ["2023-2024"], {("a", "2023-2024"): {"guess": "MISSING"}}
        )


def test_unobserved_cell_is_applicability_not_seven_missing_sources() -> None:
    row = {
        "entity_id": "a",
        "season_id": "2023-2024",
        **dict.fromkeys(complete(), "UNKNOWN_REQUIRES_REVIEW"),
    }
    gaps = owner_gaps([row], ["searched_catalog"])
    assert len(gaps) == 1
    assert gaps[0]["missing_field"] == "source_label_season_applicability"
    assert gaps[0]["blocking_or_optional"] == "OPTIONAL"


def test_no_fuzzy_identity_merge() -> None:
    conflicts = identity_conflicts(
        [
            {"entity_id": "a", "name": "Farm"},
            {"entity_id": "b", "name": "Farm"},
            {"entity_id": "a", "name": "Old Farm"},
        ]
    )
    assert {c["kind"] for c in conflicts} == {"SAME_NAME_MULTIPLE_IDS", "ID_NAME_VARIATION"}


def test_gap_requires_search_evidence_not_upload_request() -> None:
    row = {"entity_id": "a", "season_id": "2023-2024", **complete()}
    row["area"] = "UNKNOWN_REQUIRES_REVIEW"
    gaps = owner_gaps([row], ["area_catalog", "confirmed_area_overlay"])
    gap = next(g for g in gaps if g["missing_field"] == "area")
    assert gap["searched_sources"]
    assert gap["owner_action"] == "REVIEW_EXISTING_AUTHORITY_FIRST"
    assert gap["blocking_or_optional"] == "BLOCKING"
    assert gap["minimum_required_value"]


def test_schema_only_events_are_not_real_records() -> None:
    row = complete()
    row["management"] = "UNKNOWN_REQUIRES_REVIEW"
    assert classify_readiness(row) == "TRAINING_READY_WITH_LIMITATION"
    gaps = owner_gaps([{"entity_id": "a", "season_id": "s", **row}], ["templates"])
    assert gaps[0]["blocking_or_optional"] == "OPTIONAL"


@pytest.mark.parametrize(
    "key,value",
    [
        ("latitude", 1),
        ("predicted_daily_kg", "1"),
        ("source", "/Users/operator/private.csv"),
        ("coefficients", [1]),
        ("weather_values", [1]),
    ],
)
def test_public_privacy(key: str, value: object) -> None:
    with pytest.raises(ValueError, match="PUBLIC_PRIVATE"):
        validate_public({key: value})


def test_audit_does_not_mutate_input() -> None:
    facts = {("a", "s"): complete()}
    before = deepcopy(facts)
    coverage_matrix([{"entity_id": "a"}], ["s"], facts)
    assert before == facts


def test_unknown_status_rejected() -> None:
    row = complete()
    row["area"] = "ASSUMED_FROM_REGISTRY"
    with pytest.raises(ValueError, match="UNKNOWN_ASSET_STATUS"):
        classify_readiness(row)


def test_event_time_is_not_available_time() -> None:
    with pytest.raises(ValueError, match="AVAILABLE_AFTER_CUTOFF"):
        admit_predictor(
            {
                "lane": "PREDICTOR_ZONE",
                "role": "AREA",
                "event_time": "2024-03-01T00:00:00+00:00",
                "available_at": "2024-03-20T00:00:00+00:00",
            },
            "2024-03-10T00:00:00+00:00",
        )


@pytest.mark.parametrize(
    "role",
    [
        "FUTURE_HARVEST",
        "FUTURE_TOTAL",
        "FUTURE_PEAK",
        "ERA5_FUTURE",
        "REANALYSIS_FUTURE",
        "OBSERVED_FUTURE_WEATHER",
    ],
)
def test_future_answer_and_weather_rejected(role: str) -> None:
    with pytest.raises(ValueError, match="TARGET_LEAKAGE"):
        admit_predictor({"lane": "PREDICTOR_ZONE", "role": role}, "2025-01-15T00:00:00+00:00")


def test_issue_time_alone_does_not_prove_historical_availability() -> None:
    with pytest.raises(ValueError, match="HISTORICAL_AVAILABILITY_NOT_ESTABLISHED"):
        admit_predictor(
            {
                "lane": "PREDICTOR_ZONE",
                "role": "ARCHIVED_OPERATIONAL_FORECAST",
                "issue_time": "2025-01-15T00:00:00+00:00",
            },
            "2025-01-15T09:00:00+00:00",
        )


def test_label_vault_is_not_predictor_zone() -> None:
    with pytest.raises(ValueError, match="LABEL_ZONE_DENIED"):
        admit_predictor({"lane": "LABEL_VAULT"}, "2025-01-15T09:00:00+00:00")


def test_real_archive_needs_provenance_and_valid_issue_order() -> None:
    feature = dict(
        lane="PREDICTOR_ZONE",
        role="ARCHIVED_OPERATIONAL_FORECAST",
        available_at="2025-01-15T07:00:00+00:00",
        issue_time="2025-01-15T00:00:00+00:00",
        valid_time="2025-01-16T00:00:00+00:00",
        model="IFS",
        cycle="49r1",
        step=24,
        parameter="2t",
        provider="ECMWF",
        retrieval_provenance="sha256",
        stream="oper",
        expver="1",
        resolution="NATIVE_RECORDED",
        operational_run=True,
    )
    admit_predictor(feature, "2025-01-15T09:00:00+00:00")
    for key in ("model", "provider", "retrieval_provenance", "cycle", "stream"):
        invalid = {**feature, key: ""}
        with pytest.raises(ValueError, match="ARCHIVE_PROVENANCE_INCOMPLETE"):
            admit_predictor(invalid, "2025-01-15T09:00:00+00:00")
    invalid = {**feature, "available_at": "2025-01-14T23:00:00+00:00"}
    with pytest.raises(ValueError, match="FUTURE_OR_INVALID_RUN"):
        admit_predictor(invalid, "2025-01-15T09:00:00+00:00")
    feature["issue_time"] = "2025-01-16T00:00:00+00:00"
    with pytest.raises(ValueError, match="FUTURE_OR_INVALID_RUN"):
        admit_predictor(feature, "2025-01-15T09:00:00+00:00")


def test_no_unlock_before_prediction_seal_and_no_reuse_consumed_blind() -> None:
    with pytest.raises(ValueError, match="FORECAST_NOT_SEALED"):
        authorize_label_unlock({}, False)
    body = {
        "prediction_package_hash": "frozen",
        "sealed_at": "2025-01-15T09:00:00+00:00",
        "actual_access_before_seal": False,
    }
    seal = {**body, "seal_hash": digest(body)}
    authorize_label_unlock(seal, False)
    with pytest.raises(ValueError, match="BLIND_TEST_ALREADY_CONSUMED"):
        authorize_label_unlock(seal, True)
    seal["seal_hash"] = "tampered"
    with pytest.raises(ValueError, match="SEAL_HASH_MISMATCH"):
        authorize_label_unlock(seal, False)


def test_net_radiation_and_unproven_weather8_rejected() -> None:
    with pytest.raises(ValueError, match="NET_SOLAR_IS_NOT_DOWNWARD_SSRD"):
        validate_archive_claim(
            {"status": "AS_ISSUED_PARTIAL", "solar_parameter": "ssr", "weather8_complete": True}
        )
    with pytest.raises(ValueError, match="UNPROVEN_ARCHIVE_COMPLETENESS"):
        validate_archive_claim({"status": "AS_ISSUED_COMPLETE", "retrieval_success": False})
    with pytest.raises(ValueError, match="PROXY_IS_NOT_AS_ISSUED"):
        validate_archive_claim({"status": "NOT_AUDITED", "proxy_is_as_issued": True})


@pytest.mark.parametrize(
    "extra",
    [
        {"harvest": "AVAILABLE_VALID"},
        {"asset_readiness": "TRAINING_READY"},
        {"pit_backtest_ready": True},
    ],
)
def test_metadata_cannot_override_audit_conclusion(extra: dict) -> None:
    row = coverage_matrix([{"entity_id": "a"}], ["s"], {})[0]
    with pytest.raises(ValueError, match="AUDIT_CONCLUSION_OVERRIDE"):
        attach_audit_metadata(row, extra)


def test_entity_metadata_survives_without_repeated_facts() -> None:
    row = coverage_matrix(
        [{"entity_id": "a", "canonical_name": "Farm", "entity_kind": "CANONICAL_BASE"}], ["s"], {}
    )[0]
    attach_audit_metadata(row, {})
    assert row["canonical_name"] == "Farm"
    assert row["entity_kind"] == "CANONICAL_BASE"


@pytest.mark.parametrize(
    "value", [{"lat": 25, "lon": 102}, "file:///tmp/private.csv", "See /Users/operator/private.csv"]
)
def test_public_alias_and_embedded_path_rejected(value: object) -> None:
    with pytest.raises(ValueError, match="PUBLIC_PRIVATE"):
        validate_public(value)


def test_blank_archive_provenance_rejected() -> None:
    with pytest.raises(ValueError, match="ARCHIVE_PROVENANCE_INCOMPLETE"):
        admit_predictor(
            {
                "lane": "PREDICTOR_ZONE",
                "role": "ARCHIVED_OPERATIONAL_FORECAST",
                "available_at": "2025-01-15T07:00:00+00:00",
                "operational_run": True,
                "model": "",
            },
            "2025-01-15T09:00:00+00:00",
        )
