"""Explicit Owner-controlled S4 real fit/predict -> independent verify -> score."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from decimal import Context, Decimal, localcontext
from pathlib import Path
from typing import Any, cast

from backend.research import v019_accuracy_models as models
from backend.research import v019_accuracy_study as study
from backend.research import v019_owner_replay as owner
from backend.research import v019_real_training as train
from backend.research import v019_research_execution as engine
from backend.research import v019_retrospective_scoring as peaks
from backend.research import v019_synthetic_validation as metrics
from backend.research.v019_daily_curve import DailyKg, canonical_bytes
from backend.research.v019_synthetic_validation import digest

MODE = "OWNER_CONTROLLED_RETROSPECTIVE"
S3 = "v0-19-s3-owner-controlled-replay-r1-CEYrwE"
S4 = "v0-19-s4-accuracy-r1-181d23e3-20261023"
METHODS = ("baseline", "S2", "VOLUME_CALIBRATION_V1", "VOLUME_TIMING_V1")


def code_identity() -> str:
    return digest(
        {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (
                Path(__file__),
                Path(train.__file__),
                Path(models.__file__),
                Path(study.__file__),
            )
        }
    )


def seal(body: dict[str, Any]) -> dict[str, Any]:
    return {"payload": body, "sha256": digest(body)}


def unseal(value: dict[str, Any]) -> dict[str, Any]:
    if set(value) != {"payload", "sha256"} or value["sha256"] != digest(value["payload"]):
        raise ValueError("SEAL_MISMATCH")
    return cast(dict[str, Any], value["payload"])


def validation_members(admission: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for r in admission["inventory"]:
        if r["status"] != "ADMIT" or r["season"] != "2024-2025":
            continue
        start, end = date.fromisoformat(r["start"]), date.fromisoformat(r["end"])
        for n, w in ((7, "H7_PREFIX"), (15, "H15_LOCAL")):
            for i in range((end - start).days - n + 2):
                first = start + timedelta(days=i)
                result.append(
                    {
                        "base_id": r["base_id"],
                        "candidate_id": digest(
                            {
                                "base": r["base_id"],
                                "season": r["season"],
                                "start": str(first),
                                "days": n,
                            }
                        ),
                        "window": w,
                        "target_start": str(first),
                        "target_end": str(first + timedelta(days=n - 1)),
                        "origin": str(first - timedelta(days=1)) + "T23:59:59.999999+08:00",
                        "cutoff": str(first - timedelta(days=1)) + "T23:59:59.999999+08:00",
                    }
                )
    return result


def predict_run(root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    bundle = train.load_training(root)
    a = json.loads(owner.read_bytes(root / S3 / "a/phase-a.json", study.S3_PINS["a/phase-a.json"]))
    content = owner.verify_a(a, "REAL")
    receipt = json.loads(
        owner.read_bytes(
            root / S3 / "verify-a/phase-a-verification.json",
            study.S3_PINS["verify-a/phase-a-verification.json"],
        )
    )
    if not receipt["payload"]["verified"] or receipt["payload"]["a_sha256"] != a["sha256"]:
        raise ValueError("ORIGINAL_S3_VERIFY_A_REQUIRED")
    # Previous S4 identity is verified without decoding any evaluation values.
    previous = json.loads(
        owner.read_bytes(
            root / S4 / "manifest.json",
            "97aa111ca707152e220e26b2a2909c639df4c8c6348765c3a21b854bcd696d52",
        )
    )
    if previous["code_git_sha"] != "181d23e3cd0aa68f490baa3c4e5721bd43760fe4":
        raise ValueError("PRIOR_S4_SOURCE_IDENTITY")
    members = content["formal_c0"]["payload"]["review"]["payload"]["members"]
    if (
        len(members) != 19032
        or len({r["base_id"] for r in members}) != 39
        or Counter(r["window"] for r in members) != {"H7_PREFIX": 9672, "H15_LOCAL": 9360}
        or any(r["admission_status"] != "ADMIT" for r in members)
    ):
        raise ValueError("FROZEN_C0_CHANGED")
    if bundle["profiles"]["B"] != content["profile"] or bundle["registry"] != content["registry"]:
        raise ValueError("S3_PROFILE_OR_REGISTRY_IDENTITY")
    fits, experiments = {}, {}
    for e in ("A", "B"):
        fitted = train.fit_verified(bundle, e)
        fits[e] = fitted
        if e == "A":
            mm = validation_members(bundle["admission"])
            baseline = train.curves(
                bundle["profiles"]["A"],
                bundle["registry"],
                {r["base_id"] for r in mm},
                date(2024, 7, 1),
                date(2025, 4, 15),
            )
        else:
            mm = members
            baseline = {"baseline": {}, "S2": {}}
            for bid, rr in content["full_curves"].items():
                baseline["baseline"][bid] = engine.curve_rows(rr["baseline"])
                baseline["S2"][bid] = engine.curve_rows(rr["candidate"])
        generated = train.predict_verified(bundle, fitted, baseline)
        curves = generated["curves"]
        # Invariance of calibrated mass is checked on each full/partial bin.
        for bid, volume in curves["VOLUME_CALIBRATION_V1"].items():
            timing = curves["VOLUME_TIMING_V1"][bid]
            for i in range(0, len(volume), 7):
                if sum((r.kg for r in volume[i : i + 7]), Decimal(0)) != sum(
                    (r.kg for r in timing[i : i + 7]), Decimal(0)
                ):
                    raise ValueError("CALIBRATED_BIN_MASS_DRIFT")
        inventory = []
        for m in mm:
            per_model = {}
            for model in METHODS:
                try:
                    rr = models.window(
                        curves[model].get(m["base_id"], ()),
                        date.fromisoformat(m["target_start"]),
                        7 if m["window"] == "H7_PREFIX" else 15,
                    )
                    per_model[model] = {
                        "status": "COMPLETED",
                        "window_sha256": digest(engine._serialize(rr)),
                        "peaks": {k: v for k, v in peaks._view(rr).items() if k != "daily"},
                    }
                except ValueError as exc:
                    per_model[model] = {"status": "FAILED", "reason": str(exc)}
            inventory.append({"candidate_id": m["candidate_id"], "models": per_model})
        experiments[e] = {
            "fit_sha256": fitted["sha256"],
            "fitted_parameters_sha256": fitted["fitted"]["sha256"],
            "training_bases": sorted(fitted["fitted"]["base_factors"]),
            "members": mm,
            "inventory": inventory,
            "curves": {
                model: {bid: engine._serialize(rr) for bid, rr in bases.items()}
                for model, bases in curves.items()
            },
            "failures": generated["failures"],
            "role": "TEMPORAL_VALIDATION" if e == "A" else "EXPOSED_HISTORICAL_BENCHMARK",
        }
    training = seal(
        {
            "admission": bundle["admission"],
            "input_pins": train.PINS,
            "code_identity": code_identity(),
            "training_evaluation_seasons_excluded": ["2025-2026"],
            "mixed_authority_bytes_hash_checked": True,
            "evaluation_label_values_decoded": False,
            "historical_known_at": "NOT_PROVEN",
            "strict_pit": False,
        }
    )
    fitted_models = seal(
        {
            "training_manifest_sha256": training["sha256"],
            "experiments": fits,
            "config": models.CONFIG,
            "code_identity": code_identity(),
        }
    )
    predictions = seal(
        {
            "training_manifest_sha256": training["sha256"],
            "fitted_models_sha256": fitted_models["sha256"],
            "s3_a_sha256": a["sha256"],
            "s3_c0_sha256": content["formal_c0"]["sha256"],
            "experiments": experiments,
            "code_identity": code_identity(),
            "model_ids": list(METHODS),
            "base_names": {
                b["base_id"]: b["canonical_base_name"] for b in content["registry"]["bases"]
            },
            "experiment_type": "RETROSPECTIVE_REPLAY",
            "historical_issued_at": None,
            "strict_pit": False,
            "labels_2025_2026_read": False,
            "production_eligible": False,
        }
    )
    return training, fitted_models, predictions


def load_a(path: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    manifest = json.loads((path / "manifest.json").read_bytes())
    values = tuple(
        json.loads(owner.read_bytes(path / name, manifest["file_sha256"][name]))
        for name in ("training-manifest.json", "fitted-models.json", "predictions.json")
    )
    for v in values:
        unseal(v)
        if v["payload"]["code_identity"] != code_identity():
            raise ValueError("EXECUTING_CODE_IDENTITY_CHANGED")
    t, f, p = values
    if (
        f["payload"]["training_manifest_sha256"] != t["sha256"]
        or p["payload"]["fitted_models_sha256"] != f["sha256"]
    ):
        raise ValueError("PREDICTION_TRAINING_LINK")
    return t, f, p


def verify_run(root: Path, path: Path) -> dict[str, Any]:
    stored = load_a(path)
    recomputed = predict_run(root)
    if stored != recomputed:
        raise ValueError("INDEPENDENT_FIT_OR_PREDICTION_RECOMPUTATION_MISMATCH")
    return {
        "verified": True,
        "prediction_sha256": stored[2]["sha256"],
        "code_identity": code_identity(),
        "label_values_2025_2026_read": False,
        "recomputed_fit_A": stored[1]["payload"]["experiments"]["A"]["sha256"],
        "recomputed_fit_B": stored[1]["payload"]["experiments"]["B"]["sha256"],
    }


def evaluate(
    curves: dict[str, Any],
    actual: dict[str, tuple[DailyKg, ...]],
    members: list[dict[str, Any]],
    training_bases: list[str],
    label_identity: str,
) -> dict[str, Any]:
    clock = datetime.now(UTC)
    result = study.compare(curves, actual, members, label_identity=label_identity, scored_at=clock)
    result["per_base"] = {
        bid: study.compare(
            {m: {bid: c.get(bid, ())} for m, c in curves.items()},
            {bid: actual.get(bid, ())},
            [r for r in members if r["base_id"] == bid],
            label_identity=label_identity,
            scored_at=clock,
        )
        for bid in sorted({r["base_id"] for r in members})
    }
    result["seen_unseen"] = {
        role: study.compare(
            curves,
            actual,
            [r for r in members if (r["base_id"] in training_bases) == seen],
            label_identity=label_identity,
            scored_at=clock,
        )
        for role, seen in (("SEEN", True), ("UNSEEN_GLOBAL_FALLBACK", False))
    }
    counts = {}
    for m, cc in curves.items():
        counts[m] = 0
        for member in members:
            try:
                models.window(
                    cc.get(member["base_id"], ()),
                    date.fromisoformat(member["target_start"]),
                    7 if member["window"] == "H7_PREFIX" else 15,
                )
                counts[m] += 1
            except ValueError:
                pass  # Missing prediction remains in joint Cm failures above.
    result["model_valid_prediction_counts"] = counts
    full_denominators = {}
    for w, n in (("H7_PREFIX", 7), ("H15_LOCAL", 15)):
        mass = Decimal(0)
        complete = 0
        for member in members:
            if member["window"] != w:
                continue
            try:
                rr = models.window(
                    actual.get(member["base_id"], ()), date.fromisoformat(member["target_start"]), n
                )
                mass += sum((r.kg for r in rr), Decimal(0))
                complete += 1
            except ValueError:
                pass
        full_denominators[w] = {
            "actual_kg": str(mass),
            "label_complete_members": complete,
            "candidate_members": sum(r["window"] == w for r in members),
        }
    result["full_C0_actual_denominators"] = full_denominators
    result["comparison_status"] = (
        "COMPLETE_FOUR_MODEL_COMMON_COHORT"
        if all(n == len(members) for n in counts.values()) and not result["failures"]
        else "BLOCKED_INCOMPLETE_COMPARISON_NO_OVERALL_WINNER"
    )
    return result


def score_run(root: Path, path: Path, verification: Path) -> dict[str, Any]:
    t, f, p = load_a(path)
    receipt = json.loads((verification / "verification.json").read_bytes())
    if (
        not receipt.get("verified")
        or receipt.get("prediction_sha256") != p["sha256"]
        or receipt.get("code_identity") != code_identity()
    ):
        raise ValueError("INDEPENDENT_VERIFICATION_REQUIRED")
    # Revalidate exact fits and inputs before opening the frozen target labels.
    verify_run(root, path)
    previous = json.loads(
        owner.read_bytes(
            root / S4 / "manifest.json",
            "97aa111ca707152e220e26b2a2909c639df4c8c6348765c3a21b854bcd696d52",
        )
    )
    for name, sha in previous["file_sha256"].items():
        owner.read_bytes(root / S4 / name, sha)
    raw = owner.read_bytes(root / S3 / "b/report.json", study.S3_PINS["b/report.json"])
    original = json.loads(raw)
    if (
        original["a_seal_sha256"] != p["payload"]["s3_a_sha256"]
        or original["admitted_count"] != 19032
    ):
        raise ValueError("FROZEN_LABEL_REPORT_MEMBERSHIP")
    actual_b: dict[str, list[DailyKg]] = {}
    for r in original["actual_daily"]:
        actual_b.setdefault(r["base_id"], []).append(
            DailyKg(date.fromisoformat(r["date"]), Decimal(r["kg"]))
        )
    daily_a = t["payload"]["admission"]["daily"]
    actual_a: dict[str, list[DailyKg]] = {}
    for r in daily_a:
        if r["season"] == "2024-2025":
            actual_a.setdefault(r["base_id"], []).append(
                DailyKg(date.fromisoformat(r["date"]), Decimal(r["kg"]))
            )
    result = {}
    for e, actual in (("A", actual_a), ("B", actual_b)):
        experiment = p["payload"]["experiments"][e]
        curves = {
            m: {bid: engine.curve_rows(rr) for bid, rr in cc.items()}
            for m, cc in experiment["curves"].items()
        }
        labels = {b: tuple(sorted(rr, key=lambda r: r.day)) for b, rr in actual.items()}
        result[e] = evaluate(
            curves,
            labels,
            experiment["members"],
            experiment["training_bases"],
            t["payload"]["admission"]["daily_sha256"]
            if e == "A"
            else study.S3_PINS["b/report.json"],
        )
        result[e]["fit_sha256"] = experiment["fit_sha256"]
    # Original real baseline/S2 denominators and errors must survive unchanged.
    complete = result["B"]["comparison_status"] == "COMPLETE_FOUR_MODEL_COMMON_COHORT"
    if complete:
        for w, g in original["groups"].items():
            for name in metrics.ERROR_METRICS:
                for model, side in (("baseline", "baseline"), ("S2", "candidate")):
                    if (
                        result["B"]["groups"][w][model]["metrics"][name]["candidate"]
                        != g["metrics"][name][side]
                    ):
                        raise ValueError("ORIGINAL_S1_METRIC_NUMERATOR_OR_DENOMINATOR_DRIFT")
    result["B"]["original_s3_metric_parity_checked"] = complete
    return {
        "experiments": result,
        "predictions_sha256": p["sha256"],
        "fitted_models_sha256": f["sha256"],
        "code_identity": code_identity(),
        "strict_pit": False,
        "historical_status": "EXPOSED_HISTORICAL_BENCHMARK",
        "experiment_type": "RETROSPECTIVE_REPLAY",
        "physical_basis": "CONDITIONAL_CROSS_SOURCE_RECORDED_INBOUND_WEIGHT",
        "physical_equivalence": "NOT_PROVEN",
        "historical_area_known_at": "NOT_PROVEN",
        "real_training_performed": True,
        "real_scoring_performed": True,
        "production_eligible": False,
        "actual_daily": original["actual_daily"],
    }


def report_files(
    comparison: dict[str, Any],
    training: dict[str, Any],
    fitted: dict[str, Any],
    predictions: dict[str, Any],
) -> dict[str, bytes]:
    with localcontext(Context(prec=50)):
        return _report_files(comparison, training, fitted, predictions)


def _report_files(
    comparison: dict[str, Any],
    training: dict[str, Any],
    fitted: dict[str, Any],
    predictions: dict[str, Any],
) -> dict[str, bytes]:
    def change_label(value: str | None) -> str:
        if value is None:
            return "NOT_COMPUTABLE"
        delta = Decimal(value)
        return "IMPROVED" if delta < 0 else "DEGRADED" if delta > 0 else "TIED"

    admission = training["payload"]["admission"]
    lines = [
        "# V0.19 S4 真实训练与四模型条件研究",
        "",
        "RETROSPECTIVE_REPLAY / EXPOSED_HISTORICAL_BENCHMARK / STRICT_PIT=false。",
        "历史记录为入库公斤数；与 SOURCE_002 净重的物理等价、历史面积 known_at 尚未证明。",
        "不证明盲测、历史真实签发或生产准确率。重叠窗口不视为独立样本。",
        "",
        f"训练候选 Base-season={admission['candidate_base_seasons']}，"
        f"准入={admission['admitted_base_seasons']}。",
        "",
    ]
    for e in ("A", "B"):
        fit = fitted["payload"]["experiments"][e]
        result = comparison["experiments"][e]
        lines += [
            f"## 实验 {e}",
            "",
            f"训练季={fit['training_seasons']}；分箱={fit['fitted']['training_bin_count']}；"
            f"训练基地={len(fit['fitted']['base_factors'])}；fit={fit['sha256']}",
            f"实际全局数量系数={fit['fitted']['global_factor']}；候选成员={result['candidate_count']}。",
            f"比较状态={result['comparison_status']}；不完整共同样本不得宣称整体优胜。",
            "",
        ]
        for w, models_ in result["groups"].items():
            lines += [
                f"### {w}",
                "",
                "| 指标 | BASELINE | S2 | VOLUME | VOLUME+TIMING |",
                "|---|---:|---:|---:|---:|",
            ]
            for name in metrics.ERROR_METRICS:
                values = [str(models_[m]["metrics"][name]["candidate"]["value"]) for m in METHODS]
                lines.append("| " + name + " | " + " | ".join(values) + " |")
            lines += [
                "",
                "H7 七日峰起点误差为零属于唯一七日窗口的结构结果。完整产季 WAPE 不可计算。",
                "",
            ]
            base = models_["baseline"]["metrics"]
            for m in METHODS[1:]:
                mm = models_[m]["metrics"]
                if any(
                    mm[n]["candidate"]["value"] is None or base[n]["candidate"]["value"] is None
                    for n in (
                        "DAILY_WAPE",
                        "SINGLE_DAY_PEAK_DATE_MAE",
                        "ROLLING_7DAY_PEAK_START_MAE",
                    )
                ):
                    lines.append(f"{m}：NOT_COMPUTABLE，详见指标原因及完整失败台账。")
                    continue
                delta = Decimal(mm["DAILY_WAPE"]["candidate"]["value"]) - Decimal(
                    base["DAILY_WAPE"]["candidate"]["value"]
                )
                date_delta = Decimal(
                    mm["SINGLE_DAY_PEAK_DATE_MAE"]["candidate"]["value"]
                ) - Decimal(base["SINGLE_DAY_PEAK_DATE_MAE"]["candidate"]["value"])
                rolling_delta = Decimal(
                    mm["ROLLING_7DAY_PEAK_START_MAE"]["candidate"]["value"]
                ) - Decimal(base["ROLLING_7DAY_PEAK_START_MAE"]["candidate"]["value"])
                state = (
                    "MIXED"
                    if delta < 0 and (date_delta > 0 or rolling_delta > 0)
                    else "NO_RELIABLE_GAIN"
                    if delta >= 0
                    else "CONDITIONAL_GAIN_NOT_PRODUCTION_VALIDATION"
                )
                lines.append(
                    f"{m}：WAPE 变化 {delta * 100} 个百分点；单日峰日期变化 {date_delta} 天；"
                    f"七日峰起点变化 {rolling_delta} 天。{state}。"
                )
        lines += [
            "### 各基地 H7/H15 结果",
            "",
            "| Base | Window | Baseline WAPE | S2 WAPE | Volume WAPE | Timing WAPE | "
            "Volume变化 | Timing变化 |",
            "|---|---|---:|---:|---:|---:|---|---|",
        ]
        for bid, result_ in result["per_base"].items():
            for w, mm in result_["groups"].items():
                lines.append(
                    "| "
                    + predictions["payload"]["base_names"][bid]
                    + " | "
                    + w
                    + " | "
                    + " | ".join(
                        str(mm[m]["metrics"]["DAILY_WAPE"]["candidate"]["value"]) for m in METHODS
                    )
                    + " | "
                    + " | ".join(
                        change_label(mm[m]["metrics"]["BASE_BREADTH"]["per_base_delta"].get(bid))
                        for m in METHODS[2:]
                    )
                    + " |"
                )
        lines += [
            "",
            "### 逐基地峰日期与峰量",
            "",
            "| Base | Window | Model | 单日峰日期 MAE 天 | 单日峰量 MAE kg | "
            "七日峰起点 MAE 天 | 七日峰量 MAE kg |",
            "|---|---|---|---:|---:|---:|---:|",
        ]
        for bid, rr in result["per_base"].items():
            for w, mm in rr["groups"].items():
                for m in METHODS:
                    values = mm[m]["metrics"]
                    lines.append(
                        "| "
                        + predictions["payload"]["base_names"][bid]
                        + " | "
                        + w
                        + " | "
                        + m
                        + " | "
                        + " | ".join(
                            str(values[n]["candidate"]["value"])
                            for n in (
                                "SINGLE_DAY_PEAK_DATE_MAE",
                                "SINGLE_DAY_PEAK_QUANTITY_MAE",
                                "ROLLING_7DAY_PEAK_START_MAE",
                                "ROLLING_7DAY_PEAK_QUANTITY_MAE",
                            )
                        )
                        + " |"
                    )
        lines += [
            "",
            "### 未见训练基地的全局回退",
            "",
            "| 分组 | Window | BASELINE WAPE | S2 WAPE | VOLUME WAPE | TIMING WAPE |",
            "|---|---|---:|---:|---:|---:|",
        ]
        for role, group in result["seen_unseen"].items():
            for w, mm in group["groups"].items():
                lines.append(
                    "| "
                    + role
                    + " | "
                    + w
                    + " | "
                    + " | ".join(
                        str(mm[m]["metrics"]["DAILY_WAPE"]["candidate"]["value"]) for m in METHODS
                    )
                    + " |"
                )
        lines += [
            "",
            "### 共同样本、分母与改善/退化",
            "",
            "| Window | Model | 有效/C0 | actual kg 分母 | 绝对误差 kg 分子 | 改善/退化/持平基地 |",
            "|---|---|---:|---:|---:|---|",
        ]
        for w, mm in result["groups"].items():
            for m in METHODS:
                value = mm[m]["metrics"]["DAILY_WAPE"]
                breadth = mm[m]["metrics"]["BASE_BREADTH"]
                lines.append(
                    f"| {w} | {m} | {value['common_count']}/{value['candidate_count']} | "
                    f"{value['candidate']['denominator']} | {value['candidate']['numerator']} | "
                    f"{breadth['improved']}/{breadth['worsened']}/{breadth['tied']} |"
                )
        lines += [""]
    lines += [
        "## 训练成员拒绝与边界分箱",
        "",
        "```json",
        json.dumps(
            [
                {k: r[k] for k in ("base_id", "season", "s6_candidate", "status", "reason")}
                for r in admission["inventory"]
                if r["status"] != "ADMIT"
            ],
            ensure_ascii=False,
            indent=2,
        ),
        "```",
        "",
        "完整训练分箱以 July01 锚定，不完整末箱只保留台账，不进入拟合。"
        "数量与时间模型结构、收缩强度及分配规则均沿用 S4 冻结配置。",
        "无论改善或退化均保留。没有依据 2025–2026 误差选择训练成员或调整参数。",
        "当前资料仍缺可追溯历史签发、入库与完整田间采收之间的映射，以及更强的物候/管理和可用时间证据。未晋级或部署。",
    ]
    lines += [
        "",
        "## 实际日量示例（固定排序首个基地，support 最后十四日）",
        "",
        "| Base | 日期 | 实际入库净重 kg | BASELINE kg | S2 kg | VOLUME kg | TIMING kg |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    cc = predictions["payload"]["experiments"]["B"]["curves"]
    bid = sorted(cc["baseline"])[0]
    labels = {(r["base_id"], r["date"]): r["kg"] for r in comparison["actual_daily"]}
    lookup = {m: {r["date"]: r["kg"] for r in cc[m].get(bid, [])} for m in METHODS}
    for day in sorted(lookup["baseline"])[-14:]:
        lines.append(
            "| "
            + predictions["payload"]["base_names"][bid]
            + " | "
            + day
            + " | "
            + labels.get((bid, day), "NOT_COMPUTABLE")
            + " | "
            + " | ".join(lookup[m].get(day, "NOT_COMPUTABLE") for m in METHODS)
            + " |"
        )
    text = "\n".join(lines) + "\n"
    return {
        "comparison.json": canonical_bytes(compact(comparison)),
        "report.md": text.encode(),
        "report.html": (
            '<!doctype html><meta charset="utf-8"><title>S4 real training</title>'
            "<style>body{font:14px system-ui;max-width:1300px;margin:30px auto}"
            "table{border-collapse:collapse}td{border:1px solid #ddd;padding:5px}"
            "pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>" + study.markdown_html(text)
        ).encode(),
    }


def compact(value: dict[str, Any]) -> dict[str, Any]:
    """Store repeated cohort membership once, retaining exact member/exclusion ledgers."""
    cohorts: dict[str, Any] = {}
    exclusions: dict[str, Any] = {}

    def visit(obj: Any) -> Any:
        if isinstance(obj, list):
            return [visit(v) for v in obj]
        if not isinstance(obj, dict):
            return obj
        result = {}
        for k, v in obj.items():
            if k == "common_member_ids":
                key = digest(v)
                cohorts[key] = v
                result["common_member_ids_ref"] = key
            elif k == "exclusions":
                key = digest(v)
                exclusions[key] = v
                result["exclusions_ref"] = key
            else:
                result[k] = visit(v)
        return result

    result = visit(value)
    result["cohort_member_sets"] = cohorts
    result["exclusion_ledgers"] = exclusions
    return cast(dict[str, Any], result)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("predict", "verify", "score"))
    parser.add_argument("--owner-command", required=True, choices=(train.TASK,))
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--a", type=Path)
    parser.add_argument("--verification", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if subprocess.check_output(["git", "status", "--porcelain"], text=True).strip():
        raise ValueError("COMMITTED_CLEAN_SOURCE_REQUIRED_FOR_REAL_EXECUTION")
    metadata = {
        "task_id": train.TASK,
        "mode": MODE,
        "actual_execution_time": datetime.now(UTC).isoformat(),
        "code_git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "code_identity": code_identity(),
        "command": sys.argv,
        "pid": os.getpid(),
        "authorization_source": "DIRECT_OWNER_TASK_CURRENT_SCOPE",
        "production_eligible": False,
    }
    if args.phase == "predict":
        t, f, p = predict_run(args.artifact_root)
        files = {
            "training-manifest.json": canonical_bytes(t),
            "fitted-models.json": canonical_bytes(f),
            "predictions.json": canonical_bytes(p),
        }
    elif args.phase == "verify":
        if args.a is None:
            parser.error("--a required")
        files = {"verification.json": canonical_bytes(verify_run(args.artifact_root, args.a))}
    else:
        if args.a is None or args.verification is None:
            parser.error("--a and --verification required")
        c = score_run(args.artifact_root, args.a, args.verification)
        files = report_files(c, *load_a(args.a))
    metadata["completed_at"] = datetime.now(UTC).isoformat()
    owner.write_bundle(args.output, files, metadata)
    print(json.dumps({"phase": args.phase, "output": str(args.output), "files": list(files)}))


if __name__ == "__main__":
    main()
