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
    # v0.2-S1 adds the /commit endpoint on the same router; the
    # original "commit not in router" assertion was an I5-only
    # invariant that S1 explicitly upgrades. We move that guarantee
    # to a separate "no later scope" assertion below.
    assert "identity_mapping" not in router.lower()
    assert "label_snapshot" not in router.lower()
    assert "backtest" not in router.lower()


def test_v0_2_s1_adds_commit_endpoint_without_later_scope() -> None:
    """v0.2-S1 introduces the atomic-commit endpoint while still keeping
    I7+ (label_snapshot, backtest, aggregation) out of scope.
    """
    router = (ROOT / "app" / "api" / "actual_harvest_imports.py").read_text()
    assert '"/imports/{import_id}/commit"' in router
    # I7+ scope terms must NOT appear as actual route handlers. The
    # string ``active_label_created`` is a pre-existing response flag on
    # the preview endpoint and is NOT a forbidden scope term in itself.
    forbidden = (
        "cutoff",
        "winner_selection",
        "canonical_grain_aggregation",
        "evaluation_label_snapshot",
    )
    lowered = router.lower()
    for needle in forbidden:
        assert needle not in lowered, (
            f"forbidden S2+ scope term {needle!r} found in router"
        )
    # The router MUST NOT register /imports/{id}/label_snapshot or
    # /imports/{id}/backtest endpoints. Use a substring check.
    assert "/label_snapshot" not in router
    assert "/backtest" not in router


def test_alembic_head_revision_is_unchanged_in_source() -> None:
    versions = list((ROOT / "alembic" / "versions").glob("*.py"))
    assert any(
        'revision = "0018_actual_harvest_import_staging"' in path.read_text() for path in versions
    )
