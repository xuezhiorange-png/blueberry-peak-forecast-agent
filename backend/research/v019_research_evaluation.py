"""Independent, authorized retrospective label scoring; strict PIT untouched."""

from __future__ import annotations

import html
from collections import Counter
from datetime import date, timedelta
from decimal import Context, Decimal, localcontext
from pathlib import Path
from typing import Any

from backend.research import v019_owner_scope_adapter as scope
from backend.research import v019_real_phase_a_adapter as io
from backend.research import v019_research_authorization as auth
from backend.research import v019_research_execution as phase_a
from backend.research import v019_retrospective_scoring as old_scoring
from backend.research import v019_synthetic_validation as metrics
from backend.research.v019_daily_curve import DailyKg, canonical_bytes


def _accumulator() -> dict[str, Any]:
    return {
        "count": 0,
        "rows": 0,
        "bases": set(),
        "metrics": {
            n: {
                "ids": [],
                "reasons": {},
                "baseline": Decimal(0),
                "candidate": Decimal(0),
                "actual": Decimal(0),
                "rows": 0,
                "bases": set(),
            }
            for n in metrics.ERROR_METRICS
        },
        "base_errors": {},
    }


def _add(
    acc: dict[str, Any],
    member: dict[str, Any],
    reason: str | None,
    actual: Decimal,
    errors: dict[str, dict[str, Decimal]],
    positive: bool,
) -> None:
    acc["count"] += 1
    bid, sid = member["base_id"], member["candidate_id"]
    n = 7 if member["window"] == "H7_PREFIX" else 15
    acc["rows"] += n
    acc["bases"].add(bid)
    for name, m in acc["metrics"].items():
        why = reason
        if why is None and name == "SEASON_TOTAL_WAPE":
            why = "INCOMPLETE_CALENDAR"
        if why is None and name.endswith(("DATE_MAE", "START_MAE")) and not positive:
            why = "NO_POSITIVE_ACTUAL_PEAK"
        if why:
            m["reasons"][sid] = why
            continue
        m["ids"].append(sid)
        m["actual"] += actual
        m["rows"] += n
        m["bases"].add(bid)
        for side in ("baseline", "candidate"):
            m[side] += errors[side][name]
    if reason is None:
        b = acc["base_errors"].setdefault(bid, [Decimal(0), Decimal(0), Decimal(0)])
        b[0] += errors["baseline"]["DAILY_MAE"]
        b[1] += errors["candidate"]["DAILY_MAE"]
        b[2] += actual


def _finish(acc: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, m in acc["metrics"].items():
        ids = m["ids"]
        reasons = dict(m["reasons"])
        if name.endswith("WAPE") and not m["actual"]:
            reasons.update({sid: "ZERO_DENOMINATOR" for sid in ids})
            ids = []
        denominator = (
            m["actual"]
            if name.endswith("WAPE")
            else Decimal(m["rows"] if name == "DAILY_MAE" else len(ids))
        )
        result[name] = {
            side: metrics._fraction(m[side] if ids else Decimal(0), denominator)
            for side in ("baseline", "candidate")
        }
        result[name].update(
            {
                "common_count": len(ids),
                "candidate_count": acc["count"],
                "common_members_sha256": metrics.digest(sorted(ids)),
                "common_member_ids": sorted(ids),
                "exclusions": reasons,
                "reasons": dict(Counter(reasons.values())),
                "not_computable_count": acc["count"] - len(ids),
                "sample_coverage": str(Decimal(len(ids)) / Decimal(acc["count"]))
                if acc["count"]
                else None,
                "base_coverage": metrics._fraction(
                    Decimal(len(m["bases"]) if ids else 0), Decimal(len(acc["bases"]))
                ),
                "target_row_coverage": metrics._fraction(
                    Decimal(m["rows"] if ids else 0), Decimal(acc["rows"])
                ),
            }
        )
    be = acc["base_errors"]
    total = sum((v[2] for v in be.values()), Decimal(0))
    result["BASE_BREADTH"] = {
        "n_base": len(be),
        "improved": sum(v[1] < v[0] for v in be.values()),
        "tied": sum(v[1] == v[0] for v in be.values()),
        "worsened": sum(v[1] > v[0] for v in be.values()),
        "per_base_delta": {b: str(v[1] - v[0]) for b, v in sorted(be.items())},
        "improved_actual_kg_share": metrics._fraction(
            sum((v[2] for v in be.values() if v[1] < v[0]), Decimal(0)), total
        ),
        "status": "COMPUTED" if be else "NOT_COMPUTABLE",
    }
    result["SAMPLE_COVERAGE"] = {n: result[n]["sample_coverage"] for n in metrics.ERROR_METRICS}
    result["NOT_COMPUTABLE_COUNT"] = {
        n: result[n]["not_computable_count"] for n in metrics.ERROR_METRICS
    }
    return {
        "metrics": result,
        "candidate_minus_baseline": {
            n: str(
                Decimal(result[n]["candidate"]["value"]) - Decimal(result[n]["baseline"]["value"])
            )
            if result[n]["baseline"]["value"] is not None
            else None
            for n in metrics.ERROR_METRICS
        },
    }


def _label_rows(
    value: dict[str, Any], content: dict[str, Any], ctx: auth.Context, *, clock: str
) -> tuple[dict[tuple[str, str], DailyKg], dict[tuple[str, str], str]]:
    if (
        set(value) != {"data_class", "source_hash", "physical_basis", "unit", "mature_at", "rows"}
        or value["data_class"] != ctx.mode
        or value["source_hash"] != scope.SOURCE_SHA256
        or value["physical_basis"] != "RECORDED_MARKETABLE_NET_WEIGHT"
        or value["unit"] != "kg"
    ):
        raise ValueError("LABEL_SOURCE_SCHEMA_OR_PHYSICAL_BASIS")
    authority = {(d["base_id"], d["date"]): d for d in content["day_authorities"]}
    mature = auth.aware(value["mature_at"]) <= auth.aware(clock)
    rows: dict[tuple[str, str], DailyKg] = {}
    invalid: dict[tuple[str, str], str] = {}
    for r in value["rows"]:
        if set(r) != {"base_id", "date", "kg", "day_authority_sha256"}:
            raise ValueError("LABEL_ROW_SCHEMA")
        key = r["base_id"], r["date"]
        if key not in authority:
            raise ValueError("LABEL_OUTSIDE_APPROVED_SOURCE_CALENDAR")
        issues = []
        priority = [
            "UNVERIFIED_AUTHORITY",
            "IDENTITY_OR_SOURCE_HASH_MISMATCH",
            "INVALID_VALUE_OR_DUPLICATE_DATE",
        ]
        if key in rows or key in invalid:
            issues.append("INVALID_VALUE_OR_DUPLICATE_DATE")
        if key in invalid:
            issues.append(invalid[key])
        if r["day_authority_sha256"] != metrics.digest(authority[key]) or not mature:
            issues.append("UNVERIFIED_AUTHORITY")
        try:
            if type(r["kg"]) is not str:
                raise ValueError("DECIMAL_STRING_REQUIRED")
            kg = Decimal(r["kg"])
            if not kg.is_finite() or kg < 0:
                raise ValueError("INVALID_KG")
            numerator, denominator = kg.as_integer_ratio()
            if numerator * 1_000_000 % denominator:
                raise ValueError("KG_NOT_EXACT_MICRO")
            if authority[key]["new_quantity_status"] == "CONFIRMED_ZERO" and kg != 0:
                issues.append("IDENTITY_OR_SOURCE_HASH_MISMATCH")
        except (ValueError, ArithmeticError):
            issues.append("INVALID_VALUE_OR_DUPLICATE_DATE")
            kg = Decimal(0)
        if issues:
            invalid[key] = min(issues, key=priority.index)
            rows.pop(key, None)
        elif key not in invalid:
            rows[key] = DailyKg(date.fromisoformat(r["date"]), kg)
    return rows, invalid


def run_b(
    seal_path: Path,
    seal_sha256: str,
    label_path: Path,
    label_sha256: str,
    ctx: auth.Context,
    grants: object,
) -> dict[str, Any]:
    auth.require(
        ctx,
        grants,
        "B_SCORING",
        metrics.digest({"a_sha256": seal_sha256, "label_sha256": label_sha256}),
    )
    auth.require(ctx, grants, "A_SEAL_REVIEW", seal_sha256)
    auth.require(
        ctx,
        grants,
        "B_LABEL_READ",
        metrics.digest(
            {"a_sha256": seal_sha256, "path": str(label_path), "label_sha256": label_sha256}
        ),
    )
    seal = auth.read_json(seal_path)
    if seal["sha256"] != seal_sha256:
        raise ValueError("APPROVED_A_SEAL_REQUIRED")
    content = phase_a.verify_a(seal, ctx)  # must complete BEFORE label I/O
    raw = io._read_pinned(label_path, label_sha256, "labels.json")
    clock = auth.now()
    labels = io._object(raw)
    rows, invalid = _label_rows(labels, content, ctx, clock=clock)
    c0 = auth.unseal(content["formal_c0"])
    members = auth.unseal(c0["review"])["members"]
    predictions = {r["candidate_id"]: r for r in content["members"]}
    full = {
        b: {side: {r.day: r for r in phase_a.curve_rows(rr)} for side, rr in c.items()}
        for b, c in content["full_curves"].items()
    }
    groups = {w: _accumulator() for w in ("H7_PREFIX", "H15_LOCAL")}
    perbase = {
        b["base_id"]: {w: _accumulator() for w in groups} for b in content["registry"]["bases"]
    }
    failures, numerical = [], []
    with localcontext(Context(prec=50)):
        for m in members:
            sid, bid, window = m["candidate_id"], m["base_id"], m["window"]
            if m["admission_status"] != "ADMIT":
                failures.append(
                    {
                        "candidate_id": sid,
                        "reason": "C0_NOT_ADMITTED",
                        "detail": m["failure_reason"],
                    }
                )
                continue
            reason = (
                "IDENTITY_OR_SOURCE_HASH_MISMATCH" if predictions[sid]["failure_reason"] else None
            )
            start, end = (date.fromisoformat(m[k]) for k in ("target_start", "target_end"))
            dates = [start + timedelta(days=i) for i in range((end - start).days + 1)]
            errors: dict[str, dict[str, Decimal]] = {}
            bad = [invalid[(bid, str(d))] for d in dates if (bid, str(d)) in invalid]
            if bad:
                priorities = [
                    "UNVERIFIED_AUTHORITY",
                    "IDENTITY_OR_SOURCE_HASH_MISMATCH",
                    "INVALID_VALUE_OR_DUPLICATE_DATE",
                ]
                reason = min(bad, key=priorities.index)
            if reason is None and any((bid, str(d)) not in rows for d in dates):
                reason = "INCOMPLETE_CALENDAR"
            actual = Decimal(0)
            view: dict[str, Any] = {
                "candidate_id": sid,
                "base_id": bid,
                "window": window,
                "baseline": predictions[sid].get("baseline"),
                "candidate": predictions[sid].get("candidate"),
                "origin": m["origin"],
                "cutoff": m["cutoff"],
                "target_start": m["target_start"],
                "target_end": m["target_end"],
            }
            if reason is None:
                rr = tuple(rows[bid, str(d)] for d in dates)
                actual = sum((r.kg for r in rr), Decimal(0))
                lab = metrics.Labels(
                    sid, sid, label_sha256, rr, auth.aware(clock), auth.aware(clock), True
                )
                for side in ("baseline", "candidate"):
                    f = metrics.Forecast(
                        side, sid, sid, sid, tuple(full[bid][side][d] for d in dates)
                    )
                    errors[side] = metrics._errors(f, lab)
                av = old_scoring._view(rr, actual=True)
                view.update(
                    actual_peak=av["single_day_peak"],
                    actual_rolling7=av["rolling7_peak"],
                    error_numerators=metrics._json(
                        {
                            side: {
                                n: value for n, value in values.items() if n != "SEASON_TOTAL_WAPE"
                            }
                            for side, values in errors.items()
                        }
                    ),
                    error_denominators={
                        n: (
                            str(actual)
                            if n == "DAILY_WAPE"
                            else str(len(rr))
                            if n == "DAILY_MAE"
                            else "0"
                            if n == "SEASON_TOTAL_WAPE"
                            or (n.endswith(("DATE_MAE", "START_MAE")) and not actual)
                            else "1"
                        )
                        for n in metrics.ERROR_METRICS
                    },
                    season_total_wape_status="NOT_COMPUTABLE_FULL_SEASON_NOT_ADMITTED",
                )
            else:
                failures.append({"candidate_id": sid, "reason": reason})
            view["not_computable_reason"] = reason
            numerical.append(view)
            for acc in (groups[window], perbase[bid][window]):
                _add(acc, m, reason, actual, errors, actual > 0)
        result = {
            "groups": {w: _finish(a) for w, a in groups.items()},
            "per_base": {b: {w: _finish(a) for w, a in v.items()} for b, v in perbase.items()},
        }
    body = {
        "data_class": ctx.mode,
        "experiment_type": "RETROSPECTIVE_REPLAY",
        "scope": auth.restrictions(),
        "scope_version": scope.SCOPE_VERSION,
        "report_scope": "CONDITIONAL_ON_COMMON_COMPUTABLE_COHORT_NOT_PRODUCTION_ACCURACY",
        "a_seal_sha256": seal_sha256,
        "prediction_content_sha256": seal["payload"]["prediction_sha256"],
        "label_sha256": label_sha256,
        "code_sha256": auth.code_identity(),
        "registered_count": len(members),
        "admitted_count": sum(m["admission_status"] == "ADMIT" for m in members),
        "synthetic_simulation": ctx.mode == "SYNTHETIC",
        "real_scoring_performed": ctx.mode == "REAL",
        "base_count": len(perbase),
        "executed_at": seal["payload"]["executed_at"],
        "scored_at": clock,
        "historical_issued_at": None,
        "members": numerical,
        "failures": failures,
        "phase_a_failures": content["failures"],
        "daily_predictions": content["full_curves"],
        "actual_daily": [
            {"base_id": bid, "date": day, "kg": str(r.kg)} for (bid, day), r in sorted(rows.items())
        ],
        "admission_inventory": [
            {
                "candidate_id": m["candidate_id"],
                "status": m["admission_status"],
                "reason": m["failure_reason"],
            }
            for m in members
        ],
        **result,
        "overall_winner": None,
    }
    # Current permissions are checked again, after calculations and before release.
    auth.require(
        ctx,
        grants,
        "B_SCORING",
        metrics.digest({"a_sha256": seal_sha256, "label_sha256": label_sha256}),
    )
    auth.require(ctx, grants, "A_SEAL_REVIEW", seal_sha256)
    auth.require(
        ctx,
        grants,
        "B_LABEL_READ",
        metrics.digest(
            {"a_sha256": seal_sha256, "path": str(label_path), "label_sha256": label_sha256}
        ),
    )
    return {**body, "report_sha256": metrics.digest(body)}


def render(report: dict[str, Any]) -> dict[str, bytes]:
    lines = [
        "# Retrospective research report — " + report["data_class"],
        "",
        report["report_scope"],
        "",
        "STRICT_PIT=false; historical_issued_at=null; no training/promotion.",
        "Physical equivalence and historical area known_at NOT_PROVEN.",
        "",
        f"Registered={report['registered_count']}; admitted={report['admitted_count']}; "
        f"Bases={report['base_count']}",
        "",
    ]
    for window, group in report["groups"].items():
        lines += [
            "## " + window,
            "",
            "| Metric | Baseline | Candidate | Common / C0 |",
            "| --- | --- | --- | --- |",
        ]
        for name, m in group["metrics"].items():
            if name in metrics.ERROR_METRICS:
                lines.append(
                    f"| {name} | {m['baseline']['numerator']} / {m['baseline']['denominator']} "
                    f"= {m['baseline']['value']} | {m['candidate']['numerator']} / "
                    f"{m['candidate']['denominator']} = {m['candidate']['value']} | "
                    f"{m['common_count']} / {m['candidate_count']} |"
                )
            else:
                lines.append(f"| {name} | {old_scoring.json_value(m)} | — | — |")
    for bid, detail in report["per_base"].items():
        lines += [
            "",
            "## " + bid,
            "",
            "| Window | Metric | Baseline | Candidate | Delta |",
            "| --- | --- | --- | --- | --- |",
        ]
        for window, group in detail.items():
            for name in metrics.ERROR_METRICS:
                m = group["metrics"][name]
                lines.append(
                    f"| {window} | {name} | {m['baseline']['value']} | {m['candidate']['value']} | "
                    f"{group['candidate_minus_baseline'][name]} |"
                )
        lines += [
            "",
            "| Date | Baseline kg | Candidate kg | Actual kg |",
            "| --- | --- | --- | --- |",
        ]
        actual = {r["date"]: r["kg"] for r in report["actual_daily"] if r["base_id"] == bid}
        c = report["daily_predictions"].get(bid)
        if c:
            for a, b in zip(c["baseline"], c["candidate"], strict=True):
                lines.append(
                    f"| {a['date']} | {a['kg']} | {b['kg']} | "
                    f"{actual.get(a['date'], 'UNKNOWN_NOT_LABELLED')} |"
                )
    lines += [
        "",
        "## Complete member peak/error/failure inventory",
        "",
        "| ID | Base | Window | Result |",
        "| --- | --- | --- | --- |",
    ]
    for r in report["members"]:
        lines.append(
            f"| {r['candidate_id']} | {r['base_id']} | {r['window']} | "
            f"{old_scoring.json_value(r)} |"
        )
    lines += ["", "## Retained failures / non-admitted members", ""]
    lines += [old_scoring.json_value(r) for r in report["failures"]]
    md = "\n".join(lines).rstrip() + "\n"
    # Semantic tables and collapsed per-base/inventory sections keep the full
    # 39-base report navigable without external resources or client arithmetic.
    parts, table, details = [], False, False
    for line in lines:
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(not c.replace("-", "").replace(":", "").strip() for c in cells):
                continue
            if not table:
                parts.append('<div class="table"><table>')
            tag = "td" if table else "th"
            parts.append(
                "<tr>" + "".join(f"<{tag}>{html.escape(c)}</{tag}>" for c in cells) + "</tr>"
            )
            table = True
            continue
        if table:
            parts.append("</table></div>")
            table = False
        if line.startswith("## "):
            if details:
                parts.append("</details>")
            title = line[3:]
            opened = " open" if title in {"H7_PREFIX", "H15_LOCAL"} else ""
            parts.append(f"<details{opened}><summary>{html.escape(title)}</summary>")
            details = True
        elif line.startswith("# "):
            parts.append("<h1>" + html.escape(line[2:]) + "</h1>")
        elif line:
            parts.append("<p>" + html.escape(line) + "</p>")
    if table:
        parts.append("</table></div>")
    if details:
        parts.append("</details>")
    page = (
        '<!doctype html><html lang="en"><meta charset="utf-8"><title>Research report</title>'
        "<style>body{font:14px/1.5 system-ui;margin:20px;max-width:1300px}"
        ".table{overflow:auto}table{border-collapse:collapse}td,th{border:1px solid #bbb;"
        "padding:6px;text-align:left}p{overflow-wrap:anywhere}summary{font-size:18px;"
        "padding:12px;cursor:pointer}details{margin:12px 0}</style>"
        + "\n".join(parts)
        + "</html>\n"
    )
    return {
        "report.json": canonical_bytes(report),
        "report.md": md.encode(),
        "report.html": page.encode(),
    }
