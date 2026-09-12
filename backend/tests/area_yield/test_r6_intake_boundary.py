from pathlib import Path

import pytest

from scripts import run_frozen_evidence_expansion_r6 as runner


def test_unapproved_source_never_opened(monkeypatch):
    def forbidden(*args):
        pytest.fail("source opened before authorization")

    monkeypatch.setattr(runner, "parse_source", forbidden)
    with pytest.raises(ValueError, match="authorization"):
        runner.intake(Path("."), {"mode": "authorized_xls", "legacy_sealed_test": True})


@pytest.mark.parametrize(
    "defect",
    [
        "invalid_date_count",
        "null_quantity_row_count",
        "negative_quantity_row_count",
        "duplicate_row_count",
    ],
)
def test_new_source_defects_never_silently_dropped(monkeypatch, defect):
    profile = dict.fromkeys(
        (
            "invalid_date_count",
            "null_quantity_row_count",
            "negative_quantity_row_count",
            "duplicate_row_count",
        ),
        0,
    )
    profile[defect] = 1
    monkeypatch.setattr(runner, "parse_source", lambda *args: {"profile": profile, "rows": []})
    spec = {
        "mode": "authorized_xls",
        "authorization_reference": "unit fixture",
        "legacy_sealed_test": False,
        "path": "synthetic.xls",
        "source_hash": "a" * 64,
    }
    with pytest.raises(ValueError, match="unresolved"):
        runner.intake(Path("."), spec)
