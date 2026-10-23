"""Real frozen Ridge math on synthetic date-bound input, no private data."""

import copy
from datetime import date, timedelta
from decimal import Decimal

import pytest

from backend.research import v019_origin_features as f
from backend.research import v019_origin_models as m
from backend.research.v019_synthetic_validation import digest


def fixture():
    history = []
    for y in [2023, 2024]:
        for i in range(65):
            history.append(
                {
                    "base_id": "SYNTHETIC-a",
                    "season": f"{y}-{y + 1}",
                    "date": str(date(y, 7, 1) + timedelta(days=i)),
                    "state": "VALID_OBSERVED",
                    "kg": str(i + 1),
                    "source_sha256": "a" * 64,
                    "authority_sha256": "b" * 64,
                }
            )
    records = [
        f.snapshot(
            "SYNTHETIC-a",
            "2023-2024",
            date(2023, 8, 1) + timedelta(days=i),
            Decimal(100),
            history,
            15,
        )
        for i in range(5)
    ]
    labels = [
        {"base_id": r["base_id"], "season": r["season"], "date": r["date"], "kg": r["kg"]}
        for r in history
        if r["season"] == "2023-2024"
    ]
    return history, records, labels


def test_actual_ridge_pair_fixed_fit_scaler_and_repeatability():
    _, records, labels = fixture()
    fit = m.fit_pair(
        records, labels, allowed_seasons=("2023-2024",), evaluation_start=date(2024, 7, 1)
    )
    assert fit == m.fit_pair(
        list(reversed(records)),
        labels[::-1],
        allowed_seasons=("2023-2024",),
        evaluation_start=date(2024, 7, 1),
    )
    assert fit["training_origin_count"] == 5 and fit["training_target_count"] == 75
    assert fit["models"]["M0"]["alpha"] == "10.000000"
    assert len(fit["models"]["M0"]["coefficients"]) == 10
    assert len(fit["models"]["M1"]["coefficients"]) == 14
    assert fit["models"]["M0"]["training_label_hash"] == fit["models"]["M1"]["training_label_hash"]
    assert fit["models"]["M0"]["training_row_keys"] == fit["models"]["M1"]["training_row_keys"]


def test_adjacent_origin_actual_progress_changes_m1_not_matched_m0():
    h, rr, labels = fixture()
    fit = m.fit_pair(rr, labels, allowed_seasons=("2023-2024",), evaluation_start=date(2024, 7, 1))
    a = f.snapshot("SYNTHETIC-a", "2024-2025", date(2024, 8, 1), Decimal(100), h, 15)
    b = f.snapshot("SYNTHETIC-a", "2024-2025", date(2024, 8, 2), Decimal(100), h, 15)
    pa, pb = m.predict_pair(fit, a), m.predict_pair(fit, b)
    assert pa == m.predict_pair(fit, a)
    assert pa["predictions"]["M0"][1:] == pb["predictions"]["M0"][:-1]
    assert pa["predictions"]["M1"][1:] != pb["predictions"]["M1"][:-1]
    assert all(
        Decimal(v["kg"]) >= 0 and len(v["kg"].split(".")[1]) == 6
        for rr in pa["predictions"].values()
        for v in rr
    )


def test_incomplete_future_unauthorized_training_and_hash_drift_fail_closed():
    h, rr, ll = fixture()
    fit = m.fit_pair(rr, ll, allowed_seasons=("2023-2024",), evaluation_start=date(2024, 7, 1))
    early = f.snapshot("SYNTHETIC-a", "2024-2025", date(2024, 7, 2), Decimal(100), h, 15)
    assert m.predict_pair(fit, early)["status"] == "NOT_COMPUTABLE"
    assert "predictions" not in m.predict_pair(fit, early)
    with pytest.raises(ValueError, match="TEMPORAL"):
        m.fit_pair(rr, ll, allowed_seasons=("2023-2024",), evaluation_start=date(2023, 8, 1))
    bad = copy.deepcopy(fit)
    bad["models"]["M1"]["coefficients"][0] = "9000"
    with pytest.raises(ValueError, match="SEAL"):
        m.predict_pair(bad, early)
    with pytest.raises(ValueError, match="UNAUTHORIZED"):
        m.fit_pair(
            rr,
            ll + [{"season": "2025-2026"}],
            allowed_seasons=("2023-2024",),
            evaluation_start=date(2024, 7, 1),
        )
    assert fit["sha256"] == digest({k: v for k, v in fit.items() if k != "sha256"})


def test_compiled_pair_is_immutable_and_has_no_source_file_io(monkeypatch):
    from pathlib import Path

    h, rr, ll = fixture()
    fit = m.fit_pair(rr, ll, allowed_seasons=("2023-2024",), evaluation_start=date(2024, 7, 1))
    row = f.snapshot("SYNTHETIC-a", "2024-2025", date(2024, 8, 1), Decimal(100), h, 15)
    compiled = m.compile_pair(fit)
    expected = m.predict_pair(fit, row)
    fit["models"]["M1"]["coefficients"][0] = "9999"

    def fail(*args, **kw):
        raise AssertionError("PREDICTOR_OPENED_SOURCE")

    monkeypatch.setattr(Path, "read_bytes", fail)
    assert compiled.predict(row) == expected
