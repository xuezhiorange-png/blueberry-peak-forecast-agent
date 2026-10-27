"""V0_21 S3: four explicit synthetic scopes, sealed inputs, independent labels.

No forecast generation, real-data permission, model fitting, or production API.
Legacy error arithmetic and metric finalization are called unchanged; this
adapter supplies generic scope lengths and the four additive V0.21 metrics.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import io
import re
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import Field

from backend.research import v019_research_evaluation as aggregation
from backend.research import v019_synthetic_validation as math
from backend.research import v021_cycle_features as cycle
from backend.research import v021_structure_scenarios as structure
from backend.research.v019_daily_curve import DailyKg, _micro

Record = dict[str, Any]
FAMILIES = (
    "FULL_SEASON_PEAK",
    "DECLARED_REMAINING_SEASON_PEAK",
    "ORIGIN_H7_PREFIX",
    "ORIGIN_H15_LOCAL",
)
ADDITIVE = (
    "V0_21_ROLLING_15DAY_PEAK_START_MAE",
    "V0_21_ROLLING_15DAY_PEAK_QUANTITY_MAE",
    "V0_21_ORIGIN_WINDOW_TOTAL_MAE",
    "V0_21_ORIGIN_WINDOW_TOTAL_WAPE",
)
BASIS = "RECORDED_INBOUND_WEIGHT"
Side = Literal["baseline", "candidate"]


class Model(cycle.Contract):
    model_id: str
    fit_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    trained_through: date


class Calendar(cycle.Contract):
    calendar_id: str
    base_id: str
    season: str
    season_start: date | None
    season_end: date | None
    timezone: str
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_version: str
    known_at: str | None


class CurveSpec(cycle.Contract):
    curve_id: str
    member_id: str
    origin_id: str
    side: Side
    prediction_version: str
    support_start: date
    support_end: date | None


class Case(cycle.Contract):
    case_id: str
    scope_id: str
    member_id: str
    scope: cycle.Scope
    origin_id: str
    calendar_id: str
    evaluation_family: Literal[
        "FULL_SEASON_PEAK", "DECLARED_REMAINING_SEASON_PEAK", "ORIGIN_H7_PREFIX", "ORIGIN_H15_LOCAL"
    ]
    remaining_start: date | None
    split: str
    area_mu: str
    baseline_curve_id: str
    candidate_curve_id: str


class Protocol(cycle.Contract):
    schema_version: Literal["V0_21_S3_PROTOCOL_R1"]
    data_class: Literal["SYNTHETIC_TEST_FIXTURE"]
    comparison_family: str
    season: str
    variety: str
    production_system: str
    quantity_basis: str
    unit: str
    area_basis: Literal["PLANTED", "PRODUCTIVE", "EFFECTIVE"]
    business_timezone: str
    source_population_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    training_scope_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    label_authority_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    label_source_version: str
    models: dict[Side, Model]
    calendars: list[Calendar]
    curves: list[CurveSpec]
    cases: list[Case]


class Row(cycle.Contract):
    date: str = Field(max_length=30)
    kg: str = Field(max_length=40)


class Prediction(cycle.Contract):
    curve_id: str
    member_id: str
    scope: cycle.Scope
    origin_id: str
    prediction_version: str
    model_id: str
    fit_sha256: str
    config_sha256: str
    quantity_basis: str
    unit: str
    source_population_sha256: str
    area_mu: str
    area_authority_sha256: str
    issued_at: str | None
    input_available_at: str | None
    input_ingested_at: str | None
    rows: list[Row] | None
    failure: str | None


class Predictions(cycle.Contract):
    schema_version: Literal["V0_21_S3_PREDICTIONS_R1"]
    data_class: Literal["SYNTHETIC_TEST_FIXTURE"]
    registration_sha256: str
    curves: list[Prediction]


class Label(cycle.Contract):
    case_id: str
    member_id: str
    scope: cycle.Scope
    quantity_basis: str
    unit: str
    area_mu: str
    area_authority_sha256: str
    complete: bool
    mature: bool
    available_at: str | None
    complete_at: str | None
    mature_at: str | None
    rows: list[Row]


class Labels(cycle.Contract):
    schema_version: Literal["V0_21_S3_LABELS_R1"]
    data_class: Literal["SYNTHETIC_TEST_FIXTURE"]
    registration_sha256: str
    label_authority_sha256: str
    source_version: str
    labels: list[Label]


def _six(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000001")), "f")


def _dates(start: date, end: date) -> list[str]:
    if end < start or (end - start).days > 1095:
        raise ValueError("INVALID_SCOPE_CALENDAR")
    return [str(start + timedelta(days=i)) for i in range((end - start).days + 1)]


def _unique(rows: list[Any], key: str) -> None:
    ids = [getattr(r, key) for r in rows]
    if len(ids) != len(set(ids)) or any(not value.strip() for value in ids):
        raise ValueError("DUPLICATE_OR_EMPTY_REGISTERED_ID")


def _failure(code: str) -> Record:
    if code in {"PHYSICAL_BASIS_MISMATCH", "AREA_NOT_POSITIVE"}:
        principal = "PHYSICAL_BASIS_MISMATCH"
    elif code in {"INVALID_VALUE_OR_DUPLICATE_DATE", "KG_PRECISION_INVALID"}:
        principal = "INVALID_VALUE_OR_DUPLICATE_DATE"
    elif code in {
        "INCOMPLETE_CALENDAR",
        "UNKNOWN_SEASON_END",
        "INVALID_SCOPE_CALENDAR",
        "INVALID_REMAINING_BOUNDARY",
        "SCOPE_OUTSIDE_SEASON",
        "CURVE_SUPPORT_MISMATCH",
        "H7_REQUIRES_H15_PREDICTION_SUPPORT",
    }:
        principal = "INCOMPLETE_CALENDAR"
    elif code in {
        "MEMBER_IDENTITY_MISMATCH",
        "MODEL_IDENTITY_MISMATCH",
        "AREA_IDENTITY_MISMATCH",
        "PREDICTION_IDENTITY_MISMATCH",
        "MISSING_PREDICTION",
        "LABEL_IDENTITY_MISMATCH",
        "CONFLICTING_LABEL_VERSIONS",
    }:
        principal = "IDENTITY_OR_SOURCE_HASH_MISMATCH"
    else:
        principal = "UNVERIFIED_AUTHORITY"
    return dict(principal=principal, detail=code)


def _principal(failures: list[Record]) -> str | None:
    order = [
        "UNVERIFIED_AUTHORITY",
        "PHYSICAL_BASIS_MISMATCH",
        "IDENTITY_OR_SOURCE_HASH_MISMATCH",
        "INVALID_VALUE_OR_DUPLICATE_DATE",
        "INCOMPLETE_CALENDAR",
    ]
    return min((f["principal"] for f in failures), key=order.index) if failures else None


def _parse_rows(
    raw: list[Row], expected: list[str] | None = None
) -> tuple[tuple[DailyKg, ...], str | None]:
    try:
        values = []
        for row in raw:
            if len(row.kg) > 30 or not re.fullmatch(r"\d+(?:\.\d{1,6})?", row.kg):
                return (), "INVALID_VALUE_OR_DUPLICATE_DATE"
            kg = Decimal(row.kg)
            _micro(kg)  # Frozen kg six-decimal/nonnegative contract, unchanged.
            values.append(DailyKg(date.fromisoformat(row.date), kg))
        rows = tuple(values)
        own = tuple(r.day for r in rows)
        reason = math._calendar_reason(rows, own)
        if reason:
            return (), reason
        if expected is not None:
            reason = math._calendar_reason(rows, tuple(date.fromisoformat(d) for d in expected))
        return rows, reason
    except (ValueError, ArithmeticError):
        return (), "INVALID_VALUE_OR_DUPLICATE_DATE"


def _serialize(rows: tuple[DailyKg, ...]) -> list[dict[str, str]]:
    return [dict(date=str(r.day), kg=_six(r.kg)) for r in rows]


def _peak(rows: tuple[DailyKg, ...], n: int, *, actual: bool) -> Record:
    count = len(rows) - n + 1
    if count <= 0:
        return dict(
            date=None,
            start_date=None,
            end_date=None,
            quantity_kg=None,
            daily=[],
            reason=f"NO_COMPLETE_{n}DAY_WINDOW",
            candidate_window_count=0,
            timing_skill_interpretable=False,
        )
    if n in (1, 7):
        start, total = math._peak(rows, n == 7)
    else:
        options = tuple(
            DailyKg(rows[i].day, sum((r.kg for r in rows[i : i + n]), Decimal(0)))
            for i in range(count)
        )
        start, total = math._peak(options, False)
    selected = rows[(start - rows[0].day).days : (start - rows[0].day).days + n]
    positive = any(r.kg > 0 for r in rows)
    missing_time = actual and not positive
    return dict(
        date=None if missing_time else str(start),
        start_date=None if missing_time else str(start),
        end_date=None if missing_time else str(start + timedelta(days=n - 1)),
        quantity_kg=_six(total),
        daily=_serialize(selected),
        reason="NO_POSITIVE_ACTUAL_PEAK" if missing_time else None,
        candidate_window_count=count,
        timing_skill_interpretable=count > 1 and not missing_time,
    )


def _peaks(rows: tuple[DailyKg, ...], *, actual: bool = False) -> Record:
    return {
        name: _peak(rows, n, actual=actual)
        for name, n in (("single_day", 1), ("rolling7", 7), ("rolling15", 15))
    }


def _case_registration(case: Case, p: Protocol, s1: Record, s2: Record) -> Record:
    members = {m["member_id"]: m for m in s1["original_declarations"]["members"]}
    origins = {o["origin_id"]: o for o in s1["original_declarations"]["origins"]}
    member, origin_raw = members.get(case.member_id), origins.get(case.origin_id)
    calendar = next((c for c in p.calendars if c.calendar_id == case.calendar_id), None)
    failures = []
    origin = cycle.Origin.model_validate(origin_raw) if origin_raw else None
    if not member or member["scope"] != case.scope.model_dump():
        failures.append(_failure("MEMBER_IDENTITY_MISMATCH"))
    if origin is None or (origin.base, origin.season, origin.timezone) != (
        case.scope.base,
        case.scope.season,
        p.business_timezone,
    ):
        failures.append(_failure("ORIGIN_IDENTITY_NOT_PROVEN"))
    scope_dates: list[str] = []
    if calendar is None or (calendar.base_id, calendar.season, calendar.timezone) != (
        case.scope.base,
        case.scope.season,
        p.business_timezone,
    ):
        failures.append(_failure("CALENDAR_IDENTITY_NOT_PROVEN"))
    elif calendar.season_start is None or calendar.season_end is None:
        failures.append(_failure("UNKNOWN_SEASON_END"))
    elif origin:
        try:
            if cycle._aware(calendar.known_at) > origin.cutoff or not structure._known(
                calendar.source_version
            ):
                raise ValueError("CALENDAR_NOT_KNOWN_AT_CUTOFF")
            if case.evaluation_family == FAMILIES[0]:
                start, end = calendar.season_start, calendar.season_end
            elif case.evaluation_family == FAMILIES[1]:
                if (
                    case.remaining_start is None
                    or case.remaining_start < origin.origin_date + timedelta(days=1)
                ):
                    raise ValueError("INVALID_REMAINING_BOUNDARY")
                start, end = case.remaining_start, calendar.season_end
            else:
                start = origin.origin_date + timedelta(days=1)
                end = origin.origin_date + timedelta(
                    days=7 if case.evaluation_family == FAMILIES[2] else 15
                )
            if start < calendar.season_start or end > calendar.season_end:
                raise ValueError("SCOPE_OUTSIDE_SEASON")
            scope_dates = _dates(start, end)
            target = datetime.combine(start, time.min, ZoneInfo(p.business_timezone))
            if origin.cutoff >= target:
                raise ValueError("CUTOFF_NOT_BEFORE_TARGET_START")
        except ValueError as exc:
            failures.append(_failure(str(exc)))
    if origin and case.evaluation_family == FAMILIES[2]:
        for ref in (case.baseline_curve_id, case.candidate_curve_id):
            curve = next((v for v in p.curves if v.curve_id == ref), None)
            if (
                curve is None
                or curve.support_end is None
                or curve.support_start > origin.origin_date + timedelta(days=1)
                or curve.support_end < origin.origin_date + timedelta(days=15)
            ):
                failures.append(_failure("H7_REQUIRES_H15_PREDICTION_SUPPORT"))
    feature = next(
        (
            f
            for f in s1["origin_snapshots"]
            if f["origin_id"] == case.origin_id and f["member_id"] == case.member_id
        ),
        None,
    )
    structural = next(
        (
            f
            for f in s2["origin_snapshots"]
            if f["origin_id"] == case.origin_id
            and f["comparison"]["next_member_id"] == case.member_id
        ),
        None,
    )
    frozen_features: Record = {}
    area_mu, area_hash = case.area_mu, None
    if (
        not feature
        or feature["status"] != "PREPARED"
        or not structural
        or structural["comparison"]["status"] != "COMPARABLE"
    ):
        failures.append(_failure("ORIGIN_FEATURES_NOT_PREPARED"))
    else:
        frozen_features = dict(
            cycle={
                k: copy.deepcopy(feature[k])
                for k in (
                    "scope",
                    "origin_date",
                    "timezone",
                    "cutoff",
                    "features",
                    "planned_events",
                )
            },
            structure=copy.deepcopy(structural["comparison"]),
        )
        area = structural["comparison"]["area_changes"][p.area_basis]
        area_hash = cycle.digest(
            dict(
                scope=case.scope.model_dump(),
                basis=p.area_basis,
                value_mu=area["next_mu"],
                record_ids=area["next_record_ids"],
            )
        )
        try:
            if structure._number(case.area_mu) != structure._number(area["next_mu"]):
                raise ValueError("AREA_IDENTITY_MISMATCH")
            if Decimal(case.area_mu) <= 0:
                raise ValueError("AREA_NOT_POSITIVE")
        except ValueError as exc:
            failures.append(_failure(str(exc)))
    return dict(
        case_id=case.case_id,
        scope_id=case.scope_id,
        member_id=case.member_id,
        scope=case.scope.model_dump(),
        origin=origin.model_dump(mode="json")
        if origin
        else dict(
            origin_id=case.origin_id, origin_date=None, cutoff=None, timezone=p.business_timezone
        ),
        calendar=calendar.model_dump(mode="json") if calendar else None,
        calendar_sha256=cycle.digest(calendar.model_dump(mode="json")) if calendar else None,
        evaluation_family=case.evaluation_family,
        split=case.split,
        dates=scope_dates,
        area_mu=area_mu,
        area_authority_sha256=area_hash,
        prediction_refs=dict(baseline=case.baseline_curve_id, candidate=case.candidate_curve_id),
        features=frozen_features,
        feature_sha256=cycle.digest(frozen_features),
        failures=failures,
        principal_reason=_principal(failures),
    )


def register(s1_result: Record, s2_result: Record, protocol: Record) -> Record:
    """Register C0/scope/features with no label or prediction-value interface."""
    if any(
        v.get("data_class") != "SYNTHETIC_TEST_FIXTURE" for v in (s1_result, s2_result, protocol)
    ):
        raise ValueError("SYNTHETIC_ONLY")
    p = Protocol.model_validate(protocol)
    if (
        len(p.cases) > 2048
        or len(p.curves) > 4096
        or len(cycle.canonical(protocol)) > cycle.MAX_BYTES
    ):
        raise ValueError("S3_INPUT_SIZE_LIMIT")
    if p.quantity_basis != BASIS or p.unit != "kg":
        raise ValueError("PHYSICAL_BASIS_MISMATCH")
    if not structure._known(p.comparison_family) or set(p.models) != {"baseline", "candidate"}:
        raise ValueError("PRE_REGISTRATION_IDENTITY_REQUIRED")
    if (
        s2_result["input_identity"]["s1_result_sha256"] != s1_result["result_sha256"]
        or structure.prepare(s1_result, s2_result["original_declarations"]) != s2_result
    ):
        raise ValueError("S1_S2_RECOMPUTATION_MISMATCH")
    if s2_result["business_timezone"] != p.business_timezone:
        raise ValueError("BUSINESS_TIMEZONE_MISMATCH")
    for rows, key in ((p.cases, "case_id"), (p.curves, "curve_id"), (p.calendars, "calendar_id")):
        _unique(rows, key)
    _unique(p.cases, "scope_id")
    if any(
        (c.scope.season, c.scope.variety, c.scope.production_system)
        != (p.season, p.variety, p.production_system)
        for c in p.cases
    ):
        raise ValueError("COMPARISON_COHORT_ISOLATION_PRE_REGISTRATION_REQUIRED")
    curve_keys = [(c.member_id, c.origin_id, c.side) for c in p.curves]
    if len(curve_keys) != len(set(curve_keys)):
        raise ValueError("ONE_PREDICTION_VERSION_PER_ORIGIN_REQUIRED")
    curves = {c.curve_id: c for c in p.curves}
    for c in p.cases:
        for side, ref in (("baseline", c.baseline_curve_id), ("candidate", c.candidate_curve_id)):
            spec = curves.get(ref)
            if spec and (spec.member_id, spec.origin_id, spec.side) != (
                c.member_id,
                c.origin_id,
                side,
            ):
                raise ValueError("H7_H15_VERSION_OR_MEMBER_MISMATCH")
    full = [
        (c.scope.base, c.scope.season, c.split)
        for c in p.cases
        if c.evaluation_family == FAMILIES[0]
    ]
    units = [
        (c.member_id, c.origin_id, c.split, c.evaluation_family, str(c.remaining_start))
        for c in p.cases
    ]
    if len(full) != len(set(full)):
        raise ValueError("ONE_FULL_SEASON_ISSUANCE_REQUIRED")
    if len(units) != len(set(units)):
        raise ValueError("C0_DUPLICATE_COMPARISON_UNIT")
    with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
        cases = [
            _case_registration(c, p, s1_result, s2_result)
            for c in sorted(p.cases, key=lambda c: c.case_id)
        ]
    body = dict(
        schema_version="V0_21_S3_REGISTRATION_R1",
        data_class="SYNTHETIC_TEST_FIXTURE",
        protocol=copy.deepcopy(protocol),
        evidence=dict(s1=copy.deepcopy(s1_result), s2=copy.deepcopy(s2_result)),
        cases=cases,
        candidate_count=len(cases),
        c0_member_ids=[c["case_id"] for c in cases],
        c0_members_sha256=math.digest([c["case_id"] for c in cases]),
        strict_pit_validated=False,
        real_source_authority_proven=False,
        model_use_authorized=False,
        labels_read=False,
        c0_status="SYNTHETIC_REGISTERED_ONLY",
    )
    return {**body, "registration_sha256": cycle.digest(body)}


def _verify_registration(value: Record) -> None:
    if value.get("data_class") != "SYNTHETIC_TEST_FIXTURE":
        raise ValueError("SYNTHETIC_ONLY")
    if register(value["evidence"]["s1"], value["evidence"]["s2"], value["protocol"]) != value:
        raise ValueError("REGISTRATION_SEAL_MISMATCH")


def _curve(spec: CurveSpec, raw: Prediction | None, case: Record, p: Protocol) -> Record:
    failures = []
    if raw is None or raw.failure or raw.rows is None:
        failures.append(_failure("MISSING_PREDICTION"))
        return dict(
            status="NOT_COMPUTABLE",
            failures=failures,
            rows=[],
            support_reason=None,
            declared_failure=raw.failure if raw else None,
        )
    origin = case["origin"]
    try:
        cutoff = cycle._aware(origin["cutoff"])
        issued, available, ingested = [
            cycle._aware(t) for t in (raw.issued_at, raw.input_available_at, raw.input_ingested_at)
        ]
        if issued > cutoff:
            raise ValueError("ISSUED_AFTER_CUTOFF")
        if issued < cutoff:
            raise ValueError("FEATURE_SNAPSHOT_CUTOFF_AFTER_ISSUANCE")
        if max(available, ingested) > cutoff or max(available, ingested) > issued:
            raise ValueError("INPUT_AVAILABLE_AFTER_CUTOFF")
        if issued >= datetime.combine(spec.support_start, time.min, ZoneInfo(p.business_timezone)):
            raise ValueError("ISSUANCE_NOT_BEFORE_TARGET_START")
        if p.models[spec.side].trained_through >= date.fromisoformat(origin["origin_date"]):
            raise ValueError("TRAINING_NOT_BEFORE_ORIGIN")
    except ValueError as exc:
        failures.append(_failure(str(exc)))
    if (raw.quantity_basis, raw.unit) != (p.quantity_basis, p.unit):
        failures.append(_failure("PHYSICAL_BASIS_MISMATCH"))
    model = p.models[spec.side]
    if (raw.model_id, raw.fit_sha256, raw.config_sha256) != (
        model.model_id,
        model.fit_sha256,
        model.config_sha256,
    ):
        failures.append(_failure("MODEL_IDENTITY_MISMATCH"))
    if (
        raw.scope.model_dump() != case["scope"]
        or raw.member_id != spec.member_id
        or raw.origin_id != spec.origin_id
        or raw.prediction_version != spec.prediction_version
        or raw.source_population_sha256 != p.source_population_sha256
    ):
        failures.append(_failure("PREDICTION_IDENTITY_MISMATCH"))
    if raw.area_mu != case["area_mu"] or raw.area_authority_sha256 != case["area_authority_sha256"]:
        failures.append(_failure("AREA_IDENTITY_MISMATCH"))
    rows, why = _parse_rows(raw.rows)
    if why:
        failures.append(_failure(why))
    support_reason = None
    if spec.support_end is None:
        support_reason = "UNKNOWN_SEASON_END"
    elif spec.support_start > spec.support_end or any(
        r.day < spec.support_start or r.day > spec.support_end for r in rows
    ):
        failures.append(_failure("CURVE_SUPPORT_MISMATCH"))
    else:
        support_reason = math._calendar_reason(
            rows, tuple(date.fromisoformat(d) for d in _dates(spec.support_start, spec.support_end))
        )
    return dict(
        status="NOT_COMPUTABLE" if failures else "SEALED_SYNTHETIC_CURVE",
        failures=failures,
        rows=_serialize(rows),
        support_reason=support_reason,
    )


def seal_predictions(registration: Record, predictions: Record) -> Record:
    """Phase A seals supplied synthetic vectors. This function never accepts labels."""
    _verify_registration(registration)
    p = Protocol.model_validate(registration["protocol"])
    raw = Predictions.model_validate(predictions)
    if raw.registration_sha256 != registration["registration_sha256"]:
        raise ValueError("PREDICTION_REGISTRATION_MISMATCH")
    _unique(raw.curves, "curve_id")
    by_id = {c.curve_id: c for c in raw.curves}
    if not by_id.keys() <= {s.curve_id for s in p.curves}:
        raise ValueError("PREDICTION_COHORT_EXPANSION")
    specs = {s.curve_id: s for s in p.curves}
    by_member = {(c["member_id"], c["origin"]["origin_id"]): c for c in registration["cases"]}
    curves = {}
    cases = []
    with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
        for spec in sorted(p.curves, key=lambda c: c.curve_id):
            case = by_member.get((spec.member_id, spec.origin_id))
            if case is None:
                raise ValueError("UNREFERENCED_CURVE_SPEC")
            curves[spec.curve_id] = _curve(spec, by_id.get(spec.curve_id), case, p)
        for case in registration["cases"]:
            value = dict(case_id=case["case_id"], failures=copy.deepcopy(case["failures"]))
            for side in ("baseline", "candidate"):
                ref = case["prediction_refs"][side]
                source = curves.get(ref)
                failures = (
                    copy.deepcopy(source["failures"])
                    if source
                    else [_failure("MISSING_PREDICTION")]
                )
                rows: tuple[DailyKg, ...] = ()
                if source is not None and not failures and case["dates"]:
                    spec = specs[ref]
                    expected = case["dates"]
                    if (
                        spec.support_end is None
                        or date.fromisoformat(expected[0]) < spec.support_start
                        or date.fromisoformat(expected[-1]) > spec.support_end
                    ):
                        failures.append(_failure("CURVE_SUPPORT_MISMATCH"))
                    rows, why = _parse_rows(
                        [
                            Row.model_validate(r)
                            for r in source["rows"]
                            if r["date"] in set(expected)
                        ],
                        expected,
                    )
                    if why:
                        failures.append(_failure(why))
                if not case["dates"]:
                    failures.append(_failure("INCOMPLETE_CALENDAR"))
                identity = dict(
                    model=p.models[side].model_dump(mode="json"),
                    version=specs[ref].prediction_version if ref in specs else None,
                    origin=case["origin"],
                    scope=case["scope"],
                    feature_sha256=case["feature_sha256"],
                    rows=_serialize(rows),
                )
                value[side] = dict(
                    status="NOT_COMPUTABLE" if failures else "SEALED_SYNTHETIC_PREDICTION",
                    failures=failures,
                    rows=_serialize(rows),
                    prediction_identity_sha256=cycle.digest(identity),
                    peaks=_peaks(rows) if rows and not failures else None,
                )
                value["failures"].extend(failures)
            value["principal_reason"] = _principal(value["failures"])
            cases.append(value)
    body = dict(
        schema_version="V0_21_S3_PREDICTION_SEAL_R1",
        data_class="SYNTHETIC_TEST_FIXTURE",
        registration=copy.deepcopy(registration),
        raw_predictions=copy.deepcopy(predictions),
        curves=curves,
        cases=cases,
        labels_read=False,
        real_prediction_generated=False,
        strict_pit_validated=False,
    )
    return {**body, "seal_sha256": cycle.digest(body)}


def _verify_seal(value: Record) -> None:
    if value.get("data_class") != "SYNTHETIC_TEST_FIXTURE":
        raise ValueError("SYNTHETIC_ONLY")
    if seal_predictions(value["registration"], value["raw_predictions"]) != value:
        raise ValueError("PREDICTION_SEAL_MISMATCH")


def _label(
    lab: Label | None, case: Record, p: Protocol, as_of: datetime
) -> tuple[tuple[DailyKg, ...], list[Record]]:
    if lab is None:
        return (), [_failure("MISSING_LABEL")]
    failures = []
    try:
        clocks = [cycle._aware(t) for t in (lab.available_at, lab.complete_at, lab.mature_at)]
        if not lab.complete or not lab.mature:
            raise ValueError("LABEL_NOT_COMPLETE_OR_MATURE")
        if any(t > as_of for t in clocks):
            raise ValueError("LABEL_NOT_AVAILABLE_AT_SCORING")
        if case["dates"]:
            end = datetime.combine(
                date.fromisoformat(case["dates"][-1]) + timedelta(days=1),
                time.min,
                ZoneInfo(p.business_timezone),
            )
            if clocks[1] < end or clocks[2] < end:
                raise ValueError("LABEL_MATURITY_BEFORE_SCOPE_COMPLETE")
    except ValueError as exc:
        failures.append(_failure(str(exc)))
    if (lab.quantity_basis, lab.unit) != (p.quantity_basis, p.unit):
        failures.append(_failure("PHYSICAL_BASIS_MISMATCH"))
    if lab.member_id != case["member_id"] or lab.scope.model_dump() != case["scope"]:
        failures.append(_failure("LABEL_IDENTITY_MISMATCH"))
    if (lab.area_mu, lab.area_authority_sha256) != (case["area_mu"], case["area_authority_sha256"]):
        failures.append(_failure("AREA_IDENTITY_MISMATCH"))
    rows, reason = _parse_rows(lab.rows, case["dates"])
    if reason:
        failures.append(_failure(reason))
    return rows, failures


def _metric_reason(name: str, case: Record, data: Record) -> str | None:
    if data["principal_reason"]:
        return str(data["principal_reason"])
    family = case["evaluation_family"]
    if name == "SEASON_TOTAL_WAPE" and family != FAMILIES[0]:
        return "INCOMPLETE_CALENDAR"
    if name in ADDITIVE[:2] and family not in FAMILIES[:2]:
        return "NOT_APPLICABLE_SCOPE"
    if name in ADDITIVE[2:] and family not in FAMILIES[2:]:
        return "NOT_APPLICABLE_SCOPE"
    n = 15 if name in ADDITIVE[:2] else 7 if name.startswith("ROLLING_7") else 1
    if len(case["dates"]) < n:
        return f"NO_COMPLETE_{n}DAY_WINDOW"
    if name.endswith(("DATE_MAE", "START_MAE")) and not data["positive_actual"]:
        return "NO_POSITIVE_ACTUAL_PEAK"
    return None


def _annotate_metric(
    value: Record, name: str, cases: list[Record], data: dict[str, Record]
) -> Record:
    value = copy.deepcopy(value)
    for side in ("baseline", "candidate"):
        value[side]["metric_value"] = value[side]["value"]
        value[side]["ratio"] = value[side]["value"]
    ids = value["common_member_ids"]
    value["baseline_available_count"] = sum(data[c["case_id"]]["baseline_available"] for c in cases)
    value["candidate_available_count"] = sum(
        data[c["case_id"]]["candidate_available"] for c in cases
    )
    b, c = value["baseline"]["value"], value["candidate"]["value"]
    value["candidate_minus_baseline"] = (
        str(Decimal(c) - Decimal(b)) if b is not None and c is not None else None
    )
    value["principal_failure_reasons"] = value["exclusions"]
    if name.endswith(("DATE_MAE", "START_MAE")):
        n = 15 if name in ADDITIVE[:2] else 7 if name.startswith("ROLLING_7") else 1
        counts = {
            c["case_id"]: max(0, len(c["dates"]) - n + 1) for c in cases if c["case_id"] in ids
        }
        value["candidate_window_counts"] = counts
        value["structural_member_ids"] = [sid for sid, count in counts.items() if count == 1]
        value["timing_skill_interpretable"] = bool(ids) and all(n > 1 for n in counts.values())
    return value


def _additive(name: str, cases: list[Record], data: dict[str, Record]) -> Record:
    excluded = {}
    common = []
    for case in cases:
        reason = _metric_reason(name, case, data[case["case_id"]])
        if reason:
            excluded[case["case_id"]] = reason
        else:
            common.append(case)
    actual = sum((data[c["case_id"]]["actual_total"] for c in common), Decimal(0))
    if name.endswith("WAPE") and not actual:
        excluded.update({c["case_id"]: "ZERO_DENOMINATOR" for c in common})
        common = []
    denominator = actual if name.endswith("WAPE") else Decimal(len(common))
    values = {}
    for side in ("baseline", "candidate"):
        numerator = sum((data[c["case_id"]]["errors"][side][name] for c in common), Decimal(0))
        values[side] = math._fraction(numerator, denominator)
    ids = sorted(c["case_id"] for c in common)
    value = dict(
        **values,
        candidate_count=len(cases),
        common_count=len(common),
        common_member_ids=ids,
        common_members_sha256=math.digest(ids),
        not_computable_count=len(cases) - len(common),
        exclusions=excluded,
        reasons=dict(sorted(Counter(excluded.values()).items())),
        sample_coverage=str(Decimal(len(common)) / Decimal(len(cases))) if cases else None,
        base_coverage=math._fraction(
            Decimal(len({c["scope"]["base"] for c in common})),
            Decimal(len({c["scope"]["base"] for c in cases})),
        ),
        target_row_coverage=math._fraction(
            Decimal(sum(len(c["dates"]) for c in common)),
            Decimal(sum(len(c["dates"]) for c in cases)),
        ),
    )
    return _annotate_metric(value, name, cases, data)


def _group(cases: list[Record], data: dict[str, Record]) -> Record:
    # Populate the existing generic accumulator; its original _add is H7/H15-only.
    # No fake FULL_SEASON flag or physical-basis relabel is passed to an old gate.
    acc = aggregation._accumulator()
    acc.update(
        count=len(cases),
        rows=sum(len(c["dates"]) for c in cases),
        bases={c["scope"]["base"] for c in cases},
    )
    for case in cases:
        sid = case["case_id"]
        row = data[sid]
        for name, slot in acc["metrics"].items():
            reason = _metric_reason(name, case, row)
            if reason:
                slot["reasons"][sid] = reason
                continue
            slot["ids"].append(sid)
            slot["rows"] += len(case["dates"])
            slot["bases"].add(case["scope"]["base"])
            slot["actual"] += row["actual_total"]
            for side in ("baseline", "candidate"):
                slot[side] += row["errors"][side][name]
        if _metric_reason("DAILY_MAE", case, row) is None:
            base = acc["base_errors"].setdefault(
                case["scope"]["base"], [Decimal(0), Decimal(0), Decimal(0)]
            )
            base[0] += row["errors"]["baseline"]["DAILY_MAE"]
            base[1] += row["errors"]["candidate"]["DAILY_MAE"]
            base[2] += row["actual_total"]
    old = aggregation._finish(acc)
    metrics = {
        name: _annotate_metric(old["metrics"][name], name, cases, data)
        for name in math.ERROR_METRICS
    }
    metrics.update(
        {
            name: copy.deepcopy(old["metrics"][name])
            for name in math.METRICS
            if name not in math.ERROR_METRICS
        }
    )
    for name in ADDITIVE:
        metrics[name] = _additive(name, cases, data)
    for name in ADDITIVE:
        metrics["SAMPLE_COVERAGE"][name] = metrics[name]["sample_coverage"]
        metrics["NOT_COMPUTABLE_COUNT"][name] = metrics[name]["not_computable_count"]
    changes = {
        name: m["candidate_minus_baseline"]
        for name, m in metrics.items()
        if name in (*math.ERROR_METRICS, *ADDITIVE)
    }
    daily = metrics["DAILY_MAE"]
    deltas = [Decimal(v) for v in changes.values() if v is not None]
    diagnostic = (
        "INCONCLUSIVE"
        if daily["common_count"] != len(cases)
        or not deltas
        or daily["baseline_available_count"] != daily["candidate_available_count"]
        else "MIXED"
        if any(v < 0 for v in deltas) and any(v > 0 for v in deltas)
        else "IMPROVED"
        if any(v < 0 for v in deltas)
        else "WORSENED"
        if any(v > 0 for v in deltas)
        else "TIED"
    )
    return dict(
        candidate_count=len(cases),
        metrics=metrics,
        candidate_minus_baseline=changes,
        diagnosis=diagnostic,
        conclusion_scope="SYNTHETIC_CONDITIONAL_ON_COMMON_COHORT",
        overlapping_origins_not_independent=True,
        clustering_unit="BASE_AND_SEASON",
        date_denominator_complete=all(bool(c["dates"]) for c in cases),
    )


def score(seal: Record, labels: Record, *, as_of: str) -> Record:
    """Phase B verifies A before touching the separately supplied synthetic labels."""
    _verify_seal(seal)
    p = Protocol.model_validate(seal["registration"]["protocol"])
    bundle = Labels.model_validate(labels)
    clock = cycle._aware(as_of)
    if (bundle.registration_sha256, bundle.label_authority_sha256, bundle.source_version) != (
        seal["registration"]["registration_sha256"],
        p.label_authority_sha256,
        p.label_source_version,
    ):
        raise ValueError("LABEL_AUTHORITY_OR_REGISTRATION_MISMATCH")
    _unique(bundle.labels, "case_id")
    cases = seal["registration"]["cases"]
    by_id = {c["case_id"]: c for c in cases}
    labs = {label.case_id: label for label in bundle.labels}
    if not labs.keys() <= by_id.keys():
        raise ValueError("LABEL_COHORT_EXPANSION")
    pred = {c["case_id"]: c for c in seal["cases"]}
    with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
        label_data = {sid: _label(labs.get(sid), case, p, clock) for sid, case in by_id.items()}
        seen: dict[tuple[str, str], list[tuple[str, Decimal]]] = {}
        for sid, (rows, failures) in label_data.items():
            if failures:
                continue
            for r in rows:
                seen.setdefault((by_id[sid]["member_id"], str(r.day)), []).append((sid, r.kg))
        for values in seen.values():
            if len({v for _, v in values}) > 1:
                for sid, _ in values:
                    if not any(
                        f["detail"] == "CONFLICTING_LABEL_VERSIONS" for f in label_data[sid][1]
                    ):
                        label_data[sid][1].append(_failure("CONFLICTING_LABEL_VERSIONS"))
        data = {}
        ledger = []
        for case in cases:
            sid = case["case_id"]
            prediction = pred[sid]
            aa, failures = label_data[sid]
            all_failures = copy.deepcopy(prediction["failures"]) + failures
            if not case["dates"]:
                all_failures.append(_failure("INCOMPLETE_CALENDAR"))
            why = _principal(all_failures)
            row = dict(
                principal_reason=why,
                positive_actual=any(r.kg > 0 for r in aa),
                actual_total=sum((r.kg for r in aa), Decimal(0)),
                errors={},
                baseline_available=prediction["baseline"]["status"]
                == "SEALED_SYNTHETIC_PREDICTION",
                candidate_available=prediction["candidate"]["status"]
                == "SEALED_SYNTHETIC_PREDICTION",
            )
            detail = dict(
                case_id=sid,
                scope_id=case["scope_id"],
                scope=case["scope"],
                member_id=case["member_id"],
                origin=case["origin"],
                evaluation_family=case["evaluation_family"],
                split=case["split"],
                dates=case["dates"],
                principal_reason=why,
                failures=all_failures,
                daily=[],
                totals=None,
                actual_peaks=None,
                baseline_peaks=prediction["baseline"]["peaks"],
                candidate_peaks=prediction["candidate"]["peaks"],
            )
            if why is None:
                detail["actual_peaks"] = _peaks(aa, actual=True)
                total = row["actual_total"]
                totals = dict(actual_kg=_six(total))
                predicted_rows = {}
                for side in ("baseline", "candidate"):
                    pp, _ = _parse_rows(
                        [Row.model_validate(r) for r in prediction[side]["rows"]], case["dates"]
                    )
                    predicted_rows[side] = pp
                    errors = math._errors(
                        math.Forecast(
                            p.models[side].model_id,
                            sid,
                            p.models[side].fit_sha256,
                            p.source_population_sha256,
                            pp,
                        ),
                        math.Labels(sid, sid, p.label_authority_sha256, aa, clock, clock, True),
                    )
                    peaks = _peaks(pp)
                    if len(pp) >= 15:
                        actual15 = detail["actual_peaks"]["rolling15"]
                        errors[ADDITIVE[0]] = (
                            Decimal(
                                abs(
                                    (
                                        date.fromisoformat(peaks["rolling15"]["start_date"])
                                        - date.fromisoformat(actual15["start_date"])
                                    ).days
                                )
                            )
                            if row["positive_actual"]
                            else Decimal(0)
                        )
                        errors[ADDITIVE[1]] = abs(
                            Decimal(peaks["rolling15"]["quantity_kg"])
                            - Decimal(actual15["quantity_kg"])
                        )
                    predicted_total = sum((r.kg for r in pp), Decimal(0))
                    errors[ADDITIVE[2]] = errors[ADDITIVE[3]] = abs(predicted_total - total)
                    row["errors"][side] = errors
                    totals.update(
                        {
                            side + "_kg": _six(predicted_total),
                            side + "_signed_error_kg": _six(predicted_total - total),
                            side + "_absolute_error_kg": _six(abs(predicted_total - total)),
                        }
                    )
                detail["totals"] = totals
                detail["daily"] = [
                    dict(
                        date=str(a.day),
                        actual_kg=_six(a.kg),
                        baseline_kg=_six(b.kg),
                        candidate_kg=_six(c.kg),
                        baseline_signed_error_kg=_six(b.kg - a.kg),
                        candidate_signed_error_kg=_six(c.kg - a.kg),
                        baseline_absolute_error_kg=_six(abs(b.kg - a.kg)),
                        candidate_absolute_error_kg=_six(abs(c.kg - a.kg)),
                    )
                    for a, b, c in zip(
                        aa, predicted_rows["baseline"], predicted_rows["candidate"], strict=True
                    )
                ]
            data[sid] = row
            ledger.append(detail)
        groups: dict[str, list[Record]] = {}
        for case in cases:
            groups.setdefault(case["split"] + ":" + case["evaluation_family"], []).append(case)
        body = dict(
            schema_version="V0_21_S3_EVALUATION_R1",
            data_class="SYNTHETIC_TEST_FIXTURE",
            comparison_family=p.comparison_family,
            quantity_basis=p.quantity_basis,
            unit=p.unit,
            registration_sha256=seal["registration"]["registration_sha256"],
            prediction_seal_sha256=seal["seal_sha256"],
            label_payload_sha256=cycle.digest(labels),
            scoring_as_of=clock.astimezone(UTC).isoformat(),
            candidate_count=len(cases),
            groups={k: _group(v, data) for k, v in sorted(groups.items())},
            member_ledger=ledger,
            strict_pit_validated=False,
            real_source_authority_proven=False,
            real_scoring_performed=False,
            model_training=False,
            production_forecast_change=False,
            s4_implemented=False,
            overlapping_origins_not_independent=True,
        )
    return {**body, "result_sha256": cycle.digest(body)}


def _daily_csv(result: Record) -> bytes:
    target = io.StringIO(newline="")
    writer = csv.writer(target, lineterminator="\n")
    writer.writerow(
        [
            "case_id",
            "evaluation_family",
            "date",
            "actual_kg",
            "baseline_kg",
            "candidate_kg",
            "baseline_signed_error_kg",
            "candidate_signed_error_kg",
            "baseline_absolute_error_kg",
            "candidate_absolute_error_kg",
        ]
    )
    for case in result["member_ledger"]:
        sid = case["case_id"]
        if sid.lstrip().startswith(("=", "+", "-", "@")):
            sid = "'" + sid
        for r in case["daily"]:
            writer.writerow(
                [
                    sid,
                    case["evaluation_family"],
                    *[
                        r[k]
                        for k in (
                            "date",
                            "actual_kg",
                            "baseline_kg",
                            "candidate_kg",
                            "baseline_signed_error_kg",
                            "candidate_signed_error_kg",
                            "baseline_absolute_error_kg",
                            "candidate_absolute_error_kg",
                        )
                    ],
                ]
            )
    return target.getvalue().encode()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command, fields in (
        ("register", ("s1", "s2", "protocol")),
        ("seal", ("registration", "predictions")),
        ("score", ("seal", "labels")),
    ):
        child = sub.add_parser(command)
        for field in fields:
            child.add_argument("--" + field, type=Path, required=True)
        child.add_argument("--output", type=Path, required=True)
        if command == "score":
            child.add_argument("--as-of", required=True)
    args = parser.parse_args()
    files = {}

    def read(name: str) -> Record:
        path = getattr(args, name)
        value = cycle._read(path)
        files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        return value

    if args.command == "register":
        protocol = read("protocol")
        if protocol.get("data_class") != "SYNTHETIC_TEST_FIXTURE":
            raise ValueError("SYNTHETIC_ONLY")
        result = register(read("s1"), read("s2"), protocol)
        name = "registration.json"
    elif args.command == "seal":
        reg = read("registration")
        _verify_registration(reg)
        result = seal_predictions(reg, read("predictions"))
        name = "prediction-seal.json"
    else:
        sealed = read("seal")
        _verify_seal(sealed)
        result = score(sealed, read("labels"), as_of=args.as_of)
        name = "evaluation.json"
    args.output.mkdir(mode=0o700)
    manifest = dict(
        schema_version="V0_21_S3_RUN_MANIFEST_R1",
        phase=args.command,
        executed_at_utc=datetime.now(UTC).isoformat(),
        module_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        input_file_sha256=files,
        synthetic_only=True,
        strict_pit_validated=False,
    )
    outputs = {
        name: cycle.canonical(result) + b"\n",
        "manifest.json": cycle.canonical(manifest) + b"\n",
    }
    if args.command == "score":
        outputs["daily-errors.csv"] = _daily_csv(result)
    for filename, raw in outputs.items():
        path = args.output / filename
        with path.open("xb") as f:
            f.write(raw)
        path.chmod(0o600)
    print(
        cycle.canonical(
            dict(
                phase=args.command,
                result_sha256=result.get(
                    "result_sha256", result.get("seal_sha256", result.get("registration_sha256"))
                ),
                synthetic_only=True,
            )
        ).decode()
    )


if __name__ == "__main__":
    main()
