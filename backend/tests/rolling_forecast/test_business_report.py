"""Business export is a projection of saved authority, never a new forecast."""

import csv
import io

import pytest

from backend.app.rolling_forecast import application
from backend.app.rolling_forecast.business_report import export_report
from backend.research.v019_synthetic_validation import digest
from backend.tests.rolling_forecast.source_readiness_package import create_package
from backend.tests.rolling_forecast.test_inbound import compute


@pytest.fixture
def saved_pair(tmp_path):
    catalog, _ = create_package(tmp_path / "SYNTHETIC-source")
    source = catalog.contexts[0].snapshots[0]
    result = []
    for i, origin in enumerate(("2026-11-05", "2026-11-06")):
        value = compute(catalog, i)
        result.append(
            dict(
                run_id=i + 1,
                base_id="SYNTHETIC_INBOUND_BASE",
                target_season="2026-2027",
                origin_date=origin,
                result_hash=digest(value),
                result=value,
                input={
                    "observation_snapshot": source.model_dump(mode="json"),
                    "model_source": {
                        "path": "/private/DO_NOT_EXPORT",
                        "coefficients": "DO_NOT_EXPORT",
                    },
                },
            )
        )
    return result


def test_html_csv_preserve_saved_values_and_identity(saved_pair):
    first, second = saved_pair
    compared = application.compare(first, second)
    html = export_report(first, "html", compared)
    assert html["run_id"] == 1 and html["result_hash"] == first["result_hash"]
    assert html["comparison_result_hash"] == second["result_hash"]
    assert "538.941049" in html["content"] and "1031.362335" in html["content"]
    assert "合成示例，不代表实际产量" in html["content"]
    assert "DO_NOT_EXPORT" not in html["content"] and "coefficients" not in html["content"]
    assert "<script" not in html["content"] and "<svg" in html["content"]
    assert "共同目标日期" in html["content"]
    data = export_report(first, "csv", compared)
    rows = list(csv.DictReader(io.StringIO(data["content"].lstrip("\ufeff"))))
    assert len(rows) == 30
    for name in ("M0", "M1"):
        selected = [r for r in rows if r["model"] == name]
        assert [r["forecast_kg"] for r in selected] == [
            d["kg"] for d in first["result"]["models"][name]["daily_forecast_kg"]
        ]
        assert (
            selected[0]["h7_prefix_total_kg"]
            == first["result"]["models"][name]["H7"]["forecast_total_kg"]
        )
    assert export_report(second, "html")["result_hash"] != html["result_hash"]
    m1 = [r for r in rows if r["model"] == "M1" and r["common_target_daily_delta_kg"]]
    assert len(m1) == 14
    assert (
        m1[0]["common_target_daily_delta_kg"]
        == compared["models"]["M1"]["common_target_daily_delta_kg"][0]["kg"]
    )


def test_exports_escape_html_and_csv_formulas(saved_pair):
    run = saved_pair[0]
    run["base_id"] = "=1+1"
    rows = list(csv.DictReader(io.StringIO(export_report(run, "csv")["content"].lstrip("\ufeff"))))
    assert rows[0]["base_id"] == "'=1+1"
    run["base_id"] = "<img src=x onerror=alert(1)>"
    content = export_report(run, "html")["content"]
    assert "<img" not in content and "&lt;img" in content


def test_uncomputed_model_keeps_reason_without_fake_zero(saved_pair):
    run = saved_pair[0]
    model = run["result"]["models"]["M1"]
    model.update(
        status="NOT_COMPUTABLE",
        H7=None,
        H15=None,
        daily_forecast_kg=[],
        blocker_reason=["INCOMPLETE_PRIOR_OBSERVATIONS"],
    )
    rows = list(csv.DictReader(io.StringIO(export_report(run, "csv")["content"].lstrip("\ufeff"))))
    empty = [r for r in rows if r["model"] == "M1"]
    assert len(empty) == 1 and empty[0]["forecast_kg"] == ""
    assert empty[0]["h7_prefix_total_kg"] == ""
    assert empty[0]["blocker_reason"] == "INCOMPLETE_PRIOR_OBSERVATIONS"
    assert "INCOMPLETE_PRIOR_OBSERVATIONS" in export_report(run, "html")["content"]
