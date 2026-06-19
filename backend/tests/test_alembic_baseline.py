from pathlib import Path


def test_task0_alembic_baseline_revision_exists():
    revision_path = Path("backend/alembic/versions/0001_task0_baseline.py")

    assert revision_path.exists()
    source = revision_path.read_text()
    assert 'revision: str = "0001_task0_baseline"' in source
    assert "down_revision: str | None = None" in source
    assert "def upgrade() -> None:" in source
    assert "def downgrade() -> None:" in source
