"""S3 local SYNTHETIC preparation only; no real-data loader or scoring entry.

Phase A cannot accept labels. Phase B verifies that immutable prediction seal
before examining synthetic labels. A content digest is not a signature, data
permission, or evidence that a real prediction was issued before its labels.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass, is_dataclass, replace
from datetime import date, datetime, timedelta
from decimal import Context, Decimal, localcontext
from typing import Any

from backend.research.v019_daily_curve import (
    CurveInput,
    DailyKg,
    canonical_bytes,
    generate_candidate,
    method_config,
)

BASELINE = "OPERATIONAL_PEAK:AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1"
CANDIDATE = "BIN_CENTER_LINEAR_PER_BIN_MASS_V1"
AUTHORITIES = (
    "BASE_SUBFARM_VARIETY_IDENTITY",
    "AREA_AND_EFFECTIVE_DATE",
    "RUN_AND_ISSUED_AT",
    "MODEL_PROFILE_FIT_HASH",
    "HARVEST_DATE_AND_UNIT",
    "LABEL_AUTHORITY",
    "AVAILABLE_AT_INGESTED_AT",
    "INPUT_CUTOFF",
    "LABEL_MATURITY_COMPLETENESS",
    "TRAIN_VALIDATION_EXPOSED_OOT_SPLIT",
    "COMMON_COHORT_MEMBERSHIP_HASH",
    "PREDICTION_LABEL_SEALS",
)
ERROR_METRICS = (
    "SEASON_TOTAL_WAPE",
    "DAILY_WAPE",
    "DAILY_MAE",
    "SINGLE_DAY_PEAK_DATE_MAE",
    "SINGLE_DAY_PEAK_QUANTITY_MAE",
    "ROLLING_7DAY_PEAK_START_MAE",
    "ROLLING_7DAY_PEAK_QUANTITY_MAE",
)
METRICS = ERROR_METRICS + ("BASE_BREADTH", "SAMPLE_COVERAGE", "NOT_COMPUTABLE_COUNT")
D = Decimal


def _json(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _json(asdict(value))
    if isinstance(value, dict):
        return {key: _json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        # str preserves exact Decimal input; even invalid values can be sealed
        # and retained as explicit non-computable cases, never silently dropped.
        return str(value)
    return value


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(_json(value))).hexdigest()


def _hash(value: str) -> bool:
    return re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _aware(value: datetime) -> bool:
    return isinstance(value, datetime) and value.utcoffset() is not None


@dataclass(frozen=True)
class Authority:
    name: str
    status: str
    evidence_sha256: str | None


@dataclass(frozen=True)
class Sample:
    sample_id: str
    base_id: str
    organization_id: str
    subfarm_id: str
    variety_id: str
    season: str
    area_mu: Decimal
    area_effective_date: date
    origin: datetime
    issued_at: datetime
    cutoff: datetime
    input_available_at: datetime
    input_ingested_at: datetime
    dates: tuple[date, ...]
    window: str
    physical_basis: str
    unit: str
    profile_sha256: str
    input_sha256: str
    label_authority_sha256: str
    train_scope_sha256: str
    split: str
    full_season_registered: bool
    authorities: tuple[Authority, ...]
    data_class: str = "SYNTHETIC"

    @property
    def identity_sha256(self) -> str:
        return digest(self)


@dataclass(frozen=True)
class Forecast:
    model_id: str
    sample_identity_sha256: str
    fit_sha256: str
    source_sha256: str
    rows: tuple[DailyKg, ...]


@dataclass(frozen=True)
class Pair:
    sample_id: str
    baseline: Forecast | None
    candidate: Forecast | None
    failure: str | None = None


@dataclass(frozen=True)
class Labels:
    sample_id: str
    sample_identity_sha256: str
    authority_sha256: str
    rows: tuple[DailyKg, ...]
    available_at: datetime
    mature_at: datetime
    mature: bool


@dataclass(frozen=True)
class PredictionSeal:
    samples: tuple[Sample, ...]
    pairs: tuple[Pair, ...]
    raw: bytes
    sha256: str


def _permission(samples: tuple[Sample, ...], authorized: bool) -> None:
    if not authorized or any(
        s.data_class != "SYNTHETIC"
        or not all(
            value.startswith("SYNTHETIC-")
            for value in (
                s.sample_id,
                s.base_id,
                s.organization_id,
                s.subfarm_id,
                s.variety_id,
                s.season,
            )
        )
        for s in samples
    ):
        raise PermissionError("SYNTHETIC_AUTHORIZATION_REQUIRED_NO_REAL_SCORING_ENTRY")


def _seal_body(samples: tuple[Sample, ...], pairs: tuple[Pair, ...]) -> dict[str, Any]:
    return {
        "data_class": "SYNTHETIC",
        "baseline_id": BASELINE,
        "candidate_id": CANDIDATE,
        "method_config_sha256": digest(method_config()),
        "c0": _json(samples),
        "c0_sha256": digest(samples),
        "pairs": _json(pairs),
        "forecast_sha256": {
            p.sample_id: {
                "baseline": digest(p.baseline) if p.baseline else None,
                "candidate": digest(p.candidate) if p.candidate else None,
            }
            for p in pairs
        },
        "labels_read": False,
    }


def freeze_predictions(
    samples: tuple[Sample, ...], pairs: tuple[Pair, ...], *, synthetic_authorized: bool
) -> PredictionSeal:
    """Label-free Phase A; every registered unit, including failures, is retained."""
    _permission(samples, synthetic_authorized)
    samples = tuple(sorted(samples, key=lambda s: s.sample_id))
    pairs = tuple(sorted(pairs, key=lambda p: p.sample_id))
    ids = [s.sample_id for s in samples]
    if len(ids) != len(set(ids)) or [p.sample_id for p in pairs] != ids:
        raise ValueError("C0_EXACT_MEMBERSHIP_REQUIRED_INCLUDE_FAILED_ORIGINS")
    units = [digest(replace(s, sample_id="")) for s in samples]
    if len(units) != len(set(units)):
        raise ValueError("C0_DUPLICATE_COMPARISON_UNIT")
    if any((p.baseline is None or p.candidate is None) and not p.failure for p in pairs):
        raise ValueError("MISSING_PREDICTION_FAILURE_REASON_REQUIRED")
    # One registered full-season issuance per base/season/split: no stitching
    # or post-hoc best-origin selection even if all dates happen to be complete.
    full = [(s.base_id, s.season, s.split) for s in samples if s.window == "FULL_SEASON"]
    if len(full) != len(set(full)):
        raise ValueError("ONE_FULL_SEASON_ISSUANCE_REQUIRED")
    raw = canonical_bytes(_seal_body(samples, pairs))
    return PredictionSeal(samples, pairs, raw, hashlib.sha256(raw).hexdigest())


def real_scoring_preflight() -> dict[str, Any]:
    """No filesystem discovery: unknown authorities stay unknown, not absent."""
    return {
        "S3_REAL_SCORING": "BLOCKED",
        "data_read_authorization": "BLOCKED",
        "experiment_authorization": "BLOCKED",
        "formal_s3_pr_authorized": False,
        "authorities": {name: {"status": "NOT_VERIFIED", "evidence": None} for name in AUTHORITIES},
        "allowed_authority_states": ["AVAILABLE", "NOT_VERIFIED", "MISSING", "BLOCKED"],
    }


def generate_synthetic_predictions(
    samples: tuple[Sample, ...], requests: dict[str, CurveInput], *, synthetic_authorized: bool
) -> PredictionSeal:
    """Run the ONE frozen S2 candidate without labels, preserving failed origins.

    Caller first registers C0 and its complete input identities. No search,
    training or normalization of query windows occurs in this adapter.
    """
    _permission(samples, synthetic_authorized)
    if not set(requests) <= {s.sample_id for s in samples}:
        raise ValueError("C0_INPUT_EXPANSION")
    pairs = []
    for s in samples:
        request = requests.get(s.sample_id)
        if request is None:
            pairs.append(Pair(s.sample_id, None, None, "MISSING_REGISTERED_INPUT"))
            continue
        try:
            result = generate_candidate(request)
            if (
                result.input_sha256 != s.input_sha256
                or request.baseline_source_sha256 != s.profile_sha256
            ):
                raise ValueError("INPUT_OR_PROFILE_IDENTITY_MISMATCH")
            old = {r.day: r for r in request.baseline}
            new = {r.day: r for r in result.rows}
            baseline = tuple(old[day] for day in s.dates)
            candidate = tuple(new[day] for day in s.dates)
            pairs.append(
                Pair(
                    s.sample_id,
                    Forecast(
                        BASELINE,
                        s.identity_sha256,
                        s.profile_sha256,
                        request.baseline_source_sha256,
                        baseline,
                    ),
                    Forecast(
                        CANDIDATE,
                        s.identity_sha256,
                        result.config_sha256,
                        result.result_sha256,
                        candidate,
                    ),
                )
            )
        except (ValueError, KeyError) as exc:
            pairs.append(Pair(s.sample_id, None, None, f"SYNTHETIC_GENERATION_FAILURE:{exc}"))
    return freeze_predictions(samples, tuple(pairs), synthetic_authorized=True)


def _calendar_reason(rows: tuple[DailyKg, ...], expected: tuple[date, ...]) -> str | None:
    if (
        len({r.day for r in rows}) != len(rows)
        or any(
            type(r.day) is not date or not isinstance(r.kg, D) or not r.kg.is_finite() or r.kg < 0
            for r in rows
        )
        or [r.day for r in rows] != sorted(r.day for r in rows)
    ):
        return "INVALID_VALUE_OR_DUPLICATE_DATE"
    if tuple(r.day for r in rows) != expected:
        return "INCOMPLETE_CALENDAR"
    return None


def _reason(s: Sample, p: Pair, lab: Labels | None, as_of: datetime) -> str | None:
    if (
        len(s.authorities) != len(AUTHORITIES)
        or {a.name for a in s.authorities} != set(AUTHORITIES)
        or any(
            a.status != "AVAILABLE" or not a.evidence_sha256 or not _hash(a.evidence_sha256)
            for a in s.authorities
        )
        or lab is None
        or not lab.mature
        or not all(
            _aware(t)
            for t in (
                s.origin,
                s.issued_at,
                s.cutoff,
                s.input_available_at,
                s.input_ingested_at,
                lab.available_at,
                lab.mature_at,
            )
        )
    ):
        return "UNVERIFIED_AUTHORITY"
    if (
        lab.available_at > as_of
        or lab.mature_at > as_of
        or s.input_available_at > s.cutoff
        or s.input_ingested_at > s.cutoff
        or s.cutoff > s.issued_at
        or s.issued_at > as_of
        or s.area_effective_date > s.origin.date()
    ):
        return "UNVERIFIED_AUTHORITY"
    if (
        s.physical_basis != "ACTUAL_HARVEST_KG"
        or s.unit != "kg"
        or not s.area_mu.is_finite()
        or s.area_mu <= 0
    ):
        return "PHYSICAL_BASIS_MISMATCH"
    if (
        not all(
            _hash(h)
            for h in (
                s.profile_sha256,
                s.input_sha256,
                s.label_authority_sha256,
                s.train_scope_sha256,
            )
        )
        or lab.sample_identity_sha256 != s.identity_sha256
        or lab.authority_sha256 != s.label_authority_sha256
        or p.baseline is None
        or p.candidate is None
    ):
        return "IDENTITY_OR_SOURCE_HASH_MISMATCH"
    for f, model in ((p.baseline, BASELINE), (p.candidate, CANDIDATE)):
        if (
            f.model_id != model
            or f.sample_identity_sha256 != s.identity_sha256
            or not _hash(f.fit_sha256)
            or not _hash(f.source_sha256)
        ):
            return "IDENTITY_OR_SOURCE_HASH_MISMATCH"
    if not s.dates or any(type(d) is not date for d in s.dates):
        return "INCOMPLETE_CALENDAR"
    if any(y - x != timedelta(days=1) for x, y in zip(s.dates, s.dates[1:], strict=False)):
        return "INCOMPLETE_CALENDAR"
    if s.window in ("H7_PREFIX", "H15_LOCAL"):
        # Only Asia/Shanghai local business dates are accepted, never UTC truncation.
        if s.origin.utcoffset() != timedelta(hours=8):
            return "UNVERIFIED_AUTHORITY"
        n = 7 if s.window == "H7_PREFIX" else 15
        if s.dates != tuple(s.origin.date() + timedelta(days=i + 1) for i in range(n)):
            return "INCOMPLETE_CALENDAR"
    elif s.window != "FULL_SEASON" or not s.full_season_registered:
        return "INCOMPLETE_CALENDAR"
    reasons = [_calendar_reason(f.rows, s.dates) for f in (p.baseline, p.candidate, lab)]
    if "INVALID_VALUE_OR_DUPLICATE_DATE" in reasons:
        return "INVALID_VALUE_OR_DUPLICATE_DATE"
    return "INCOMPLETE_CALENDAR" if any(reasons) else None


def _peak(rows: tuple[DailyKg, ...], rolling: bool) -> tuple[date, Decimal]:
    options = (
        [(rows[i].day, sum((r.kg for r in rows[i : i + 7]), D(0))) for i in range(len(rows) - 6)]
        if rolling
        else [(r.day, r.kg) for r in rows]
    )
    return min(options, key=lambda item: (-item[1], item[0]))


def _errors(p: Forecast, lab: Labels) -> dict[str, Decimal]:
    actual = sum((r.kg for r in lab.rows), D(0))
    daily = sum((abs(x.kg - y.kg) for x, y in zip(p.rows, lab.rows, strict=True)), D(0))
    pd, pq = _peak(p.rows, False)
    ad, aq = _peak(lab.rows, False)
    out = {
        "SEASON_TOTAL_WAPE": abs(sum((r.kg for r in p.rows), D(0)) - actual),
        "DAILY_WAPE": daily,
        "DAILY_MAE": daily,
        "SINGLE_DAY_PEAK_DATE_MAE": D(abs((pd - ad).days)),
        "SINGLE_DAY_PEAK_QUANTITY_MAE": abs(pq - aq),
    }
    if len(lab.rows) >= 7:
        ps, pr = _peak(p.rows, True)
        ast, ar = _peak(lab.rows, True)
        out.update(
            ROLLING_7DAY_PEAK_START_MAE=D(abs((ps - ast).days)),
            ROLLING_7DAY_PEAK_QUANTITY_MAE=abs(pr - ar),
        )
    return out


def _fraction(numerator: Decimal, denominator: Decimal) -> dict[str, str | None]:
    return {
        "numerator": str(numerator),
        "denominator": str(denominator),
        "value": str(numerator / denominator) if denominator else None,
    }


def _diagnostics(
    common: list[Sample], pairs: dict[str, Pair], labs: dict[str, Labels]
) -> dict[str, Any]:
    """Preregistered diagnostics, never a parameter search or winner decision."""
    out: dict[str, Any] = {}
    for side in ("baseline", "candidate"):
        bias = D(0)
        dates: Counter[str] = Counter()
        starts: Counter[str] = Counter()
        lead: dict[int, Decimal] = {}
        for s in common:
            f = getattr(pairs[s.sample_id], side)
            lab = labs[s.sample_id]
            assert f is not None
            for p, a in zip(f.rows, lab.rows, strict=True):
                bias += p.kg - a.kg
                k = (p.day - s.origin.date()).days
                lead[k] = lead.get(k, D(0)) + abs(p.kg - a.kg)
            if any(r.kg > 0 for r in lab.rows):
                for rolling, counts in ((False, dates), (True, starts)):
                    if rolling and len(s.dates) < 7:
                        continue
                    delta = (_peak(f.rows, rolling)[0] - _peak(lab.rows, rolling)[0]).days
                    counts["early" if delta < 0 else "late" if delta > 0 else "same"] += 1
        out[side] = {
            "signed_bias_kg": str(bias),
            "day_peak_direction": dict(sorted(dates.items())),
            "rolling7_direction": dict(sorted(starts.items())),
            "absolute_error_by_lead": {str(k): str(v) for k, v in sorted(lead.items())},
        }
    return out


def _group(
    samples: tuple[Sample, ...], pairs: dict[str, Pair], labs: dict[str, Labels], as_of: datetime
) -> dict[str, Any]:
    reasons = {
        s.sample_id: _reason(s, pairs[s.sample_id], labs.get(s.sample_id), as_of) for s in samples
    }
    metrics: dict[str, Any] = {}
    count = len(samples)
    candidate_rows = sum(len(s.dates) for s in samples)
    candidate_bases = len({s.base_id for s in samples})
    for name in ERROR_METRICS:
        excluded = {key: reason for key, reason in reasons.items() if reason}
        for s in samples:
            if s.sample_id in excluded:
                continue
            reason = None
            if name == "SEASON_TOTAL_WAPE" and s.window != "FULL_SEASON":
                reason = "INCOMPLETE_CALENDAR"
            elif name.startswith("ROLLING_") and len(s.dates) < 7:
                reason = "NO_COMPLETE_7DAY_WINDOW"
            elif name.endswith(("DATE_MAE", "START_MAE")) and not any(
                r.kg > 0 for r in labs[s.sample_id].rows
            ):
                reason = "NO_POSITIVE_ACTUAL_PEAK"
            if reason:
                excluded[s.sample_id] = reason
        common = [s for s in samples if s.sample_id not in excluded]
        actual = sum((sum((r.kg for r in labs[s.sample_id].rows), D(0)) for s in common), D(0))
        if name.endswith("WAPE") and not actual:
            excluded.update({s.sample_id: "ZERO_DENOMINATOR" for s in common})
            common = []
        row_count = sum(len(s.dates) for s in common)
        denominator = (
            actual
            if name.endswith("WAPE")
            else D(row_count if name == "DAILY_MAE" else len(common))
        )
        model_values = {}
        for side in ("baseline", "candidate"):
            numerator = D(0)
            for s in common:
                forecast = getattr(pairs[s.sample_id], side)
                assert forecast is not None
                numerator += _errors(forecast, labs[s.sample_id])[name]
            model_values[side] = _fraction(numerator, denominator)
        members = [s.sample_id for s in common]
        metrics[name] = {
            **model_values,
            "candidate_count": count,
            "common_count": len(common),
            "common_member_ids": members,
            "common_members_sha256": digest(members),
            "not_computable_count": count - len(common),
            "sample_coverage": str(D(len(common)) / D(count)) if count else None,
            "base_coverage": _fraction(D(len({s.base_id for s in common})), D(candidate_bases)),
            "target_row_coverage": _fraction(D(row_count), D(candidate_rows)),
            "reasons": dict(sorted(Counter(excluded.values()).items())),
            "exclusions": excluded,
            "empty_reason": "EMPTY_COHORT" if not count else None,
            "baseline_available_count": sum(
                pairs[s.sample_id].baseline is not None for s in samples
            ),
            "candidate_available_count": sum(
                pairs[s.sample_id].candidate is not None for s in samples
            ),
        }
    daily_members = set(metrics["DAILY_MAE"]["common_member_ids"])
    base_values: dict[str, list[Decimal]] = {}
    for s in samples:
        if s.sample_id not in daily_members:
            continue
        p, lab = pairs[s.sample_id], labs[s.sample_id]
        assert p.baseline is not None and p.candidate is not None
        values = base_values.setdefault(s.base_id, [D(0), D(0), D(0)])
        values[0] += _errors(p.baseline, lab)["DAILY_MAE"]
        values[1] += _errors(p.candidate, lab)["DAILY_MAE"]
        values[2] += sum((r.kg for r in lab.rows), D(0))
    mass = sum((v[2] for v in base_values.values()), D(0))
    good_mass = sum((v[2] for v in base_values.values() if v[1] < v[0]), D(0))
    metrics["BASE_BREADTH"] = {
        "n_base": len(base_values),
        "improved": sum(v[1] < v[0] for v in base_values.values()),
        "tied": sum(v[1] == v[0] for v in base_values.values()),
        "worsened": sum(v[1] > v[0] for v in base_values.values()),
        "per_base_delta": {key: str(v[1] - v[0]) for key, v in sorted(base_values.items())},
        "improved_actual_kg_share": _fraction(good_mass, mass),
        "status": "PASS_SYNTHETIC" if base_values else "NOT_COMPUTABLE",
    }
    metrics["SAMPLE_COVERAGE"] = {name: metrics[name]["sample_coverage"] for name in ERROR_METRICS}
    metrics["NOT_COMPUTABLE_COUNT"] = {
        name: metrics[name]["not_computable_count"] for name in ERROR_METRICS
    }
    common_samples = [s for s in samples if s.sample_id in daily_members]
    robustness: dict[str, Any] = {}
    if samples and samples[0].window == "H15_LOCAL":
        # Rank once by H15 absolute-error reduction, tie by base ID, then remove
        # WHOLE bases. This is a diagnostic, never a changed main cohort.
        ranked = sorted(
            base_values, key=lambda key: (base_values[key][1] - base_values[key][0], key)
        )
        for n in (1, 2):
            removed = ranked[:n]
            retained = [s for s in common_samples if s.base_id not in removed]
            sensitivity_values = {}
            for side in ("baseline", "candidate"):
                error = D(0)
                for s in retained:
                    f = getattr(pairs[s.sample_id], side)
                    assert f is not None
                    error += _errors(f, labs[s.sample_id])["DAILY_MAE"]
                mass = sum((r.kg for s in retained for r in labs[s.sample_id].rows), D(0))
                sensitivity_values[side] = {
                    "daily_wape": _fraction(error, mass),
                    "daily_mae": _fraction(error, D(sum(len(s.dates) for s in retained))),
                }
            robustness[f"remove_top_{n}_bases"] = {
                "removed_base_ids": removed,
                "remaining_count": len(retained),
                "metrics": sensitivity_values,
            }
    return {
        "metrics": metrics,
        "diagnostics": _diagnostics(common_samples, pairs, labs),
        "h15_whole_base_sensitivity": robustness,
    }


def evaluate_synthetic(
    seal: PredictionSeal, labels: Iterable[Labels], *, as_of: datetime, synthetic_authorized: bool
) -> dict[str, Any]:
    """Phase B consumes only literal synthetic labels. Real scoring has no entry."""
    _permission(seal.samples, synthetic_authorized)
    expected = freeze_predictions(seal.samples, seal.pairs, synthetic_authorized=True)
    if expected.raw != seal.raw or expected.sha256 != seal.sha256:
        raise ValueError("PREDICTION_SEAL_MISMATCH")
    if not _aware(as_of):
        raise ValueError("SCORING_AS_OF_TIMEZONE_REQUIRED")
    label_list = tuple(labels)
    ids = [lab.sample_id for lab in label_list]
    if len(ids) != len(set(ids)) or not set(ids) <= {s.sample_id for s in seal.samples}:
        raise ValueError("LABEL_COHORT_EXPANSION_OR_DUPLICATE")
    labs = {lab.sample_id: lab for lab in label_list}
    pairs = {p.sample_id: p for p in seal.pairs}
    groups: dict[str, list[Sample]] = {}
    for s in seal.samples:
        groups.setdefault(f"{s.split}:{s.window}", []).append(s)
    with localcontext(Context(prec=50)):
        result = {
            "data_class": "SYNTHETIC",
            "prediction_seal_sha256": seal.sha256,
            "labels_sha256": digest(tuple(sorted(label_list, key=lambda lab: lab.sample_id))),
            "as_of": as_of.isoformat(),
            "groups": {
                key: _group(tuple(value), pairs, labs, as_of)
                for key, value in sorted(groups.items())
            },
            "empty_cohort": {"reason": "EMPTY_COHORT", "count": 0, "value": None}
            if not seal.samples
            else None,
            "conclusion_scope": "CONDITIONAL_ON_COMMON_COMPUTABLE_COHORT",
            "overall_winner": None,
            "strict_pit": False,
            "prospective_accuracy_validated": False,
            "real_scoring_executed": False,
        }
        return {**result, "result_sha256": digest(result)}
