from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_i5_adds_validation_endpoints_without_commit_or_later_scope() -> None:
    migration = ROOT / "alembic" / "versions" / "0019_actual_harvest_validation_evidence.py"
    assert migration.exists()
    assert 'revision = "0019_actual_harvest_validation_evidence"' in migration.read_text()
    assert 'down_revision = "0018_actual_harvest_import_staging"' in migration.read_text()
    router = (ROOT / "app" / "api" / "actual_harvest_imports.py").read_text()
    assert '"/imports/{import_id}/validate"' in router
    assert '"/imports/{import_id}/errors"' in router
    assert '"/imports/{import_id}/commit"' not in router
    assert "identity_mapping" not in router.lower()
    assert "label_snapshot" not in router.lower()
    assert "backtest" not in router.lower()


def test_alembic_head_revision_is_unchanged_in_source() -> None:
    versions = list((ROOT / "alembic" / "versions").glob("*.py"))
    assert any(
        'revision = "0018_actual_harvest_import_staging"' in path.read_text() for path in versions
    )
