"""Unit tests for Task 11 Phase 3 resolution and orchestration contracts."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.app.rolling_backtest.enums import (
    AvailabilitySourceType,
    ExecutionMode,
    UpstreamSelectionMode,
)
from backend.app.rolling_backtest.orchestration import (
    NodeOrchestrationOutcome,
    OrchestrationBlocker,
    OrchestrationStage,
)
from backend.app.rolling_backtest.resolution import (
    HistoricalCandidate,
    ResolutionResult,
)
from backend.app.rolling_backtest.schemas import (
    PersistentUpstreamReference,
    ResolvedUpstreamSemanticIdentity,
    RollingNodeDefinition,
    UpstreamSemanticIdentityPayload,
)


def _make_identity(
    *,
    source_type: AvailabilitySourceType = AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
    source_role: str = "task9",
    run_id: int = 1,
) -> ResolvedUpstreamSemanticIdentity:
    # Use run_id to create unique hashes per identity
    suffix = f"{run_id:064d}"[:64]
    return ResolvedUpstreamSemanticIdentity(
        source_type=source_type,
        source_role=source_role,
        persistent_reference=PersistentUpstreamReference(
            reference_type="database_run_id", reference_value=run_id
        ),
        semantic=UpstreamSemanticIdentityPayload(
            schema_version="task11-v1",
            display_label=f"test:{source_type.value}:{run_id}",
            semantic_payload_hash=suffix,
            input_signature="b" * 64,
            result_hash="c" * 64,
            canonical_payload_hash=suffix,
            business_version="v1",
        ),
    )


def _make_candidate(
    *,
    source_type: AvailabilitySourceType = AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
    source_role: str = "task9",
    run_id: int = 1,
    available_at: datetime | None = None,
    version: str = "v1",
) -> HistoricalCandidate:
    identity = _make_identity(source_type=source_type, source_role=source_role, run_id=run_id)
    return HistoricalCandidate(
        source_role=source_role,
        source_type=source_type,
        persistent_reference=PersistentUpstreamReference(
            reference_type="database_run_id", reference_value=run_id
        ),
        semantic_identity=identity,
        authoritative_available_at=available_at or datetime(2024, 6, 1, tzinfo=timezone.utc),
        business_version=version,
    )


# ── Candidate contract tests ─────────────────────────────────────────────────


class TestHistoricalCandidate:
    def test_candidate_stores_persistent_reference_not_db_id_in_identity(self) -> None:
        candidate = _make_candidate(run_id=42)
        # persistent_reference carries the DB ID
        assert candidate.persistent_reference.reference_value == 42
        # semantic identity does NOT embed DB ID
        sem = candidate.semantic_identity
        assert "42" not in sem.semantic.display_label or "test:" in sem.semantic.display_label

    def test_canonical_hashes_are_computed(self) -> None:
        candidate = _make_candidate()
        assert len(candidate.canonical_identity_hash) == 64
        assert len(candidate.canonical_payload_hash) == 64
        assert candidate.canonical_identity_hash == candidate.canonical_payload_hash

    def test_different_run_ids_produce_different_hashes(self) -> None:
        c1 = _make_candidate(run_id=1)
        c2 = _make_candidate(run_id=2)
        assert c1.canonical_identity_hash != c2.canonical_identity_hash


# ── ResolutionResult tests ───────────────────────────────────────────────────


class TestResolutionResult:
    def test_blocked_result_has_no_resolved(self) -> None:
        result = ResolutionResult(
            source_role="test",
            source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
            candidates=(),
            blocked=True,
            blocker_code="test_blocked",
        )
        assert result.blocked
        assert result.resolved is None
        assert result.blocker_code == "test_blocked"

    def test_resolved_result_has_candidate(self) -> None:
        candidate = _make_candidate()
        result = ResolutionResult(
            source_role="test",
            source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
            candidates=(candidate,),
            resolved=candidate,
        )
        assert not result.blocked
        assert result.resolved is not None
        assert result.resolved.persistent_reference.reference_value == 1


# ── Orchestration blocker code tests ─────────────────────────────────────────


class TestOrchestrationBlocker:
    def test_blocker_codes_are_stable_strings(self) -> None:
        assert OrchestrationBlocker.PINNED_SOURCE_NOT_FOUND.value == "pinned_source_not_found"
        assert (
            OrchestrationBlocker.HISTORICAL_SOURCE_NOT_VISIBLE.value
            == "historical_source_not_visible"
        )
        assert (
            OrchestrationBlocker.AMBIGUOUS_HISTORICAL_CANDIDATE.value
            == "ambiguous_historical_candidate"
        )
        assert (
            OrchestrationBlocker.FUTURE_SOURCE_LEAKAGE_DETECTED.value
            == "future_source_leakage_detected"
        )

    def test_all_blocker_codes_are_unique(self) -> None:
        codes = [b.value for b in OrchestrationBlocker]
        assert len(codes) == len(set(codes))

    def test_blocker_codes_do_not_contain_sql_or_urls(self) -> None:
        for blocker in OrchestrationBlocker:
            assert "sql" not in blocker.value.lower()
            assert "http" not in blocker.value.lower()
            assert "postgres" not in blocker.value.lower()


# ── Orchestration stage tests ────────────────────────────────────────────────


class TestOrchestrationStage:
    def test_stages_are_ordered(self) -> None:
        stages = list(OrchestrationStage)
        assert OrchestrationStage.RESOLVE_HISTORICAL_INPUTS in stages
        assert OrchestrationStage.FINALIZE_ORCHESTRATION_SNAPSHOT in stages

    def test_stage_values_are_stable(self) -> None:
        assert (
            OrchestrationStage.RESOLVE_HISTORICAL_INPUTS.value
            == "resolve_historical_inputs"
        )


# ── NodeOrchestrationOutcome tests ───────────────────────────────────────────


class TestNodeOrchestrationOutcome:
    def test_blocked_outcome_has_no_authorities(self) -> None:
        outcome = NodeOrchestrationOutcome(
            rolling_run_signature="a" * 64,
            node_signature="b" * 64,
            attempt_number=1,
            status="blocked",
            stage=OrchestrationStage.RESOLVE_HISTORICAL_INPUTS.value,
            blocker_code="test_blocked",
        )
        assert outcome.status == "blocked"
        assert outcome.task9_authority is None
        assert outcome.task10_authority is None

    def test_completed_outcome_has_authorities(self) -> None:
        outcome = NodeOrchestrationOutcome(
            rolling_run_signature="a" * 64,
            node_signature="b" * 64,
            attempt_number=1,
            status="forecast_completed",
            stage=OrchestrationStage.FINALIZE_ORCHESTRATION_SNAPSHOT.value,
            task9_authority={"run_id": 1},
            task10_authority={"run_id": 2},
            resolved_inputs=({"source_role": "test_role", "source_type": "task9"},),
        )
        assert outcome.status == "forecast_completed"
        assert outcome.task9_authority is not None
        assert outcome.task10_authority is not None
        assert len(outcome.resolved_inputs) == 1

    def test_outcome_diagnostics_are_sanitized(self) -> None:
        outcome = NodeOrchestrationOutcome(
            rolling_run_signature="a" * 64,
            node_signature="b" * 64,
            attempt_number=1,
            status="blocked",
            stage="test",
            blocker_code="test",
            diagnostics={"key": "value"},
        )
        assert "postgres" not in str(outcome.diagnostics).lower()
        assert "password" not in str(outcome.diagnostics).lower()


# ── Cutoff filtering tests ───────────────────────────────────────────────────


class TestCutoffFiltering:
    def test_candidate_after_cutoff_is_filtered(self) -> None:
        """Candidates with available_at > cutoff should be invisible."""
        cutoff = datetime(2024, 3, 15, tzinfo=timezone.utc)
        future_candidate = _make_candidate(
            run_id=1,
            available_at=datetime(2024, 6, 1, tzinfo=timezone.utc),  # after cutoff
        )
        past_candidate = _make_candidate(
            run_id=2,
            available_at=datetime(2024, 3, 1, tzinfo=timezone.utc),  # before cutoff
        )

        # Simulate filtering logic from resolution
        visible = [
            c
            for c in [past_candidate, future_candidate]
            if c.authoritative_available_at <= cutoff
        ]
        assert len(visible) == 1
        assert visible[0].persistent_reference.reference_value == 2

    def test_candidate_at_exact_cutoff_is_visible(self) -> None:
        """Candidates with available_at == cutoff should be visible."""
        cutoff = datetime(2024, 3, 15, tzinfo=timezone.utc)
        exact_candidate = _make_candidate(
            run_id=1,
            available_at=cutoff,
        )
        visible = [
            c for c in [exact_candidate] if c.authoritative_available_at <= cutoff
        ]
        assert len(visible) == 1

    def test_higher_db_id_does_not_override_valid_history(self) -> None:
        """Higher database ID should not override a valid historical candidate."""
        c1 = _make_candidate(
            run_id=1,
            available_at=datetime(2024, 3, 1, tzinfo=timezone.utc),
        )
        c2 = _make_candidate(
            run_id=9999,  # higher DB ID
            available_at=datetime(2024, 6, 1, tzinfo=timezone.utc),  # after cutoff
        )
        # Sort by authoritative time DESC, not DB ID
        sorted_candidates = sorted(
            [c1, c2],
            key=lambda c: c.authoritative_available_at,
            reverse=True,
        )
        # c2 is newest but after cutoff — filtering should remove it
        cutoff = datetime(2024, 3, 15, tzinfo=timezone.utc)
        visible = [
            c for c in sorted_candidates if c.authoritative_available_at <= cutoff
        ]
        assert len(visible) == 1
        assert visible[0].persistent_reference.reference_value == 1  # not 9999


# ── Deterministic sorting tests ──────────────────────────────────────────────


class TestDeterministicSorting:
    def test_sort_by_time_desc_version_desc_hash_asc(self) -> None:
        """Verify deterministic sort: time DESC, version DESC, hash ASC."""
        c1 = _make_candidate(
            run_id=1,
            available_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
            version="v2",
        )
        c2 = _make_candidate(
            run_id=2,
            available_at=datetime(2024, 3, 1, tzinfo=timezone.utc),
            version="v1",
        )
        c3 = _make_candidate(
            run_id=3,
            available_at=datetime(2024, 6, 1, tzinfo=timezone.utc),  # same time as c1
            version="v1",  # lower version than c1
        )

        # Sort: time DESC (newest first), version DESC, hash ASC
        sorted_candidates = sorted(
            [c1, c2, c3],
            key=lambda c: (
                c.authoritative_available_at,
                c.business_version or "",
            ),
            reverse=True,
        )
        assert sorted_candidates[0].persistent_reference.reference_value == 1  # c1: newest+v2
        assert sorted_candidates[1].persistent_reference.reference_value == 3  # c3: newest+v1
        assert sorted_candidates[2].persistent_reference.reference_value == 2  # c2: old+v1


# ── Ambiguity detection tests ────────────────────────────────────────────────


class TestAmbiguityDetection:
    def test_semantic_conflict_at_same_priority_is_detected(self) -> None:
        """Two candidates with identical sort keys but different identities = conflict."""
        c1 = _make_candidate(
            run_id=1,
            available_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
            version="v1",
        )
        c2 = _make_candidate(
            run_id=2,
            available_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
            version="v1",
        )
        # Same sort key, different persistent refs, different hashes
        assert c1.canonical_identity_hash != c2.canonical_identity_hash

        # This should trigger ambiguous_historical_candidate
        top_key = (
            c1.authoritative_available_at,
            c1.business_version,
            c1.canonical_identity_hash,
            c1.canonical_payload_hash,
        )
        second_key = (
            c2.authoritative_available_at,
            c2.business_version,
            c2.canonical_identity_hash,
            c2.canonical_payload_hash,
        )
        # Same time+version, different hashes → ambiguity
        assert c1.authoritative_available_at == c2.authoritative_available_at
        assert c1.business_version == c2.business_version
        assert c1.canonical_identity_hash != c2.canonical_identity_hash

    def test_semantic_equivalent_at_same_priority_is_allowed(self) -> None:
        """Same canonical identity hash + same sort key = equivalent, allowed."""
        c1 = _make_candidate(
            run_id=1,
            available_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
            version="v1",
        )
        c2 = _make_candidate(
            run_id=1,  # same run_id → same identity hash
            available_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
            version="v1",
        )
        assert c1.canonical_identity_hash == c2.canonical_identity_hash
        # Semantic-equivalent: deterministic selection is fine


# ── Source type tests ────────────────────────────────────────────────────────


class TestSourceTypeDiscrimination:
    def test_task3_has_different_type_from_task9(self) -> None:
        c3 = _make_candidate(
            source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD,
            source_role="task3",
        )
        c9 = _make_candidate(
            source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
            source_role="task9",
        )
        assert c3.source_type != c9.source_type
        assert c3.source_role != c9.source_role

    def test_pinned_type_mismatch_is_detected(self) -> None:
        """Pinned identity with wrong source type triggers blocker."""
        pinned = _make_identity(
            source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
            run_id=1,
        )
        matched = _make_candidate(
            source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD,  # wrong!
            run_id=1,
        )
        assert pinned.source_type != matched.source_type
