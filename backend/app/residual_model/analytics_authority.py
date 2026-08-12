from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from backend.app.models.analytics import AnalyticsBuildRun
from backend.app.residual_model.enums import FeatureSourceDomain, ForecastInputSourceClass
from backend.app.residual_model.feature_registry import feature_definition_map
from backend.app.residual_model.schemas import FeatureValue

ANALYTICS_FACTORY_RECEIPT_SOURCE_CLASS = ForecastInputSourceClass.ANALYTICS_FACTORY_RECEIPT.value
ANALYTICS_VISIBILITY_POLICY_VERSION = "v0-3-s1-forecast-input-pit-visibility-v1"


class AnalyticsFeatureAuthorityError(ValueError):
    """Raised when a non-missing Analytics feature lacks a persisted build run."""


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def analytics_source_cutoff(build_run: AnalyticsBuildRun) -> datetime:
    return _utc(build_run.finished_at or build_run.started_at)


def _source_ref(build_run: AnalyticsBuildRun, source_cutoff: datetime) -> dict[str, object]:
    return {
        "source_class": ANALYTICS_FACTORY_RECEIPT_SOURCE_CLASS,
        "visibility_policy_version": ANALYTICS_VISIBILITY_POLICY_VERSION,
        "analytics_build_run_id": build_run.id,
        "aggregation_version": build_run.aggregation_version,
        "config_hash": build_run.config_hash,
        "source_max_raw_id": build_run.source_max_raw_id,
        "source_cutoff": source_cutoff.isoformat(),
    }


def bind_analytics_feature_authority(
    *,
    feature_values: Sequence[FeatureValue],
    build_run: AnalyticsBuildRun | None,
    forecast_cutoff_at: datetime,
) -> tuple[FeatureValue, ...]:
    """Bind Analytics feature values to one persisted factory-receipt build.

    The authoritative source cutoff is retained on ``source_available_at``;
    generic visibility then blocks a build created after the exact forecast
    cutoff.  The source class and build identity are included in the feature
    provenance so the composite residual feature cannot hide its dependency.
    """

    definitions = feature_definition_map()
    source_cutoff = analytics_source_cutoff(build_run) if build_run is not None else None
    bound: list[FeatureValue] = []
    for feature in feature_values:
        definition = definitions.get(feature.feature_name)
        if definition is None or definition.source_domain != FeatureSourceDomain.ANALYTICS:
            bound.append(feature)
            continue
        if feature.value is None:
            bound.append(feature)
            continue
        if build_run is None or source_cutoff is None:
            raise AnalyticsFeatureAuthorityError(
                f"{feature.feature_name}: persisted AnalyticsBuildRun is required"
            )
        # Keep the real source cutoff even when it is after the forecast
        # cutoff; audit_feature_visibility will produce the stable
        # FUTURE_AVAILABLE_AT blocker instead of allowing a forged timestamp.
        bound.append(
            feature.model_copy(
                update={
                    "source_ref": _source_ref(build_run, source_cutoff),
                    "source_version": build_run.aggregation_version,
                    "source_available_at": source_cutoff,
                }
            )
        )
    return tuple(bound)
