from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_i4_does_not_add_migration_or_later_lifecycle_endpoints() -> None:
    assert not list((ROOT / "alembic" / "versions").glob("0019*"))
    router = (ROOT / "app" / "api" / "actual_harvest_imports.py").read_text()
    assert '"/imports/{import_id}/validate"' not in router
    assert '"/imports/{import_id}/errors"' not in router
    assert '"/imports/{import_id}/commit"' not in router
    assert "identity_mapping" not in router.lower()
    assert "label_snapshot" not in router.lower()
    assert "backtest" not in router.lower()


def test_alembic_head_revision_is_unchanged_in_source() -> None:
    versions = list((ROOT / "alembic" / "versions").glob("*.py"))
    assert any(
        'revision = "0018_actual_harvest_import_staging"' in path.read_text() for path in versions
    )
