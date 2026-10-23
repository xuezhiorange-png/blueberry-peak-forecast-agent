"""Deterministic private S5 reports and source-hashed SVG scientific figures."""

from __future__ import annotations

import html
import json
from datetime import date, timedelta
from decimal import Context, Decimal, localcontext
from typing import Any

from backend.research import v019_accuracy_study as study
from backend.research import v019_real_training_cli as s4
from backend.research import v019_stability as stable
from backend.research import v019_stability_diagnostics as diag
from backend.research.v019_daily_curve import canonical_bytes
from backend.research.v019_synthetic_validation import ERROR_METRICS, digest

D = Decimal
SHORT = {
    "baseline": "Baseline",
    "S2": "S2",
    "VOLUME_CALIBRATION_V1": "Volume",
    "VOLUME_TIMING_V1": "Volume+Timing",
    stable.METHOD: "Consensus",
}
COLORS = {
    m: c
    for m, c in zip(
        diag.METHODS, ("#64748b", "#0284c7", "#d97706", "#7c3aed", "#15803d"), strict=True
    )
}
LIMITS = [
    "RETROSPECTIVE_REPLAY / EXPOSED_HISTORICAL_BENCHMARK / EXPLORATORY",
    "STRICT_PIT=false / PRODUCTION_ELIGIBLE=false / GENERALIZATION_ESTABLISHED=false",
    "历史训练是入库公斤数；SOURCE_002 是原果入库称重净重，两者物理等价未证明。",
    "历史面积 known_at、历史真实提前签发均未证明。2025–2026 已暴露，不能称为盲测。",
    "重叠 H7/H15 窗口不是独立样本；完整产季评分没有准入。",
    "实验 A 的新方法全部 BASELINE_FALLBACK；等于基线不等于模型获得验证性改善。",
    "误差账目解释的是固定样本上的算术变化，不证明产季、天气或标签口径的因果效应。",
]


def num(value: Any, places: int = 4, *, percent: bool = False) -> str:
    if value is None:
        return "NOT_COMPUTABLE"
    return f"{D(str(value)) * (100 if percent else 1):.{places}f}"


def mdrow(cells: list[Any]) -> str:
    return "| " + " | ".join(map(str, cells)) + " |"


def text(
    x: Any, y: Any, value: Any, *, anchor: str = "start", size: int = 13, extra: str = ""
) -> str:
    return (
        f'<text x="{D(x):.2f}" y="{D(y):.2f}" text-anchor="{anchor}" '
        f'font-size="{size}" {extra}>{html.escape(str(value))}</text>'
    )


def svg(title: str, data: Any, nodes: list[str], width: int = 1200, height: int = 460) -> bytes:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="{html.escape(title, quote=True)}">'
        f'<title>{html.escape(title)}</title><metadata data-sha256="{digest(data)}"/>'
        '<style>text{font-family:system-ui,"Noto Sans CJK SC",sans-serif;fill:#243247}'
        ".grid{stroke:#dbe3ec;stroke-width:1}.axis{stroke:#64748b}</style>"
        f'<rect width="{width}" height="{height}" fill="#f8fafc"/>'
        + text(25, 30, title, size=19)
        + "".join(nodes)
        + "</svg>"
    ).encode()


def axis(nodes: list[str], x: D, y: D, w: D, h: D, maximum: D, label: str) -> None:
    for j in range(5):
        yy = y + h - h * j / 4
        nodes.append(f'<line class="grid" x1="{x}" x2="{x + w}" y1="{yy}" y2="{yy}"/>')
        nodes.append(text(x - 8, yy + 4, num(maximum * j / 4, 2), anchor="end", size=11))
    nodes.append(text(x, y - 12, label, size=12))


def factor_distribution(run: dict[str, Any]) -> tuple[bytes, Any]:
    data = []
    ff = run["factors"]["experiments"]["B"]["base_factors"]
    for bid, r in sorted(ff.items()):
        data.append(
            {
                "base_id": bid,
                "name": run["names"][bid],
                "raw": r["raw_pooled_factor"],
                "shrunk": r["original_shrunk_factor"],
                "stable": r["consensus"]["stable_factor"],
            }
        )
    nodes: list[str] = []
    maximum = max(
        D(1), *(D(r[k]) for r in data for k in ("raw", "shrunk", "stable") if r[k] is not None)
    ) * D("1.12")
    x, y, w, h = D(70), D(100), D(1300), D(250)
    axis(nodes, x, y, w, h, maximum, "dimensionless factor")
    colors = {
        "raw": "#94a3b8",
        "shrunk": COLORS["VOLUME_CALIBRATION_V1"],
        "stable": COLORS[stable.METHOD],
    }
    for i, (key, color) in enumerate(colors.items()):
        nodes += [
            f'<rect x="{70 + i * 260}" y="53" width="13" height="13" fill="{color}"/>',
            text(90 + i * 260, 65, key),
        ]
    step = w / max(len(data), 1)
    for i, r in enumerate(data):
        for j, key in enumerate(colors):
            value = D(r[key]) if r[key] is not None else D(0)
            xx, hh = x + step * i + step * j / 4, value / maximum * h
            nodes.append(
                f'<rect x="{xx:.2f}" y="{y + h - hh:.2f}" width="{step / 4:.2f}" '
                f'height="{hh:.2f}" fill="{colors[key]}">'
                f"<title>{html.escape(r['name'])} {key}={r[key]}</title></rect>"
            )
        xx = x + step * i + step / 2
        nodes.append(
            text(
                xx,
                y + h + 12,
                r["name"],
                anchor="end",
                size=12,
                extra=f'transform="rotate(-60 {xx:.2f} {y + h + 12})"',
            )
        )
    return svg("历史训练基地系数：原始比值 / S4 收缩 / 保守候选", data, nodes, 1420, 560), data


def season_scatter(run: dict[str, Any]) -> tuple[bytes, Any]:
    ff = run["new"]["experiments"]["B"]["fitted"]["base_records"]
    data = [
        {"base_id": b, "name": run["names"][b], **ff[b]} for b in run["factors"]["two_season_bases"]
    ]
    valid = [r for r in data if r["F1"] is not None and r["F2"] is not None]
    maximum = max(D(1), *(D(r[k]) for r in valid for k in ("F1", "F2"))) * D("1.12")
    nodes: list[str] = []
    x, y, w, h = D(75), D(85), D(470), D(330)
    axis(nodes, x, y, w, h, maximum, "F2: 2024–2025")
    nodes.append(
        f'<line x1="{x}" x2="{x + w}" y1="{y + h}" y2="{y}" '
        'stroke="#94a3b8" stroke-dasharray="5 5"/>'
    )
    for i, r in enumerate(valid):
        xx, yy = x + D(r["F1"]) / maximum * w, y + h - D(r["F2"]) / maximum * h
        nodes.append(
            f'<circle cx="{xx:.2f}" cy="{yy:.2f}" r="5" fill="#0369a1">'
            f"<title>{html.escape(r['name'])} F1={r['F1']}; F2={r['F2']}</title></circle>"
        )
        nodes += [
            text(xx + 7, yy - 5, i + 1, size=11),
            text(590, 90 + i * 26, f"{i + 1}. {r['name']}: {num(r['F1'], 3)} → {num(r['F2'], 3)}"),
        ]
    for j in range(5):
        nodes.append(
            text(x + w * j / 4, y + h + 20, num(maximum * j / 4, 2), anchor="middle", size=11)
        )
    nodes.append(text(200, 460, "F1: 2023–2024；两季同用 Fold B、完整历史业务季"))
    return svg("共同历史基地的两季数量系数（不是独立验证）", data, nodes, 1200, 490), data


def wape_chart(run: dict[str, Any]) -> tuple[bytes, Any]:
    data = [
        {
            "experiment": e,
            "window": w,
            "values": {
                m: g[m]["metrics"]["DAILY_WAPE"]["candidate"]["value"] for m in diag.METHODS
            },
        }
        for e in ("A", "B")
        for w, g in run["comparison"]["experiments"][e]["groups"].items()
    ]
    nodes: list[str] = []
    maximum = max(
        D(1), *(D(v) * 100 for r in data for v in r["values"].values() if v is not None)
    ) * D("1.1")
    for k, panel in enumerate(data):
        x, y, w, h = D(65 + (k % 2) * 590), D(105 + (k // 2) * 295), D(490), D(185)
        nodes.append(text(x, y - 43, panel["experiment"] + " / " + panel["window"], size=16))
        axis(nodes, x, y, w, h, maximum, "WAPE %")
        for i, (m, v) in enumerate(panel["values"].items()):
            value = D(v) * 100 if v is not None else D(0)
            hh, xx = value / maximum * h, x + D(i) * w / 5 + 10
            nodes.append(
                f'<rect x="{xx}" y="{y + h - hh:.2f}" width="62" '
                f'height="{hh:.2f}" fill="{COLORS[m]}"/>'
            )
            nodes += [
                text(
                    xx + 31,
                    y + h - hh - 6,
                    num(value, 2) if v is not None else "NC",
                    anchor="middle",
                    size=12,
                ),
                text(xx + 31, y + h + 18, SHORT[m], anchor="middle", size=10),
            ]
    return svg("五模型整体数量加权 WAPE（A 留季验证 / B 暴露回放）", data, nodes, 1200, 670), data


def breadth_chart(run: dict[str, Any]) -> tuple[bytes, Any]:
    data = [
        {
            "experiment": e,
            "window": w,
            "values": {m: g[m]["metrics"]["BASE_BREADTH"] for m in diag.METHODS},
        }
        for e in ("A", "B")
        for w, g in run["comparison"]["experiments"][e]["groups"].items()
    ]
    nodes: list[str] = [
        text(25, 58, "绿色=改善；灰色=持平（包括基线回退）；红色=退化。相对原 Baseline。")
    ]
    for k, panel in enumerate(data):
        x, y = D(25 + (k % 2) * 590), D(105 + (k // 2) * 245)
        nodes.append(text(x, y - 15, panel["experiment"] + " / " + panel["window"], size=16))
        for i, (m, a) in enumerate(panel["values"].items()):
            nodes.append(text(x, y + i * 32 + 15, SHORT[m], size=12))
            xx = x + 125
            for key, color in (
                ("improved", "#15803d"),
                ("tied", "#cbd5e1"),
                ("worsened", "#dc2626"),
            ):
                width = D(a[key]) * 375 / max(a["n_base"], 1)
                nodes.append(
                    f'<rect x="{xx:.2f}" y="{y + i * 32}" width="{width:.2f}" '
                    f'height="22" fill="{color}"/>'
                )
                if a[key]:
                    nodes.append(
                        text(xx + width / 2, y + i * 32 + 16, a[key], anchor="middle", size=12)
                    )
                xx += width
            nodes.append(text(x + 510, y + i * 32 + 16, f"n={a['n_base']}", size=11))
    return svg("改善 / 持平 / 退化基地数：不把回退算作改善", data, nodes, 1200, 590), data


def daily_chart(run: dict[str, Any], bid: str, reason: str) -> tuple[bytes, Any]:
    ex = run["old"]["experiments"]["B"]
    dates: set[date] = set()
    for member in ex["members"]:
        if member["base_id"] != bid:
            continue
        start = date.fromisoformat(member["target_start"])
        dates.update(
            start + timedelta(days=i) for i in range(7 if member["window"] == "H7_PREFIX" else 15)
        )
    days = sorted(dates)
    aa = {r.day: str(r.kg) for r in run["labels"]["B"][bid]}
    series = {
        m: {date.fromisoformat(r["date"]): r["kg"] for r in cc[bid]}
        for m, cc in ex["curves"].items()
    }
    series[stable.METHOD] = {
        date.fromisoformat(r["date"]): r["kg"]
        for r in run["new"]["experiments"]["B"]["curves"][bid]
    }
    data = {
        "base_id": bid,
        "selection_rule": reason,
        "dates": [str(d) for d in days],
        "actual": [aa[d] for d in days],
        "models": {m: [rr[d] for d in days] for m, rr in series.items()},
    }
    values: dict[str, Any] = {"actual": data["actual"]}
    values.update({m: [rr[d] for d in days] for m, rr in series.items()})
    maximum = max(D(1), *(D(v) for rr in values.values() for v in rr)) * D("1.08")
    nodes: list[str] = []
    x, y, w, h = D(80), D(105), D(1060), D(265)
    axis(nodes, x, y, w, h, maximum, "kg / day")
    for j in range(min(5, len(days))):
        index = j * (len(days) - 1) // 4
        nodes.append(
            text(
                x + w * index / max(len(days) - 1, 1),
                y + h + 20,
                days[index],
                anchor="middle",
                size=11,
            )
        )
    for i, (m, vv) in enumerate(values.items()):
        color = "#111827" if m == "actual" else COLORS[m]
        points = " ".join(
            f"{x + w * j / max(len(days) - 1, 1):.2f},{y + h - D(v) / maximum * h:.2f}"
            for j, v in enumerate(vv)
        )
        nodes.append(
            f'<polyline points="{points}" fill="none" stroke="{color}" '
            f'stroke-width="{3 if m == "actual" else 2}"/>'
        )
        nodes.append(
            text(
                30 + i * 190,
                65,
                "实际入库净重" if m == "actual" else SHORT[m],
                size=12,
                extra=f'style="fill:{color}"',
            )
        )
    return svg(f"{run['names'][bid]} 日曲线 / {reason}", data, nodes, 1200, 430), data


def figures(run: dict[str, Any]) -> tuple[dict[str, bytes], dict[str, Any]]:
    images, source = {}, {}
    for name, fn in (
        ("factor-distribution.svg", factor_distribution),
        ("two-season-factors.svg", season_scatter),
        ("five-model-wape.svg", wape_chart),
        ("base-improvement-degradation.svg", breadth_chart),
    ):
        images[name], source[name] = fn(run)
    rows = run["analysis"]["experiments"]["B"]["official_repeated_window_accounting"]["H7_PREFIX"][
        "base_contributions"
    ]
    ranked = sorted(
        rows,
        key=lambda b: (
            D(rows[b]["models"]["VOLUME_CALIBRATION_V1"]["error_change_vs_baseline_kg"]),
            b,
        ),
    )
    common = run["factors"]["two_season_bases"]
    selection = [
        (common[0] if common else sorted(rows)[0], "FIRST_COMMON_ID"),
        (ranked[-1], "LARGEST_OLD_VOLUME_HARM"),
        (ranked[0], "LARGEST_OLD_VOLUME_GAIN"),
    ]
    for i, (bid, reason) in enumerate(selection):
        name = f"daily-example-{i + 1}.svg"
        images[name], source[name] = daily_chart(run, bid, reason)
    return images, source


def report_files(run: dict[str, Any]) -> dict[str, bytes]:
    with localcontext(Context(prec=50)):
        return _report(run)


def _report(run: dict[str, Any]) -> dict[str, bytes]:
    if run.get("execution_kind") not in {"REAL_FIXED_SOURCE_OWNER_COMMAND", "SYNTHETIC_END_TO_END"}:
        raise ValueError("EXPLICIT_REPORT_EXECUTION_IDENTITY_REQUIRED")
    images, sources = figures(run)
    lines = ["# V0.19 S5 跨季稳定性诊断与保守候选", "", run["execution_kind"], ""]
    lines += ["- " + v for v in LIMITS] + ["", "## 先看结论及证据边界", ""]
    factors = run["factors"]
    sets = factors["training_identity_sets"]
    lines += [
        f"历史合格成员：{len(sets[stable.SEASONS[0]])}+{len(sets[stable.SEASONS[1]])} "
        "个 Base-season；"
        f"唯一 Base={len(set().union(*map(set, sets.values())))}；"
        f"精确共同身份={len(factors['two_season_bases'])}。",
        "旧四模型只读复用；新候选没有根据评价误差选择参数、成员或方法。",
        "",
        "| 固定 2023–2024 训练行的分步审计 | 分箱数 | 基地数 | 实际 kg/mu 之和 | "
        "基线 kg/mu 之和 | 全局系数 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for key, r in factors["global_ratio_decomposition"].items():
        if isinstance(r, dict):
            lines.append(
                mdrow(
                    [
                        key,
                        r["training_bins"],
                        r["base_count"],
                        num(r["sum_actual_kg_per_mu"]),
                        num(r["sum_baseline_kg_per_mu"]),
                        num(r["factor"], 8),
                    ]
                )
            )
    lines += [
        "",
        "这个分步恒等式隔离了参考分母变化和新增训练行；不是将 Fold B 用于较早验证，"
        "更不能识别产季本身的因果效应。",
        "训练数据、Profile、Fit、评价成员、实际量权重及物理口径同时存在差异，"
        "A/B 的 WAPE 不可直接作跨季模型效果归因。",
        "",
        "![基地系数分布](factor-distribution.svg)",
        "",
        "![两季系数对照](two-season-factors.svg)",
        "",
        "![五模型 WAPE](five-model-wape.svg)",
        "",
        "![改善退化基地](base-improvement-degradation.svg)",
        "",
    ]
    for e in ("A", "B"):
        ex = run["comparison"]["experiments"][e]
        analysis = run["analysis"]["experiments"][e]
        ff = factors["experiments"][e]
        lines += [
            f"## 实验 {e}",
            "",
            f"训练={ff['training_seasons']}；全局系数={ff['global_factor']}；"
            f"评价 Base={analysis['evaluation_base_count']}；成员={analysis['candidate_count']}；"
            f"新候选 BASELINE_FALLBACK 基地={analysis['fallback_base_count']}。",
            f"旧四模型所有指标和共同集合精确保留={ex['old_four_metric_parity']}。",
            "",
        ]
        for window, mm in ex["groups"].items():
            audit = analysis["official_repeated_window_accounting"][window]
            lines += [
                f"### {window}",
                "",
                "| 指标 | Baseline | S2 | Volume | Volume+Timing | Consensus |",
                "|---|---:|---:|---:|---:|---:|",
            ]
            for metric in ERROR_METRICS:
                lines.append(
                    "| "
                    + metric
                    + (" (%)" if metric.endswith("WAPE") else "")
                    + " | "
                    + " | ".join(
                        num(
                            mm[m]["metrics"][metric]["candidate"]["value"],
                            6,
                            percent=metric.endswith("WAPE"),
                        )
                        for m in diag.METHODS
                    )
                    + " |"
                )
            lines += [
                "",
                "| Model | 数量加权 WAPE % | Base 等权 WAPE % | 改善/退化/持平 | "
                "WAPE 共同/C0 | 峰日期共同/C0 |",
                "|---|---:|---:|---|---:|---:|",
            ]
            for m in diag.METHODS:
                met, be = mm[m]["metrics"], audit["base_equal_WAPE"][m]
                b = met["BASE_BREADTH"]
                lines.append(
                    mdrow(
                        [
                            SHORT[m],
                            num(met["DAILY_WAPE"]["candidate"]["value"], 6, percent=True),
                            num(be["base_equal_WAPE"], 6, percent=True),
                            f"{b['improved']}/{b['worsened']}/{b['tied']}",
                            f"{met['DAILY_WAPE']['common_count']}/{met['DAILY_WAPE']['candidate_count']}",
                            str(met["SINGLE_DAY_PEAK_DATE_MAE"]["common_count"])
                            + "/"
                            + str(met["SINGLE_DAY_PEAK_DATE_MAE"]["candidate_count"]),
                        ]
                    )
                )
            lines += [
                "",
                "| Model | 实际 kg 分母 | 绝对误差 kg 分子 | 过预测误差 kg | 欠预测误差 kg | "
                "有符号偏差 kg |",
                "|---|---:|---:|---:|---:|---:|",
            ]
            for m, r in audit["aggregate"]["models"].items():
                lines.append(
                    f"| {SHORT[m]} | {num(audit['aggregate']['actual_kg'], 6)} | "
                    + " | ".join(
                        num(r[k], 6)
                        for k in (
                            "absolute_error_kg",
                            "overprediction_error_kg",
                            "underprediction_error_kg",
                            "signed_bias_kg",
                        )
                    )
                    + " |"
                )
            lines += [
                "",
                "重复窗口中的同一天按其出现次数计入上表，这是原 S1 算术，不是独立观察数。",
                "",
                "| Baseline 原方向 | 数量校准消除误差 kg | 数量校准新增误差 kg | 加权日出现数 |",
                "|---|---:|---:|---:|",
            ]
            for k, r in audit["volume_change_by_baseline_direction"].items():
                lines.append(
                    mdrow(
                        [
                            k,
                            num(r["improved_error_kg"], 6),
                            num(r["degraded_error_kg"], 6),
                            r["day_occurrences"],
                        ]
                    )
                )
            harm = audit["observed_harm_gain"]
            lines += [
                "",
                "| Model | 相对基线 gross harm pp | gross gain pp | 净 WAPE 变化 pp |",
                "|---|---:|---:|---:|",
            ]
            for m in diag.METHODS:
                r = harm[m]
                delta = (
                    D(r["gross_harm_pp"]) - D(r["gross_gain_pp"])
                    if r["gross_harm_pp"] is not None
                    else None
                )
                lines.append(
                    mdrow(
                        [
                            SHORT[m],
                            num(r["gross_harm_pp"], 6),
                            num(r["gross_gain_pp"], 6),
                            num(delta, 6),
                        ]
                    )
                )
            trade = harm["volume_to_stable_tradeoff"]
            volume = "VOLUME_CALIBRATION_V1"
            denominator = D(audit["aggregate"]["actual_kg"])
            direction = audit["volume_change_by_baseline_direction"]
            lines += ["", "#### 可核对的误差变化解释", ""]
            for kind, r in direction.items():
                delta = D(r["degraded_error_kg"]) - D(r["improved_error_kg"])
                lines.append(
                    f"{kind} 日期的数量校准净误差变化为 {num(delta, 6)} kg"
                    + (
                        f"（{num(delta * 100 / denominator, 6)} pp）"
                        if denominator
                        else "（分母为零）"
                    )
                    + "；这是固定预测与标签逐日比较的结果，不是机制因果证明。"
                )
            ranked = sorted(
                audit["base_contributions"].items(),
                key=lambda item: (
                    -D(item[1]["models"][volume]["error_change_vs_baseline_kg"]),
                    item[0],
                ),
            )
            lines.append(
                "按旧 Volume 的误差增加量排序，贡献最大的基地为："
                + "；".join(
                    f"{run['names'][bid]} ({bid}) "
                    f"{num(r['models'][volume]['WAPE_contribution_change_pp'], 6)} pp"
                    for bid, r in ranked[:3]
                )
                + "。完整基地列表保留，未按表现剔除。"
            )
            lines += [
                "",
                f"相对旧 Volume，观测到的退化误差减少 {num(trade['harm_avoided_kg'], 6)} kg；"
                f"同时牺牲改善 {num(trade['gain_forgone_kg'], 6)} kg。"
                "不是未来风险概率，也不是泛化证明。",
                "",
                "#### 全部基地的官方 WAPE 贡献",
                "",
                "| Base ID | 基地 | 实际权重 % | Baseline error kg | Volume error kg | "
                "Consensus error kg | Volume Δpp | Consensus Δpp |",
                "|---|---|---:|---:|---:|---:|---:|---:|",
            ]
            for bid, r in audit["base_contributions"].items():
                vv = r["models"]
                lines.append(
                    f"| {bid} | {run['names'][bid]} | {num(r['actual_weight'], 4, percent=True)} | "
                    + " | ".join(
                        num(vv[m]["absolute_error_kg"], 4)
                        for m in ("baseline", "VOLUME_CALIBRATION_V1", stable.METHOD)
                    )
                    + " | "
                    + " | ".join(
                        num(vv[m]["WAPE_contribution_change_pp"], 6)
                        for m in ("VOLUME_CALIBRATION_V1", stable.METHOD)
                    )
                    + " |"
                )
            lines += [
                "",
                "#### 月份与七日分箱误差",
                "",
                "| Month | 实际 kg | Baseline error kg | Volume error kg | Consensus error kg |",
                "|---|---:|---:|---:|---:|",
            ]
            for month, r in audit["by_month"].items():
                lines.append(
                    f"| {month} | {num(r['actual_kg'], 4)} | "
                    + " | ".join(
                        num(r["models"][m]["absolute_error_kg"], 4)
                        for m in ("baseline", "VOLUME_CALIBRATION_V1", stable.METHOD)
                    )
                    + " |"
                )
            lines += [
                "",
                "| July01 anchored bin | 实际 kg | Baseline error kg | Volume error kg | "
                "Consensus error kg |",
                "|---|---:|---:|---:|---:|",
            ]
            for bin_id, r in audit["by_season_7day_bin"].items():
                lines.append(
                    f"| {bin_id} | {num(r['actual_kg'], 4)} | "
                    + " | ".join(
                        num(r["models"][m]["absolute_error_kg"], 4)
                        for m in ("baseline", "VOLUME_CALIBRATION_V1", stable.METHOD)
                    )
                    + " |"
                )
            lines += [
                "",
                "SAMPLE_COVERAGE / NOT_COMPUTABLE_COUNT（完整成员及原因见 JSON）：",
                "",
                "```json",
                json.dumps(
                    {
                        m: {
                            k: mm[m]["metrics"][k]
                            for k in ("SAMPLE_COVERAGE", "NOT_COMPUTABLE_COUNT")
                        }
                        for m in diag.METHODS
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                "```",
                "",
            ]
        lines += [
            "### 历史训练系数（完整分箱拟合与完整季 F1/F2 分列）",
            "",
            "| Base ID | 基地 | 完整分箱数 | 原始 pooled F | S4 final F | 新 F | F1 | F2 | "
            "spread | weight | Mode |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
        for bid, r in ff["base_factors"].items():
            c = r["consensus"]
            lines.append(
                mdrow(
                    [
                        bid,
                        run["names"][bid],
                        r["complete_training_bins"],
                        num(r["raw_pooled_factor"], 6),
                        num(r["original_shrunk_factor"], 6),
                    ]
                )
                + " "
                + " | ".join(
                    num(c[k], 6) for k in ("stable_factor", "F1", "F2", "spread", "weight")
                )
                + f" | {c['mode']} |"
            )
        lines += [
            "",
            "| Base ID | 历史季 | 来源成员数 | 面积 mu | 完整季实际 kg/mu | "
            "完整季基线 kg/mu | 日期数 |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
        for r in ff["full_season_summaries"]:
            members = next(
                m
                for m in ff["base_factors"][r["base_id"]]["training_members"]
                if m["season"] == r["season"]
            )
            lines.append(
                mdrow(
                    [
                        r["base_id"],
                        r["season"],
                        members["source_member_count"],
                        r["area_mu"],
                        num(r["actual_kg_per_mu"], 6),
                        num(r["baseline_kg_per_mu"], 6),
                        r["days"],
                    ]
                )
            )
        lines += [
            "",
            "### 唯一 Base×日数量（不重复窗口）",
            "",
            "| Base ID | 基地 | Seen | 实际 kg | Baseline kg | Volume kg | Consensus kg | "
            "Baseline abs error kg | Volume abs error kg | Consensus abs error kg |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for bid, r in analysis["unique_base_days"].items():
            lines.append(
                mdrow([bid, run["names"][bid], r["seen_in_original_fit"], num(r["actual_kg"], 4)])
                + " "
                + " | ".join(
                    num(r["models"][m][k], 4)
                    for k in ("predicted_kg", "absolute_error_kg")
                    for m in ("baseline", "VOLUME_CALIBRATION_V1", stable.METHOD)
                )
                + " |"
            )
        lines += [
            "",
            "### Seen / Unseen（原 fit 身份）",
            "",
            "| Group | Window | Baseline WAPE % | Volume WAPE % | Consensus WAPE % |",
            "|---|---|---:|---:|---:|",
        ]
        for group, data in ex["seen_unseen"].items():
            for window, mm in data["groups"].items():
                lines.append(
                    f"| {group} | {window} | "
                    + " | ".join(
                        num(mm[m]["metrics"]["DAILY_WAPE"]["candidate"]["value"], 6, percent=True)
                        for m in ("baseline", "VOLUME_CALIBRATION_V1", stable.METHOD)
                    )
                    + " |"
                )
    lines += [
        "",
        "## 评价成员变化的身份审计（仅在实验 B 内分组）",
        "",
        "共有基地按 A/B 精确 Base ID 取交集；其 B 期标签和权重与 A 不同，"
        "不能据此识别产季效应或将两组 WAPE 直接相减解释为泛化。",
        "",
        "| Window | 成员组 | Base 数 | B 实际权重 % | Baseline WAPE % | "
        "Volume WAPE % | Consensus WAPE % |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for window, groups in run["analysis"]["B_common_vs_additional_identity_audit"].items():
        for group, r in groups.items():
            lines.append(
                mdrow(
                    [
                        window,
                        group,
                        len(r["base_ids"]),
                        num(r["actual_weight"], 6, percent=True),
                        *(
                            num(r["WAPE"][m], 6, percent=True)
                            for m in ("baseline", "VOLUME_CALIBRATION_V1", stable.METHOD)
                        ),
                    ]
                )
            )
    lines += [
        "## 典型基地实际曲线（只作诊断，不筛选评分样本）",
        "",
        "![共同基地固定首项](daily-example-1.svg)",
        "",
        "![旧数量校准最大退化贡献](daily-example-2.svg)",
        "",
        "![旧数量校准最大改善贡献](daily-example-3.svg)",
        "",
        "## 仍缺的数据与结论边界",
        "",
        "需要同一可核验物理口径、完整成员和单位的独立未暴露产季；历史面积生效/known_at、真实签发、"
        "物候、修剪/促早、有效采摘能力及当时可用天气等可追溯时间证据。现有相关性不能替代这些证据。",
        "本候选只控制校准幅度。回退牺牲潜在改善；两季一致也不保证未来稳定。"
        "单日峰/七日峰指标及所有失败、全零、不可计算样本均保留；H7 七日峰起点为零是结构结果。",
        "没有重新训练旧模型，没有读取评价标签调参，没有修改生产模型或晋级。",
        "",
    ]
    markdown = "\n".join(lines)
    body = (
        study.markdown_html(markdown)
        .replace("<table>", '<div class="table-scroll"><table>')
        .replace("</table>", "</table></div>")
    )
    for name, raw in images.items():
        # Exactly the generated local figure placeholders, not arbitrary HTML from data.
        for line in lines:
            if line.startswith("![") and line.endswith(f"]({name})"):
                body = body.replace(
                    "<p>" + html.escape(line) + "</p>", "<figure>" + raw.decode() + "</figure>"
                )
    document = (
        '<!doctype html><meta charset="utf-8"><title>V0.19 S5 stability research</title>'
        "<style>body{font:14px system-ui;max-width:1440px;margin:28px auto;padding:0 18px;"
        "color:#243247;overflow-wrap:anywhere}"
        "h1,h2{color:#11263b}h2{margin-top:42px}table{border-collapse:collapse;width:100%;font-size:12px}"
        "td{border:1px solid #d6dfeb;padding:6px;min-width:70px;vertical-align:top;"
        "overflow-wrap:anywhere}"
        "tr:first-child{font-weight:600;background:#edf2f7}.table-scroll{overflow-x:auto;max-width:100%}"
        "pre{white-space:pre-wrap;font-size:11px;background:#f4f7fa;padding:12px}"
        "figure{margin:24px 0}"
        "svg{display:block;width:100%;height:auto}p,li{line-height:1.6}</style>" + body
    )
    analysis = {
        **run["analysis"],
        "chart_source_data": sources,
        "limitations": LIMITS,
        "execution_kind": run["execution_kind"],
    }
    return {
        "stability-analysis.json": canonical_bytes(analysis),
        "factor-diagnostics.json": canonical_bytes(run["factors"]),
        "five-model-comparison.json": canonical_bytes(s4.compact(run["comparison"])),
        "report.md": markdown.encode(),
        "report.html": document.encode(),
        **images,
    }
