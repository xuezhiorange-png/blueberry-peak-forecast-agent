"""Safe business projections of canonical saved runs; no forecast arithmetic."""

import csv
import io
import json
import re
from html import escape
from typing import Any, Literal

from backend.app.rolling_forecast.source_readiness import public_name


def text(value: Any) -> str:
    return escape(str(value), quote=True)


def csv_text(value: Any) -> str:
    rendered = str(value)
    return (
        "'" + rendered
        if rendered.lstrip(" \t\r\n\ufeff").startswith(("=", "+", "-", "@"))
        else rendered
    )


def export_report(
    run: dict[str, Any], kind: Literal["html", "csv"], comparison: dict[str, Any] | None = None
) -> dict[str, Any]:
    if comparison and (comparison["left_run"], comparison["left_result_hash"]) != (
        run["run_id"],
        run["result_hash"],
    ):
        raise ValueError("REPORT_IDENTITY_MISMATCH")
    result = run["result"]
    source = run["input"]["observation_snapshot"]
    synthetic = source["provenance"] == "SYNTHETIC_TEST_FIXTURE"
    notice = "合成示例，不代表实际产量" if synthetic else "研究 Shadow，未经前瞻性准确率验证"
    # Whitelist public identity. Never serialize inputs, private paths or parameters.
    identity = dict(run_id=run["run_id"], result_hash=run["result_hash"], origin=run["origin_date"])
    rows, sections = [], []
    for name, model in result["models"].items():
        h7, h15 = model.get("H7") or {}, model.get("H15") or {}
        compared_model = comparison["models"][name] if comparison else None
        common = (
            {d["date"]: d["kg"] for d in compared_model["common_target_daily_delta_kg"]}
            if compared_model is not None and compared_model["status"] == "COMPARABLE"
            else {}
        )
        public = dict(
            model=name,
            model_id=model["model_id"],
            status=model["status"],
            forecast_target_quantity_basis=model.get("forecast_target_quantity_basis"),
            model_training_target_quantity_basis=model.get("model_training_target_quantity_basis"),
            H7=h7,
            H15=h15,
            reasons=model.get("blocker_reason") or [],
        )
        daily = model["daily_forecast_kg"]
        for day in daily or [{"date": "", "kg": ""}]:
            rows.append(
                dict(
                    **identity,
                    base_id=run["base_id"],
                    target_season=run["target_season"],
                    model=name,
                    model_id=model["model_id"],
                    status=model["status"],
                    blocker_reason=";".join(model.get("blocker_reason") or []),
                    target_date=day["date"],
                    forecast_kg=day["kg"],
                    h7_prefix_total_kg=h7.get("forecast_total_kg", ""),
                    h15_total_kg=h15.get("forecast_total_kg", ""),
                    single_peak_date=h15.get("single_day_peak_date", ""),
                    single_peak_kg=h15.get("single_day_peak_kg", ""),
                    rolling7_start=h15.get("rolling_7day_peak_start", ""),
                    rolling7_end=h15.get("rolling_7day_peak_end", ""),
                    rolling7_cumulative_kg=h15.get("rolling_7day_peak_cumulative_kg", ""),
                    feature_quantity_basis=result["feature_snapshot"]["quantity_basis"],
                    target_quantity_basis=model.get("forecast_target_quantity_basis", ""),
                    source_complete=result["feature_snapshot"]["complete"],
                    source_system=public_name(source["source_system"]),
                    comparison_run_id=comparison["right_run"] if comparison else "",
                    comparison_result_hash=comparison["right_result_hash"] if comparison else "",
                    comparison_origin=comparison["right_origin"] if comparison else "",
                    comparison_status=compared_model["status"]
                    if compared_model
                    else "NOT_REQUESTED",
                    common_target_daily_delta_kg=common.get(day["date"], ""),
                    notice=notice,
                )
            )
        # Coordinates only: all quantities and peaks above come from saved results.
        values = [float(d["kg"]) for d in daily]
        top = max(values, default=0) or 1
        points = " ".join(f"{10 + i * 40},{160 - v / top * 145:.2f}" for i, v in enumerate(values))
        table = "".join(
            f"<tr><td>{text(d['date'])}</td><td>{text(d['kg'])}</td></tr>" for d in daily
        )
        sections.append(
            f"<section><h2>{text(name)} · {text(model['model_id'])}</h2>"
            f"<p>前7日累计：{text(h7.get('forecast_total_kg', '未计算'))} kg；"
            f"15日累计：{text(h15.get('forecast_total_kg', '未计算'))} kg</p>"
            f'<svg role="img" aria-label="15日预测曲线" viewBox="0 0 600 180">'
            f'<polyline fill="none" stroke="#006c67" stroke-width="3" points="{points}"/></svg>'
            f"<p>15日内单日峰：{text(h15.get('single_day_peak_date', '未计算'))} / "
            f"{text(h15.get('single_day_peak_kg', ''))} kg；15日内最高连续7日累计："
            f"{text(h15.get('rolling_7day_peak_cumulative_kg', '未计算'))} kg，"
            f"{text(h15.get('rolling_7day_peak_start', ''))} 至 "
            f"{text(h15.get('rolling_7day_peak_end', ''))}</p>"
            "<table><thead><tr><th>目标日期</th><th>预测 kg</th></tr></thead>"
            f"<tbody>{table}</tbody></table>"
            "<details><summary>模型与状态</summary><pre>"
            f"{text(json.dumps(public, ensure_ascii=False, indent=2))}</pre></details></section>"
        )
    if kind == "csv":
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(
            {
                k: str(v)
                if k == "common_target_daily_delta_kg" and re.fullmatch(r"-?\d+\.\d{6}", str(v))
                else csv_text(v)
                for k, v in row.items()
            }
            for row in rows
        )
        content, mime, filename = (
            "\ufeff" + output.getvalue(),
            "text/csv;charset=utf-8",
            "forecast-daily.csv",
        )
    else:
        compared = ""
        if comparison:
            compared = "<section><h2>Origin 对比 / 共同目标日期</h2>"
            compared += (
                f"<p>{text(comparison['left_origin'])} → {text(comparison['right_origin'])}</p>"
            )
            compared += "<p>窗口累计变化覆盖不同日期；共同日期变化单列。不可比较时不输出差值。</p>"
            for name, value in comparison["models"].items():
                compared += f"<h3>{text(name)} · {text(value['status'])}</h3>"
                if value["status"] != "COMPARABLE":
                    compared += f"<p>{text('；'.join(value['reasons']))}</p>"
                    continue
                for window, metrics in value["windows"].items():
                    compared += (
                        f"<p>{text(window)} 不同窗口累计变化 {text(metrics['total_delta_kg'])} kg；"
                        f"单日峰移动 {text(metrics['single_peak_date_delta_days'])} 日；"
                        f"峰量变化 {text(metrics['single_peak_kg_delta'])} kg；"
                        f"七日峰起点移动 {text(metrics['rolling7_start_delta_days'])} 日；"
                        f"累计变化 {text(metrics['rolling7_kg_delta'])} kg。</p>"
                    )
                compared += "<table><caption>共同目标日期预测修正</caption>"
                compared += "<tr><th>日期</th><th>后者 − 前者 kg</th></tr>"
                for d in value["common_target_daily_delta_kg"]:
                    compared += f"<tr><td>{text(d['date'])}</td><td>{text(d['kg'])}</td></tr>"
                compared += "</table>"
            compared += "<details><summary>比较身份</summary><pre>"
            compared += (
                text(
                    json.dumps(
                        {
                            k: comparison[k]
                            for k in (
                                "left_run",
                                "right_run",
                                "left_result_hash",
                                "right_result_hash",
                                "comparison_hash",
                            )
                        },
                        indent=2,
                    )
                )
                + "</pre></details></section>"
            )
        content = (
            '<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
            "style-src 'unsafe-inline'; img-src data:\"><title>滚动预测业务报告</title>"
            "<style>body{font:16px system-ui;max-width:960px;margin:auto;padding:20px;"
            "color:#183333}section{border-top:1px solid #ccc;margin-top:24px}"
            "table{border-collapse:collapse;width:100%}td,th{padding:8px;"
            "border-bottom:1px solid #ddd;text-align:left}"
            "pre{white-space:pre-wrap;overflow-wrap:anywhere}"
            "svg{max-width:100%;width:600px}</style>"
            + f"<h1>滚动预测业务报告</h1><p>{text(notice)}</p>"
            + f"<p>基地：{text(run['base_id'])}；产季：{text(run['target_season'])}；"
            + f"Origin：{text(run['origin_date'])}</p>"
            + f"<p>来源：{text(public_name(source['source_system']))}</p>"
            + f"<p>特征数量口径：{text(result['feature_snapshot']['quantity_basis'])}；"
            + f"观测完整：{text(result['feature_snapshot']['complete'])}</p>"
            + "<p>入库记录重量不等于田间采收量。高峰限于本次预测窗口；STRICT_PIT=false。"
            + "未执行实际标签评分，不证明生产预测准确率。</p>"
            + "".join(sections)
            + compared
            + "<details><summary>保存身份</summary><pre>"
            + f"{text(json.dumps(identity, indent=2))}</pre></details></html>"
        )
        mime, filename = "text/html;charset=utf-8", "forecast-report.html"
    return dict(
        **identity,
        comparison_run_id=comparison["right_run"] if comparison else None,
        comparison_result_hash=comparison["right_result_hash"] if comparison else None,
        filename=filename,
        mime=mime,
        content=content,
    )
