"""Small business report; reuse the R3 review page rather than duplicate images."""

from html import escape
from pathlib import Path

from ..r2_common import JSONDict, read_json, verify_seal, write_json_new
from ..r3.evaluation import compact_metrics

ROOT = Path(__file__).resolve().parents[1]


def business_report(report: JSONDict, output: Path) -> None:
    if not verify_seal(report, "report_hash"):
        raise ValueError("REPORT_HASH_INVALID")
    for model in report["models"]:
        recalculated = compact_metrics(model["per_image"])
        if any(model["metrics"].get(key) != value for key, value in recalculated.items()):
            raise ValueError("REPORT_METRICS_DO_NOT_RECOMPUTE")
    if output.exists():
        raise ValueError("OUTPUT_ALREADY_EXISTS")
    output.mkdir(parents=True)
    write_json_new(output / "evaluation.json", report)
    dataset = read_json(ROOT / "evidence/r3/pilot_dataset_manifest.json")
    rows_a = {row["image_id"]: row for row in report["models"][0]["per_image"]}
    rows_b = {row["image_id"]: row for row in report["models"][1]["per_image"]}
    lines = [
        "# R4 真实蓝莓参考与冻结算法评价",
        "",
        f"结果：{report['status']}；合格GT图片{report['qualified_gt_images']}；"
        f"未评分图片{report['unscorable_images']}。",
        "",
        "使用R3全部8张合法公开图：4张Commons照片、4张Quality1500×1000派生PNG。",
        "来源/原始与派生hash/许可保留在R3清单；未接入公司果园或当前产季actual。",
        "",
        "| 图片 | 许可 | A原始预测数量 | B原始预测数量 | 合格参考数量 | A/B计数误差 |",
        "| --- | --- | ---: | ---: | --- | --- |",
    ]
    for image in dataset["images"]:
        key = image["image_id"]
        a, b = rows_a[key], rows_b[key]
        ref = a["reference_count"] if a["reference_count"] is not None else "NOT_EVALUABLE"
        errors = (
            f"{a['signed_count_error']}/{b['signed_count_error']}"
            if a["signed_count_error"] is not None
            else "NOT_EVALUABLE"
        )
        lines.append(
            f"| {key} | {image['license_id']} | {a['predicted_count']} | "
            f"{b['predicted_count']} | {ref} | {errors} |"
        )
    lines += [
        "",
        "真实参考是谁提供和审核：本轮未收到真实人工A/B标注、仲裁或Owner核验批准。",
        "任务A/B/ADJUDICATOR均未分配。Codex/浏览器工程测试不是人类审核。",
        "100个候选框、675个半自动polygon、500个manual损坏区域框均未升级为单果GT。",
        "",
        "计数定义：完整图中可区分的单颗可见蓝莓，tight visible bbox；不猜测隐藏果；",
        "接触/遮挡/出画按固定R4指南，极小/不确定果和不可逐果果串需标记并仲裁。",
        "范围是预注册完整图，不是看过模型错误后选择的ROI。原R3合同未改变。",
        "",
        "两套算法分别为RGB_threshold_and_4_connected_components_v2和",
        "CPU_NumPy_logistic_pixel_classifier_v2；原R2模型、阈值、后处理和R3预测均未改变。",
        "上表是算法输出，不是准确计数。最大分歧图片A1161/B66；该差异不能说明哪套正确。",
        "",
        "漏计/误计在哪里、哪种场景最难：缺合格GT，目前不能判断或排序。",
        "密集、遮挡、反光可作为人工审查重点，当前分层身份未知，不能填造分层零误差。",
        "",
        "可计算：8张图片/16次已有推理的数量、模型分歧、来源与hash完整性。",
        "不可计算：真实TP/FP/FN、Precision/Recall/F1、RESEARCH_AP50、CountMAE/Bias、",
        "总漏计/误计、真实COCO_MAP50/50_95：保持null/NOT_EVALUABLE。",
        "官方COCO未跑真实GT；将来实际运行时记录pycocotools2.0.11/maxDets1,10,100。",
        "",
        "公开标签和R3结果已曝光，只能EXPOSED_EXTERNAL_EVALUATION，不能称为blind test。",
        "不能代表公司果园：基地/拍摄时间/品种未知；无跨基地、日期、设备验证。",
        "视觉数量不能换算采摘kg；没有生产视觉批准或产量模型改动。",
        "",
        "下一步：先由两位真实人员完成这8张图的独立全分辨率逐果标注，第三位仲裁，",
        "保留身份/来源/独立性证据和实际批准记录，再运行冻结预测评价。",
        "或由Owner向BlueberryDCM权利人取得明确公司关联用途许可，再核对逐果方法与样本质量。",
        "新发现BerryMachine CC BY4资源仍待物种/真实人工方法/受控读取核验，不是已准入GT。",
        "后续公司果园试点建议先取得30–50张获准全图，覆盖至少3基地、3日期和2设备/角度，",
        "含负样本、密集和遮挡；这是初步采集建议，正式样本量需依据误差目标重新确定。",
        "",
        "代码/工作包：r4/，evidence/r4/human_annotation_package.json、task_A/B/ADJUDICATOR.json。",
        "清洁编辑预览：examples/r4/clean_annotation_preview.html（不是合格标注来源）。",
        "已有模型审核页面：examples/r3/real_review.html（不要交给独立标注者看预测答案）。",
        "本地全分辨率任务由prepare-work命令重建；原图不重复提交Git。",
        "",
        f"report_hash={report['report_hash']}",
        f"prediction_lock_hash={report['prediction_lock_hash']}",
    ]
    lines.extend(
        [
            "",
            "| 模型 | 合格评价图数 | TP/FP/FN | Precision/Recall/F1 | Count MAE/Bias | COCO状态 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )

    def value(item: object) -> str:
        return str(item) if item is not None else "NOT_EVALUABLE"

    for model in report["models"]:
        metric = model["metrics"]
        lines.append(
            f"| {model['model_key']} | {metric['evaluated_count']} | "
            + "/".join(value(metric[key]) for key in ("tp", "fp", "fn"))
            + " | "
            + "/".join(value(metric[key]) for key in ("precision", "recall", "f1"))
            + " | "
            + "/".join(value(metric[key]) for key in ("count_mae", "count_bias"))
            + " | "
            + model["coco"]["status"]
            + " |"
        )
    if report["qualified_gt_images"]:
        lines = [
            line
            for line in lines
            if not any(
                text in line
                for text in (
                    "未收到真实人工",
                    "任务A/B/ADJUDICATOR均未分配",
                    "缺合格GT，目前不能判断",
                    "不可计算：真实",
                    "总漏计/误计、真实COCO",
                    "官方COCO未跑真实GT",
                )
            )
        ]
        lines.extend(
            [
                "参考来源：绑定Owner核验批准记录及reference/approval hashes，",
                "离线工具验证完整性，不认证人类身份；未准入图片仍不评分。",
                "漏检/误检目标与逐图错误在evaluation.json；只能代表合格外部范围。",
            ]
        )
    (output / "report.md").write_text("\n".join(lines) + "\n")
    # A compact readable artifact with real numbers; all image review remains in R3.
    text = "\n".join(lines)
    html = (
        '<!doctype html><meta charset="utf-8"><title>R4 real reference status</title>'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        "style-src 'unsafe-inline'\"><style>body{max-width:1000px;margin:32px auto;"
        "padding:0 20px;font:15px/1.6 system-ui;color:#203247}pre{white-space:pre-wrap;"
        "overflow-wrap:anywhere;font:inherit}</style><h1>公开真实图片：参考审核待完成</h1>"
        "<p>EXPOSED EXTERNAL EVALUATION · NOT COMPANY ORCHARD APPROVAL</p><pre>"
        + escape(text)
        + "</pre>"
    )
    (output / "report.html").write_text(html)
