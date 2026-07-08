from pathlib import Path

import pytest

# Slice 1 Batch 4 marker annotation: this file is owned by the
# `postgres-migration` shard per ci-shard-manifest.yml.
pytestmark = [pytest.mark.postgres, pytest.mark.migration]


def test_task0_alembic_baseline_revision_exists():
    revision_path = Path("backend/alembic/versions/0001_task0_baseline.py")

    assert revision_path.exists()
    source = revision_path.read_text()
    assert 'revision: str = "0001_task0_baseline"' in source
    assert "down_revision: str | None = None" in source
    assert "def upgrade() -> None:" in source
    assert "def downgrade() -> None:" in source
