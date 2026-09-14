"""Synthetic contract evidence only: software PASS never qualifies a real provider."""

import json
import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from scripts.audit_weather_source_r1 import (
    PROOF_KEYS,
    VARIABLES,
    RunIdentity,
    Sample,
    Support,
    digest,
    qualify,
    validate_evidence,
    window,
)

pytestmark = pytest.mark.unit


def sample(days=15):
    origin = datetime(2026, 9, 14, 6, tzinfo=UTC)
    run = RunIdentity(
        provider="SYNTHETIC",
        model="FIXTURE",
        model_cycle="TEST_ONLY",
        product="forecast",
        stream="oper",
        member_or_control="control",
        source_revision="fixture-v1",
        model_initialization_at=origin - timedelta(hours=6),
    )
    start, end = window(origin, days)
    rows = tuple(
        Support(
            variable=v,
            start=start + timedelta(hours=i),
            end=start + timedelta(hours=i + 1),
            valid_time=start + timedelta(hours=i + 1),
            lead_time=int(
                (start + timedelta(hours=i + 1) - run.model_initialization_at).total_seconds()
            ),
            run=run,
        )
        for v in VARIABLES
        for i in range(int((end - start).total_seconds() / 3600))
    )
    return Sample(
        base_id="SYNTHETIC_BASE",
        forecast_origin_at=origin,
        forecast_origin_timezone="Asia/Shanghai",
        run=run,
        issued_at=origin,
        available_at=origin,
        retrieved_at=origin + timedelta(days=30),
        raw_artifact_hash="0" * 64,
        normalized_payload_hash=digest([r.model_dump(mode="json") for r in rows]),
        processing_version="synthetic-normalized-intervals-v1",
        role="HISTORICAL_FORECAST_ARCHIVE",
        generation_mode="AS_ISSUED",
        evidence=dict.fromkeys(PROOF_KEYS, "PROJECT_VERIFIED"),
        evidence_references=dict.fromkeys(PROOF_KEYS, "synthetic-only-proof"),
        candidate_zone_used_as_authority=False,
        supports=rows,
    )


def changed_rows(s, rows):
    return s.model_copy(
        update={
            "supports": tuple(rows),
            "normalized_payload_hash": digest([r.model_dump(mode="json") for r in rows]),
        }
    )


def test_exact_issued_available_boundary_and_determinism():
    s = sample()
    a = qualify(s)
    assert a["pit_status"] == "PIT_CONTRACT_PASS"
    assert a["w7_pit_status"] == a["w15_pit_status"] == "PASS"
    assert a == qualify(Sample.model_validate_json(s.model_dump_json()))
    assert a["weather_source_authority_frozen"] is False


@pytest.mark.parametrize("key", ["issued_at", "available_at"])
def test_future_issue_or_available_rejected(key):
    s = sample()
    assert (
        qualify(s.model_copy(update={key: s.forecast_origin_at + timedelta(seconds=1)}))[
            "w7_pit_status"
        ]
        == "BLOCKED"
    )


@pytest.mark.parametrize("key", ["issued_at", "available_at"])
def test_init_or_today_retrieval_is_not_historical_availability(key):
    s = sample()
    assert s.run.model_initialization_at < s.forecast_origin_at < s.retrieved_at
    assert qualify(s.model_copy(update={key: None}))["pit_status"] == "PIT_NOT_ESTABLISHED"


@pytest.mark.parametrize("days", [7, 15])
def test_complete_and_missing_window(days):
    s = sample(days)
    assert qualify(s)[f"w{days}_pit_status"] == "PASS"
    assert qualify(changed_rows(s, s.supports[1:]))[f"w{days}_pit_status"] == "BLOCKED"


def test_360_hours_does_not_cover_fifteen_shanghai_days():
    s = sample()
    end = s.run.model_initialization_at + timedelta(hours=360)
    assert window(s.forecast_origin_at, 15)[1] - end == timedelta(hours=16)
    cropped = changed_rows(s, [r for r in s.supports if r.end <= end])
    assert qualify(cropped)["w7_pit_status"] == "PASS"
    assert qualify(cropped)["w15_pit_status"] == "BLOCKED"


def test_mixed_run_even_if_older_is_rejected():
    s = sample()
    other = s.run.model_copy(update={"source_revision": "another-run"})
    rows = [s.supports[0].model_copy(update={"run": other}), *s.supports[1:]]
    assert "MIXED_RUN_FORBIDDEN" in qualify(changed_rows(s, rows))["reasons"]


@pytest.mark.parametrize(
    "role,mode",
    [
        ("HISTORICAL_ACTUAL_WEATHER", "REANALYSIS"),
        ("HISTORICAL_FORECAST_ARCHIVE", "HINDCAST"),
        ("HISTORICAL_FORECAST_ARCHIVE", "STITCHED"),
    ],
)
def test_actual_hindcast_stitch_substitution_rejected(role, mode):
    assert (
        "NOT_AS_ISSUED_FORECAST"
        in qualify(sample().model_copy(update={"role": role, "generation_mode": mode}))["reasons"]
    )


@pytest.mark.parametrize("key", PROOF_KEYS)
@pytest.mark.parametrize("status", ["NOT_VERIFIED", "DOCUMENTED"])
def test_documented_or_unknown_is_not_project_proof(key, status):
    s = sample()
    assert (
        qualify(s.model_copy(update={"evidence": {**s.evidence, key: status}}))["pit_status"]
        == "PIT_NOT_ESTABLISHED"
    )


def test_candidate_zone_not_authority():
    assert (
        "CANDIDATE_ZONE_AUTHORITY_FORBIDDEN"
        in qualify(sample().model_copy(update={"candidate_zone_used_as_authority": True}))[
            "reasons"
        ]
    )


def test_hash_and_duplicate_gate():
    s = sample()
    assert (
        "NORMALIZED_PAYLOAD_HASH_MISMATCH"
        in qualify(s.model_copy(update={"normalized_payload_hash": "1" * 64}))["reasons"]
    )
    assert (
        "DUPLICATE_OR_OVERLAPPING_SUPPORT"
        in qualify(changed_rows(s, [*s.supports, s.supports[0]]))["reasons"]
    )


def test_naive_time_and_bad_lead_rejected():
    raw = sample().model_dump(mode="json")
    raw["forecast_origin_at"] = "2026-09-14T06:00:00"
    with pytest.raises(ValidationError):
        Sample.model_validate(raw)
    raw = sample().supports[0].model_dump(mode="json")
    raw["lead_time"] = 0
    with pytest.raises(ValidationError):
        Support.model_validate(raw)


def test_local_day_boundary_cannot_clip_accumulations():
    s = sample()
    first = s.supports[0].model_copy(update={"start": s.supports[0].start - timedelta(hours=1)})
    assert qualify(changed_rows(s, [first, *s.supports[1:]]))["w7_coverage_complete"] is False


def test_checked_in_evidence_offline_replay(monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("NETWORK_FORBIDDEN")

    monkeypatch.setattr(socket, "socket", no_network)
    config = json.loads(Path("configs/weather_source_authority_r1.json").read_text())
    evidence = json.loads(
        Path("docs/v0-5/s2/weather-source-authority-evidence-r1.json").read_text()
    )
    assert validate_evidence(config, evidence) == validate_evidence(config, evidence)
    assert evidence["recommendation"]["historical_as_issued_authority_candidate"] == "NONE"
    config["candidate_zone_used_as_authority"] = True
    with pytest.raises(ValueError, match="CANDIDATE_ZONE"):
        validate_evidence(config, evidence)
