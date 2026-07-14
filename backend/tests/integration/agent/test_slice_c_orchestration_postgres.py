"""Real PostgreSQL acceptance evidence for TASK-013 Slice C Phase C1."""

import os

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agent.canonical import canonical_json_dumps
from backend.app.agent.slice_c.engine import validate_citation
from backend.tests.integration.agent.test_orchestration_postgres import (
    _production_postgres_outputs,
)


@pytest.mark.postgres
@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("RUN_POSTGRES_INTEGRATION") != "1",
    reason="set RUN_POSTGRES_INTEGRATION=1 for real PostgreSQL evidence",
)
async def test_slice_c_orchestration_uses_real_postgres_authorities(
    transactional_pg_session: AsyncSession,
) -> None:
    output, repeated, _ = await _production_postgres_outputs(transactional_pg_session)

    assert len(output.explanation.structured_payload) == 8
    assert len(output.recommendations.decisions) == 7
    assert all(
        decision.status == "BLOCKED"
        and decision.reason_code == "REQUIRED_THRESHOLD_MISSING"
        and decision.advisory_text is None
        for decision in output.recommendations.decisions[:6]
    )
    assert output.recommendations.decisions[-1].category == "MISSING_DATA_IMPACT"
    assert output.provenance["task8_authority"] is not None
    assert output.provenance["task9_authority"] is not None
    assert output.provenance["task10_authority"] is not None
    assert output.daily_curve
    assert output.peak

    source = output.model_dump(
        mode="json",
        exclude={"explanation", "recommendations"},
    )
    for section in output.explanation.structured_payload:
        for paragraph in section.paragraphs:
            for pointer in paragraph.evidence_field_paths:
                assert pointer.startswith("/")
            if paragraph.citation is not None:
                validate_citation(source, paragraph.citation)
    for decision in output.recommendations.decisions:
        for evidence in decision.evidence:
            validate_citation(source, evidence.citation)

    assert canonical_json_dumps(output.model_dump(mode="json")) == canonical_json_dumps(
        repeated.model_dump(mode="json")
    )
