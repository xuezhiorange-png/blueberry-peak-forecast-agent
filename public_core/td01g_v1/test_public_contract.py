"""TD01G_PUBLIC_CORE_V1 scope: independent synthetic contracts, no history audit."""

import hashlib
import io
import json
import subprocess
import sys
import zipfile
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal, localcontext
from pathlib import Path

import pytest
from backend.app import public_core as core
from backend.app.etl.history import synthetic_publication as publication
from backend.app.etl.history.schemas import EXPECTED_HEADERS
from backend.research.v019_daily_curve import (
    BASELINE_POLICY,
    CurveInput,
    DailyKg,
    generate_candidate,
    select_window,
)
from openpyxl import load_workbook
from openpyxl.comments import Comment


def test_export_quality_and_all_independent_bytes(tmp_path):
    first, second = tmp_path / "one", tmp_path / "two"
    a, b = core.generate(41, first), core.generate(41, second)
    assert a == b
    assert {p.name: p.read_bytes() for p in first.iterdir()} == {
        p.name: p.read_bytes() for p in second.iterdir()
    }
    assert a["row_count"] == 98
    assert a["quality_reasons"].keys() >= {
        "empty_weight",
        "zero_weight",
        "negative_weight",
        "invalid_date",
        "suspected_duplicate",
    }
    assert a["formal_source_admitted"] is False
    package = publication.generate(41)
    for season in a["seasons"]:
        prefix = "SYNTHETIC_ONLY_" + season.replace("-", "_")
        publication.check_csv((first / (prefix + ".csv")).read_bytes(), package, season)
        publication.check_xlsx((first / (prefix + ".xlsx")).read_bytes(), package, season)
    with pytest.raises(FileExistsError):
        core.generate(41, first)


@pytest.mark.parametrize("usage", ["TRAINING", "FORMAL_FORECAST", "REAL_SCORING", "AUTHORITY"])
def test_no_formal_source_admission(usage):
    with pytest.raises(ValueError, match="SYNTHETIC_NOT_A_FORMAL_SOURCE"):
        publication.require_usage(publication.generate(), usage)


def test_unknown_real_source_rejected_before_access(tmp_path, monkeypatch):
    def deny(*args, **kwargs):
        pytest.fail("source file must not be inspected")

    monkeypatch.setattr(Path, "open", deny)
    monkeypatch.setattr(Path, "exists", deny)
    with pytest.raises(ValueError, match="REAL_SOURCE_READ_NOT_AUTHORIZED"):
        core.execute(41, tmp_path / "out", real_source=tmp_path / "renamed.xlsx")


@pytest.mark.parametrize("mutation", ["identity", "class", "weight", "relation"])
def test_labels_cannot_turn_different_records_into_synthetic(mutation):
    package = publication.generate()
    if mutation == "identity":
        bad = replace(package, source_identity="UNAUTHORIZED_INPUT")
    elif mutation == "class":
        bad = replace(package, data_class="PUBLIC_CODE")
    else:
        row = package.rows[0]
        values = list(row.values)
        values[6 if mutation == "weight" else 2] = (
            "9999.000000" if mutation == "weight" else "UNVERIFIED_RELATION"
        )
        bad = replace(package, rows=(replace(row, values=tuple(values)), *package.rows[1:]))
    with pytest.raises(ValueError, match="NOT_GENERATOR_OUTPUT"):
        publication.validate_public(bad)


@pytest.mark.parametrize("mutation", ["hidden", "comment", "formula", "link", "author", "extra"])
def test_complete_workbook_and_metadata_binding(mutation):
    package = publication.generate()
    data = publication.xlsx_bytes(package)
    if mutation == "extra":
        stream = io.BytesIO(data)
        with zipfile.ZipFile(stream, "a") as archive:
            archive.writestr("xl/vbaProject.bin", b"SYNTHETIC_ONLY_NOT_AUTHORITY")
        modified = stream.getvalue()
    else:
        book = load_workbook(io.BytesIO(data))
        assert tuple(c.value for c in book.active[1]) == EXPECTED_HEADERS
        if mutation == "hidden":
            book.create_sheet("SYNTHETIC_HIDDEN").sheet_state = "hidden"
        elif mutation == "comment":
            book.active["A2"].comment = Comment("SYNTHETIC_NOTE", "SYNTHETIC_AUTHOR")
        elif mutation == "formula":
            book.active["A2"] = "=1+1"
        elif mutation == "link":
            book.active["A2"].hyperlink = "https://invalid.example"
        else:
            book.properties.creator = "SYNTHETIC_OTHER"
        stream = io.BytesIO()
        book.save(stream)
        book.close()
        modified = stream.getvalue()
    with pytest.raises(ValueError, match="UNSAFE_PUBLIC_WORKBOOK"):
        publication.check_xlsx(modified, package)


def test_csv_changed_weight_is_refused(tmp_path):
    core.generate(41, tmp_path / "out")
    data = (tmp_path / "out/SYNTHETIC_ONLY_2039_2040.csv").read_bytes()
    with pytest.raises(ValueError, match="CONTENT_BINDING"):
        publication.check_csv(
            data.replace(b"SYNTHETIC_FARM_1", b"SYNTHETIC_OTHER"),
            publication.generate(),
            "2039-2040",
        )


def test_actual_frozen_curve_invariants_and_decimal_context():
    first = core.curve(41)
    assert all(first["invariants"].values())
    assert first["h7"] == first["h15"][:7]
    rows = first["daily"]
    assert len(rows) == 28 and len(first["h7"]) == 7 and len(first["h15"]) == 15
    assert all(Decimal(r["kg"]) >= 0 and Decimal(r["kg"]).as_tuple().exponent == -6 for r in rows)
    # Existing solver receives the same synthetic source under changed contexts.
    from datetime import date

    start = date(2040, 7, 1)
    base = tuple(DailyKg(start + timedelta(days=i), Decimal(i // 7 + 1)) for i in range(28))
    request = CurveInput(
        start, start, base[-1].day, base, "a" * 64, BASELINE_POLICY, "Asia/Shanghai"
    )
    results = []
    for precision in (6, 28, 50):
        with localcontext() as ctx:
            ctx.prec = precision
            results.append(generate_candidate(request))
    assert results[0] == results[1] == results[2]
    assert all(b.baseline_micro_kg == b.candidate_micro_kg for b in results[0].bins)
    assert (
        select_window(results[0], origin=start, horizon=7)
        == select_window(results[0], origin=start, horizon=15)[:7]
    )
    with pytest.raises(ValueError, match="QUERY_OUTSIDE_SUPPORT"):
        select_window(results[0], origin=base[-1].day, horizon=7)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "negative", "float"])
def test_invalid_daily_inputs_are_not_filled_or_rounded(mutation):
    from datetime import date

    start = date(2040, 7, 1)
    rows = [DailyKg(start + timedelta(days=i), Decimal("1")) for i in range(21)]
    if mutation == "missing":
        rows.pop(8)
    elif mutation == "duplicate":
        rows[8] = rows[7]
    elif mutation == "negative":
        rows[8] = DailyKg(rows[8].day, Decimal("-1"))
    else:
        rows[8] = DailyKg(rows[8].day, 1.0)
    with pytest.raises(ValueError):
        generate_candidate(
            CurveInput(
                start,
                start,
                start + timedelta(days=20),
                tuple(rows),
                "a" * 64,
                BASELINE_POLICY,
                "Asia/Shanghai",
            )
        )


def test_two_independent_installed_cli_processes_are_identical(tmp_path):
    for n in (1, 2):
        subprocess.run(
            [
                sys.executable,
                "-I",
                "-B",
                "-m",
                "backend.app.public_core",
                "demo",
                "--seed",
                "41",
                "--output-dir",
                str(tmp_path / str(n)),
            ],
            check=True,
            capture_output=True,
        )
    one, two = tmp_path / "1", tmp_path / "2"
    assert {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in one.iterdir()} == {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in two.iterdir()
    }
    report = json.loads((one / "public-core-run.json").read_bytes())
    assert report["DATA_CLASS"] == "SYNTHETIC_ONLY"
    assert report["REAL_FORECAST_VALIDATED"] is False
    assert report["STRICT_REAL_PIT_VALIDATED"] is False
    assert report["PRODUCTION_MODEL_ADMITTED"] is False


def test_registered_samples_are_full_generator_output(tmp_path):
    publication.export(publication.generate(41), tmp_path / "generated")
    source = Path(__file__).resolve().parents[1] / "docs/tech-debt/td01c-synthetic-example"
    assert {p.name: p.read_bytes() for p in source.iterdir()} == {
        p.name: p.read_bytes() for p in (tmp_path / "generated").iterdir()
    }
