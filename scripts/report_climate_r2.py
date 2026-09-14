"""Render the review-only climate study pack from hash-verified private artifacts."""

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from scripts.climate_source_r2 import file_hash, write_json


def render(root: Path, replay: Path, source_root: Path, output: Path) -> None:
    manifest = json.loads((root / "artifact-manifest.json").read_text())
    if json.loads((replay / "artifact-manifest.json").read_text()) != manifest:
        raise ValueError("STUDY_REPLAY_MISMATCH")
    for name, sha in manifest["file_hashes"].items():
        if file_hash(root / name) != sha or file_hash(replay / name) != sha:
            raise ValueError("STUDY_ARTIFACT_CHANGED")
    profiles = json.loads((root / "base-climate-profile-v1.json").read_text())
    result = json.loads((root / "candidate-study.json").read_text())
    source = json.loads((root / "climate-source-snapshot-manifest.json").read_text())
    ids_path = source_root / "cds-request-id-supplement.json"
    ids = json.loads(ids_path.read_text())
    zones = json.loads((root / "candidate-zone-profile.json").read_text())
    rows = list(csv.DictReader((root / "base-climate-profile-v1.csv").open()))
    selected = result["selected"]
    shifts = [
        p["canonical_base_name"]
        for i, p in enumerate(profiles)
        if result["baseline_labels"][i] != result["recent_labels"][i]
    ]
    severity = dict(Counter(p["drift_severity"] for p in profiles))
    common = (
        "\n本报告只提出候选，不建立生产气候区 authority，不开启 S2。"
        "BASE_REGISTRY_V1 及 R2 alias authority 保持不变。"
        "不使用采摘量、亩产、面积、峰值或预测误差。\n"
    )
    source_rows = "\n".join(
        f"| {f['file']} | {len(f['months'])} | {f['sha256']} |" for f in source["files"]
    )
    audit = (
        f"""# S1 R2 climate source audit

TASK_ID=V0_5_S1_CLIMATE_PROFILE_AND_YUNNAN_ZONE_STUDY_R2

Base main: `7de37a0db5fdfef1504582090825483d7c97c52f`.
Registry: `{manifest["registry_hash"]}`. Frozen S1 input hashes verified before study.
Source: ERA5-Land monthly means, CDS dataset `reanalysis-era5-land-monthly-means`.
[Official catalogue](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land-monthly-means)
and frozen catalogue/constraints both show 2026-08, not inferred from today's month.
Purpose: LONG_TERM_AND_RECENT_CLIMATE_PROFILE_RESEARCH; not operational weather authority.

Minimal NetCDF: 25,176 bytes; SHA256
`d68c66bd3ac33099811dee8f996ac6dd1332777057c1f854f12389dc52e51f37`.
It was fully loaded: 2020-01; t2m in K; 21×21 points; CF-1.7; ECMWF.
User-provided minimal request ID: `e7b4ca5e-a4da-452c-ad4c-50af07c334c8`.
No credentials are included in code, requests or evidence.

## Raw snapshot gate and offline replay

All five original NetCDF files fully readable. Four variables each have exactly 428 ordered
monthly observations, no duplicates/missing months, finite values on the entire downloaded grid.
1991–2020=360, 1996–2025=360, 2021–2025=60, 2026 Jan–Aug=8 **for each variable**.
Source gate and separate replay with socket connections disabled both PASS, before profiling.
Snapshot hash: `{source["hash"]}`.

| Raw file | Months | SHA256 |
|---|---:|---|
{source_rows}

Private root: `blueberry-area-yield-artifacts/climate-zone-r2-source`.
Every request, receipt, variable metadata, size, timestamp and original file is retained.
The completed-results object did not expose a request_id attribute. Original receipts retain null.
An append-only supplement recovered all five successful job IDs by exact request equality from
the CDS jobs API, without another retrieval. Supplement SHA256: `{file_hash(ids_path)}`.
Job IDs: {", ".join(item["request_id"] for item in ids)}.

## Units and extraction

[ERA5-Land monthly accumulation documentation](https://confluence.ecmwf.int/pages/viewpage.action?pageId=177471794)
establishes that moda accumulation values have an effective daily period.
Actual file units: t2m/d2m=K, tp=m, ssrd=J m**-2. Conversion:

- temperatures: K − 273.15;
- precipitation: daily-mean accumulation ×1000×actual calendar days → monthly mm;
- radiation: daily-mean energy ×actual calendar days/1e6 → monthly MJ/m²;
- moisture: day-weighted temperature minus dewpoint, in °C; no nonlinear VPD proxy asserted.

Nearest 0.1° cell, tie to lower coordinate; no interpolation. Every profile records selected
grid coordinates and haversine distance (Earth radius 6371.0088 km).
Canonical coordinates unchanged:
`SOURCE_CRS_UNCONFIRMED_WGS84_QUERY_ASSUMPTION`; DEM elevation still requires CRS review.
VPD, GDD, chilling, frost, heat-stress and ET0 are explicitly deferred, never imputed.
"""
        + common
    )
    candidate_rows = "\n".join(
        f"| {s['method']} | {s['k']} | {s['sizes']} | {s['silhouette']:.4f} | "
        f"{s['calinski_harabasz']:.3f} | {s['davies_bouldin']:.4f} | "
        f"{s['method_ari']:.4f} | {s['resample_ari_mean']:.4f} | "
        f"{s['coordinate_agreement']:.4f} | {s['eligible']} |"
        for s in result["scores"]
    )
    zone_text = "\n\n".join(
        f"### Z{z['zone'] + 1}: {z['descriptive_label']}\n\n"
        f"基地数：{z['base_count']}；成员：{'、'.join(z['members'])}。\n\n"
        f"地理范围：{json.dumps(z['geography'], ensure_ascii=False)}。\n\n"
        + "\n".join(
            f"- {k}: min/median/max = {v['min']:.3f}/{v['median']:.3f}/{v['max']:.3f}"
            for k, v in z["climate"].items()
        )
        for z in zones
    )
    study_doc = (
        f"""# 云南气候分区候选研究 R2

推荐：{selected["method"]}，K={selected["k"]}；仅待评审候选，不是预设五分区。
38 个 YUNNAN_CORE 基地等权；1 个外省基地保留登记、不拟合。

## 冻结方法与选择规则

配置：`configs/climate_zone_r2.json`，在首次画像/聚类运行前写入。
主时段1991–2020；种子42；K-means n_init=20；Ward 欧氏距离；单线程数值运算。
紧凑特征：{", ".join(result["features"])}。
按优先级排除 |Pearson r|≥0.9 的冗余变量：{json.dumps(result["exclusions"], ensure_ascii=False)}。
完整相关矩阵、各候选方差比和标准化参数保存在 candidate-study.json，不加面积权重。
温度为按日数加权的多年平均；降水/辐射为完整年累计的多年均值。
季节性为12个月降水气候值的总体SD/均值；暖季固定May–Oct，不声称农业季节阈值。

门槛：每组≥3基地、30次80%无放回重采样平均ARI≥0.75、坐标一致率≥0.9、
两方法ARI≥0.6。通过后等权秩综合 silhouette、DB、重采样、坐标一致率、
海拔/温度/降水组内方差比；不单看最高分。重采样拟合后用最近质心扩展至全38基地。
这不是置信区间或外部泛化证明。唯一通过预设门槛的候选为 K-means K=5。

| 方法 | K | 组大小 | Silhouette | CH | DB | 方法ARI | 重采样均值ARI | 坐标一致率 | 资格 |
|---|---:|---|---:|---:|---:|---:|---:|---:|---|
{candidate_rows}

## 稳定性与限制

推荐候选重采样最差ARI={selected["resample_ari_min"]:.4f}，均值仅略高于门槛；
不能表述为强稳定或已批准分区。高K出现单例/小组，低K重采样不稳定。
1996–2025沿用K、特征、标准化方法和算法，不重新选K；标签以最大重叠匹配消除任意编号影响。
一致率={result["temporal_agreement"]:.6f}，变化基地：{"、".join(shifts)}。
38/38在±0.01°八个偏移位置下候选区不变；这不证明CRS已确认或气候值完全不变。
最近质心是Ward外样本诊断规则，不伪装成Ward原生predict。
没有行政区特征/边界约束；簇允许地理不连续，地理范围和气候统计供人工解释性评审。

## 候选区画像

{zone_text}
"""
        + common
    )
    columns = [
        "canonical_base_name",
        "elevation_m",
        "baseline_annual_mean_temperature_c",
        "baseline_annual_precipitation_mm",
        "recent_annual_mean_temperature_c",
        "recent_annual_precipitation_mm",
        "temperature_30y_shift_c",
        "precipitation_30y_shift_mm",
        "drift_temperature_c",
        "drift_precipitation_mm",
        "ytd_temperature_c",
        "ytd_precipitation_mm",
        "baseline_zone",
        "recent_zone",
        "zone_temporal_stability",
        "coordinate_status",
    ]

    def cell(row: dict[str, Any], col: str) -> str:
        if col in ("baseline_zone", "recent_zone"):
            return "Z" + str(int(row[col]) + 1)
        try:
            return f"{float(row[col]):.3f}"
        except ValueError:
            return str(row[col])

    table = "| " + " | ".join(columns) + " |\n|" + "---|" * len(columns) + "\n"
    table += "\n".join("| " + " | ".join(cell(row, c) for c in columns) + " |" for row in rows)
    review = "# 气候区候选评审包 R2\n\n"
    review += (
        "基准=1991–2020；recent=1996–2025；drift=2021–2025对基准；"
        "YTD=2026 Jan–Aug对基准同月份。温度°C、降水mm。"
        "Z编号仅展示层+1，私有机器产物从0开始。\n\n"
    )
    review += (
        table + "\n\n需要评审：低重采样稳定性、三基地近期迁区、坐标/DEM caveat及各区地理合理性。"
        "只有后续明确授权才能冻结。\n" + common
    )
    drift_doc = (
        f"""# 气候漂移与2026年内诊断 R2

四个时段分别保存，没有用2026不完整年份替代30年气候值。
1996–2025与1991–2020为两个完整360月窗口；2021–2025为60月。
2026 Jan–Aug仅与每个基准年份Jan–Aug统计的多年平均比较，不年化、不与全年比较。
2021–2025降水百分比异常分母为1991–2020年降水；未给YTD冠以“全年缺水”。

漂移强度用温度/降水年异常除以基准30年的年际样本标准差，取两者绝对值最大：
<1 LOW、<2 MODERATE、其余HIGH。这是描述性标准差分档，不是农业风险或显著性检验。
基地数：{json.dumps(severity, ensure_ascii=False)}。
不因5年异常移动基地，也不使用2026诊断重新选择K。
逐基地全部变化见 [评审表](yunnan-climate-zone-review-pack.md)。
湿度只报告露点差，辐射为MJ/m²；两个指标均保留相同时段和同月对比。
"""
        + common
    )
    output.mkdir(parents=True, exist_ok=True)
    for name, text in {
        "climate-profile-source-audit.md": audit,
        "yunnan-climate-zone-candidate-study.md": study_doc,
        "yunnan-climate-zone-review-pack.md": review,
        "climate-drift-review.md": drift_doc,
    }.items():
        with (output / name).open("x", encoding="utf-8") as stream:
            stream.write(text)
    evidence = {
        "task_id": "V0_5_S1_CLIMATE_PROFILE_AND_YUNNAN_ZONE_STUDY_R2",
        "base_main_sha": "7de37a0db5fdfef1504582090825483d7c97c52f",
        "registry_hash": manifest["registry_hash"],
        "source_hash": source["hash"],
        "artifact_manifest": manifest,
        "source_gate": "PASS",
        "offline_source_replay": "PASS",
        "study_replay": "PASS",
        "population": 38,
        "out_of_yunnan_excluded": 1,
        "candidate_k": list(range(3, 9)),
        "selected": selected,
        "recommendation_status": result["recommendation_status"],
        "temporal_agreement": result["temporal_agreement"],
        "recent_shift_bases": shifts,
        "coordinate_stable": sum(
            r["status"] == "LOCATION_SENSITIVITY_STABLE" for r in result["coordinate_sensitivity"]
        ),
        "drift_counts": severity,
        "climate_zone_mapping_frozen": False,
        "climate_zone_profile_authority_frozen": False,
        "yield_features_used": False,
        "harvest_features_used": False,
        "area_weights_used": False,
        "forecast_model_changed": False,
        "database_changed": False,
        "mcp_changed": False,
        "ready_authorized": False,
        "merge_authorized": False,
        "private_artifact_directory": "blueberry-area-yield-artifacts/" + root.name,
        "request_id_supplement_hash": file_hash(ids_path),
        "request_ids": ids,
    }
    write_json(output / "climate-zone-evidence.json", evidence)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--replay", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    render(args.artifacts, args.replay, args.source, args.output)
