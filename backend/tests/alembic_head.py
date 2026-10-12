"""Current migration graph assertions, distinct from historical revision identity."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def unique_head(config: Config | None = None) -> str:
    if config is None:
        backend = Path(__file__).resolve().parents[1]
        config = Config(str(backend / "alembic.ini"))
        config.set_main_option("script_location", str(backend / "alembic"))
    return assert_unique_head(ScriptDirectory.from_config(config))


def assert_unique_head(script: ScriptDirectory) -> str:
    heads = script.get_heads()
    assert len(heads) == 1, f"Expected exactly one Alembic head, got {heads!r}"
    head = heads[0]
    assert head, "Alembic head must be nonempty"
    revisions = {revision.revision for revision in script.iterate_revisions(head, "base")}
    assert "0040_hierarchical_forecast" in revisions, "Historical 0040 must remain an ancestor"
    return head
