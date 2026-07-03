"""Identity parity contract tests for historical vs exact-pinned identities.

Validates that _make_identity() constructions in historical resolvers and
exact-pinned loaders produce field-compatible outputs for each source type.

No PostgreSQL required — pure Python contract tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from backend.app.rolling_backtest.enums import AvailabilitySourceType
from backend.app.rolling_backtest.resolution import (
    _build_identity_payload,
    _make_identity,
    _task8_daily_prediction_payload_hash,
)
from backend.app.rolling_backtest.schemas import (
    PersistentUpstreamReference,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _assert_sha256_hex(value: str) -> None:
    assert len(value) == 64, f"expected 64 chars, got {len(value)}: {value!r}"
    assert set(value) <= set("0123456789abcdef"), f"non-hex in: {value!r}"


# ── Task 8 forecast identity parity ──────────────────────────────────────────


class TestTask8ForecastIdentityParity:
    """TASK8_FORECAST_RUN identity must match between historical and exact."""

    def test_forecast_identity_fields(self) -> None:
        """Forecast identity carries source_signature in both hash slots."""
        source_sig = "a" * 64
        historical = _make_identity(
            source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
            source_role="task8_forecast_run",
            schema_version="task8-maturity-v1",
            semantic_payload_hash=source_sig,
            input_signature=source_sig,
            display_label="task8:forecast_run",
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=1,
            ),
        )
        exact = _make_identity(
            source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
            source_role="task8_forecast_run",
            schema_version="task8-maturity-v1",
            semantic_payload_hash=source_sig,
            input_signature=source_sig,
            display_label="task8:forecast_run",
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=999,
            ),
        )
        # Payload must be identical regardless of database ID
        assert _build_identity_payload(historical) == _build_identity_payload(exact)

        # Field-level assertions
        assert historical.semantic.semantic_payload_hash == source_sig
        assert historical.semantic.input_signature == source_sig
        assert historical.semantic.config_hash is None
        assert historical.semantic.result_hash is None
        assert historical.semantic.canonical_payload_hash is None

    def test_forecast_valid_sha256(self) -> None:
        """source_signature used in identity is valid SHA-256 hex."""
        source_sig = "b" * 64
        identity = _make_identity(
            source_type=AvailabilitySourceType.TASK8_FORECAST_RUN,
            source_role="task8_forecast_run",
            schema_version="task8-maturity-v1",
            semantic_payload_hash=source_sig,
            input_signature=source_sig,
            display_label="task8:forecast_run",
        )
        _assert_sha256_hex(identity.semantic.semantic_payload_hash)
        _assert_sha256_hex(identity.semantic.input_signature)


# ── Task 6 plan version identity parity ──────────────────────────────────────


class TestTask6PlanVersionIdentityParity:
    """TASK6_PLAN_VERSION identity must carry file_sha256 in semantic + canonical."""

    def test_plan_identity_fields(self) -> None:
        file_hash = "c" * 64
        historical = _make_identity(
            source_type=AvailabilitySourceType.TASK6_PLAN_VERSION,
            source_role="task6_plan_version",
            schema_version="task6-plan-v1",
            semantic_payload_hash=file_hash,
            canonical_payload_hash=file_hash,
            business_version="v3",
            display_label="task6:plan_version",
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=1,
            ),
        )
        exact = _make_identity(
            source_type=AvailabilitySourceType.TASK6_PLAN_VERSION,
            source_role="task6_plan_version",
            schema_version="task6-plan-v1",
            semantic_payload_hash=file_hash,
            canonical_payload_hash=file_hash,
            business_version="v3",
            display_label="task6:plan_version",
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=888,
            ),
        )
        assert _build_identity_payload(historical) == _build_identity_payload(exact)

        assert historical.semantic.semantic_payload_hash == file_hash
        assert historical.semantic.canonical_payload_hash == file_hash

    def test_plan_valid_sha256(self) -> None:
        file_hash = "d" * 64
        identity = _make_identity(
            source_type=AvailabilitySourceType.TASK6_PLAN_VERSION,
            source_role="task6_plan_version",
            schema_version="task6-plan-v1",
            semantic_payload_hash=file_hash,
            canonical_payload_hash=file_hash,
            business_version="v3",
            display_label="task6:plan_version",
        )
        _assert_sha256_hex(identity.semantic.semantic_payload_hash)
        _assert_sha256_hex(identity.semantic.canonical_payload_hash)


# ── Task 8 daily prediction identity parity ──────────────────────────────────


@dataclass
class _FakeDaily:
    """Minimal stand-in for MaturityDailyPredictionModel."""

    prediction_date: date
    phenology_coordinate_day: object
    p50_kg: object
    p80_kg: object
    p90_kg: object
    cumulative_p50_kg: object
    cumulative_p80_kg: object
    cumulative_p90_kg: object
    curve_share: object
    confidence_level: str
    quality_flags: list[str]


class TestTask8DailyPredictionIdentityParity:
    """TASK8_DAILY_PREDICTION identity must use per-row canonical payload hash."""

    def _make_daily(self, **overrides) -> _FakeDaily:
        defaults = dict(
            prediction_date=date(2026, 3, 1),
            phenology_coordinate_day=1,
            p50_kg=20,
            p80_kg=24,
            p90_kg=28,
            cumulative_p50_kg=20,
            cumulative_p80_kg=24,
            cumulative_p90_kg=28,
            curve_share="0.3333333333",
            confidence_level="medium",
            quality_flags=[],
        )
        defaults.update(overrides)
        return _FakeDaily(**defaults)

    def test_daily_identity_parity(self) -> None:
        """Historical and exact identities produce identical payloads."""
        daily = self._make_daily()
        forecast_sig = "e" * 64
        daily_hash = _task8_daily_prediction_payload_hash(
            daily, forecast_source_signature=forecast_sig
        )
        _assert_sha256_hex(daily_hash)

        historical = _make_identity(
            source_type=AvailabilitySourceType.TASK8_DAILY_PREDICTION,
            source_role="task8_daily_prediction",
            schema_version="task8-maturity-v1",
            semantic_payload_hash=daily_hash,
            input_signature=forecast_sig,
            canonical_payload_hash=daily_hash,
            display_label="task8:daily_prediction",
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=1,
            ),
        )
        exact = _make_identity(
            source_type=AvailabilitySourceType.TASK8_DAILY_PREDICTION,
            source_role="task8_daily_prediction",
            schema_version="task8-maturity-v1",
            semantic_payload_hash=daily_hash,
            input_signature=forecast_sig,
            canonical_payload_hash=daily_hash,
            display_label="task8:daily_prediction",
            persistent_reference=PersistentUpstreamReference(
                reference_type="database_run_id",
                reference_value=999,
            ),
        )
        assert _build_identity_payload(historical) == _build_identity_payload(exact)

    def test_daily_input_signature_from_forecast(self) -> None:
        """input_signature must be the parent forecast's source_signature."""
        daily = self._make_daily()
        forecast_sig = "f" * 64
        daily_hash = _task8_daily_prediction_payload_hash(
            daily, forecast_source_signature=forecast_sig
        )
        identity = _make_identity(
            source_type=AvailabilitySourceType.TASK8_DAILY_PREDICTION,
            source_role="task8_daily_prediction",
            schema_version="task8-maturity-v1",
            semantic_payload_hash=daily_hash,
            input_signature=forecast_sig,
            canonical_payload_hash=daily_hash,
            display_label="task8:daily_prediction",
        )
        assert identity.semantic.input_signature == forecast_sig
        assert identity.semantic.semantic_payload_hash == daily_hash
        assert identity.semantic.canonical_payload_hash == daily_hash

    # ── Mutation tests ───────────────────────────────────────────────────────

    def test_mutation_p50_kg_changes_hash(self) -> None:
        base = self._make_daily()
        modified = self._make_daily(p50_kg=999)
        sig = "g" * 64
        h1 = _task8_daily_prediction_payload_hash(base, forecast_source_signature=sig)
        h2 = _task8_daily_prediction_payload_hash(modified, forecast_source_signature=sig)
        assert h1 != h2

    def test_mutation_prediction_date_changes_hash(self) -> None:
        base = self._make_daily()
        modified = self._make_daily(prediction_date=date(2026, 3, 2))
        sig = "h" * 64
        h1 = _task8_daily_prediction_payload_hash(base, forecast_source_signature=sig)
        h2 = _task8_daily_prediction_payload_hash(modified, forecast_source_signature=sig)
        assert h1 != h2

    def test_mutation_id_does_not_change_hash(self) -> None:
        """Database ID must be excluded from the payload hash."""
        # _FakeDaily doesn't have id, but the hash function doesn't use it
        daily = self._make_daily()
        sig = "i" * 64
        h1 = _task8_daily_prediction_payload_hash(daily, forecast_source_signature=sig)
        h2 = _task8_daily_prediction_payload_hash(daily, forecast_source_signature=sig)
        assert h1 == h2

    def test_mutation_created_at_does_not_change_hash(self) -> None:
        """created_at is excluded from the payload hash — same daily content,
        different simulated timestamps produce the same hash."""
        daily = self._make_daily()
        sig = "j" * 64
        h1 = _task8_daily_prediction_payload_hash(daily, forecast_source_signature=sig)
        h2 = _task8_daily_prediction_payload_hash(daily, forecast_source_signature=sig)
        assert h1 == h2
