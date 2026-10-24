"""Executable onboarding scenarios; no source enrollment, fitting or real IO."""

import csv
import json
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import pytest

from backend.app.rolling_forecast import source_readiness as readiness
from backend.app.rolling_forecast.source_requirements import SourceRequirements, template
from backend.tests.rolling_forecast.source_readiness_package import SCENARIOS, create_package
from backend.tests.rolling_forecast.test_source_readiness import inspect


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_cli_nine_explicit_synthetic_scenarios(tmp_path, scenario):
    catalog, path = create_package(tmp_path / "package", scenario)
    assert not catalog.capabilities
    assert not catalog.contexts[0].review_snapshots
    output = tmp_path / "reports"
    response = subprocess.run(
        [
            sys.executable,
            "-m",
            "backend.app.rolling_forecast.source_readiness",
            "inspect",
            "--catalog",
            str(path),
            "--context",
            "SYNTHETIC-INBOUND-CONTEXT",
            "--origin",
            "2026-11-05",
            "--cutoff",
            "2026-11-05T17:00:00+08:00",
            "--mode",
            "synthetic-full",
            "--output-dir",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    expected = inspect(catalog, "synthetic-full")
    good = scenario in ("complete", "confirmed-zero")
    assert response.returncode == (0 if good else 2), response.stderr
    assert json.loads((output / "readiness-report.json").read_bytes()) == expected
    assert json.loads(response.stdout)["status"] == expected["status"]
    assert expected["m1_feature_readiness"] == ("COMPUTABLE" if good else "NOT_COMPUTABLE")
    if scenario == "confirmed-zero":
        assert expected["counts"]["CONFIRMED_ZERO"] == 1
    if scenario == "missing-day":
        assert expected["windows"]["past_7d_harvest_kg"]["missing_dates"] == ["2026-11-04"]
    if scenario == "metadata-only":
        assert expected["windows"]["past_7d_harvest_kg"]["time_unproven_dates"] == [
            f"2026-10-{d}" for d in (29, 30, 31)
        ] + [f"2026-11-0{d}" for d in range(1, 5)]
    with (output / "daily-readiness.csv").open(encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == 35
    assert "reason_details_zh" in rows[0]
    assert output.stat().st_mode & 0o777 == 0o700
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in output.iterdir())
    for name in ("readiness-report.json", "daily-readiness.csv", "readiness-report.html"):
        data = (output / name).read_bytes()
        assert b"quantity_kg" not in data and str(tmp_path).encode() not in data
        assert b"SYNTHETIC-farm" not in data and b"coefficients" not in data


def test_package_reuses_frozen_fixture_without_refit(tmp_path, monkeypatch):
    from backend.tests.rolling_forecast import test_model_artifacts

    def forbidden(*args, **kwargs):
        raise AssertionError("PACKAGE_MUST_NOT_TRAIN")

    monkeypatch.setattr(test_model_artifacts, "reference", forbidden)
    # inbound_fixture imported the reference too; catch both import shapes.
    from backend.tests.rolling_forecast import inbound_fixture

    monkeypatch.setattr(inbound_fixture, "reference", forbidden)
    catalog, _ = create_package(tmp_path / "package")
    assert inspect(catalog, "synthetic-full")["m1_feature_readiness"] == "COMPUTABLE"


def test_cli_real_guard_before_any_source_read(tmp_path, monkeypatch, capsys):
    _, path = create_package(tmp_path / "package")
    value = json.loads(path.read_bytes())
    value["contexts"][0]["snapshots"][0]["provenance"] = "AUTHORIZED_HISTORICAL"
    path.write_text(json.dumps(value))
    original = Path.read_bytes

    def guarded(p):
        assert p == path, "REAL_DAY_OR_MODEL_READ"
        return original(p)

    monkeypatch.setattr(Path, "read_bytes", guarded)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "source_readiness",
            "inspect",
            "--catalog",
            str(path),
            "--context",
            "SYNTHETIC-INBOUND-CONTEXT",
            "--origin",
            "2026-11-05",
            "--cutoff",
            "2026-11-05T00:00:00+08:00",
            "--mode",
            "synthetic-full",
            "--output-dir",
            str(tmp_path / "blocked"),
        ],
    )
    with pytest.raises(SystemExit) as stopped:
        readiness.main()
    assert stopped.value.code == 2
    assert "REAL_SOURCE_EXECUTION_NOT_AUTHORIZED" in capsys.readouterr().out


def test_filled_template_cannot_approve_source_or_expose_private_material(tmp_path):
    model = template().model_dump(mode="json")
    for item in model["items"]:
        item.update(
            accountable_owner="PRIVATE-CUSTODIAN",
            evidence_reference="/private/secret",
            evidence_sha256="a" * 64,
            declared_details="PRIVATE-WEIGHTS",
            claim_status="SUPPLIED_NOT_VERIFIED",
        )
    filled = SourceRequirements.model_validate(model)
    catalog, _ = create_package(tmp_path / "package")
    c = catalog.contexts[0]
    report = readiness.inspect_source(
        c,
        c.snapshots[0].reference,
        c.models[0].reference,
        date(2026, 11, 5),
        datetime.fromisoformat("2026-11-05T00:00:00+08:00"),
        requirements=filled,
    )
    raw = json.dumps(report)
    assert "PRIVATE-" not in raw and "/private" not in raw
    assert report["m1_feature_readiness"] == "NOT_PROVEN"
    assert {i["status"] for i in report["source_requirements"]} == {"PENDING_SOURCE_AUTHORITY"}
    assert not report["real_business_use_authorized"]
    with pytest.raises(ValueError):
        SourceRequirements.model_validate({**model, "real_source_enrolled": True})
    stored = Path("docs/v0-19/s9/inbound-source-requirements-v1.json")
    assert SourceRequirements.model_validate_json(stored.read_bytes()) == template()


def test_output_escapes_html_and_refuses_unowned_directory(tmp_path):
    from backend.app.rolling_forecast.source_readiness_report import render_html

    catalog, _ = create_package(tmp_path / "package")
    report = inspect(catalog)
    report["source_system"] = "<script>alert('SYNTHETIC')</script>"
    html = render_html(report)
    assert "<script>" not in html and "&lt;script&gt;" in html
    owner = tmp_path / "unrelated"
    owner.mkdir()
    marker = owner / "keep.txt"
    marker.write_text("unrelated")
    link = tmp_path / "alias"
    link.symlink_to(owner)
    with pytest.raises(ValueError, match="OUTPUT_PATH_UNSAFE"):
        readiness.write_reports(report, link / "new")
    assert marker.read_text() == "unrelated" and not (owner / "new").exists()


def test_timezone_naive_cutoff_is_rejected(tmp_path):
    catalog, _ = create_package(tmp_path / "package")
    c = catalog.contexts[0]
    with pytest.raises(ValueError, match="TIMEZONE_REQUIRED"):
        readiness.inspect_source(
            c,
            c.snapshots[0].reference,
            c.models[0].reference,
            date(2026, 11, 5),
            datetime(2026, 11, 5),
        )
