"""Static, escaped, quantity-free business reports; never modify input evidence."""

import csv
import html
import json
from pathlib import Path
from typing import Any

STATUS = {
    "COMPLETE": "完整",
    "CONFIRMED_ZERO": "有权威的零值",
    "MISSING": "缺失",
    "PARTIAL": "成员或记录不完整",
    "LATE": "晚到",
    "CONFLICT": "冲突",
    "UNKNOWN": "未知",
    "METADATA_VALID": "元数据结构有效；日记录尚未证明",
    "SYNTHETIC_FULL_VALIDATED": "合成来源完整校验通过；不代表真实来源获批",
    "INCOMPLETE": "输入不完整，M1 不可计算",
    "BLOCKED": "检查被阻断，请补齐材料或修正合成输入",
    "PENDING_SOURCE_AUTHORITY": "真实来源权威待核验",
    "NOT_PROVEN": "未证明（未读取日重量）",
    "COMPUTABLE": "合成来源的 M1 特征可计算；仍须运行时加载器验证模型",
    "NOT_COMPUTABLE": "M1 不可计算；不能用 M0 冒充",
}
WINDOWS = {
    "past_7d_harvest_kg": "最近 7 日",
    "past_14d_harvest_kg": "最近 14 日",
    "past_28d_harvest_kg": "最近 28 日",
    "season_to_date_harvest_kg": "产季累计至 D−1",
}
REASONS = {
    "MISSING_DAY_INDEX": "缺少该日期的来源索引",
    "NO_RECORD_WITHOUT_ZERO_AUTHORITY": "没有日记录，也没有确认零值权威；不能补零",
    "PARTIAL_MEMBER_COVERAGE": "基地登记成员未全部覆盖",
    "DAY_TIME_AUTHORITY_MISSING": "缺少该日数据可见时间证明",
    "SOURCE_TIME_UNVERIFIED": "来源记录时间未被可信权威确认",
    "SOURCE_TIMESTAMP_MISSING": "来源记录或系统接收时间缺失",
    "LATE_SOURCE_RECORD": "来源记录或系统接收晚于指定截止点",
    "LATE_COMPLETENESS_AUTHORITY": "每日完整性证明在截止点之后才可知",
    "SOURCE_COMPLETENESS_AFTER_CUTOFF": "来源完整性权威晚于截止点",
    "DUPLICATE_SOURCE_RECORD": "Logical ID 或 Revision ID 重复；不自行选择新 Winner",
    "SOURCE_CONFLICT": "本日属于冲突记录的影响范围",
    "SOURCE_MEMBER_MISMATCH": "日记录成员不在该基地的精确登记集合",
    "SOURCE_MEMBER_COVERAGE_CONFLICT": "成员覆盖含重复或未登记身份",
    "SOURCE_DAY_IDENTITY_MISMATCH": "日记录的基地、产季、日期或系统身份不一致",
    "SOURCE_SNAPSHOT_HASH_MISMATCH": "来源文件与固定 Hash 不一致",
    "OBSERVATION_SNAPSHOT_IDENTITY_MISMATCH": "索引身份或规范化 Hash 不一致",
    "SOURCE_BASIS_UNVERIFIED": "重量口径、来源证明或冻结 Fit 绑定未通过",
    "REAL_SOURCE_EXECUTION_NOT_AUTHORIZED": "本任务不授权读取真实来源日重量文件",
    "SOURCE_RECORD_SCHEMA_INVALID": "日记录字段或 Decimal kg 不符合 S8 合同",
    "SOURCE_SCHEMA_INVALID": "来源合同字段缺失或类型不合法，不能继续完整验收",
    "DUPLICATE_SOURCE_DAY": "业务日期或日文件索引重复",
    "SOURCE_GRADE_CONFLICT": "纳入品级与剔除品级存在交集",
    "AMBIGUOUS_BASE_MEMBERSHIP": "来源成员重复或对应多个基地，不能猜测映射",
    "READINESS_RUNTIME_PARITY_MISMATCH": "逐日诊断与权威特征缺失审计不一致，禁止放行",
    "SOURCE_GRADE_UNVERIFIED": "存在未登记的品级，不能自动纳入或剔除",
    "AUTHORIZED_ZERO_CONFLICT": "确认零值与实际记录非零量冲突",
    "SOURCE_PATH_UNSAFE": "来源对象路径、权限或文件大小不符合安全合同",
    "SOURCE_OBJECT_UNAVAILABLE": "显式指定的来源对象不可访问",
    "SOURCE_COMPLETENESS_UNKNOWN": "来源声明的完整性未知",
    "SOURCE_COMPLETENESS_PARTIAL": "来源明确为部分数据",
    "NO_COMPLETENESS_AUTHORITY_FOR_DAY": "没有覆盖该日的完整性权威",
    "OUTSIDE_SEASON_SUPPORT": "所需历史日期在显式产季支持范围之外",
    "INCOMPLETE_PRIOR_OBSERVATIONS": "至少一个先验窗口不完整",
    "OBSERVATION_TIME_OR_COMPLETENESS_UNPROVEN": "先验观测时间或完整性未通过，请查看逐日原因",
    "HARVEST_STATE_INCOMPLETE_PRIOR_WINDOW": "所需先验窗口早于产季起点",
}


def explain(code: str) -> str:
    return REASONS.get(code, "请核对该项显式来源合同及对应证明")


def _text(value: object) -> str:
    return html.escape(str(value), quote=True)


def render_html(report: dict[str, Any]) -> str:
    e = _text
    windows = "".join(
        "<tr><th>"
        + e(WINDOWS[key])
        + "</th><td>"
        + str(w["required_count"])
        + "</td><td>"
        + str(w["complete_count"])
        + "</td><td>"
        + str(w["claimed_complete_count"])
        + "</td><td>"
        + e(w["status"])
        + "</td><td>"
        + e("、".join(w["unverified_dates"]) or "无")
        + "</td></tr>"
        for key, w in report["windows"].items()
    )
    daily = "".join(
        "<tr><td>"
        + e(d["business_date"])
        + "</td><td>"
        + e(STATUS.get(d["status"], d["status"]))
        + "</td><td>"
        + str(d["covered_member_count"])
        + "/"
        + str(d["expected_member_count"])
        + "</td><td>"
        + e(d["record_count"] if d["record_count"] is not None else "未读取")
        + "</td><td>"
        + e(d["excluded_record_count"] if d["excluded_record_count"] is not None else "未读取")
        + "</td><td>"
        + "<br>".join(e(c) + "：" + e(explain(c)) for c in d["reasons"])
        + "</td><td>"
        + e("、".join(d["missing_members"]) or "无")
        + "</td></tr>"
        for d in report["daily"]
    )
    materials = "".join(
        "<li><strong>"
        + e(i["title"])
        + "</strong>："
        + e(i["required_fields"])
        + "；材料"
        + ("已填写但未核验" if i["materials_supplied"] else "未提供")
        + "；PENDING_SOURCE_AUTHORITY</li>"
        for i in report["source_requirements"]
    )
    blockers = "".join("<li>" + e(c) + "：" + e(explain(c)) + "</li>" for c in report["blockers"])
    checks = "".join("<li>" + e(k) + "：" + e(v) + "</li>" for k, v in report["checks"].items())
    return (
        """<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<title>入库来源接入准备与质量验收</title><style>
*{box-sizing:border-box}body{margin:0;background:#f3f6f7;color:#162d36;
font:15px/1.65 system-ui,-apple-system,sans-serif;overflow-wrap:anywhere}
main{max-width:1180px;margin:auto;padding:28px}
header,section{background:white;padding:24px;margin:18px 0;border:1px solid #d7e2e5;
border-radius:8px}h1{font-size:27px;margin:0 0 12px}h2{font-size:20px}h3{font-size:17px}
.warning{background:#fff7df;border-left:4px solid #ad791c;padding:14px}
.status{font-weight:700;color:#154c5b}.scroll{overflow:auto}table{width:100%;
border-collapse:collapse;min-width:730px}th,td{border:1px solid #d7e2e5;padding:9px;
text-align:left;vertical-align:top;overflow-wrap:anywhere}th{background:#edf4f6}
code{overflow-wrap:anywhere}li{margin:8px 0}.muted{color:#596d75}
@media(max-width:600px){main{padding:10px}header,section{padding:15px}h1{font-size:23px}}
@media print{body{background:white}main{max-width:none;padding:0}section{break-inside:avoid}}
</style><main><header><p>BLUEBERRY / S9 · 接入准备，不是生产验收</p>
<h1>入库来源接入准备与质量验收</h1><p class="status">"""
        + e(STATUS.get(report["status"], report["status"]))
        + "</p>"
        + (
            "<p>基地 <strong>"
            + e(report["base_id"])
            + "</strong> · 产季 "
            + e(report["season"])
            + " · Origin "
            + e(report["origin"])
            + " · 截止 "
            + e(report["cutoff"])
            + "</p>"
            + "<p>来源 "
            + e(report.get("source_system", "未知"))
            + " · 模式 "
            + e(report["mode"])
            + " · 数据类别 "
            + e(report.get("data_class", "未验证"))
            + "</p>"
            + "<p class='warning'>真实业务使用：未授权。STRICT_PIT：未验证。"
            + "模板完整、Hash 匹配或报告生成均不构成来源授权；合成记录不是真实记录。</p></header>"
            + "<section><h2>预测所需数量及日期口径</h2><p>特征观测口径："
            + e(report["quantity_basis"])
            + "；模型登记目标："
            + e(report["model_training_target_quantity_basis"] or "未证明")
            + "。原始记录重量、毛重、净重与田间采收量不能因名称相似而视为等价。</p>"
            + "<p>业务日期时区："
            + e(report.get("business_timezone", "未证明"))
            + "；截止时间以显式 UTC 时刻记录。</p>"
            + "<p>只检查产季起点至 D−1 的特征日期；预测目标为 D+1…D+15。"
            + "沿用 harvest_kg 特征字段名不等于已验证的田间采收重量。</p>"
            + "<p class='status'>M1 特征："
            + e(STATUS.get(report["m1_feature_readiness"], report["m1_feature_readiness"]))
            + "</p><p>来源证明与模型证明分开：本工具不读取模型参数，也不签发预测。"
            + "冻结模型文件仍须由 S7 加载器独立验证。本检查不读取评价标签。</p><ul>"
            + checks
            + "</ul></section>"
            + "<section><h2>先验窗口完整性</h2><p>元数据预检的“已验证”固定为 0；"
            + "索引声明不能替代日记录验收。"
            + "缺失和未知不补零，不完整 M1 不以 M0 冒充。</p><div class='scroll'><table><thead><tr>"
            + "<th>窗口</th><th>要求日期数</th><th>已验证完整</th>"
            + "<th>索引声明完整</th><th>状态</th><th>未验证或不合格日期</th>"
            + "</tr></thead><tbody>"
            + windows
            + "</tbody></table></div></section>"
            + "<section><h2>阻断项与责任人补充材料</h2><ul>"
            + (blockers or "<li>无合成数据技术阻断；真实来源仍待权威核验。</li>")
            + "</ul><ol>"
            + materials
            + "</ol><p>真实负责人、等价性和成员身份必须由责任人提供，"
            + "程序不自动编造或批准。</p></section>"
            + "<section><h2>逐日补齐清单</h2><p>仅包含日期、条数、原因与脱敏成员；"
            + "不输出原始重量、私有路径或模型参数。</p>"
            + "<p>日记录状态："
            + e("；".join(f"{STATUS[k]} {v} 日" for k, v in report["counts"].items()))
            + "。未读取日记录时，所有日期均为未证明。</p><p>缺少索引 "
            + str(report["index_issue_counts"]["missing_index_days"])
            + " 日；部分成员 "
            + str(report["index_issue_counts"]["partial_member_days"])
            + " 日；时间未证明 "
            + str(report["index_issue_counts"]["unproven_time_days"])
            + " 日。"
            + "</p><div class='scroll'><table><thead><tr>"
            + "<th>业务日</th><th>状态</th><th>成员覆盖</th><th>记录条数</th>"
            + "<th>剔除品级条数</th><th>原因</th><th>缺失成员（脱敏）</th>"
            + "</tr></thead><tbody>"
            + daily
            + "</tbody></table></div></section>"
            + "<footer><p class='muted'>业务摘要 SHA256 <code>"
            + e(report["business_summary_hash"])
            + "</code> · 本地静态报告，无外部脚本或网络请求。</p></footer></main></html>\n"
        )
    )


def new_directory(path: Path) -> Path:
    target = path.absolute()
    if target.exists() or target.is_symlink():
        raise FileExistsError("OUTPUT_DIRECTORY_MUST_BE_NEW")
    trusted_aliases = {Path("/tmp"), Path("/var")}
    if any(p.is_symlink() and p not in trusted_aliases for p in target.parents):
        raise ValueError("OUTPUT_PATH_UNSAFE")
    target = target.resolve()
    target.mkdir(mode=0o700)
    return target


def write_reports(report: dict[str, Any], output_dir: Path) -> None:
    target = new_directory(output_dir)
    for name, text in (
        (
            "readiness-report.json",
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        ),
        ("readiness-report.html", render_html(report)),
    ):
        with (target / name).open("x", encoding="utf-8") as file:
            (target / name).chmod(0o600)
            file.write(text)
    columns = [
        "business_date",
        "status",
        "expected_member_count",
        "covered_member_count",
        "record_count",
        "excluded_record_count",
        "time_status",
        "reasons",
        "reason_details_zh",
        "missing_members",
    ]
    path = target / "daily-readiness.csv"
    with path.open("x", encoding="utf-8-sig", newline="") as file:
        path.chmod(0o600)
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        for day in report["daily"]:
            row = {
                k: "|".join(day[k]) if isinstance(day[k], list) else day[k]
                for k in columns
                if k != "reason_details_zh"
            }
            row["reason_details_zh"] = "；".join(explain(c) for c in day["reasons"])
            writer.writerow(row)
