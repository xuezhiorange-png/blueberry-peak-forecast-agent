"""Independent numerical Phase B for CLOSED synthetic retrospective artifacts.

The strict as-issued evaluator is unchanged. This policy permits late simulated
computation, NEVER backdates it, and delegates errors/peaks/fractions to its
existing arithmetic. No real input, label-file or Owner-permit switch exists.
"""

from __future__ import annotations

import html
from collections import Counter
from datetime import datetime, timedelta
from decimal import Context, Decimal, localcontext
from typing import Any

from backend.research import v019_retrospective_engine as engine
from backend.research import v019_synthetic_validation as math
from backend.research.v019_daily_curve import DailyKg


def _labels(seal: engine.PhaseASeal) -> tuple[math.Labels, ...]:
    # Only reached after B permit and complete Phase A reconstruction succeed.
    from backend.research.v019_retrospective_labels import fixture_payload

    raw = fixture_payload()
    if math.digest(raw) != engine.LABEL_PAYLOAD_SHA256:
        raise ValueError("SYNTHETIC_LABEL_FIXTURE_IDENTITY_MISMATCH")
    fixture = seal.c0.candidates.experiment.fixture
    labels = []
    for s in seal.predictions.samples:
        if fixture == "MISSING_LABEL" and s.base_id.endswith("D"):
            continue
        rows = tuple(
            DailyKg(
                d,
                Decimal(
                    "0" if fixture == "ZERO_ACTUAL" else raw[s.base_id][(d - engine.START).days]
                ),
            )
            for d in s.dates
        )
        if fixture == "INVALID_LABEL" and s.base_id.endswith("D"):
            rows = rows[:-1] + (rows[0],)
        labels.append(
            math.Labels(
                s.sample_id,
                s.identity_sha256,
                s.label_authority_sha256,
                rows,
                datetime.fromisoformat("2001-07-01T00:00:00Z"),
                datetime.fromisoformat("2001-08-01T00:00:00Z"),
                True,
            )
        )
    return tuple(labels)


def _reason(
    s: math.Sample, pair: math.Pair, lab: math.Labels | None, as_of: datetime
) -> str | None:
    """Separate retrospective policy, not a modification/flag on strict._reason."""
    if (
        lab is None
        or not lab.mature
        or not math._aware(as_of)
        or any(
            not math._aware(t)
            for t in (s.origin, s.issued_at, s.cutoff, lab.available_at, lab.mature_at)
        )
        or lab.available_at > as_of
        or lab.mature_at > as_of
        or s.issued_at > as_of
        or s.input_available_at > s.cutoff
        or s.input_ingested_at > s.cutoff
        or s.cutoff > s.issued_at
        or len(s.authorities) != len(math.AUTHORITIES)
        or any(a.status != "AVAILABLE" for a in s.authorities)
    ):
        return "UNVERIFIED_AUTHORITY"
    if s.physical_basis != "ACTUAL_HARVEST_KG" or s.unit != "kg" or s.area_mu <= 0:
        return "PHYSICAL_BASIS_MISMATCH"
    if (
        pair.baseline is None
        or pair.candidate is None
        or lab.sample_identity_sha256 != s.identity_sha256
        or lab.authority_sha256 != s.label_authority_sha256
        or any(
            f.sample_identity_sha256 != s.identity_sha256 for f in (pair.baseline, pair.candidate)
        )
    ):
        return "IDENTITY_OR_SOURCE_HASH_MISMATCH"
    reasons = [math._calendar_reason(f.rows, s.dates) for f in (pair.baseline, pair.candidate, lab)]
    if "INVALID_VALUE_OR_DUPLICATE_DATE" in reasons:
        return "INVALID_VALUE_OR_DUPLICATE_DATE"
    return "INCOMPLETE_CALENDAR" if any(reasons) else None


def _aggregate(
    samples: tuple[math.Sample, ...],
    pairs: dict[str, math.Pair],
    labs: dict[str, math.Labels],
    as_of: datetime,
) -> dict[str, Any]:
    """S1 aggregation/denominators; reuse the original numerical primitives."""
    initial = {
        s.sample_id: _reason(s, pairs[s.sample_id], labs.get(s.sample_id), as_of) for s in samples
    }
    metrics: dict[str, Any] = {}
    count = len(samples)
    nrows = sum(len(s.dates) for s in samples)
    nbases = len({s.base_id for s in samples})
    for name in math.ERROR_METRICS:
        excluded = {k: r for k, r in initial.items() if r}
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
        actual = sum((r.kg for s in common for r in labs[s.sample_id].rows), Decimal(0))
        if name.endswith("WAPE") and not actual:
            excluded.update({s.sample_id: "ZERO_DENOMINATOR" for s in common})
            common = []
        rows = sum(len(s.dates) for s in common)
        denominator = (
            actual
            if name.endswith("WAPE")
            else Decimal(rows if name == "DAILY_MAE" else len(common))
        )
        values = {}
        for side in ("baseline", "candidate"):
            numerator = Decimal(0)
            for s in common:
                forecast = getattr(pairs[s.sample_id], side)
                assert forecast is not None
                numerator += math._errors(forecast, labs[s.sample_id])[name]
            values[side] = math._fraction(numerator, denominator)
        members = [s.sample_id for s in common]
        metrics[name] = {
            **values,
            "candidate_count": count,
            "common_count": len(common),
            "common_member_ids": members,
            "common_members_sha256": math.digest(members),
            "not_computable_count": count - len(common),
            "sample_coverage": str(Decimal(len(common)) / Decimal(count)) if count else None,
            "base_coverage": math._fraction(
                Decimal(len({s.base_id for s in common})), Decimal(nbases)
            ),
            "target_row_coverage": math._fraction(Decimal(rows), Decimal(nrows)),
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
    valid = [s for s in samples if s.sample_id in metrics["DAILY_MAE"]["common_member_ids"]]
    base: dict[str, list[Decimal]] = {}
    for s in valid:
        pair, lab = pairs[s.sample_id], labs[s.sample_id]
        assert pair.baseline is not None and pair.candidate is not None
        value = base.setdefault(s.base_id, [Decimal(0), Decimal(0), Decimal(0)])
        value[0] += math._errors(pair.baseline, lab)["DAILY_MAE"]
        value[1] += math._errors(pair.candidate, lab)["DAILY_MAE"]
        value[2] += sum((r.kg for r in lab.rows), Decimal(0))
    total = sum((v[2] for v in base.values()), Decimal(0))
    improved = sum((v[2] for v in base.values() if v[1] < v[0]), Decimal(0))
    metrics["BASE_BREADTH"] = {
        "n_base": len(base),
        "improved": sum(v[1] < v[0] for v in base.values()),
        "tied": sum(v[1] == v[0] for v in base.values()),
        "worsened": sum(v[1] > v[0] for v in base.values()),
        "per_base_delta": {k: str(v[1] - v[0]) for k, v in sorted(base.items())},
        "improved_actual_kg_share": math._fraction(improved, total),
        "status": "PASS_SYNTHETIC" if base else "NOT_COMPUTABLE",
    }
    metrics["SAMPLE_COVERAGE"] = {k: metrics[k]["sample_coverage"] for k in math.ERROR_METRICS}
    metrics["NOT_COMPUTABLE_COUNT"] = {
        k: metrics[k]["not_computable_count"] for k in math.ERROR_METRICS
    }
    sensitivity = {}
    if samples and samples[0].window == "H15_LOCAL":
        ranked = sorted(base, key=lambda k: (base[k][1] - base[k][0], k))
        for n in (1, 2):
            removed = ranked[:n]
            retained = [s for s in valid if s.base_id not in removed]
            stats = {}
            for side in ("baseline", "candidate"):
                error = sum(
                    (
                        math._errors(getattr(pairs[s.sample_id], side), labs[s.sample_id])[
                            "DAILY_MAE"
                        ]
                        for s in retained
                    ),
                    Decimal(0),
                )
                mass = sum((r.kg for s in retained for r in labs[s.sample_id].rows), Decimal(0))
                stats[side] = {
                    "daily_wape": math._fraction(error, mass),
                    "daily_mae": math._fraction(
                        error, Decimal(sum(len(s.dates) for s in retained))
                    ),
                }
            sensitivity[f"remove_top_{n}_bases"] = {
                "removed_base_ids": removed,
                "remaining_count": len(retained),
                "metrics": stats,
            }
    deltas = {
        name: str(
            Decimal(metrics[name]["candidate"]["value"])
            - Decimal(metrics[name]["baseline"]["value"])
        )
        if metrics[name]["candidate"]["value"] is not None
        and metrics[name]["baseline"]["value"] is not None
        else None
        for name in math.ERROR_METRICS
    }
    return {
        "metrics": metrics,
        "candidate_minus_baseline": deltas,
        "diagnostics": math._diagnostics(valid, pairs, labs),
        "h15_whole_base_sensitivity": sensitivity,
    }


def _view(rows: tuple[DailyKg, ...], *, actual: bool = False) -> dict[str, Any]:
    day, quantity = math._peak(rows, False)
    positive = any(r.kg > 0 for r in rows)
    start, mass = math._peak(rows, True)
    return {
        "daily": [{"date": str(r.day), "kg": str(r.kg)} for r in rows],
        "single_day_peak": {
            "date": str(day) if positive or not actual else None,
            "quantity_kg": str(quantity),
        },
        "rolling7_peak": {
            "start_date": str(start) if positive or not actual else None,
            "end_date": str(start + timedelta(days=6)) if positive or not actual else None,
            "quantity_kg": str(mass),
        },
    }


def score(seal: engine.PhaseASeal, *, permit: object = None) -> dict[str, Any]:
    engine._permit(permit, "B", seal.sha256)
    engine.verify(seal)  # Reconstruct from registered inputs BEFORE labels.
    labels = _labels(seal)
    samples = seal.predictions.samples
    labs = {x.sample_id: x for x in labels}
    if len(labs) != len(labels) or not set(labs) <= {s.sample_id for s in samples}:
        raise ValueError("LABEL_COHORT_EXPANSION_OR_DUPLICATE")
    pairs = {p.sample_id: p for p in seal.predictions.pairs}
    grouped: dict[str, list[math.Sample]] = {}
    for s in samples:
        grouped.setdefault(f"{s.split}:{s.window}", []).append(s)
    as_of = datetime.fromisoformat(seal.c0.candidates.experiment.score_at)
    with localcontext(Context(prec=50)):
        groups = {k: _aggregate(tuple(v), pairs, labs, as_of) for k, v in sorted(grouped.items())}
        per_base = {
            k: {
                bid: _aggregate(tuple(s for s in v if s.base_id == bid), pairs, labs, as_of)
                for bid in sorted({s.base_id for s in v})
            }
            for k, v in sorted(grouped.items())
        }
        views = {}
        for s in samples:
            pair = pairs[s.sample_id]
            reason = _reason(s, pair, labs.get(s.sample_id), as_of)
            views[s.sample_id] = {
                "base_id": s.base_id,
                "window": s.window,
                "origin": s.origin.isoformat(),
                "cutoff": s.cutoff.isoformat(),
                "computed_at": s.issued_at.isoformat(),
                "historical_issued_at": None,
                "failure": pair.failure,
                "not_computable_reason": reason,
                "baseline": _view(pair.baseline.rows) if pair.baseline else None,
                "candidate": _view(pair.candidate.rows) if pair.candidate else None,
                "actual": _view(labs[s.sample_id].rows, actual=True) if reason is None else None,
            }
    from backend.research.v019_owner_scope_adapter import boundary

    boundaries = boundary()
    checks = {
        "c0_verified_before_labels": True,  # engine.verify above must complete or raise.
        "all_registered_members_retained": len(pairs) == len(samples)
        and set(pairs) == {s.sample_id for s in samples},
        "all_ten_metrics_computed_or_explained": all(
            set(g["metrics"]) == set(math.METRICS) for g in groups.values()
        ),
        "real_c0_not_admitted": boundaries["formally_admitted_c0_count"] == 0,
        "late_computation_preserved": all(
            s.issued_at.isoformat() == seal.c0.candidates.experiment.computed_at for s in samples
        ),
    }
    body = {
        "engine_id": "V019_RETROSPECTIVE_ENGINE_R1",
        "data_class": "SYNTHETIC",
        "full_synthetic_end_to_end": "PASS" if all(checks.values()) else "FAIL",
        "stage_checks": checks,
        "prediction_kind": "RETROSPECTIVE_REPLAY",
        "strict_pit": False,
        "clock_provenance": "EXPLICIT_SIMULATED_CLOCK_NOT_HISTORICAL_ISSUANCE",
        "registered_count": len(samples),
        "synthetic_admitted_count": len(seal.c0.candidates.samples),
        "computed_pair_count": sum(
            p.baseline is not None and p.candidate is not None for p in pairs.values()
        ),
        "generation_failure_count": len(seal.failures),
        "synthetic_c0_sha256": seal.c0.sha256,
        "phase_a_sha256": seal.sha256,
        "labels_sha256": math.digest(labels),
        "source_code_sha256": engine._source_identity(),
        "groups": groups,
        "per_base": per_base,
        "curves_and_peaks": views,
        "failures": list(seal.failures),
        "inputs": {
            "profile": engine._profile(),
            "bases": math._json(engine._bases()),
            "full_support": [str(engine.START), str(engine.END)],
        },
        "real_boundaries": {
            **boundaries,
            "formally_admitted_c0_count": 0,
            "real_prediction_authorized": False,
            "real_scoring_authorized": False,
            "real_prediction_generated": False,
            "real_scoring_performed": False,
            "s3_formal_complete": False,
        },
        "report_scope": "SYNTHETIC_NUMERICAL_REHEARSAL_NOT_REAL_ACCURACY_OR_MODEL_PROMOTION",
        "full_season_control": "SEPARATE_21_DAY_FICTIONAL_CALENDAR_NOT_REAL_SEASON_ADMISSION",
        "overall_winner": None,
    }
    return {**body, "report_sha256": math.digest(body)}


def render(report: dict[str, Any]) -> dict[str, bytes]:
    """No recalculation in presentation: display sealed backend numbers only."""
    lines = [
        "# SYNTHETIC retrospective numerical report",
        "",
        report["report_scope"],
        "",
        f"Report SHA256: `{report['report_sha256']}`",
        "",
        "Late computation is preserved; strict PIT=false. Real C0=0; real execution BLOCKED.",
        "",
    ]
    for key, group in report["groups"].items():
        lines += [
            f"## {key}",
            "",
            "| Metric | baseline | candidate | common / candidate |",
            "| --- | --- | --- | --- |",
        ]
        for name, m in group["metrics"].items():
            if name in math.ERROR_METRICS:
                lines.append(
                    f"| {name} | {m['baseline']['value']} | {m['candidate']['value']} | "
                    f"{m['common_count']} / {m['candidate_count']} |"
                )
            else:
                lines.append(f"| {name} | {json_value(m)} | — | — |")
        lines += ["", "### Per Base paired absolute-error delta (candidate - baseline)", ""]
        for bid, delta in group["metrics"]["BASE_BREADTH"]["per_base_delta"].items():
            lines.append(f"- {bid}: {delta} kg")
        lines += [
            "",
            "### Per Base numerical comparison (negative delta = lower error)",
            "",
            "| Base | Metric | baseline | candidate | delta |",
            "| --- | --- | --- | --- | --- |",
        ]
        for bid, detail in report["per_base"][key].items():
            for name in math.ERROR_METRICS:
                m = detail["metrics"][name]
                lines.append(
                    f"| {bid} | {name} | {m['baseline']['value']} | "
                    f"{m['candidate']['value']} | {detail['candidate_minus_baseline'][name]} |"
                )
        lines.append("")
    for sid, view in report["curves_and_peaks"].items():
        lines += [
            f"## {sid}",
            "",
            f"origin={view['origin']}; computed_at={view['computed_at']}; "
            "historical_issued_at=None",
            "",
        ]
        if view["failure"] or view["not_computable_reason"]:
            lines += [f"Failure/reason: {view['failure']} / {view['not_computable_reason']}", ""]
        if view["baseline"] and view["candidate"] and view["actual"]:
            for kind in ("baseline", "candidate", "actual"):
                lines.append(
                    f"{kind} peak: {json_value(view[kind]['single_day_peak'])}; "
                    f"rolling7: {json_value(view[kind]['rolling7_peak'])}"
                )
            lines += [
                "",
                "| Date | baseline kg | candidate kg | actual kg |",
                "| --- | --- | --- | --- |",
            ]
            for a, b, c in zip(
                view["baseline"]["daily"],
                view["candidate"]["daily"],
                view["actual"]["daily"],
                strict=True,
            ):
                lines.append(f"| {a['date']} | {a['kg']} | {b['kg']} | {c['kg']} |")
            lines.append("")
    md = "\n".join(lines).rstrip() + "\n"
    # Semantic standalone tables; escaped text only, no scripts/network resources.
    sections = []
    table_open = False
    for line in lines:
        if line.startswith("|"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if all(cell.replace("-", "").replace(":", "").strip() == "" for cell in cells):
                continue
            if not table_open:
                sections.append('<div class="table"><table>')
            tag = "td" if table_open else "th"
            sections.append(
                "<tr>" + "".join(f"<{tag}>{html.escape(c)}</{tag}>" for c in cells) + "</tr>"
            )
            table_open = True
            continue
        if table_open:
            sections.append("</table></div>")
            table_open = False
        level = len(line) - len(line.lstrip("#"))
        if 1 <= level <= 6 and line[level : level + 1] == " ":
            sections.append(f"<h{level}>{html.escape(line[level + 1 :])}</h{level}>")
        elif line:
            sections.append(f"<p>{html.escape(line)}</p>")
    if table_open:
        sections.append("</table></div>")
    page = (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        "<title>SYNTHETIC research report</title><style>"
        "body{max-width:1100px;margin:2rem auto;padding:1rem;font:15px/1.5 system-ui}"
        "p{overflow-wrap:anywhere}.table{overflow:auto}table{border-collapse:collapse;width:100%}"
        "td,th{border:1px solid #bbb;padding:.4rem;text-align:left}th{background:#eee}</style>"
        + "\n".join(sections)
        + "</html>\n"
    )
    return {"report.md": md.encode(), "report.html": page.encode()}


def json_value(value: object) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, sort_keys=True)
