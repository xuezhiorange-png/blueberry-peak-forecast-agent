"""Authoritative read composition. No inference, calibration, scoring or writes."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.forecast_intelligence.errors import HierarchicalForecastError
from backend.app.forecast_intelligence.persistence import HierarchicalRunRepository
from backend.app.forecast_intelligence.read_schemas import (
    AuthorityIdentity,
    Capability,
    CurveData,
    DailyReadRow,
    ForecastIdentity,
    ForecastReadQuery,
    HierarchyData,
    HierarchyIdentity,
    HorizonQuality,
    IntervalCoverage,
    OverviewData,
    QualityData,
    QualityReadQuery,
    ReadError,
    ReadModel,
    ReadResponse,
)
from backend.app.forecast_quality.operational_peak_persistence import (
    OperationalPeakPersistenceIntegrityError,
    OperationalPeakRunNotFoundError,
    OperationalPeakRunRepository,
)

FORECAST_FAMILY = "OPERATIONAL_PEAK_FORECAST_RUN_V1"
READ_POLICY = "V0_17_FORECAST_INTELLIGENCE_READ_PROJECTION_R1"
M1_MODEL = "V0_15_S5_M1_RIDGE"
S2_POLICY = "V0_16_ROLLING_DATE_BOUND_CONFORMAL_R1"
S3_POLICY = "V0_16_M1_STANDARDIZED_LINEAR_ATTRIBUTION_R1"
S4_POLICY = "V0_16_FORECASTOPS_MONITORING_R1"
EVIDENCE_ROOT = Path(__file__).resolve().parents[3] / "docs/v0-16/evidence"
PUBLIC_EVIDENCE_HASHES = {
    "forecastops-monitoring-r1/point-quality-summary-r1.json": (
        "ed59148e7fc01935a66f2341f0155a5facbf9fb9ee857396f4051ab0eeb19e9e"
    ),
    "forecastops-monitoring-r1/monitoring-policy-r1.json": (
        "7ec6d4c95cec9f2463dcff11053657825cb3164235e27e6dfdf3d4a504639170"
    ),
    "forecastops-monitoring-r1/manifest-r1.json": (
        "9a81af66ca0106031c579dd8648336ae2053dd4071076367725d8d92097fb8a5"
    ),
    "forecastops-monitoring-r1/source-binding-r1.json": (
        "95f6e219229d38db42c44e0b9a3a6c371d51893c29926d6105cf35b09eccd5e0"
    ),
    "uncertainty-conformal-calibration-r1/coverage-summary-r1.json": (
        "1586144b596e315ef627ee1874a1104229337bae96a86fd4e26d066c55dadd17"
    ),
    "uncertainty-conformal-calibration-r1/conformal-policy-r1.json": (
        "4d3d2635ddbd4fecd68e59c47d46ae3f35389e78ccacc960188944fa9f158a4d"
    ),
    "uncertainty-conformal-calibration-r1/manifest-r1.json": (
        "b4b4ca6124f4aea081243ac477c01ff7c0dc0123eb846ee2cd23a2b2f9a773b1"
    ),
}


def projection_digest(value: dict[str, Any]) -> str:
    raw = (
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def response[T: ReadModel](data_type: type[T], **values: Any) -> ReadResponse[T]:
    result = ReadResponse[data_type](**values, projection_hash="0" * 64)  # type: ignore[valid-type]
    return result.model_copy(
        update={
            "projection_hash": projection_digest(
                result.model_dump(mode="json", exclude={"projection_hash"})
            )
        }
    )


def public_evidence() -> dict[str, Any] | None:
    """Read only seven fixed public files. Missing package != fabricated evidence."""
    result: dict[str, Any] = {}
    for name, expected in PUBLIC_EVIDENCE_HASHES.items():
        try:
            raw = (EVIDENCE_ROOT / name).read_bytes()
        except FileNotFoundError:
            return None
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ReadError("PUBLIC_EVIDENCE_AUTHORITY_MISMATCH", 409)
        result[name] = json.loads(raw)
    return result


class ForecastIntelligenceReadService:
    """Future MCP/Dashboard reuse this service, not transport or frozen engines."""

    def __init__(self, session: AsyncSession | None):
        self.session = session

    async def _source(self, query: ForecastReadQuery) -> tuple[dict[str, Any], dict[str, Any]]:
        if query.forecast_family != FORECAST_FAMILY or (
            (query.hierarchy_level == "BASE") != (query.source_kind == "OPERATIONAL_PEAK")
        ):
            raise ReadError("AUTHORITY_MISMATCH", 409)
        if self.session is None:
            raise ReadError("PERSISTENCE_UNAVAILABLE", 503)
        try:
            if query.source_kind == "OPERATIONAL_PEAK":
                with self.session.no_autoflush, localcontext() as context:
                    context.prec = 50
                    saved = await OperationalPeakRunRepository(self.session).get(query.run_id)
                value = saved.result
                level, entity = "BASE", saved.run.base_id
                authority = saved.run.authority_hash
                hierarchy_hash = None
                source_policy = value["policy_version"]
                run_id = saved.run.run_id
                rerun_of = saved.run.rerun_of_run_id
            else:
                with self.session.no_autoflush, localcontext() as context:
                    context.prec = 50
                    hierarchy_saved = await HierarchicalRunRepository(self.session).get(
                        query.run_id
                    )
                value = hierarchy_saved.result
                level, entity = value["target_entity_type"], value["target_entity_id"]
                authority = value["source_authority_hash"]
                hierarchy_hash = value["hierarchy_authority_hash"]
                source_policy = value["source_policy_version"]
                run_id = hierarchy_saved.run.run_id
                rerun_of = None
            if (
                run_id != query.run_id
                or level != query.hierarchy_level
                or entity != query.entity_id
                or value["target_season"] != query.target_season
                or value["origin_date"] != query.origin_date.isoformat()
                or value["baseline_id"] != query.baseline_id
                or source_policy != query.policy_version
                or (
                    query.expected_source_result_hash is not None
                    and value["result_hash"] != query.expected_source_result_hash
                )
            ):
                raise ReadError("AUTHORITY_MISMATCH", 409)
            identity = ForecastIdentity.model_validate(
                query.model_dump(exclude={"expected_source_result_hash"})
            )
            hierarchy = HierarchyIdentity(
                hierarchy_level=level, entity_id=entity, hierarchy_authority_hash=hierarchy_hash
            )
            return value, {
                "forecast_identity": identity,
                "hierarchy_identity": hierarchy,
                "authority_identity": AuthorityIdentity(
                    authority_hash=authority,
                    source_policy_version=source_policy,
                    source_baseline_id=value["baseline_id"],
                ),
                "source_kind": query.source_kind,
                "source_run_id": query.run_id,
                "source_rerun_of_run_id": rerun_of,
                "source_result_hash": value["result_hash"],
                "policy_version": value.get("reconciliation_policy_version", source_policy),
                "evidence_mode": "SAVED_FORECAST",
            }
        except OperationalPeakRunNotFoundError:
            raise ReadError("SAVED_RUN_NOT_FOUND", 404) from None
        except OperationalPeakPersistenceIntegrityError:
            raise ReadError("SAVED_RUN_INTEGRITY_FAILED", 409) from None
        except HierarchicalForecastError as exc:
            if exc.status_code == 404:
                raise ReadError("SAVED_RUN_NOT_FOUND", 404) from None
            raise ReadError("SAVED_RUN_INTEGRITY_FAILED", 409) from None
        except SQLAlchemyError:
            raise ReadError("PERSISTENCE_UNAVAILABLE", 503) from None

    @staticmethod
    def _rows(value: dict[str, Any], query: ForecastReadQuery) -> list[DailyReadRow]:
        return [
            DailyReadRow(
                forecast_run_id=query.run_id,
                hierarchy_level=query.hierarchy_level,
                entity_id=query.entity_id,
                origin_date=query.origin_date,
                target_date=date.fromisoformat(row["date"]),
                lead_day=(date.fromisoformat(row["date"]) - query.origin_date).days,
                point_forecast_kg=row["predicted_kg"],
                source_result_hash=value["result_hash"],
            )
            for row in value["daily_forecast"]
        ]

    @staticmethod
    def _completeness(value: dict[str, Any]) -> str:
        if value.get("status") == "INCOMPLETE_CHILD_COVERAGE":
            return "INCOMPLETE_CHILD_COVERAGE"
        if not value["daily_forecast"]:
            return "EMPTY"
        return "COMPLETE" if len(value["daily_forecast"]) == 15 else "PARTIAL_DATE_WINDOW"

    async def curve(self, query: ForecastReadQuery) -> ReadResponse[CurveData]:
        value, common = await self._source(query)
        rows = self._rows(value, query)
        completeness = self._completeness(value)
        status = (
            "READY"
            if completeness == "COMPLETE"
            else "EMPTY"
            if completeness == "EMPTY"
            else "PARTIAL"
        )
        return response(
            CurveData,
            capability="GET_FORECAST_CURVE",
            status=status,
            data=CurveData(
                daily_rows=rows, data_completeness=completeness, available_day_count=len(rows)
            ),
            **common,
        )

    async def overview(self, query: ForecastReadQuery) -> ReadResponse[OverviewData]:
        value, common = await self._source(query)
        rows = self._rows(value, query)
        w7, w15 = value["forecast_7d"], value["forecast_15d"]
        completeness = self._completeness(value)
        ranked = sorted(
            rows, key=lambda r: (Decimal(r.point_forecast_kg).copy_negate(), r.target_date)
        )
        # Remaining-business-window summaries may extend past this saved 15-day curve.
        # Project only the admitted curve; use the frozen earliest-date peak tie rule.
        peak_day = ranked[0].target_date if ranked else None
        peak_kg = ranked[0].point_forecast_kg if ranked else None
        status = (
            "READY"
            if completeness == "COMPLETE"
            else "EMPTY"
            if completeness == "EMPTY"
            else "PARTIAL"
        )
        data = OverviewData(
            forecast_7d_total_kg=w7["total_kg"] if w7 else None,
            forecast_15d_total_kg=w15["total_kg"] if w15 else None,
            peak_date=peak_day,
            peak_daily_quantity_kg=peak_kg,
            forecast_origin=query.origin_date,
            forecast_scope=common["hierarchy_identity"],
            forecast_run_identity=common["forecast_identity"],
            data_completeness=completeness,
            forecast_7d_status=w7["status"] if w7 else "INCOMPLETE_CHILD_COVERAGE",
            forecast_15d_status=w15["status"] if w15 else "INCOMPLETE_CHILD_COVERAGE",
            high_load_dates=ranked,
        )
        return response(
            OverviewData, capability="GET_FORECAST_OVERVIEW", status=status, data=data, **common
        )

    async def hierarchy(self, query: ForecastReadQuery) -> ReadResponse[HierarchyData]:
        value, common = await self._source(query)
        rows = self._rows(value, query)
        completeness = self._completeness(value)
        expected, included = value.get("child_expected_count"), value.get("child_included_count")
        return response(
            HierarchyData,
            capability="GET_HIERARCHICAL_FORECAST",
            status="READY"
            if completeness == "COMPLETE"
            else "EMPTY"
            if completeness == "EMPTY"
            else "PARTIAL",
            data=HierarchyData(
                daily_rows=rows,
                data_completeness=completeness,
                available_day_count=len(rows),
                reconciliation_method="BOTTOM_UP_EXACT_SUM"
                if query.source_kind == "HIERARCHICAL"
                else None,
                source_status=value.get("status", completeness),
                child_expected_count=expected,
                child_included_count=included,
                missing_child_count=expected - included if expected is not None else None,
            ),
            **common,
        )

    async def _unavailable(
        self, query: ForecastReadQuery, capability: Capability, policy: str, reason: str
    ) -> ReadResponse[ReadModel]:
        _, common = await self._source(query)
        common["policy_version"] = policy
        return response(
            ReadModel,
            capability=capability,
            status="NOT_AVAILABLE",
            unavailable_reason=reason,
            **common,
        )

    async def uncertainty(self, query: ForecastReadQuery) -> ReadResponse[ReadModel]:
        return await self._unavailable(
            query,
            "GET_FORECAST_UNCERTAINTY",
            S2_POLICY,
            "NO_EXACT_BOUND_M1_INTERVAL_AUTHORITY_FOR_SAVED_RUN",
        )

    async def attribution(self, query: ForecastReadQuery) -> ReadResponse[ReadModel]:
        return await self._unavailable(
            query,
            "GET_FORECAST_ATTRIBUTION",
            S3_POLICY,
            "NO_EXACT_M1_MODEL_FEATURE_SEALED_PREDICTION_ATTRIBUTION_AUTHORITY",
        )

    async def quality(self, query: QualityReadQuery) -> ReadResponse[QualityData]:
        common: dict[str, Any] = {
            "capability": "GET_FORECAST_QUALITY",
            "source_kind": "PUBLIC_FROZEN_HISTORICAL_EVIDENCE",
            "policy_version": S4_POLICY,
            "evidence_mode": "RETROSPECTIVE_OBSERVATION",
        }
        if query.mode == "CURRENT_PRODUCTION_ACCURACY":
            return response(
                QualityData,
                status="NO_CURRENT_ACTUAL",
                unavailable_reason="当前产季暂无可用于正式评分的实际采收数据。",
                **{**common, "evidence_mode": "NO_CURRENT_ACTUAL"},
            )
        evidence = public_evidence()
        if evidence is None:
            return response(
                QualityData,
                status="NOT_AVAILABLE",
                unavailable_reason="PUBLIC_HISTORICAL_EVIDENCE_NOT_PACKAGED",
                **common,
            )
        point = evidence["forecastops-monitoring-r1/point-quality-summary-r1.json"]["horizons"]
        coverage = evidence["uncertainty-conformal-calibration-r1/coverage-summary-r1.json"]
        manifest = evidence["forecastops-monitoring-r1/manifest-r1.json"]
        result_hash = manifest["result_hash"]
        if (
            query.expected_source_result_hash is not None
            and query.expected_source_result_hash != result_hash
        ):
            raise ReadError("AUTHORITY_MISMATCH", 409)
        horizons = []
        for horizon in ("H1", "H3", "H7", "H15"):
            p = point.get(horizon)
            intervals = [
                IntervalCoverage(
                    interval=name,
                    **{key: row[key] for key in IntervalCoverage.model_fields if key != "interval"},
                )
                for name, row in sorted(coverage.get(horizon, {}).items())
            ]
            horizons.append(
                HorizonQuality(
                    horizon=horizon,
                    point_status="READY" if p else "NOT_AVAILABLE",
                    daily_row_count=p["daily_row_count"] if p else None,
                    scorable_origin_count=p["scorable_origin_count"] if p else None,
                    wape=p["daily_wape"] if p else None,
                    mae_kg=p["daily_mae_kg"] if p else None,
                    bias_kg=p["daily_bias_kg"] if p else None,
                    cumulative_wape=p["cumulative_wape"] if p else None,
                    interval_status="READY" if intervals else "NOT_AVAILABLE",
                    interval_coverage=intervals,
                )
            )
        binding = evidence["forecastops-monitoring-r1/source-binding-r1.json"]
        common.update(
            source_result_hash=result_hash,
            authority_identity=AuthorityIdentity(
                authority_hash=binding["contract_hash"],
                source_policy_version=S4_POLICY,
                source_baseline_id=M1_MODEL,
                source_evidence_hashes=PUBLIC_EVIDENCE_HASHES,
            ),
        )
        return response(
            QualityData,
            status="READY" if all(h.point_status == "READY" for h in horizons) else "PARTIAL",
            data=QualityData(horizons=horizons),
            **common,
        )
