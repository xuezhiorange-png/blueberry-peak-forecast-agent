"""Private numerical S6 reports. Images are computed SVG, not illustrative data."""

from __future__ import annotations

import html
import json
from datetime import date, timedelta
from decimal import Context, Decimal, localcontext
from typing import Any

from backend.research import v019_accuracy_study as study
from backend.research import v019_origin_evaluation as evaluation
from backend.research import v019_origin_features as features
from backend.research import v019_real_training_cli as old
from backend.research.v019_daily_curve import canonical_bytes
from backend.research.v019_stability_report import axis, mdrow, num, svg, text
from backend.research.v019_synthetic_validation import ERROR_METRICS

LIMITS = [
    "RETROSPECTIVE_REPLAY / EXPOSED_HISTORICAL_BENCHMARK / RETROSPECTIVE_DATE_BOUND",
    "STRICT_PIT=false / PRODUCTION_ACCURACY_VALIDATED=false / PRODUCTION_ELIGIBLE=false",
    "训练为历史入库公斤数；SOURCE_002 为原果入库称重净重，物理等价及历史面积 known_at 尚未证明。",
    "业务日期不能证明历史 available_at。特征物化器已读取完整历史来源；不声称目标标签从未暴露。",
    "预测器只接收逐 origin 过去聚合快照与合法训练标签，不打开完整历史评分报告。",
    "相邻 origin 及重叠窗口不是独立样本。全产季未准入；H7 rolling7 起点 MAE=0 为结构结果。",
    "M0/M1 共同可计算子集之外的 C0 全部保留，缺失不补零；不能推广为全 C0 或生产精度。",
    "静态 Operational Peak 属于不同模型家族，仅在相同标签和成员上作业务背景，"
    "不作直接公平模型晋级排名。",
]


def examples(run: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    records = run["features"]["records"]
    for e, ex in run["predictions"]["experiments"].items():
        grouped: dict[str, dict[str, str]] = {}
        for k, r in ex["origins"].items():
            if r["status"] == "COMPUTED" and len(records[k]["target_dates"]) == 15:
                q = records[k]
                grouped.setdefault(q["base_id"], {})[q["origin"]] = k
        for bid, origins in sorted(grouped.items())[:2]:
            valid = [
                d
                for d in sorted(origins)
                if str(date.fromisoformat(d) + timedelta(days=1)) in origins
            ]
            if not valid:
                continue
            expected = ("2025" if e == "A" else "2026") + "-01-15"
            d = expected if expected in valid else valid[len(valid) // 2]
            k0 = origins[d]
            k1 = origins[str(date.fromisoformat(d) + timedelta(days=1))]
            p0, p1 = ex["origins"][k0]["predictions"], ex["origins"][k1]["predictions"]
            aa = {str(r.day): str(r.kg) for r in run["actual"][e][bid]}
            dates = sorted(set(records[k0]["target_dates"]) | set(records[k1]["target_dates"]))
            maps = {
                label: {r["date"]: r["kg"] for r in rr}
                for label, rr in [
                    ("M0_D", p0["M0"]),
                    ("M1_D", p0["M1"]),
                    ("M0_Dplus1", p1["M0"]),
                    ("M1_Dplus1", p1["M1"]),
                ]
            }
            common = sorted(set(maps["M0_D"]) & set(maps["M0_Dplus1"]))
            target = common[0]
            result.append(
                {
                    "experiment": e,
                    "base_id": bid,
                    "name": run["names"][bid],
                    "origins": [d, records[k1]["origin"]],
                    "selection_rule": "FIRST_TWO_BASE_IDS_FIXED_JAN15_ELSE_MIDDLE_ORIGIN_"
                    "NO_ERROR_SELECTION",
                    "features": [records[k0]["values"], records[k1]["values"]],
                    "state_coefficients": dict(
                        zip(
                            features.FEATURES,
                            run["fits"]["experiments"][e]["models"]["M1"]["coefficients"][-4:],
                            strict=True,
                        )
                    ),
                    "dates": dates,
                    "actual": {t: aa[t] for t in dates},
                    "predictions": maps,
                    "same_target_date": target,
                    "same_target_M0_delta_kg": str(
                        Decimal(maps["M0_Dplus1"][target]) - Decimal(maps["M0_D"][target])
                    ),
                    "same_target_M1_delta_kg": str(
                        Decimal(maps["M1_Dplus1"][target]) - Decimal(maps["M1_D"][target])
                    ),
                    "peaks": {
                        "D": {m: evaluation.peaks(evaluation.curve(rr)) for m, rr in p0.items()},
                        "Dplus1": {
                            m: evaluation.peaks(evaluation.curve(rr)) for m, rr in p1.items()
                        },
                    },
                }
            )
    return result


def example_chart(item: dict[str, Any]) -> bytes:
    x, y, w, h = Decimal(75), Decimal(100), Decimal(1080), Decimal(260)
    data = {"actual": item["actual"], **item["predictions"]}
    maximum = max(Decimal(1), *(Decimal(v) for rr in data.values() for v in rr.values())) * Decimal(
        "1.12"
    )
    nodes: list[str] = []
    axis(nodes, x, y, w, h, maximum, "kg / target business day")
    colors = ["#111827", "#2563eb", "#d97706", "#0891b2", "#15803d"]
    for i, ((name, rr), color) in enumerate(zip(data.items(), colors, strict=True)):
        points = " ".join(
            f"{x + w * j / (len(item['dates']) - 1):.2f},{y + h - Decimal(rr[t]) / maximum * h:.2f}"
            for j, t in enumerate(item["dates"])
            if t in rr
        )
        nodes.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2"/>')
        nodes.append(text(25 + i * 225, 65, name, size=12, extra=f'style="fill:{color}"'))
    for i in [0, 7, 15]:
        nodes.append(text(x + w * i / 15, y + h + 30, item["dates"][i], anchor="middle", size=12))
    return svg(
        f"{item['experiment']} / {item['name']} / origins {item['origins']}", item, nodes, 1200, 440
    )


def metric_chart(comparison: dict[str, Any]) -> bytes:
    data = {}
    nodes: list[str] = []
    for i, (e, ex) in enumerate(comparison["experiments"].items()):
        for j, (w, g) in enumerate(ex["groups"].items()):
            values = {
                m: g["paired"]["metrics"]["DAILY_WAPE"][side]["value"]
                for m, side in [("M0", "baseline"), ("M1", "candidate")]
            }
            data[e + "_" + w] = values
            x, y = Decimal(70 + j * 600), Decimal(100 + i * 300)
            width, height = Decimal(500), Decimal(195)
            maximum = max(
                Decimal(1), *(Decimal(v) * 100 for v in values.values() if v is not None)
            ) * Decimal("1.1")
            axis(nodes, x, y, width, height, maximum, "WAPE %")
            nodes.append(text(x, y - 40, e + " / " + w, size=16))
            for k, (name, v) in enumerate(values.items()):
                xx = x + 60 + k * 210
                if v is None:
                    nodes.append(text(xx, y + height / 2, "NOT_COMPUTABLE", size=11))
                else:
                    hh = Decimal(v) * 100 / maximum * height
                    nodes.append(
                        f'<rect x="{xx}" y="{y + height - hh}" width="100" height="{hh}" '
                        f'fill="{["#2563eb", "#15803d"][k]}"/>'
                    )
                    nodes.append(
                        text(
                            xx + 50,
                            y + height - hh - 8,
                            num(v, 4, percent=True),
                            anchor="middle",
                            size=12,
                        )
                    )
                nodes.append(text(xx + 50, y + height + 25, name, anchor="middle"))
    return svg(
        "同成员、同标签、同训练范围的动态 Ridge 配对；静态模型不参与排名", data, nodes, 1200, 710
    )


def files(run: dict[str, Any]) -> dict[str, bytes]:
    with localcontext(Context(prec=50)):
        return _files(run)


def _files(run: dict[str, Any]) -> dict[str, bytes]:
    c = run["comparison"]
    example = examples(run)
    c = {
        **c,
        "examples": example,
        "limitations": LIMITS,
        "source_access_audit": run["features"]["source_access_audit"],
        "prior_bridge": run["features"]["prior_bridge"],
        "optional_inputs": {
            "phenology": {
                "status": "NOT_VERIFIED",
                "field_observation_authority": False,
                "code": "biological_growth.phenology.state_from_progress is model-derived, "
                "not field observation",
            },
            "management": {
                "status": "NOT_VERIFIED",
                "verified_execution_records_in_authorized_sources": 0,
            },
            "weather": {
                "status": "NOT_VERIFIED_FOR_THIS_EXPERIMENT",
                "forecast_available_at": "NOT_PROVEN",
                "era5_is_reanalysis_not_as_issued_forecast": True,
            },
            "used_in_model": False,
        },
    }
    lines = [
        "# V0.19 S6 基于实际采收进度的动态预测",
        "",
        "RETROSPECTIVE_DATE_BOUND；不是严格 PIT，也不是生产准确率验收。",
        "",
    ] + ["- " + v for v in LIMITS]
    lines += [
        "",
        "## 来源与准入",
        "",
        "V0.15 四项聚合及 Ridge 原求解器直接复用；alpha=10、训练集 population std、"
        "零方差 scale=1、未惩罚截距、非负输出。",
        "原求解器为 NumPy float64；不改数值求解。累计与指标为 Decimal precision 50，"
        "最终预测 kg 六位、half-even。",
        "M0/M1 仅有无四项状态特征不同；不会以本次结果调参或改变训练范围。",
        "2025–2026 的 season_to_date 起点仍是冻结的 7月22日，不重设到8月5日。"
        "早期旧权威只有精确成员不变时可复用。",
        "",
        "| Season | 完整状态 origins | 不完整 origins |",
        "|---|---:|---:|",
    ]
    for s in features.SEASONS:
        rr = [r for r in run["features"]["records"].values() if r["season"] == s]
        lines.append(mdrow([s, sum(r["complete"] for r in rr), sum(not r["complete"] for r in rr)]))
    lines += ["", "| Base | 精确成员一致 | 可复用早期日 | 不可复用日 |", "|---|---|---:|---:|"]
    for b, r in run["features"]["prior_bridge"].items():
        lines.append(
            mdrow(
                [
                    run["names"][b],
                    r["exact_members_equal"],
                    r["accepted_prior_days"],
                    r["rejected_prior_days"],
                ]
            )
        )
    lines += ["", "## 模型与数值比较", "", "![动态模型共同集合WAPE](dynamic-wape.svg)", ""]
    for e, ex in c["experiments"].items():
        fit = run["fits"]["experiments"][e]
        lines += [
            f"### 实验 {e}",
            "",
            f"训练季={fit['training_seasons']}；Base-season={len(fit['training_base_seasons'])}；"
            f"训练 origins={fit['training_origin_count']}；"
            f"训练 target rows={fit['training_target_count']}。",
            f"原 C0={ex['candidate_count']}；M0/M1共同可计算={ex['common_computed_count']}；"
            f"不可计算={ex['not_computable_count']}；结论={ex['classification']}。",
            "",
        ]
        for w, g in ex["groups"].items():
            lines += [
                f"#### {w}",
                "",
                "| 指标 | M0 | M1 | M1−M0 | 静态同集合（不同家族） |",
                "|---|---:|---:|---:|---:|",
            ]
            for name in ERROR_METRICS:
                m = g["paired"]["metrics"][name]
                static = g["static_on_common"]["metrics"][name]
                lines.append(
                    mdrow(
                        [
                            name,
                            num(m["baseline"]["value"], 6, percent=name.endswith("WAPE")),
                            num(m["candidate"]["value"], 6, percent=name.endswith("WAPE")),
                            num(
                                g["paired"]["candidate_minus_baseline"][name],
                                6,
                                percent=name.endswith("WAPE"),
                            ),
                            num(static["baseline"]["value"], 6, percent=name.endswith("WAPE")),
                        ]
                    )
                )
            ma = g["paired"]["metrics"]["DAILY_WAPE"]
            full = ex["full_C0_actual_denominators"][w]
            lines += [
                "",
                f"WAPE共同成员={ma['common_count']}/{ma['candidate_count']}；"
                f"共同actual分母={ma['baseline']['denominator']} kg；"
                f"完整C0有标签分母={full['actual_kg']} kg。",
                f"绝对误差分子：M0={ma['baseline']['numerator']} kg；"
                f"M1={ma['candidate']['numerator']} kg。重复窗口中的kg不是唯一产季总量。",
                "同一来源完整C0的静态WAPE="
                + num(
                    g["static_full_C0"]["metrics"]["DAILY_WAPE"]["baseline"]["value"],
                    6,
                    percent=True,
                )
                + "%。",
                "",
                "| Base | M0 WAPE % | M1 WAPE % | Δ pp | MAE共同窗口/C0 |",
                "|---|---:|---:|---:|---:|",
            ]
            for b, br in ex["per_base"].items():
                p = br[w]["paired"]
                mm = p["metrics"]["DAILY_WAPE"]
                lines.append(
                    mdrow(
                        [
                            run["names"][b],
                            num(mm["baseline"]["value"], 6, percent=True),
                            num(mm["candidate"]["value"], 6, percent=True),
                            num(p["candidate_minus_baseline"]["DAILY_WAPE"], 6, percent=True),
                            f"{p['metrics']['DAILY_MAE']['common_count']}/{p['metrics']['DAILY_MAE']['candidate_count']}",
                        ]
                    )
                )
            lines += [
                "",
                "BASE_BREADTH / SAMPLE_COVERAGE / NOT_COMPUTABLE_COUNT：",
                "",
                "```json",
                json.dumps(
                    {
                        k: g["paired"]["metrics"][k]
                        for k in ("BASE_BREADTH", "SAMPLE_COVERAGE", "NOT_COMPUTABLE_COUNT")
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                "```",
                "",
                "| Scope | M0 WAPE % | M1 WAPE % | 共同/C0 |",
                "|---|---:|---:|---:|",
            ]
            for scope, gg in ex["seen_unseen"].items():
                mm = gg[w]["paired"]["metrics"]["DAILY_WAPE"]
                lines.append(
                    mdrow(
                        [
                            scope,
                            num(mm["baseline"]["value"], 6, percent=True),
                            num(mm["candidate"]["value"], 6, percent=True),
                            f"{mm['common_count']}/{mm['candidate_count']}",
                        ]
                    )
                )
    lines += [
        "",
        "## 相邻 origin 如何更新同一目标日",
        "",
        "样例按固定 Base ID 与固定1月15日选取；无该日期则取中间合法origin，不按误差挑选。",
    ]
    images = {"dynamic-wape.svg": metric_chart(c)}
    for i, item in enumerate(example):
        name = f"dynamic-example-{i + 1}.svg"
        images[name] = example_chart(item)
        lines += [
            "",
            f"### {item['experiment']} / {item['name']} / {item['origins']}",
            "",
            f"![相邻origin曲线]({name})",
            "",
            "| 特征 | D | D+1 | 固定M1系数 |",
            "|---|---:|---:|---:|",
        ]
        for k in features.FEATURES:
            lines.append(
                mdrow(
                    [
                        k,
                        item["features"][0][k],
                        item["features"][1][k],
                        item["state_coefficients"][k],
                    ]
                )
            )
        lines += [
            "",
            f"同一目标日 {item['same_target_date']}："
            f"M0变化={item['same_target_M0_delta_kg']} kg，"
            f"M1变化={item['same_target_M1_delta_kg']} kg。"
            "变化来自冻结参数对合法过去特征的响应，未加人工调整系数。",
            "",
            "| 日期 | actual kg | M0(D) | M1(D) | M0(D+1) | M1(D+1) |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for d in item["dates"]:
            lines.append(
                mdrow(
                    [
                        d,
                        item["actual"][d],
                        *(
                            item["predictions"][k].get(d, "OUTSIDE_WINDOW")
                            for k in ("M0_D", "M1_D", "M0_Dplus1", "M1_Dplus1")
                        ),
                    ]
                )
            )
        lines += [
            "",
            "各预测窗口峰值（数量与日期均为代码计算）：",
            "",
            "```json",
            json.dumps(item["peaks"], ensure_ascii=False, indent=2),
            "```",
        ]
    ref = run["reference"]
    lines += [
        "",
        "## Operational Peak 参考曲线可靠性",
        "",
        "| Fold | 原训练季 | 原Base-season | 原Base数 | 训练行集合Hash |",
        "|---|---|---:|---:|---|",
    ]
    for f, m in ref["profile_metadata"].items():
        lines.append(
            mdrow(
                [
                    f,
                    m["train_seasons"],
                    m["train_unique_base_season_count"],
                    m["train_unique_base_count"],
                    m["train_row_set_hash"],
                ]
            )
        )
    lines += [
        "",
        "这不是当前15/37个数量权威训练成员。旧Profile基于已知标签子集；不能将新完整性权威回写到其旧身份。",
        "A缺失分箱按最近可用训练bin、距离并列取较早bin；B具有全部42个bin。分箱均从7月1日起，每个bin值是日kg/mu而不是七日总kg/mu；未发现此代码规则的锚点或单位改变。",
        "",
        "| 变化最大的bin | A日kg/mu | B日kg/mu | B−A | A/B实际引用bin |",
        "|---|---:|---:|---:|---|",
    ]
    for b in ref["largest_absolute_bin_changes"][:15]:
        lines.append(
            mdrow(
                [
                    b["bin"],
                    b["daily_kg_per_mu"]["A"],
                    b["daily_kg_per_mu"]["B"],
                    b["delta_B_minus_A"],
                    b["selected_reference_bin"],
                ]
            )
        )
    lines += [
        "",
        "| 固定Base/season | A总kg | B总kg | Δkg | 日峰日期位移 | 7日峰起点位移 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for r in sorted(
        ref["fixed_input_sensitivity"],
        key=lambda r: (-abs(Decimal(r["delta_predicted_kg"])), r["base_id"], r["season"]),
    ):
        lines.append(
            mdrow(
                [
                    run["names"][r["base_id"]] + "/" + r["season"],
                    num(r["profiles"]["A"]["predicted_kg"], 4),
                    num(r["profiles"]["B"]["predicted_kg"], 4),
                    num(r["delta_predicted_kg"], 4),
                    r["single_peak_date_shift_days"],
                    r["rolling7_start_shift_days"],
                ]
            )
        )
    lines += [
        "",
        "同一Profile按面积缩放：相对敏感度除微量舍入外相同；绝对kg敏感度排名主要反映面积，不证明基地生物反应差异。",
        "Profile原训练Ledger Hash及原成员Hash见reference-profile-diagnostics.json；"
        "不重拟合Profile，不根据2025结果挑选Profile。",
        "",
        "## 仍需真实业务观测",
        "",
        "真实田间物候观测与管理执行记录在本次获准来源中均NOT_VERIFIED；模拟物候状态不能冒充田间观察。",
        "已有WeatherDailyObservation支持日期、温度、降水、辐射、风速和来源Hash，"
        "但不证明历史forecast available_at。ERA5为再分析，不能冒充当时可用天气预报。"
        "本轮未读天气文件、未输入天气/物候/管理特征。",
        "需要可核验的来源成员、逐日完整性与合法零值、可信available_at/ingested_at、有效面积known_at、当时天气预报、物候实测及管理执行记录。",
        "采收进度只能在本轮共同可计算成员和来源标签下评价；若数量改善但峰时退化，结论必须是MIXED。缺失历史不以补零或缩短season-to-date掩盖。",
        "",
    ]
    md = "\n".join(lines)
    body = study.markdown_html(md)
    body = body.replace("<table>", '<div class="scroll"><table>').replace(
        "</table>", "</table></div>"
    )
    for name, raw in images.items():
        for line in lines:
            if line.startswith("![") and line.endswith("](" + name + ")"):
                body = body.replace(
                    "<p>" + html.escape(line) + "</p>", "<figure>" + raw.decode() + "</figure>"
                )
    doc = (
        '<!doctype html><meta charset="utf-8"><title>S6 Origin-aware forecast</title>'
        "<style>body{max-width:1440px;margin:24px auto;padding:0 20px;font:14px system-ui;"
        "color:#243247;overflow-wrap:anywhere}h2{margin-top:40px}p,li{line-height:1.6}"
        "table{border-collapse:collapse;width:100%;font-size:12px}"
        "td{border:1px solid #d6dfeb;padding:6px;min-width:75px}"
        "tr:first-child{background:#edf2f7;font-weight:600}"
        ".scroll{overflow-x:auto;max-width:100%}"
        "pre{white-space:pre-wrap;background:#f3f6fa;padding:12px;font-size:11px}"
        "figure{margin:20px 0}svg{display:block;width:100%;height:auto}</style>" + body
    )
    c["actual_daily"] = {}
    for e, mm in run["actual"].items():
        permitted = {
            (m["base_id"], str(date.fromisoformat(m["target_start"]) + timedelta(days=i)))
            for m in run["predictions"]["experiments"][e]["members"]
            for i in range(7 if m["window"] == "H7_PREFIX" else 15)
        }
        c["actual_daily"][e] = [
            {"base_id": b, "date": str(r.day), "kg": str(r.kg)}
            for b, rr in mm.items()
            for r in rr
            if (b, str(r.day)) in permitted
        ]
    return {
        "dynamic-comparison.json": canonical_bytes(old.compact(c)),
        "report.md": md.encode(),
        "report.html": doc.encode(),
        **images,
    }
