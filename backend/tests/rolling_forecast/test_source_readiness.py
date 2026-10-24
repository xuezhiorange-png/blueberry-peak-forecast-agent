"""S9 consumes explicit SYNTHETIC sources; reports never authorize real reads."""

import json
from datetime import date, datetime
from pathlib import Path

import pytest

from backend.app.rolling_forecast import source_readiness as readiness
from backend.tests.rolling_forecast.inbound_fixture import body, fixture


def inspect(catalog, mode="metadata", offset=0):
    request = body(offset)
    return readiness.inspect_source(
        catalog.contexts[0],
        "SYNTHETIC-INBOUND-SNAPSHOT",
        "SYNTHETIC",
        date.fromisoformat(request["origin_date"]),
        datetime.fromisoformat(request["origin_cutoff_at"]),
        mode=mode,
    )


def test_metadata_never_opens_day_files_or_model_parameters(tmp_path, monkeypatch):
    catalog = fixture(tmp_path)
    read = Path.read_bytes

    def guarded(path):
        assert path.name == "manifest.json", "METADATA_OPENED_QUANTITY_OR_MODEL_FILE"
        return read(path)

    monkeypatch.setattr(Path, "read_bytes", guarded)
    result = inspect(catalog)
    assert result["status"] == "METADATA_VALID"
    assert result["m1_feature_readiness"] == "NOT_PROVEN"
    assert result["day_payloads_read"] == 0
    assert result["windows"]["past_7d_harvest_kg"]["complete_count"] == 0
    assert result["windows"]["past_7d_harvest_kg"]["claimed_complete_count"] == 7
    assert not result["real_business_use_authorized"] and not result["strict_pit_validated"]


def test_full_source_and_reports_are_deterministic_and_redacted(tmp_path):
    catalog = fixture(tmp_path / "source")
    value = inspect(catalog, "synthetic-full")
    assert value["status"] == "SYNTHETIC_FULL_VALIDATED"
    assert value["m1_feature_readiness"] == "COMPUTABLE"
    assert [w["complete_count"] for w in value["windows"].values()] == [7, 14, 28, 35]
    assert value == inspect(catalog, "synthetic-full")
    for target in (tmp_path / "out1", tmp_path / "out2"):
        readiness.write_reports(value, target)
    for name in ("readiness-report.json", "daily-readiness.csv", "readiness-report.html"):
        a, b = ((tmp_path / d / name).read_bytes() for d in ("out1", "out2"))
        assert a == b
        assert b"quantity_kg" not in a and str(tmp_path).encode() not in a
        assert b"SYNTHETIC-farm" not in a and b"coefficients" not in a
    with pytest.raises(FileExistsError):
        readiness.write_reports(value, tmp_path / "out1")


@pytest.mark.parametrize(
    "problem,reason",
    [
        ("missing", "NO_RECORD_WITHOUT_ZERO_AUTHORITY"),
        ("late", "LATE_SOURCE_RECORD"),
        ("partial", "PARTIAL_MEMBER_COVERAGE"),
        ("duplicate", "DUPLICATE_SOURCE_RECORD"),
    ],
)
def test_bad_days_are_localized_and_never_zero_filled(tmp_path, problem, reason):
    from backend.tests.rolling_forecast.test_inbound import reindex

    def change(i, day):
        if i != 34:
            return
        if problem == "missing":
            day["records"] = []
        if problem == "late":
            day["records"][0]["server_ingested_at"] = "2026-11-05T10:00:00Z"
        if problem == "duplicate":
            day["records"] *= 2

    catalog = fixture(tmp_path, mutate=change)
    if problem == "partial":
        catalog = reindex(catalog, lambda m: m["days"][34].update(member_coverage=[]))
    result = inspect(catalog, "synthetic-full")
    assert result["m1_feature_readiness"] == "NOT_COMPUTABLE"
    row = next(d for d in result["daily"] if d["business_date"] == "2026-11-04")
    assert reason in row["reasons"]
    assert result["windows"]["past_7d_harvest_kg"]["complete_count"] == 6


def test_real_provenance_is_denied_before_any_source_io_even_with_matching_hash(
    tmp_path, monkeypatch
):
    c = fixture(tmp_path).contexts[0]
    source = c.snapshots[0].model_copy(
        update={"provenance": "AUTHORIZED_HISTORICAL", "target_binding": None}
    )
    c = c.model_copy(update={"snapshots": (source,)})

    def forbidden(*args):
        raise AssertionError("REAL_SOURCE_IO")

    monkeypatch.setattr(Path, "read_bytes", forbidden)
    result = readiness.inspect_source(
        c,
        source.reference,
        "SYNTHETIC",
        date(2026, 11, 5),
        datetime.fromisoformat(body()["origin_cutoff_at"]),
        mode="synthetic-full",
    )
    assert result["status"] == "BLOCKED"
    assert "REAL_SOURCE_EXECUTION_NOT_AUTHORIZED" in result["blockers"]
    assert result["day_payloads_read"] == 0


def test_business_summary_ignores_output_directory_and_wall_clock(tmp_path):
    a, b = (inspect(fixture(tmp_path / folder), "synthetic-full") for folder in ("one", "two"))
    assert a["business_summary_hash"] == b["business_summary_hash"]
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


@pytest.mark.parametrize(
    "problem,reason",
    [
        ("timestamp", "SOURCE_TIMESTAMP_MISSING"),
        ("time_authority", "SOURCE_TIME_UNVERIFIED"),
        ("member", "SOURCE_MEMBER_MISMATCH"),
        ("grade", "SOURCE_GRADE_UNVERIFIED"),
        ("float", "SOURCE_RECORD_SCHEMA_INVALID"),
        ("negative", "SOURCE_RECORD_SCHEMA_INVALID"),
        ("wrong_base", "SOURCE_DAY_IDENTITY_MISMATCH"),
    ],
)
def test_shared_s8_validation_retains_specific_bad_day_reason(tmp_path, problem, reason):
    from backend.tests.rolling_forecast.source_readiness_package import frozen_reference

    model = frozen_reference(tmp_path)

    def mutate(i, day):
        if i != 34:
            return
        row = day["records"][0]
        if problem == "timestamp":
            row["source_recorded_at"] = None
        elif problem == "time_authority":
            row["available_at_authority"] = "MISSING"
        elif problem == "member":
            row["member"] = {**row["member"], "farm_business_key": "SYNTHETIC-UNREGISTERED"}
        elif problem == "grade":
            row["grade"] = "SYNTHETIC-UNREGISTERED"
        elif problem == "float":
            row["quantity_kg"] = 1.25
        elif problem == "negative":
            row["quantity_kg"] = "-1.000000"
        else:
            day["base_id"] = "SYNTHETIC-OTHER"

    catalog = fixture(tmp_path / "source", mutate=mutate, frozen_model_reference=model)
    report = inspect(catalog, "synthetic-full")
    assert report["m1_feature_readiness"] == "NOT_COMPUTABLE"
    row = next(d for d in report["daily"] if d["business_date"] == "2026-11-04")
    assert reason in row["reasons"]
    assert report["windows"]["past_7d_harvest_kg"]["complete_count"] == 6


def test_cross_day_duplicate_marks_both_dates_and_never_imputes(tmp_path):
    from backend.tests.rolling_forecast.source_readiness_package import frozen_reference

    catalog = fixture(
        tmp_path / "source",
        frozen_model_reference=frozen_reference(tmp_path),
        mutate=lambda i, d: d["records"][0].update(logical_id="SYNTHETIC-33") if i == 34 else None,
    )
    report = inspect(catalog, "synthetic-full")
    assert report["status"] == "BLOCKED"
    assert report["windows"]["past_7d_harvest_kg"]["conflict_dates"] == ["2026-11-03", "2026-11-04"]
    assert report["windows"]["past_7d_harvest_kg"]["complete_count"] == 5


def test_future_day_files_are_never_opened_and_legal_prior_changes_predictions(
    tmp_path, monkeypatch
):
    from backend.tests.rolling_forecast.source_readiness_package import frozen_reference
    from backend.tests.rolling_forecast.test_inbound import compute

    model = frozen_reference(tmp_path)
    original = fixture(tmp_path / "original", frozen_model_reference=model)
    future = fixture(
        tmp_path / "future",
        frozen_model_reference=model,
        mutate=lambda i, d: (
            d["records"][0].update(quantity_kg="999999.000000") if i >= 35 else None
        ),
    )
    prior = fixture(
        tmp_path / "prior",
        frozen_model_reference=model,
        mutate=lambda i, d: d["records"][0].update(quantity_kg="38.000000") if i == 34 else None,
    )
    read = Path.read_bytes

    def bounded(path):
        assert not (path.name.startswith("day-") and path.name[4:14] >= "2026-11-05")
        return read(path)

    monkeypatch.setattr(Path, "read_bytes", bounded)
    assert inspect(original, "synthetic-full")["m1_feature_readiness"] == "COMPUTABLE"
    assert inspect(future, "synthetic-full")["m1_feature_readiness"] == "COMPUTABLE"
    a, b, c = (compute(x) for x in (original, future, prior))
    assert a["models"] == b["models"]
    assert a["models"]["M0"] == c["models"]["M0"]
    assert a["models"]["M1"]["daily_forecast_kg"] != c["models"]["M1"]["daily_forecast_kg"]
    from decimal import Decimal

    for key in a["feature_snapshot"]["values"]:
        assert (
            Decimal(c["feature_snapshot"]["values"][key])
            - Decimal(a["feature_snapshot"]["values"][key])
            == 3
        )


@pytest.mark.parametrize("problem", ["hash", "symlink"])
def test_day_integrity_path_failure_is_reported_without_private_values(tmp_path, problem):
    from backend.tests.rolling_forecast.source_readiness_package import create_package

    catalog, _ = create_package(tmp_path / "package")
    path = tmp_path / "package/source/day-2026-11-04.json"
    if problem == "hash":
        path.write_bytes(path.read_bytes() + b" ")
    else:
        moved = path.with_name("SYNTHETIC-original.json")
        path.rename(moved)
        path.symlink_to(moved)
    report = inspect(catalog, "synthetic-full")
    assert report["status"] == "BLOCKED"
    assert (
        "SOURCE_SNAPSHOT_HASH_MISMATCH" if problem == "hash" else "SOURCE_PATH_UNSAFE"
    ) in report["blockers"]
    assert str(tmp_path) not in json.dumps(report)


@pytest.mark.parametrize(
    "problem,reason",
    [
        ("duplicate_date", "DUPLICATE_SOURCE_DAY"),
        ("grade_intersection", "SOURCE_GRADE_CONFLICT"),
        ("duplicate_member", "SOURCE_MEMBER_COVERAGE_CONFLICT"),
    ],
)
def test_metadata_conflict_rejected_without_day_reads(tmp_path, monkeypatch, problem, reason):
    from backend.app.rolling_forecast.policy import Catalog
    from backend.research.v019_synthetic_validation import digest
    from backend.tests.rolling_forecast.inbound_fixture import write
    from backend.tests.rolling_forecast.source_readiness_package import create_package

    catalog, _ = create_package(tmp_path / "package")
    source = catalog.contexts[0].snapshots[0]
    raw = json.loads(Path(source.manifest_path).read_bytes())
    if problem == "duplicate_date":
        raw["days"].append(raw["days"][0])
    elif problem == "grade_intersection":
        raw["excluded_grades"] = raw["accepted_grades"]
    else:
        raw["days"][34]["member_coverage"] *= 2
    sealed = tmp_path.resolve() / "SYNTHETIC-index.json"
    sha = write(sealed, raw)
    value = catalog.model_dump(mode="json")
    value["contexts"][0]["snapshots"][0].update(
        manifest_path=str(sealed), manifest_sha256=sha, snapshot_hash=digest(raw)
    )
    catalog = Catalog.model_validate(value)
    original = Path.read_bytes

    def guarded(path):
        assert path == sealed, "METADATA_OPENED_DAY_FILE"
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", guarded)
    report = inspect(catalog)
    assert report["status"] == "BLOCKED" and reason in report["blockers"]
    assert report["m1_feature_readiness"] == "NOT_PROVEN" and not report["day_payloads_read"]


def test_short_prior_window_not_padded_before_calendar_start(tmp_path):
    from backend.tests.rolling_forecast.source_readiness_package import create_package

    catalog, _ = create_package(tmp_path / "package")
    c = catalog.contexts[0]
    report = readiness.inspect_source(
        c,
        c.snapshots[0].reference,
        c.models[0].reference,
        date(2026, 10, 15),
        datetime.fromisoformat("2026-10-15T09:00:00+00:00"),
        mode="synthetic-full",
    )
    assert report["m1_feature_readiness"] == "NOT_COMPUTABLE"
    assert report["windows"]["past_7d_harvest_kg"]["complete_count"] == 7
    window = report["windows"]["past_28d_harvest_kg"]
    assert window["required_count"] == 28 and window["complete_count"] == 14
    assert len(window["missing_dates"]) == 14
    assert "HARVEST_STATE_INCOMPLETE_PRIOR_WINDOW" in report["blockers"]


def test_excluded_grade_is_counted_but_not_added_to_features(tmp_path):
    from backend.tests.rolling_forecast.source_readiness_package import frozen_reference
    from backend.tests.rolling_forecast.test_inbound import compute

    model = frozen_reference(tmp_path)
    catalog = fixture(
        tmp_path / "source",
        frozen_model_reference=model,
        mutate=lambda i, d: d["records"][0].update(grade="SYNTHETIC-EXCLUDED") if i == 34 else None,
    )
    report = inspect(catalog, "synthetic-full")
    day = report["daily"][-1]
    assert day["record_count"] == 1 and day["excluded_record_count"] == 1
    assert report["m1_feature_readiness"] == "COMPUTABLE"
    assert compute(catalog)["feature_snapshot"]["values"]["past_7d_harvest_kg"] == "189.000000"
