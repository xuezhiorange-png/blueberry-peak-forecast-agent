"""Synthetic closure contracts; no credentials, network, labels or database."""

from copy import deepcopy
from datetime import datetime, timedelta

import pytest

from scripts.audit_v0_15_s0_access_closure import (
    FIELDS,
    audit_schema_readonly,
    build_reports,
    classify_tier,
    reclassify_gap,
    sanitized_access_receipt,
    verify_weather8,
)


def full_metadata() -> list[dict]:
    ids = {"2t": 167, "10u": 165, "10v": 166, "tp": 228, "ssrd": 169}
    units = {"2t": "K", "10u": "m s**-1", "10v": "m s**-1", "tp": "m", "ssrd": "J m**-2"}
    rows = []
    for p, s in FIELDS:
        valid = datetime(2025, 1, 15) + timedelta(hours=s)
        rows.append(
            dict(
                shortName=p,
                endStep=s,
                startStep=0,
                paramId=ids[p],
                units=units[p],
                stepType="accum" if p in {"tp", "ssrd"} else "instant",
                dataDate=20250115,
                dataTime=0,
                expver="1",
                model_cycle="SYNTHETIC",
                validityDate=int(valid.strftime("%Y%m%d")),
                validityTime=int(valid.strftime("%H%M")),
                resolution="SYNTHETIC",
                stream="oper",
                type="fc",
                levtype="sfc",
                **{"class": "od"},
            )
        )
    return rows


def test_full_synthetic_surface_and_single_missing_field() -> None:
    rows = full_metadata()
    assert verify_weather8(rows)["complete"] is True
    assert verify_weather8(rows[:-1])["complete"] is False


@pytest.mark.parametrize(
    "key,value",
    [
        ("units", "wrong"),
        ("paramId", 999),
        ("dataTime", 600),
        ("validityDate", 20240101),
        ("model_cycle", "DIFFERENT"),
        ("levtype", "pl"),
    ],
)
def test_weather_encoding_and_provenance_mismatch(key: str, value: object) -> None:
    rows = full_metadata()
    rows[0][key] = value
    assert verify_weather8(rows)["complete"] is False


def test_no_ssr_substitution_or_accumulation_origin_change() -> None:
    rows = full_metadata()
    rows[-1]["shortName"] = "ssr"
    assert verify_weather8(rows)["complete"] is False
    rows = full_metadata()
    rows[-1]["startStep"] = 168
    assert verify_weather8(rows)["complete"] is False


def test_retrospective_effective_time_is_not_availability() -> None:
    assert (
        classify_tier({"effective_time": "2024-01-01T00:00:00Z"}, "2025-01-01T00:00:00Z")
        == "PIT_EVIDENCE_TIER_C_RETROSPECTIVE"
    )


def test_direct_immutable_evidence_required_for_strict() -> None:
    evidence = {
        "available_at": "2024-01-01T00:00:00Z",
        "evidence_kind": "IMMUTABLE_INGESTION",
        "immutable": True,
        "source_hash": "a" * 64,
    }
    assert classify_tier(evidence, "2025-01-01T00:00:00Z") == "PIT_EVIDENCE_TIER_A_STRICT"
    assert (
        classify_tier({**evidence, "immutable": False}, "2025-01-01T00:00:00Z")
        == "PIT_EVIDENCE_TIER_C_RETROSPECTIVE"
    )
    assert classify_tier(evidence, "2023-01-01T00:00:00Z") == "PIT_EVIDENCE_TIER_C_RETROSPECTIVE"


def test_assumption_requires_frozen_result_independent_rule() -> None:
    evidence = {
        "assumption_policy_hash": "b" * 64,
        "assumption_frozen": True,
        "result_independent": True,
    }
    assert classify_tier(evidence, "2025-01-01T00:00:00Z") == "PIT_EVIDENCE_TIER_B_ASSUMED"
    assert (
        classify_tier({**evidence, "result_independent": False}, "2025-01-01T00:00:00Z")
        == "PIT_EVIDENCE_TIER_C_RETROSPECTIVE"
    )


@pytest.mark.parametrize("code", [401, 403])
def test_access_denied_does_not_mean_archive_absent(code: int) -> None:
    receipt = sanitized_access_receipt(
        {
            "http_status": code,
            "token": "DO_NOT_PUBLISH",
            "Authorization": "secret",
            "url": "private",
        }
    )
    assert receipt == {
        "http_status": code,
        "classification": "ACCESS_BLOCKED",
        "absence_proven": False,
    }


def test_missing_fields_not_complete() -> None:
    result = verify_weather8([])
    assert result["required_field_count"] == 256
    assert result["missing_field_count"] == 256
    assert result["complete"] is False


def test_gap_reclassification_preserves_input_and_unknown() -> None:
    gap = {"missing_field": "weather", "status": "MISSING", "blocking_or_optional": "BLOCKING"}
    before = deepcopy(gap)
    result = reclassify_gap(gap)
    assert result["closure_category"] == "ACCESS_BLOCKED"
    assert result["true_company_data_missing_proven"] is False
    assert gap == before
    assert result == reclassify_gap(gap)


def test_identity_not_automatically_bound() -> None:
    assert (
        reclassify_gap({"missing_field": "identity"})["closure_category"] == "IDENTITY_UNRESOLVED"
    )


def test_naive_availability_rejected() -> None:
    with pytest.raises(ValueError, match="NAIVE_TIMESTAMP"):
        classify_tier(
            {
                "available_at": "2024-01-01",
                "immutable": True,
                "source_hash": "a" * 64,
                "evidence_kind": "IMMUTABLE_INGESTION",
            },
            "2025-01-01T00:00:00Z",
        )


@pytest.mark.parametrize(
    "observation,error",
    [
        ({"db_access_available": True}, "LIVE_PROOF_REQUIRED"),
        ({"ecmwf_auth_available": True}, "LIVE_PROOF_REQUIRED"),
        ({"protected_runtime_accessed": True}, "PROTECTED_BOUNDARY_BREACH"),
        ({"current_actual_accessed": True}, "PROTECTED_BOUNDARY_BREACH"),
        ({"token": "secret"}, "UNSAFE_ACCESS_OBSERVATION_FIELD"),
        ({"actual_path": "not-allowed"}, "UNSAFE_ACCESS_OBSERVATION_FIELD"),
    ],
)
def test_no_unverified_db_success_actual_access_or_secret_input(
    tmp_path, observation: dict, error: str
) -> None:
    # Guard executes before any filesystem loader, database or actual query.
    with pytest.raises(ValueError, match=error):
        build_reports(tmp_path, observation)


@pytest.mark.parametrize("read_only", [True, False])
def test_db_metadata_transaction_readonly_and_no_actual_query(read_only: bool) -> None:
    class Connection:
        def __init__(self) -> None:
            self.queries: list[str] = []
            self.rolled_back = False

        def cursor(self):
            return self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, sql: str) -> None:
            self.queries.append(sql)

        def fetchone(self):
            return ("on" if read_only else "off",)

        def fetchall(self):
            return [("public", "synthetic", "season", "text")]

        def rollback(self) -> None:
            self.rolled_back = True

    conn = Connection()
    if read_only:
        assert audit_schema_readonly(conn) == [("public", "synthetic", "season", "text")]
        assert "FROM information_schema.columns" in conn.queries[-1]
    else:
        with pytest.raises(ValueError, match="DATABASE_READ_ONLY_NOT_ENFORCED"):
            audit_schema_readonly(conn)
        assert len(conn.queries) == 2
    assert conn.queries[0] == "BEGIN READ ONLY"
    assert conn.rolled_back
