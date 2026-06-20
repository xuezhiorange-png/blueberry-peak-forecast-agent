import pytest

from backend.app.etl.history.importer import (
    BUSINESS_FINGERPRINT_QUERY_BATCH_SIZE,
    _existing_business_rows,
)


class _FakeSession:
    def __init__(self) -> None:
        self.batch_sizes: list[int] = []

    async def execute(self, statement):  # noqa: ANN001
        criterion = next(iter(statement._where_criteria))
        self.batch_sizes.append(len(criterion.right.value))
        return []


@pytest.mark.asyncio
async def test_existing_business_row_lookup_batches_large_fingerprint_sets() -> None:
    session = _FakeSession()
    fingerprints = {
        f"fp-{index:06d}" for index in range(BUSINESS_FINGERPRINT_QUERY_BATCH_SIZE * 14 + 123)
    }

    result = await _existing_business_rows(session, fingerprints)

    assert result == {}
    assert len(session.batch_sizes) == 15
    assert max(session.batch_sizes) <= BUSINESS_FINGERPRINT_QUERY_BATCH_SIZE
    assert sum(session.batch_sizes) == len(fingerprints)
