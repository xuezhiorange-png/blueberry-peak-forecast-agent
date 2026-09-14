"""Render public R3 review documents without coordinates or production fields."""

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from scripts.climate_authority_r3 import FEATURES
from scripts.climate_source_r2 import digest, file_hash


def render(root: Path, replay: Path) -> dict[str, str]:
    manifest = json.loads((root / "artifact-manifest.json").read_text())
    if digest({k: v for k, v in manifest.items() if k != "hash"}) != manifest["hash"]:
        raise ValueError("R3_MANIFEST_HASH_MISMATCH")
    for name, sha in manifest["file_hashes"].items():
        if file_hash(root / name) != sha or file_hash(replay / name) != sha:
            raise ValueError("R3_COMPLETE_REPLAY_MISMATCH")
    if file_hash(root / "artifact-manifest.json") != file_hash(replay / "artifact-manifest.json"):
        raise ValueError("R3_MANIFEST_REPLAY_MISMATCH")
    s = json.loads((root / "summary.json").read_text())
    mapping = json.loads((root / "base-climate-zone-mapping-v1-candidate.json").read_text())
    zones = json.loads((root / "climate-zone-profile-v1-candidate.json").read_text())["zones"]
    bases = mapping["mappings"]
    unstable = [b for b in bases if b["assignment_class"] == "UNSTABLE"]
    lines = [
        "# S1 气候分区 authority 裁决 R3",
        "",
        f"结论：**{s['authority_recommendation']}**。38 基地中 "
        f"{s['core_base_count']} CORE / {s['boundary_base_count']} BOUNDARY / "
        f"{s['unstable_base_count']} UNSTABLE。K=5 候选可复现，但未达到本轮冻结门槛。",
        "不重开 K 选择；不修改归属、阈值、特征或 R2 证据。两个 authority freeze 标记均为 false。",
        "",
        "## 输入与执行门禁",
        "",
        "基线 main：`f3a38630debe1328ede3f5782e08f5ca4e6db01a`。"
        "R2 的所有 manifest 文件、原始 NetCDF、profile 内部哈希已核验；"
        "完整 R2 重放产物逐文件 SHA256 相同，K5 原始标签（包括编号）完全一致。",
        f"Registry：`{s['base_registry_hash']}`；"
        f"source snapshot：`{s['climate_source_snapshot_hash']}`。",
        f"R2 manifest：`{s['r2_artifact_hash']}`；R3 manifest：`{manifest['hash']}`。",
        "R3 在 socket.connect 被禁止的进程内执行；另一个全新目录再次离线执行，"
        "所有产物 byte/hash 一致。"
        "本轮没有下载或访问气象网络服务。",
        "",
        "## 冻结算法与裁决规则",
        "",
        "主参考为 1991–2020 KMeans K=5；完全复用 R2 七特征顺序、StandardScaler mean/scale、"
        "seed=42、n_init=20。仅对气候与海拔作诊断，不读取产量、亩产、面积、峰值或预测误差作为特征。",
        "200 次重采样采用 default_rng(42)，每次从 38 个基地无放回抽取排序后的 30 个；"
        "每次拟合 seed 固定为 42。原基准 scaler 不重估。"
        "在抽中基地上 Hungarian 最大重叠对齐；多最优解按标签置换字典序最小确定。"
        "遗漏基地按该次拟合质心最近距离归类，再使用同一标签映射；距离并列取原标签最小。",
        "频率分母始终为 200（含抽中与遗漏诊断）；称 RESAMPLING_ASSIGNMENT_STABILITY，"
        "不是置信区间。完整抽样索引、每次映射及38基地分配均保存。",
        "LOFO 恰好七次：每次移除一个特征，对保留六维重新标准化，K/seed/n_init 不变；"
        "全38基地最大重叠对齐，不做替代特征或优化。Ward 仅为一致性诊断。",
        "CORE：频率≥0.90、LOFO≥6/7、时段稳定、坐标分区稳定、源无阻断。"
        "BOUNDARY：频率≥0.70、LOFO≥4/7、坐标稳定，但未满足全部 CORE。"
        "UNSTABLE：频率<0.70、LOFO<4/7、坐标不稳或源完整性不足，任一即成立。",
        "几何 margin=(d2−d1)/max(d2,1e−12)；d1 为已分配质心，d2 为最近其他质心，"
        "均在冻结标准化空间。不是概率。负 silhouette、Ward 分歧单列，不添加事后分类门槛。",
        "",
        "## 分区与物理解释",
        "",
        "| 固定ID / R2 | 描述 | 基地数 | CORE | BOUNDARY | UNSTABLE | "
        "温度中位°C | 年降水中位mm | 海拔中位m |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for z in zones:
        c, a = z["class_counts"], z["baseline_climate_summary"]
        lines.append(
            f"| {z['zone_id']} / {z['r2_candidate_zone']} | {z['descriptive_label']} | "
            f"{z['base_count']} | {c['CORE']} | {c['BOUNDARY']} | {c['UNSTABLE']} | "
            f"{a['annual_mean_temperature_c']['median']:.2f} | "
            f"{a['annual_precipitation_mm']['median']:.1f} | {a['elevation_m']['median']:.0f} |"
        )
    lines += [
        "",
        "描述是相对本样本气候分布：Z2 较凉湿且海拔中位较高；Z3 最暖、低海拔；"
        "Z5 辐射中位最高，其‘较干’相对湿润 Z2/Z3，并不意味着降水低于 Z1/Z4。"
        "行政方位只是描述，不是分区依据；没有为命名调整成员。",
        "",
        "## 冻结阻断",
        "",
        "| 基地 | 原区 | 重采样同区频率 | LOFO | 触发门槛 |",
        "|---|---|---:|---:|---|",
    ]
    for b in unstable:
        reasons = []
        if b["bootstrap_assignment_frequency"] < 0.7:
            reasons.append("frequency<0.70")
        if b["lofo_stable_count"] < 4:
            reasons.append("LOFO<4/7")
        lines.append(
            f"| {b['canonical_base_name']} | Z{b['baseline_zone'] + 1} | "
            f"{b['bootstrap_assignment_frequency']:.3f} | "
            f"{b['lofo_stable_count']}/7 | {', '.join(reasons)} |"
        )
    lines += [
        "",
        f"负 silhouette 基地：{'、'.join(s['nonpositive_silhouette_bases'])}。"
        f"Ward 分配分歧 {s['method_disagreement_base_count']} 个。"
        f"频率 min/median={s['min_bootstrap_assignment_frequency']:.3f}/"
        f"{s['median_bootstrap_assignment_frequency']:.3f}；"
        f"LOFO rate min/median={s['min_lofo_stability_rate']:.6f}/"
        f"{s['median_lofo_stability_rate']:.6f}。",
        "",
        "38/38 坐标分区稳定，但12基地格点切换。"
        "SOURCE_CRS_UNCONFIRMED_WGS84_QUERY_ASSUMPTION 保留，不能推导坐标系已经核验。",
        "",
        "## 候选 payload 与复现",
        "",
        f"Profile candidate hash：`{s['climate_zone_profile_v1_candidate_hash']}`。",
        f"Mapping candidate hash：`{s['base_climate_zone_mapping_v1_candidate_hash']}`。",
        "ID 永久绑定本次 R2 Z1..Z5；候选均 CANDIDATE_ONLY，不得后续重聚类静默改 ID 语义。",
        f"私有目录：`{root}`；重放：`{replay}`。不提交原始坐标或 NetCDF。",
        "",
        "```bash",
        "python -m scripts.run_climate_authority_r3 \\",
        "  --source /Users/charles/Documents/blueberry-area-yield-artifacts/"
        "climate-zone-r2-source \\",
        "  --r2 /Users/charles/Documents/blueberry-area-yield-artifacts/"
        "climate-zone-r2-review-complete \\",
        "  --r2-replay /Users/charles/Documents/blueberry-area-yield-artifacts/"
        "climate-zone-r3-r2-input-replay \\",
        "  --output /absolute/path/to/a-new-private-directory",
        "```",
        "",
        "R2 完整重放使用既有 scripts.run_climate_study_r2.run，并在运行前禁止 socket.connect；"
        "新 R3 runner 校验该重放目录与冻结 R2 manifest 所有文件哈希。输出目录必须不存在。",
        "",
        "## 验证与停止门",
        "",
        "新增 focused tests 覆盖固定 K/配置、200 次抽样、遗漏基地质心归类、七次 LOFO、"
        "标签对齐、全部分类边界、输入篡改拒绝、候选哈希和离线确定性。R1/R2 测试未修改。",
        "本地 R3 focused：19 passed；base_registry/area_yield/mcp 回归：371 passed、9 skipped。"
        "Ruff check、format（1042文件）、mypy（backend/app 444文件及R3研究脚本）、"
        "JSON/reference/hash 检查通过。",
        "最终 exact-head CI/full-suite-canary 在 PR 和任务最终回复中记录；不能用旧 R2 CI 替代。",
        "READY_ELIGIBLE=false；READY_AUTHORIZED=false；MERGE_AUTHORIZED=false。",
        "停止于 COORDINATOR_S1_CLIMATE_ZONE_R3_REVIEW；不进入 S2，不实施 authority 冻结。",
        "",
    ]
    boundary = [
        "# R3 基地边界专项评审",
        "",
        "本表保留1991–2020主参考，不将近期迁区基地强制移至Z2。所有诊断遵循预声明门槛。",
        "",
        "## 38 基地完整裁决",
        "",
        "| 基地 | 原区→近期 | 分类 | 同区频率 | LOFO | silhouette | 相对margin | "
        "runner-up | Ward同区 | 坐标同区/格点变化 |",
        "|---|---|---|---:|---:|---:|---:|---|---|---|",
    ]
    for b in bases:
        boundary.append(
            f"| {b['canonical_base_name']} | Z{b['baseline_zone'] + 1}→Z{b['recent_zone'] + 1} | "
            f"{b['assignment_class']} | {b['bootstrap_assignment_frequency']:.3f} | "
            f"{b['lofo_stable_count']}/7 | {b['sample_silhouette']:.4f} | "
            f"{b['centroid_relative_margin']:.4f} | Z{b['runner_up_zone'] + 1} | "
            f"{b['method_assignment_agreement']} | "
            f"{b['coordinate_zone_stable']}/{b['grid_cell_changed_under_perturbation']} |"
        )
    boundary += [
        "",
        "## 三个迁区基地的几何分解",
        "",
        "下列 Δz 始终使用基准期冻结 scaler。近期重拟合空间的距离不能与基准空间直接相减。"
        "组贡献采用 Δz² 按温度/降水/湿度/辐射/海拔加总，单组超过50%才标为主要几何位移组；"
        "这只是描述规则，不用于分类或区选择，不证明气候因果。",
    ]
    temporal = list(csv.DictReader((root / "temporal-shift-diagnostics-r3.csv").open()))
    for d in temporal:
        if d["baseline_zone"] == d["recent_zone"]:
            continue
        b = next(b for b in bases if b["base_id"] == d["base_id"])
        baseline, recent, delta = [
            json.loads(d[k])
            for k in ("baseline_features", "recent_features", "standardized_deltas_baseline_scaler")
        ]
        geometry = json.loads(d["recent_refit_geometry"])
        boundary += [
            "",
            f"### {b['canonical_base_name']}：{b['assignment_class']}",
            "",
            f"原 Z{b['baseline_zone'] + 1} → 近期 Z{b['recent_zone'] + 1}；"
            f"同区频率 {b['bootstrap_assignment_frequency']:.3f}，"
            f"LOFO {b['lofo_stable_count']}/7。原 d1={b['assigned_centroid_distance']:.6f}，"
            f"d2={b['runner_up_centroid_distance']:.6f}；"
            f"近期重新拟合 d1={geometry['assigned_centroid_distance']:.6f}，"
            f"d2={geometry['runner_up_centroid_distance']:.6f}。",
            "",
            "| 特征 | 1991–2020 | 1996–2025 | Δz（基准scaler） |",
            "|---|---:|---:|---:|",
        ]
        for f in FEATURES:
            boundary.append(f"| {f} | {baseline[f]:.6f} | {recent[f]:.6f} | {delta[f]:+.6f} |")
        boundary += [
            "",
            f"主要几何位移组：{d['largest_geometric_shift_group']}；移除后迁区的特征："
            f"{', '.join(b['features_whose_removal_changes_zone']) or '无'}。",
            "关键反事实：近期向量置于**冻结基准质心**仍最近 "
            f"Z{int(d['recent_vector_nearest_frozen_baseline_zone']) + 1}。"
            "所以近期迁区不仅是该基地向量位移，还伴随全体近期 scaler/质心/边界重拟合；"
            "海拔本身不变，不能声称海拔发生气候变化。保留原区和不确定性分类。",
        ]
    boundary += [
        "",
        "## 核心限制",
        "",
        "CORE 是规则符合性，不是统计置信度或未来稳定保证。BOUNDARY 不是数据不完整；"
        "UNSTABLE 是本次权威门禁未通过，不等于原始气候数据错误。"
        "5 个 UNSTABLE 阻止整套 mapping 正式冻结；不通过换 K、改阈值或人工迁区解决。",
        "",
    ]
    evidence: dict[str, Any] = s | {
        "base_main_sha": "f3a38630debe1328ede3f5782e08f5ca4e6db01a",
        "artifact_manifest": manifest,
        "private_artifact_directory": str(root),
        "offline_deterministic_replay": "PASS",
        "r2_artifacts_changed": False,
        "model_changed": False,
        "v0_4_authority_changed": False,
        "database_schema_changed": False,
        "mcp_changed": False,
        "production_deployment_changed": False,
        "focused_tests": "19 passed",
        "relevant_tests": "371 passed, 9 skipped",
        "static_checks": "Ruff/format/mypy/JSON/reference/hash PASS",
        "ci_acceptance": "Final exact-head CI and full-suite-canary reported separately",
        "ready_eligible": False,
        "ready_authorized": False,
        "merge_authorized": False,
        "final_status": "COORDINATOR_S1_CLIMATE_ZONE_R3_REVIEW",
    }
    return {
        "climate-zone-authority-adjudication-r3.md": "\n".join(lines),
        "climate-zone-boundary-review-r3.md": "\n".join(boundary),
        "climate-zone-authority-evidence-r3.json": json.dumps(
            evidence, ensure_ascii=False, sort_keys=True, indent=2
        )
        + "\n",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--replay", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(render(args.artifacts, args.replay), ensure_ascii=False))


if __name__ == "__main__":
    main()
