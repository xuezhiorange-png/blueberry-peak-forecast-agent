from datetime import date
from decimal import Decimal

import pytest

from backend.app.area_yield import shape_r3 as s


def test_schema_requires_exact_quantity_and_dimensions():
    assert s.validate_headers(s.HEADERS + ["加工厂"]) is None
    with pytest.raises(ValueError):
        s.validate_headers(s.HEADERS[:-1] + ["数量"])


def test_farm_matching_not_fuzzy_and_ambiguous_rejected():
    assert s.canonical_farm(" 版纳勐旺农场 ", []) == "版纳勐旺农场"
    assert s.canonical_farm("勐旺加工厂", []) != "版纳勐旺农场"
    with pytest.raises(ValueError):
        s.canonical_farm("A", ["A"])


def test_unknown_missing_is_not_zero():
    days = [date(2023, 7, 1), date(2023, 7, 2)]
    assert s.complete_curve({days[0]: Decimal(1)}, days, False) is None


def test_complete_curve_requires_coverage_even_when_dense():
    days = [date(2023, 7, 1)]
    assert s.complete_curve({days[0]: Decimal(1)}, days, False) is None
    assert s.complete_curve({days[0]: Decimal(1)}, days, True) == [1.0]


def test_curve_normalization_nonnegative_and_sum_one():
    assert sum(s.normalize([1, 2, 3])) == pytest.approx(1)
    assert min(s.normalize([-1, 1])) == 0
    with pytest.raises(ValueError):
        s.normalize([0, 0])


def test_no_validation_in_training():
    with pytest.raises(ValueError, match="train season"):
        s.fit_shape([[1.0, 0.0]], "2024-2025", "empirical")


def test_train_shape_integrity_and_no_label_prediction_argument():
    m = s.fit_shape([[0.0, 1.0, 0.0]], "2023-2024", "empirical")
    assert sum(s.predict_shape(m, 20)) == pytest.approx(1)
    m["values"][0] = 99
    with pytest.raises(ValueError, match="integrity"):
        s.predict_shape(m, 20)


def test_canonical_peak_earliest_tie():
    assert s.shape_metrics([1.0] * 14, [1.0] * 14)["rolling_7day_window_shift_days"] == 0
    assert s.shape_metrics([1.0] * 14, [1.0] * 14)["predicted_peak_index"] == 0


def test_duplicate_grain_and_summary_detection():
    assert s.is_summary("农场合计")
    assert not s.is_summary("一分场")
    assert not s.is_summary("")


def test_calendar_does_not_depend_on_actual_peak():
    assert s.season_calendar("2023-2024")[0] == date(2023, 7, 1)
    assert s.season_calendar("2024-2025")[-1] == date(2025, 6, 30)


@pytest.mark.parametrize("sheet_name", ["23~24", "24~25"])
def test_xls_parser_reads_each_sheet_and_fields(monkeypatch, tmp_path, sheet_name):
    class Sheet:
        name = sheet_name
        nrows = 2

        def row_values(self, i):
            return s.HEADERS if i == 0 else ["2023-08-01", "链", "A", "一分场", "Dx", "12", 3.5]

        def cell_type(self, i, j):
            return 1

    class Book:
        datemode = 0

        def sheets(self):
            return [Sheet()]

    path = tmp_path / "input.xls"
    path.write_bytes(b"synthetic unit fixture")
    monkeypatch.setattr(s.xlrd, "open_workbook", lambda _: Book())
    parsed = s.parse_source(path, s.file_hash(path))
    assert parsed["profile"]["row_count"] == 1
    assert parsed["rows"][0]["quantity"] == Decimal("3.5")
    assert parsed["profile"]["sheets"][0]["name"] == sheet_name


def test_source_hash_mismatch_rejected_before_xls_open(monkeypatch, tmp_path):
    path = tmp_path / "source.xls"
    path.write_bytes(b"fixture")
    monkeypatch.setattr(s.xlrd, "open_workbook", lambda _: pytest.fail("must not open"))
    with pytest.raises(ValueError, match="hash mismatch"):
        s.parse_source(path, "wrong")


def test_ridge_shape_fit_normalizes_without_area():
    curve = [float(i + 1) for i in range(30)]
    model = s.fit_shape([curve], "2023-2024", "ridge")
    prediction = s.predict_shape(model, 31)
    assert all(v >= 0 for v in prediction)
    assert sum(prediction) == pytest.approx(1)
    assert model["alpha"] == 10


def test_overlap_counts_multiset_not_set():
    from collections import Counter

    row = {"date": date(2024, 7, 1), "farm": "A", "quantity": Decimal(1)}
    left = {"profile": {"sha256": "a"}, "signatures": Counter({("x",): 2}), "rows": [row, row]}
    right = {"profile": {"sha256": "b"}, "signatures": Counter({("x",): 1}), "rows": [row]}
    result = s.overlap(left, right)
    assert result["relation"] == "PARTIAL_OVERLAP"
    assert result["record_multiset_overlap_count"] == 1
    assert result["uploaded_only_rows"] == 1
    assert not result["daily_totals_equal"]
