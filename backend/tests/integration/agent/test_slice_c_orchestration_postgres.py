"""Real PostgreSQL acceptance evidence for TASK-013 Slice C Phase C1."""

import os

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agent.canonical import canonical_json_dumps, sha256_payload
from backend.app.agent.slice_c.engine import validate_citation
from backend.app.models.harvest_state import HarvestStateRun
from backend.app.models.residual_model import ResidualModelPredictionRun
from backend.tests.integration.agent.test_orchestration_postgres import (
    _production_orchestrator,
    _production_postgres_outputs,
    _production_request,
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
    assert output.provenance["task12_authority"] is None
    assert output.daily_curve
    assert output.peak

    dumped = output.model_dump(mode="json")
    source = {
        key: dumped[key]
        for key in (
            "request_id",
            "request_status",
            "normalized_request",
            "resolved_location",
            "parameters",
            "daily_curve",
            "peak",
            "citations",
            "confidence",
            "provenance",
            "blockers",
            "warnings",
        )
    }
    numerical_citations = [
        paragraph.citation
        for section in output.explanation.structured_payload
        for paragraph in section.paragraphs
        if paragraph.citation is not None and paragraph.kind == "AUTHORITATIVE_VALUE"
    ]
    assert numerical_citations
    assert output.parameters
    parameter_paragraph = next(
        paragraph
        for section in output.explanation.structured_payload
        for paragraph in section.paragraphs
        if paragraph.template_id == "parameter-value-v1"
    )
    assert parameter_paragraph.citation is not None
    assert output.parameters[0].citation is not None
    assert canonical_json_dumps(
        parameter_paragraph.citation.model_dump(mode="json")
    ) == canonical_json_dumps(output.parameters[0].citation.model_dump(mode="json"))
    assert all(citation.authorities for citation in numerical_citations)
    assert all("TASK_013" not in citation.source_tasks for citation in numerical_citations)
    assert all("TASK_012" not in citation.source_tasks for citation in numerical_citations)
    assert all(citation.tags == ["OVERRIDE_APPLIED"] for citation in numerical_citations)
    assert all(citation.override_refs for citation in numerical_citations)
    assert all(
        citation.override_refs[0].source_attestation == "slice-c-postgres-fixture"
        for citation in numerical_citations
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
    assert output.explanation.agent_explanation_hash == sha256_payload(
        output.explanation.model_dump(mode="python", exclude={"agent_explanation_hash"})
    )
    assert output.recommendations.agent_recommendations_hash == sha256_payload(
        output.recommendations.model_dump(mode="python", exclude={"agent_recommendations_hash"})
    )
    agent_payload = output.model_dump(mode="python")
    agent_hash = agent_payload["provenance"]["agent_forecast_output_hash"]
    agent_payload["provenance"]["agent_forecast_output_hash"] = None
    assert agent_hash == sha256_payload(agent_payload)

    before = (
        await transactional_pg_session.scalar(select(func.count()).select_from(HarvestStateRun)),
        await transactional_pg_session.scalar(
            select(func.count()).select_from(ResidualModelPredictionRun)
        ),
    )
    replay = await _production_orchestrator().execute(
        transactional_pg_session,
        request=_production_request(),
        request_received_at=output.normalized_request.request_received_at,
    )
    after = (
        await transactional_pg_session.scalar(select(func.count()).select_from(HarvestStateRun)),
        await transactional_pg_session.scalar(
            select(func.count()).select_from(ResidualModelPredictionRun)
        ),
    )
    assert before == after
    assert canonical_json_dumps(replay.model_dump(mode="json")) == canonical_json_dumps(
        output.model_dump(mode="json")
    )
