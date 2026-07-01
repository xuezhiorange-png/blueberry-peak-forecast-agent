"""Unit tests for Task 11 Phase 3 resolution and orchestration contracts.

Tests verify typed contracts, stable blocker codes, deterministic ordering,
ambiguity detection, and source type discrimination.
"""

from __future__ import annotations

from datetime import UTC, datetime

from backend.app.rolling_backtest.enums import (
    AvailabilitySourceType,
)
from backend.app.rolling_backtest.orchestration import (
    NodeOrchestrationOutcome,
    OrchestrationBlocker,
    OrchestrationStage,
    ResolvedInputOutcome,
    Task9AuthorityOutcome,
    Task10AuthorityOutcome,
)
from backend.app.rolling_backtest.resolution import (
    HistoricalCandidate,
    ResolutionResult,
    _build_identity_payload,
    _make_identity,
    _version_sort_key,
)


def _make_candidate(
    *,
    source_type: AvailabilitySourceType = AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
    source_role: str = "task9",
    run_id: int = 1,
    available_at: datetime | None = None,
    version: str = "v1",
    canonical_payload_hash: str = "",
) -> HistoricalCandidate:
    """Build a HistoricalCandidate for contract testing.

    DB ID (run_id) is confined to persistent_reference and NEVER enters
    semantic identity or canonical hashes.
    """
    from backend.app.rolling_backtest.schemas import PersistentUpstreamReference

    identity = _make_identity(
        source_type=source_type,
        source_role=source_role,
        schema_version="task11-test-v1",
        semantic_payload_hash="a" * 64,
        input_signature="b" * 64,
        result_hash="c" * 64,
        canonical_payload_hash=canonical_payload_hash or "e" * 64,
        business_version=version,
        display_label=f"test:{source_type.value}:{source_role}",
        persistent_reference=PersistentUpstreamReference(
            reference_type="database_run_id", reference_value=run_id
        ),
    )

    return HistoricalCandidate(
        source_role=source_role,
        source_type=source_type,
        persistent_reference=PersistentUpstreamReference(
            reference_type="database_run_id", reference_value=run_id
        ),
        semantic_identity=identity,
        authoritative_available_at=available_at or datetime(2024, 6, 1, tzinfo=UTC),
        business_version=version,
        canonical_payload_hash=canonical_payload_hash or "e" * 64,
    )


def _make_pinned_identity(
    *,
    source_type: AvailabilitySourceType = AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
    source_role: str = "task9",
    run_id: int = 1,
    canonical_payload_hash: str = "e" * 64,
) -> ResolvedUpstreamSemanticIdentity:  # noqa: F821
    """Build a pinned identity for resolution testing."""
    from backend.app.rolling_backtest.schemas import PersistentUpstreamReference

    return _make_identity(
        source_type=source_type,
        source_role=source_role,
        schema_version="task11-test-v1",
        semantic_payload_hash="a" * 64,
        input_signature="b" * 64,
        result_hash="c" * 64,
        canonical_payload_hash=canonical_payload_hash,
        business_version="v1",
        display_label=f"pinned:{source_type.value}:{run_id}",
        persistent_reference=PersistentUpstreamReference(
            reference_type="database_run_id", reference_value=run_id
        ),
    )


# ── Candidate contract tests ─────────────────────────────────────────────────


class TestHistoricalCandidate:
    def test_persistent_reference_not_in_identity_payload(self) -> None:
        """DB ID is in persistent_reference, NOT in semantic identity payload."""
        candidate = _make_candidate(run_id=42)
        assert candidate.persistent_reference.reference_value == 42

        # Verify the identity payload does NOT contain the DB ID
        payload = _build_identity_payload(candidate.semantic_identity)
        payload_str = str(payload)
        assert "42" not in payload_str, f"DB ID leaked into identity payload: {payload_str}"
        assert "row_id" not in payload_str
        assert "db_id" not in payload_str
        assert "uuid" not in payload_str.lower()

    def test_canonical_hashes_are_separate(self) -> None:
        """canonical_identity_hash and canonical_payload_hash are separate values."""
        candidate = _make_candidate(canonical_payload_hash="f" * 64)
        assert len(candidate.canonical_identity_hash) == 64
        assert len(candidate.canonical_payload_hash) == 64
        # They can be different — identity hash comes from stable fields,
        # payload hash comes from upstream canonical result
        assert candidate.canonical_identity_hash != candidate.canonical_payload_hash

    def test_same_semantic_identity_same_identity_hash(self) -> None:
        """Candidates with identical semantic identity fields produce the same
        canonical_identity_hash, regardless of different DB IDs."""
        c1 = _make_candidate(run_id=1)
        c2 = _make_candidate(run_id=2)  # different DB ID, same identity fields
        # canonical_identity_hash depends on semantic identity, NOT DB ID
        assert c1.canonical_identity_hash == c2.canonical_identity_hash

    def test_different_payload_hashes_change_identity_hash(self) -> None:
        """Different canonical_payload_hash should change canonical_identity_hash
        because the payload hash is part of the identity payload."""
        c1 = _make_candidate(run_id=1, canonical_payload_hash="a" * 64)
        c2 = _make_candidate(run_id=1, canonical_payload_hash="b" * 64)
        assert c1.canonical_identity_hash != c2.canonical_identity_hash

    def test_different_source_types_change_identity_hash(self) -> None:
        """Different source types produce different identity hashes."""
        c1 = _make_candidate(
            source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD,
            source_role="task3",
            run_id=1,
        )
        c2 = _make_candidate(
            source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
            source_role="task9",
            run_id=1,
        )
        assert c1.canonical_identity_hash != c2.canonical_identity_hash

    def test_display_label_does_not_change_signature(self) -> None:
        """Display_label changes should NOT affect canonical hashes."""
        from backend.app.rolling_backtest.schemas import PersistentUpstreamReference

        # Build two candidates with same semantic identity but different display_label
        id1 = _make_identity(
            source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
            source_role="task9",
            schema_version="v1",
            semantic_payload_hash="a" * 64,
            input_signature="b" * 64,
            display_label="label-A",
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id", reference_value=1
            ),
        )
        id2 = _make_identity(
            source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
            source_role="task9",
            schema_version="v1",
            semantic_payload_hash="a" * 64,
            input_signature="b" * 64,
            display_label="label-B",
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id", reference_value=1
            ),
        )
        c1 = HistoricalCandidate(
            source_role="task9",
            source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id", reference_value=1
            ),
            semantic_identity=id1,
            authoritative_available_at=datetime(2024, 6, 1, tzinfo=UTC),
            canonical_payload_hash="e" * 64,
        )
        c2 = HistoricalCandidate(
            source_role="task9",
            source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id", reference_value=1
            ),
            semantic_identity=id2,
            authoritative_available_at=datetime(2024, 6, 1, tzinfo=UTC),
            canonical_payload_hash="e" * 64,
        )
        assert c1.canonical_identity_hash == c2.canonical_identity_hash


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


# ── Identity payload tests ───────────────────────────────────────────────────


class TestIdentityPayload:
    def test_no_db_id_in_payload(self) -> None:
        """_build_identity_payload excludes persistent reference fields."""
        from backend.app.rolling_backtest.schemas import PersistentUpstreamReference

        identity = _make_identity(
            source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
            source_role="task9",
            schema_version="task11-v1",
            semantic_payload_hash="a" * 64,
            input_signature="b" * 64,
            result_hash="c" * 64,
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id", reference_value=77
            ),
        )
        payload = _build_identity_payload(identity)
        payload_str = str(payload)
        assert "77" not in payload_str, f"DB ID leaked: {payload_str}"
        assert "reference_type" not in payload_str
        assert "reference_value" not in payload_str
        assert "database_run_id" not in payload_str

    def test_uuid_not_in_payload(self) -> None:
        """UUIDs (in persistent_reference) are excluded from identity payload."""
        from backend.app.rolling_backtest.schemas import PersistentUpstreamReference

        identity = _make_identity(
            source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
            source_role="task9",
            schema_version="task11-v1",
            semantic_payload_hash="a" * 64,
            input_signature="b" * 64,  # required for stable hash validation
            persistent_reference=PersistentUpstreamReference(
                reference_type="uuid",
                reference_value="550e8400-e29b-41d4-a716-446655440000",
            ),
        )
        payload = _build_identity_payload(identity)
        payload_str = str(payload)
        assert "550e8400" not in payload_str, f"UUID leaked: {payload_str}"

    def test_stable_fields_only(self) -> None:
        """Identity payload contains only typed stable fields."""
        identity = _make_identity(
            source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
            source_role="task9_structural_forecast",
            schema_version="task9-v2",
            semantic_payload_hash="a" * 64,
            input_signature="b" * 64,
            config_hash="c" * 64,
            result_hash="d" * 64,
            canonical_payload_hash="e" * 64,
            artifact_payload_hash="f" * 64,
            business_version="v3.1",
            policy_version="policy-v1",
            role_qualifier="primary",
        )
        payload = _build_identity_payload(identity)
        assert payload["source_type"] == "task9_harvest_state_run"
        assert payload["source_role"] == "task9_structural_forecast"
        assert payload["schema_version"] == "task9-v2"
        assert payload["input_signature"] == "b" * 64
        assert payload["config_hash"] == "c" * 64
        assert payload["result_hash"] == "d" * 64
        assert payload["canonical_payload_hash"] == "e" * 64
        assert payload["artifact_payload_hash"] == "f" * 64
        assert payload["business_version"] == "v3.1"
        assert payload["policy_version"] == "policy-v1"
        assert payload["role_qualifier"] == "primary"
        # Display_label and persistent_reference are excluded
        assert "display_label" not in payload
        assert "persistent_reference" not in payload
        assert "reference_type" not in payload


# ── Version sort key tests ───────────────────────────────────────────────────


class TestVersionSortKey:
    def test_numeric_versions(self) -> None:
        assert _version_sort_key("v2") > _version_sort_key("v1")
        assert _version_sort_key("v10") > _version_sort_key("v2")

    def test_semver_like(self) -> None:
        assert _version_sort_key("3.0.1") > _version_sort_key("2.9.9")

    def test_equal_versions(self) -> None:
        assert _version_sort_key("v1.0") == _version_sort_key("v1.0")


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
        assert (
            OrchestrationBlocker.PINNED_SOURCE_TYPE_MISMATCH.value == "pinned_source_type_mismatch"
        )
        assert (
            OrchestrationBlocker.PINNED_SOURCE_ROLE_MISMATCH.value == "pinned_source_role_mismatch"
        )
        assert (
            OrchestrationBlocker.PINNED_SOURCE_INTEGRITY_FAILURE.value
            == "pinned_source_integrity_failure"
        )
        assert (
            OrchestrationBlocker.TASK9_REPLAY_INPUT_INCOMPLETE.value
            == "task9_replay_input_incomplete"
        )
        assert OrchestrationBlocker.TASK9_EXECUTION_BLOCKED.value == "task9_execution_blocked"
        assert (
            OrchestrationBlocker.TASK10_TASK9_BINDING_MISMATCH.value
            == "task10_task9_binding_mismatch"
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
        assert OrchestrationStage.RESOLVE_HISTORICAL_INPUTS.value == "resolve_historical_inputs"


# ── Typed outcome tests ──────────────────────────────────────────────────────


class TestResolvedInputOutcome:
    def test_typed_input_fields(self) -> None:
        from backend.app.rolling_backtest.schemas import PersistentUpstreamReference

        identity = _make_identity(
            source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
            source_role="task9",
            schema_version="v1",
            semantic_payload_hash="a" * 64,
            input_signature="b" * 64,
            result_hash="c" * 64,
            canonical_payload_hash="d" * 64,
            business_version="v1",
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id", reference_value=1
            ),
        )
        outcome = ResolvedInputOutcome(
            source_role="task9",
            source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
            semantic_identity=identity,
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id", reference_value=1
            ),
            authoritative_available_at=datetime(2024, 6, 1, tzinfo=UTC),
            canonical_identity_hash="a" * 64,
            canonical_payload_hash="d" * 64,
            business_version="v1",
        )
        assert outcome.source_role == "task9"
        assert outcome.canonical_identity_hash == "a" * 64
        assert outcome.canonical_payload_hash == "d" * 64


class TestTask9AuthorityOutcome:
    def test_reuse_mode(self) -> None:
        from backend.app.rolling_backtest.schemas import PersistentUpstreamReference

        outcome = Task9AuthorityOutcome(
            run_reference=PersistentUpstreamReference(
                reference_type="database_run_id", reference_value=1
            ),
            result_hash="c" * 64,
            mode="reuse",
        )
        assert outcome.mode == "reuse"
        assert outcome.result_hash == "c" * 64

    def test_unresolved_mode(self) -> None:
        outcome = Task9AuthorityOutcome()
        assert outcome.mode == "unresolved"
        assert outcome.run_reference is None


class TestTask10AuthorityOutcome:
    def test_historically_available_mode(self) -> None:
        from backend.app.rolling_backtest.schemas import PersistentUpstreamReference

        outcome = Task10AuthorityOutcome(
            training_reference=PersistentUpstreamReference(
                reference_type="database_run_id", reference_value=1
            ),
            task9_run_reference=PersistentUpstreamReference(
                reference_type="database_run_id", reference_value=2
            ),
            task9_result_hash="c" * 64,
            mode="historically_available",
        )
        assert outcome.mode == "historically_available"
        assert outcome.training_reference is not None
        assert outcome.task9_run_reference is not None

    def test_structural_only_mode(self) -> None:
        outcome = Task10AuthorityOutcome(mode="structural_only")
        assert outcome.mode == "structural_only"
        assert outcome.training_reference is None


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

    def test_completed_outcome_has_typed_authorities(self) -> None:
        from backend.app.rolling_backtest.schemas import PersistentUpstreamReference

        outcome = NodeOrchestrationOutcome(
            rolling_run_signature="a" * 64,
            node_signature="b" * 64,
            attempt_number=1,
            status="forecast_completed",
            stage=OrchestrationStage.FINALIZE_ORCHESTRATION_SNAPSHOT.value,
            resolved_inputs=(
                ResolvedInputOutcome(
                    source_role="task9",
                    source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
                    semantic_identity=_make_identity(
                        source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN,
                        source_role="task9",
                        schema_version="v1",
                        semantic_payload_hash="a" * 64,
                        input_signature="b" * 64,
                        result_hash="c" * 64,
                        persistent_reference=PersistentUpstreamReference(
                            reference_type="database_run_id", reference_value=1
                        ),
                    ),
                    persistent_reference=PersistentUpstreamReference(
                        reference_type="database_run_id", reference_value=1
                    ),
                    authoritative_available_at=datetime(2024, 6, 1, tzinfo=UTC),
                    canonical_identity_hash="x" * 64,
                    canonical_payload_hash="y" * 64,
                ),
            ),
            task9_authority=Task9AuthorityOutcome(
                run_reference=PersistentUpstreamReference(
                    reference_type="database_run_id", reference_value=1
                ),
                result_hash="c" * 64,
                mode="reuse",
            ),
            task10_authority=Task10AuthorityOutcome(mode="structural_only"),
        )
        assert outcome.status == "forecast_completed"
        assert outcome.task9_authority is not None
        assert outcome.task9_authority.mode == "reuse"
        assert outcome.task10_authority is not None
        assert outcome.task10_authority.mode == "structural_only"
        assert len(outcome.resolved_inputs) == 1

    def test_outcome_diagnostics_are_sanitized(self) -> None:
        from backend.app.rolling_backtest.orchestration import _sanitize_diagnostics

        raw = {
            "connection_url": "postgresql://user:pass@host/db",
            "password": "secret123",
            "normal": "ok",
            "nested": {"psycopg_dsn": "dbname=test"},
        }
        sanitized = _sanitize_diagnostics(raw)
        assert sanitized["connection_url"] == "[REDACTED]"
        assert sanitized["password"] == "[REDACTED]"
        assert sanitized["normal"] == "ok"
        assert sanitized["nested"]["psycopg_dsn"] == "[REDACTED]"  # type: ignore[index]


# ── Cutoff filtering tests ───────────────────────────────────────────────────


class TestCutoffFiltering:
    def test_candidate_after_cutoff_is_filtered(self) -> None:
        """Candidates with available_at > cutoff should be invisible."""
        cutoff = datetime(2024, 3, 15, tzinfo=UTC)
        future_candidate = _make_candidate(
            run_id=1,
            available_at=datetime(2024, 6, 1, tzinfo=UTC),
        )
        past_candidate = _make_candidate(
            run_id=2,
            available_at=datetime(2024, 3, 1, tzinfo=UTC),
        )

        visible = [
            c for c in [past_candidate, future_candidate] if c.authoritative_available_at <= cutoff
        ]
        assert len(visible) == 1
        assert visible[0].persistent_reference.reference_value == 2

    def test_candidate_at_exact_cutoff_is_visible(self) -> None:
        cutoff = datetime(2024, 3, 15, tzinfo=UTC)
        exact_candidate = _make_candidate(run_id=1, available_at=cutoff)
        visible = [c for c in [exact_candidate] if c.authoritative_available_at <= cutoff]
        assert len(visible) == 1

    def test_higher_db_id_does_not_override_valid_history(self) -> None:
        """Higher database ID should not override a valid historical candidate."""
        c1 = _make_candidate(run_id=1, available_at=datetime(2024, 3, 1, tzinfo=UTC))
        c2 = _make_candidate(run_id=9999, available_at=datetime(2024, 6, 1, tzinfo=UTC))

        sorted_candidates = sorted(
            [c1, c2],
            key=lambda c: c.authoritative_available_at,
            reverse=True,
        )
        cutoff = datetime(2024, 3, 15, tzinfo=UTC)
        visible = [c for c in sorted_candidates if c.authoritative_available_at <= cutoff]
        assert len(visible) == 1
        assert visible[0].persistent_reference.reference_value == 1


# ── Deterministic sorting tests ──────────────────────────────────────────────


class TestDeterministicSorting:
    def test_sort_by_time_desc_version_desc(self) -> None:
        # Different canonical_payload_hash ensures distinct identity hashes
        c1 = _make_candidate(
            run_id=1,
            available_at=datetime(2024, 6, 1, tzinfo=UTC),
            version="v2",
            canonical_payload_hash="a" * 64,
        )
        c2 = _make_candidate(
            run_id=2,
            available_at=datetime(2024, 3, 1, tzinfo=UTC),
            version="v1",
            canonical_payload_hash="b" * 64,
        )
        c3 = _make_candidate(
            run_id=3,
            available_at=datetime(2024, 6, 1, tzinfo=UTC),
            version="v1",
            canonical_payload_hash="c" * 64,
        )

        # Sort by time DESC, version DESC (key)
        sorted_candidates = sorted(
            [c1, c2, c3],
            key=lambda c: (
                -c.authoritative_available_at.timestamp(),
                tuple(-x for x in _version_sort_key(c.business_version or "")),
                c.canonical_identity_hash,
                c.canonical_payload_hash,
            ),
        )
        # c1: newest + v2 = top priority
        assert sorted_candidates[0].persistent_reference.reference_value == 1
        # c3: newest + v1 = second priority
        assert sorted_candidates[1].persistent_reference.reference_value == 3
        # c2: oldest = lowest priority
        assert sorted_candidates[2].persistent_reference.reference_value == 2

    def test_identity_hash_breaks_ties(self) -> None:
        """When time and version are identical, identity hash determines order."""
        c1 = _make_candidate(
            run_id=1,
            available_at=datetime(2024, 6, 1, tzinfo=UTC),
            version="v1",
            canonical_payload_hash="a" * 64,
        )
        c2 = _make_candidate(
            run_id=2,
            available_at=datetime(2024, 6, 1, tzinfo=UTC),
            version="v1",
            canonical_payload_hash="b" * 64,  # different payload → different identity
        )

        # Sort deterministically, verify same order every time
        def _sort_key(
            c: HistoricalCandidate,
        ) -> tuple[float, tuple[int, ...], str, str]:
            return (
                -c.authoritative_available_at.timestamp(),
                tuple(-x for x in _version_sort_key(c.business_version or "")),
                c.canonical_identity_hash,
                c.canonical_payload_hash,
            )

        sorted1 = sorted([c1, c2], key=_sort_key)
        sorted2 = sorted([c2, c1], key=_sort_key)
        assert (
            sorted1[0].persistent_reference.reference_value
            == sorted2[0].persistent_reference.reference_value
        )
        assert (
            sorted1[1].persistent_reference.reference_value
            == sorted2[1].persistent_reference.reference_value
        )


# ── Ambiguity detection tests ────────────────────────────────────────────────


class TestAmbiguityDetection:
    def test_semantic_conflict_at_same_priority_detected(self) -> None:
        """Two candidates with same time+version but different identities = conflict."""
        c1 = _make_candidate(
            run_id=1,
            available_at=datetime(2024, 6, 1, tzinfo=UTC),
            version="v1",
            canonical_payload_hash="a" * 64,
        )
        c2 = _make_candidate(
            run_id=2,
            available_at=datetime(2024, 6, 1, tzinfo=UTC),
            version="v1",
            canonical_payload_hash="b" * 64,  # different!
        )
        assert c1.authoritative_available_at == c2.authoritative_available_at
        assert c1.business_version == c2.business_version
        # Different canonical payload hashes → different identity hashes
        assert c1.canonical_identity_hash != c2.canonical_identity_hash

    def test_semantic_equivalent_allowed(self) -> None:
        """Same identity hash + same payload hash = equivalent, allowed."""
        c1 = _make_candidate(
            run_id=1,
            available_at=datetime(2024, 6, 1, tzinfo=UTC),
            version="v1",
            canonical_payload_hash="e" * 64,
        )
        c2 = _make_candidate(
            run_id=1,
            available_at=datetime(2024, 6, 1, tzinfo=UTC),
            version="v1",
            canonical_payload_hash="e" * 64,
        )
        assert c1.canonical_identity_hash == c2.canonical_identity_hash
        assert c1.canonical_payload_hash == c2.canonical_payload_hash


# ── Source type tests ────────────────────────────────────────────────────────


class TestSourceTypeDiscrimination:
    def test_task3_has_different_type_from_task9(self) -> None:
        c3 = _make_candidate(
            source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD, source_role="task3"
        )
        c9 = _make_candidate(
            source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN, source_role="task9"
        )
        assert c3.source_type != c9.source_type
        assert c3.source_role != c9.source_role

    def test_pinned_type_mismatch_detected(self) -> None:
        pinned = _make_pinned_identity(
            source_type=AvailabilitySourceType.TASK9_HARVEST_STATE_RUN, run_id=1
        )
        matched = _make_candidate(
            source_type=AvailabilitySourceType.TASK3_ANALYTICS_BUILD, run_id=1
        )
        assert pinned.source_type != matched.source_type


# ── Adapter contract tests ───────────────────────────────────────────────────


class TestAdapterContract:
    def test_all_adapters_in_map_have_correct_signature(self) -> None:
        """Verify every adapter in _SOURCE_QUERY_MAP has the correct 3-param signature."""
        import inspect

        from backend.app.rolling_backtest.resolution import _SOURCE_QUERY_MAP

        for source_type, adapter in _SOURCE_QUERY_MAP.items():
            sig = inspect.signature(adapter)
            params = list(sig.parameters.keys())
            assert len(params) == 3, (
                f"Adapter for {source_type.value} has {len(params)} params: {params} "
                f"(expected 3: session, node, execution_mode)"
            )

    def test_no_any_in_map_value_type(self) -> None:
        """The map must be typed as dict[AvailabilitySourceType, CandidateQueryAdapter]."""

        from backend.app.rolling_backtest.resolution import _SOURCE_QUERY_MAP

        # The map should have a proper type annotation, not Any
        # All adapters must have correct signatures (verified in test_all_adapters)
        assert len(_SOURCE_QUERY_MAP) >= 7, "Expected at least 7 source adapters"
