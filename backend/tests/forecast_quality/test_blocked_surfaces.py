from pathlib import Path


def test_round_b_surface_boundary_is_preserved() -> None:
    forecast_quality_root = Path("backend/app/forecast_quality")
    for blocked_name in (
        "calculator_cumulative.py",
        "peak.py",
        "quantile.py",
        "repository.py",
        "application.py",
        "__init__.py",
    ):
        assert not (forecast_quality_root / blocked_name).exists()

    assert (forecast_quality_root / "persistence.py").is_file()
    assert (forecast_quality_root / "comparison.py").is_file()
    assert Path("backend/app/models/forecast_quality.py").is_file()
