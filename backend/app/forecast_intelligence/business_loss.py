"""Pure explicit-cost asymmetric loss. Synthetic economics, never model promotion."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, Inexact, localcontext
from typing import Any

from backend.app.area_yield.v015_research_cohort import digest
from backend.app.forecast_intelligence.forecast_ops import HORIZONS as HORIZONS
from backend.app.forecast_intelligence.forecast_ops import SHANGHAI, aware, numeric

BUSINESS_LOSS_POLICY_VERSION = "V0_16_ASYMMETRIC_LINEAR_BUSINESS_LOSS_R1"
COST_CONTRACT_POLICY_VERSION = "V0_16_EXPLICIT_COST_AUTHORITY_R1"
FORECAST_COMPARISON_POLICY_VERSION = "V0_16_SAME_COST_CONTRACT_COMPARISON_R1"
FORMULA = "C_under * max(actual - forecast, 0) + C_over * max(forecast - actual, 0)"
AUTHORITY_TYPES = ("OWNER_BUSINESS_SUPPLIED", "EXPLICIT_SYNTHETIC_SCENARIO")
POINT = "V0_15_S5_M1_POINT"
UP80 = "V0_16_S2_UPPER_PLANNING_BOUND_80"
UP90 = "V0_16_S2_UPPER_PLANNING_BOUND_90"
CANDIDATES = (POINT, UP80, UP90)
TARGET_SEMANTICS = "BASE_DAILY_KG_PREFIX_D1_THROUGH_DH"
ZERO = Decimal(0)
LOSS_FIELDS = (
    "underforecast_kg",
    "overforecast_kg",
    "underforecast_loss",
    "overforecast_loss",
    "total_business_loss",
)


def decimal_text(value: Decimal) -> str:
    """Value-canonical finite Decimal, independent of ambient context/trailing zeros."""
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError("SOURCE_NUMERIC_INVALID")
    if value == 0:
        return "0"
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def hash_shape(value: str) -> None:
    if not isinstance(value, str) or not re.fullmatch("[0-9a-f]{64}", value):
        raise ValueError("SOURCE_HASH_INVALID")


@dataclass(frozen=True)
class BusinessCostContract:
    contract_id: str
    policy_version: str
    contract_version: str
    authority_type: str
    authority_reference: str
    c_under_per_kg: Decimal
    c_over_per_kg: Decimal
    loss_unit: str
    synthetic: bool
    canonical_company_cost: bool

    def __post_init__(self) -> None:
        if (
            any(
                not isinstance(v, str) or not v.strip()
                for v in (
                    self.contract_id,
                    self.contract_version,
                    self.authority_reference,
                    self.loss_unit,
                )
            )
            or self.policy_version != COST_CONTRACT_POLICY_VERSION
        ):
            raise ValueError("COST_CONTRACT_INVALID")
        if self.authority_type not in AUTHORITY_TYPES:
            raise ValueError("COST_AUTHORITY_INVALID")
        if not numeric(self.c_under_per_kg) or not numeric(self.c_over_per_kg):
            raise ValueError("COST_NUMERIC_INVALID")
        if type(self.synthetic) is not bool or self.canonical_company_cost is not False:
            raise ValueError("CANONICAL_COMPANY_COST_NOT_ESTABLISHED")
        if self.authority_type == "EXPLICIT_SYNTHETIC_SCENARIO":
            if not self.synthetic or self.loss_unit != "SYNTHETIC_LOSS_UNIT":
                raise ValueError("SYNTHETIC_COST_SEMANTICS_INVALID")
        elif self.synthetic:
            raise ValueError("COST_AUTHORITY_INVALID")

    def payload(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "policy_version": self.policy_version,
            "contract_version": self.contract_version,
            "authority_type": self.authority_type,
            "authority_reference": self.authority_reference,
            "c_under_per_kg": decimal_text(self.c_under_per_kg),
            "c_over_per_kg": decimal_text(self.c_over_per_kg),
            "loss_unit": self.loss_unit,
            "synthetic": self.synthetic,
            "canonical_company_cost": self.canonical_company_cost,
        }

    @property
    def contract_hash(self) -> str:
        return digest(self.payload())


def synthetic_contracts() -> tuple[BusinessCostContract, ...]:
    """Pre-result fixtures; these are NOT company cost estimates."""
    return tuple(
        BusinessCostContract(
            name,
            COST_CONTRACT_POLICY_VERSION,
            "R1",
            "EXPLICIT_SYNTHETIC_SCENARIO",
            "OWNER_S5_R1_PREDECLARED_SYNTHETIC_SENSITIVITY",
            Decimal(under),
            Decimal(over),
            "SYNTHETIC_LOSS_UNIT",
            True,
            False,
        )
        for name, under, over in (
            ("SYNTHETIC_BALANCED_R1", "1", "1"),
            ("SYNTHETIC_UNDER_4X_R1", "4", "1"),
            ("SYNTHETIC_OVER_4X_R1", "1", "4"),
        )
    )


def row_loss(
    actual_kg: Decimal, forecast_kg: Decimal, cost: BusinessCostContract
) -> dict[str, Decimal]:
    if not isinstance(cost, BusinessCostContract):
        raise ValueError("COST_CONTRACT_REQUIRED")
    if not numeric(actual_kg) or not numeric(forecast_kg):
        raise ValueError("SOURCE_NUMERIC_INVALID")
    with localcontext() as ctx:
        ctx.prec = 50
        ctx.traps[Inexact] = True
        try:
            under = max(actual_kg - forecast_kg, ZERO)
            over = max(forecast_kg - actual_kg, ZERO)
            ul, ol = cost.c_under_per_kg * under, cost.c_over_per_kg * over
            result = dict(zip(LOSS_FIELDS, (under, over, ul, ol, ul + ol), strict=True))
            if actual_kg - forecast_kg != under - over or (under > 0 and over > 0):
                raise ValueError("LOSS_INVARIANT_FAILED")
            return result
        except Inexact:
            raise ValueError("AUTHORITATIVE_PRECISION_EXCEEDED") from None


@dataclass(frozen=True)
class LossTarget:
    row_key: str
    base_id: str
    season: str
    forecast_origin: datetime
    lead_day: int
    target_date: date

    def validate(self) -> None:
        if self.season == "2026-2027":
            raise ValueError("FAIL_CURRENT_SEASON_ACTUAL_PRESENT")
        aware(self.forecast_origin)
        if (
            not self.row_key
            or not self.base_id
            or not self.season
            or type(self.lead_day) is not int
            or not 1 <= self.lead_day <= 15
            or self.target_date
            != self.forecast_origin.astimezone(SHANGHAI).date() + timedelta(days=self.lead_day)
        ):
            raise ValueError("TARGET_SCHEMA_INVALID")

    @property
    def origin_key(self) -> tuple[str, str, str]:
        return self.base_id, self.season, self.forecast_origin.astimezone(SHANGHAI).isoformat()

    def payload(self) -> list[Any]:
        return [self.row_key, *self.origin_key, self.lead_day, self.target_date.isoformat()]


@dataclass(frozen=True)
class ActualObservation:
    target: LossTarget
    quantity_kg: Decimal


@dataclass(frozen=True)
class CandidateValue:
    target: LossTarget
    value_kg: Decimal | None


@dataclass(frozen=True)
class ForecastCandidate:
    candidate_id: str
    source_hash: str
    rows: tuple[CandidateValue, ...]


def aggregate_loss(
    pairs: list[tuple[Decimal, Decimal]], cost: BusinessCostContract
) -> dict[str, str]:
    totals = dict.fromkeys(LOSS_FIELDS, ZERO)
    with localcontext() as ctx:
        ctx.prec = 50
        ctx.traps[Inexact] = True
        try:
            for actual, forecast in pairs:
                row = row_loss(actual, forecast, cost)
                totals = {key: totals[key] + row[key] for key in LOSS_FIELDS}
            if (
                totals["total_business_loss"]
                != totals["underforecast_loss"] + totals["overforecast_loss"]
            ):
                raise ValueError("LOSS_INVARIANT_FAILED")
            return {k: decimal_text(v) for k, v in totals.items()}
        except Inexact:
            raise ValueError("AUTHORITATIVE_PRECISION_EXCEEDED") from None


def compare_aggregates(a: dict[str, Any], b: dict[str, Any]) -> str:
    required = (
        "cost_contract_hash",
        "comparison_rowset_hash",
        "actual_authority_hash",
        "target_semantics",
        "horizon",
        "daily_row_count",
        "actual_values_hash",
    )
    if any(k not in a or k not in b or a[k] != b[k] for k in required):
        raise ValueError("COMPARISON_CONTRACT_MISMATCH")
    for key in (
        "cost_contract_hash",
        "comparison_rowset_hash",
        "actual_authority_hash",
        "actual_values_hash",
        "candidate_source_hash",
        "candidate_payload_hash",
    ):
        hash_shape(a[key])
        hash_shape(b[key])
    if a.get("candidate_id") == b.get("candidate_id") and any(
        a[k] != b[k] for k in ("candidate_source_hash", "candidate_payload_hash")
    ):
        raise ValueError("CANDIDATE_SOURCE_DRIFT")
    if any(not isinstance(v["total_business_loss"], str) for v in (a, b)):
        raise ValueError("SOURCE_NUMERIC_INVALID")
    left, right = Decimal(a["total_business_loss"]), Decimal(b["total_business_loss"])
    if not numeric(left) or not numeric(right):
        raise ValueError("SOURCE_NUMERIC_INVALID")
    return "LOWER" if left < right else "HIGHER" if left > right else "EQUAL"


def evaluate_comparison(
    cost: BusinessCostContract,
    expected_targets: list[LossTarget],
    actuals: list[ActualObservation],
    candidates: list[ForecastCandidate],
    *,
    actual_authority_hash: str,
    expected_candidate_hashes: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Common COMPLETE origin-prefix set for each H, identical across all candidates."""
    hash_shape(actual_authority_hash)
    # Metadata guard precedes all quantity validation, matching or filtering.
    all_targets = [
        *expected_targets,
        *(a.target for a in actuals),
        *(r.target for c in candidates for r in c.rows),
    ]
    if any(t.season == "2026-2027" for t in all_targets):
        raise ValueError("FAIL_CURRENT_SEASON_ACTUAL_PRESENT")
    for t in all_targets:
        t.validate()
    expected = {t.row_key: t for t in expected_targets}
    if len(expected) != len(expected_targets) or not expected:
        raise ValueError("ROWSET_ACCOUNTING_FAILED")
    groups: dict[tuple[str, str, str], dict[int, LossTarget]] = {}
    for t in expected_targets:
        group = groups.setdefault(t.origin_key, {})
        if t.lead_day in group:
            raise ValueError("ROWSET_ACCOUNTING_FAILED")
        group[t.lead_day] = t
    actual_map: dict[str, Decimal] = {}
    actual_identity: dict[tuple[str, str, date], Decimal] = {}
    for a in actuals:
        if a.target.row_key in actual_map or expected.get(a.target.row_key) != a.target:
            raise ValueError("ACTUAL_DUPLICATE_OR_ROWSET_CONFLICT")
        if not numeric(a.quantity_kg):
            raise ValueError("SOURCE_NUMERIC_INVALID")
        key = a.target.base_id, a.target.season, a.target.target_date
        if key in actual_identity and actual_identity[key] != a.quantity_kg:
            raise ValueError("ACTUAL_DUPLICATE_CONFLICT")
        actual_identity[key] = a.quantity_kg
        actual_map[a.target.row_key] = a.quantity_kg
    if len({c.candidate_id for c in candidates}) != len(candidates) or {
        c.candidate_id for c in candidates
    } != set(CANDIDATES):
        raise ValueError("CANDIDATE_IDENTITY_CONFLICT")
    maps, payload_hashes = {}, {}
    sources = {c.candidate_id: c.source_hash for c in candidates}
    if expected_candidate_hashes is not None and sources != expected_candidate_hashes:
        raise ValueError("CANDIDATE_SOURCE_DRIFT")
    for c in candidates:
        hash_shape(c.source_hash)
        values: dict[str, Decimal | None] = {}
        for r in c.rows:
            if r.target.row_key in values or expected.get(r.target.row_key) != r.target:
                raise ValueError("CANDIDATE_ROWSET_CONFLICT")
            if r.value_kg is not None and not numeric(r.value_kg):
                raise ValueError("SOURCE_NUMERIC_INVALID")
            values[r.target.row_key] = r.value_kg
        maps[c.candidate_id] = values
        payload_hashes[c.candidate_id] = digest(
            [
                [expected[k].payload(), decimal_text(v) if v is not None else None]
                for k, v in sorted(values.items())
            ]
        )
    result = {}
    with localcontext() as ctx:
        ctx.prec = 50
        ctx.traps[Inexact] = True
        for horizon in HORIZONS:
            universe = sorted(
                [t for t in expected_targets if t.lead_day <= horizon],
                key=lambda t: (t.origin_key, t.lead_day, t.row_key),
            )
            common = []
            scorable = 0
            for _, group in sorted(groups.items()):
                prefix = [group[d] for d in range(1, horizon + 1) if d in group]
                if len(prefix) == horizon and all(
                    t.row_key in actual_map
                    and all(maps[c].get(t.row_key) is not None for c in CANDIDATES)
                    for t in prefix
                ):
                    common.extend(prefix)
                    scorable += 1
            rowset_hash = digest([t.payload() for t in common])
            actual_hash = digest([[t.row_key, decimal_text(actual_map[t.row_key])] for t in common])
            summaries: dict[str, dict[str, Any]] = {}
            for c in sorted(candidates, key=lambda c: c.candidate_id):
                if not common:
                    continue
                pairs = [(actual_map[t.row_key], maps[c.candidate_id][t.row_key]) for t in common]
                # Common-row gate above proves that no None reaches authoritative arithmetic.
                valid_pairs = [(a, p) for a, p in pairs if p is not None]
                totals = aggregate_loss(valid_pairs, cost)
                summaries[c.candidate_id] = totals | {
                    "candidate_id": c.candidate_id,
                    "cost_contract_hash": cost.contract_hash,
                    "comparison_rowset_hash": rowset_hash,
                    "actual_authority_hash": actual_authority_hash,
                    "actual_values_hash": actual_hash,
                    "target_semantics": TARGET_SEMANTICS,
                    "horizon": horizon,
                    "daily_row_count": len(common),
                    "scorable_origin_count": scorable,
                    "candidate_source_hash": c.source_hash,
                    "candidate_payload_hash": payload_hashes[c.candidate_id],
                    "actual_sum_kg": decimal_text(sum((a for a, _ in valid_pairs), ZERO)),
                    "candidate_forecast_sum_kg": decimal_text(
                        sum((p for _, p in valid_pairs), ZERO)
                    ),
                }
            if summaries:
                point = summaries[POINT]
                for summary in summaries.values():
                    summary["descriptive_relation_vs_point"] = compare_aggregates(summary, point)
                    summary["loss_delta_vs_point"] = decimal_text(
                        Decimal(summary["total_business_loss"])
                        - Decimal(point["total_business_loss"])
                    )
            result[f"H{horizon}"] = {
                "comparison_status": "COMPARABLE" if common else "NOT_COMPARABLE_INCOMPLETE_ROWSET",
                "comparison_semantics": "DESCRIPTIVE_SYNTHETIC_COST_COMPARISON"
                if cost.synthetic
                else "DESCRIPTIVE_EXPLICIT_COST_COMPARISON_NOT_PRODUCTION_APPROVAL",
                "loss_unit": cost.loss_unit,
                "cost_contract_hash": cost.contract_hash,
                "expected_origin_count": len(groups),
                "scorable_origin_count": scorable,
                "expected_target_row_count": len(universe),
                "actual_row_count": sum(t.row_key in actual_map for t in universe),
                "candidate_source_row_count": {
                    c: sum(t.row_key in maps[c] for t in universe) for c in CANDIDATES
                },
                "candidate_computable_row_count": {
                    c: sum(maps[c].get(t.row_key) is not None for t in universe) for c in CANDIDATES
                },
                "common_comparable_row_count": len(common),
                "excluded_non_comparable_row_count": len(universe) - len(common),
                "comparison_rowset_hash": rowset_hash,
                "candidates": summaries,
            }
    return result
