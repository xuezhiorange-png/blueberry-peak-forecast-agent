from pathlib import Path


def test_round_a_excluded_surfaces_are_not_created() -> None:
    root = Path("backend/app/forecast_quality")
    for name in (
        "calculator_cumulative.py",
        "peak.py",
        "quantile.py",
        "comparison.py",
        "persistence.py",
        "repository.py",
        "application.py",
        "__init__.py",
    ):
        assert not (root / name).exists()
    assert not Path("backend/app/models").joinpath("forecast_quality.py").exists()
