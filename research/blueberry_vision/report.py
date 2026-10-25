"""Offline, provenance-bound synthetic review artifacts; no services or uploads."""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path

from PIL import Image, ImageDraw

from research.blueberry_vision.assets import load_asset
from research.blueberry_vision.evaluator import evaluate_predictions
from research.blueberry_vision.r2_common import (
    JSONDict,
    canonical_hash,
    file_hash,
    seal,
    verify_seal,
    write_json_new,
)

WARNING = "SYNTHETIC DEMONSTRATION — NOT REAL BLUEBERRY ACCURACY"
REPORT_VERSION = "blueberry-vision-review/2.0.0"


class ReportError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _bind(manifest: JSONDict, bundles: list[JSONDict], reports: list[JSONDict]) -> None:
    if manifest.get("SYNTHETIC") is not True or any(
        record.get("SYNTHETIC") is not True for record in manifest.get("images", [])
    ):
        raise ReportError("SYNTHETIC_ONLY")
    if not verify_seal(manifest, "manifest_hash"):
        raise ReportError("DATASET_MANIFEST_HASH_MISMATCH")
    if not bundles or len(bundles) != len(reports):
        raise ReportError("MODEL_REPORT_COUNT_MISMATCH")
    if len({report.get("scope_hash") for report in reports}) > 1:
        raise ReportError("REPORT_COMPARISON_SCOPE_MISMATCH")
    for bundle, report in zip(bundles, reports, strict=True):
        if not verify_seal(bundle, "prediction_hash") or not verify_seal(report, "report_hash"):
            raise ReportError("INPUT_ARTIFACT_HASH_MISMATCH")
        if (
            bundle.get("dataset_manifest_hash") != manifest["manifest_hash"]
            or report.get("dataset_manifest_hash") != manifest["manifest_hash"]
            or report.get("prediction_hash") != bundle["prediction_hash"]
            or report.get("model_hash") != bundle.get("model_hash")
            or report.get("config_hash") != bundle.get("config_hash")
        ):
            raise ReportError("REPORT_PROVENANCE_BINDING_MISMATCH")
        try:
            computed = evaluate_predictions(
                manifest, bundle, report.get("evaluation_splits"), report.get("evaluator_config")
            )
        except (ValueError, KeyError, TypeError) as error:
            raise ReportError("REPORT_RECOMPUTATION_FAILED") from error
        if computed != report:
            raise ReportError("REPORT_METRICS_MISMATCH")


def _image_data(image: Image.Image) -> str:
    stream = io.BytesIO()
    image.save(stream, format="PNG", optimize=False, compress_level=9)
    return "data:image/png;base64," + base64.b64encode(stream.getvalue()).decode("ascii")


def _draw_boxes(
    draw: ImageDraw.ImageDraw, objects: list[JSONDict], color: str, prefix: str
) -> None:
    for index, obj in enumerate(objects, start=1):
        x1, y1, x2, y2 = obj["bbox_xyxy"]
        draw.rectangle((x1, y1, x2 - 1, y2 - 1), outline=color, width=2)
        draw.text((x1 + 1, y1 + 1), f"{prefix}{index}", fill=color)


def _overlay(
    image: Image.Image, record: JSONDict, model: JSONDict, *, show_gt: bool = True
) -> Image.Image:
    output = Image.new("RGB", (image.width, image.height + 64), "#101923")
    output.paste(image, (0, 0))
    draw = ImageDraw.Draw(output)
    if show_gt:
        _draw_boxes(draw, record.get("objects") or [], "#57e39b", "G")
    _draw_boxes(draw, model["prediction"].get("detected_objects") or [], "#ffb55b", "P")
    lines = [
        "SYNTHETIC ONLY / visible fruit per image",
        f"GT={model['gt_count']}  Pred={model['pred_count']}  Error={model['signed_error']}",
        model["model_name"][:60],
    ]
    for index, line in enumerate(lines):
        draw.text((4, image.height + 3 + index * 18), line, fill="white")
    return output


def _summary(models: list[JSONDict]) -> Image.Image:
    image = Image.new("RGB", (900, 100 + 105 * len(models)), "#101923")
    draw = ImageDraw.Draw(image)
    draw.text((20, 15), "SYNTHETIC DEMONSTRATION / NOT REAL BLUEBERRY ACCURACY", fill="#f5c76b")
    draw.text(
        (20, 40),
        "Visible counts are not kg. AP50 is research all-points AP, not COCO mAP.",
        fill="white",
    )
    for index, model in enumerate(models):
        top = 85 + index * 105
        draw.text((20, top), model["model_name"], fill="#64dbc7")
        for line, keys in enumerate(
            (
                ("precision", "recall", "f1", "bbox_ap50_research_all_points"),
                ("count_mae", "count_bias", "tp", "fp", "fn"),
            )
        ):
            text = "  |  ".join(f"{key}={model['metrics'].get(key)}" for key in keys)
            draw.text((20, top + 22 + line * 22), text, fill="white")
    return image


def render_report(
    manifest: JSONDict,
    data_root: Path,
    prediction_bundles: list[JSONDict],
    evaluation_reports: list[JSONDict],
    output_dir: Path,
) -> JSONDict:
    """Build a new, file-openable report from bound real algorithm artifacts.

    Only synthetic records are opened. All source hashes/dimensions are checked
    through the bounded loader. Evaluation is independently rerun before rendering
    to reject stale metrics paired with new detections. Output never overwrites.
    """
    if output_dir.exists():
        raise ReportError("OUTPUT_ALREADY_EXISTS")
    _bind(manifest, prediction_bundles, evaluation_reports)
    models: list[JSONDict] = []
    rows_by_model: list[dict[str, JSONDict]] = []
    predictions_by_model: list[dict[str, JSONDict]] = []
    evaluated_ids: set[str] = set()
    for index, (bundle, evaluation) in enumerate(
        zip(prediction_bundles, evaluation_reports, strict=True)
    ):
        model_name = str(
            bundle.get("model_name") or bundle.get("detector_version") or f"Model {index + 1}"
        )
        models.append(
            {
                "model_index": index,
                "model_name": model_name,
                "model_hash": bundle["model_hash"],
                "config_hash": bundle["config_hash"],
                "prediction_hash": bundle["prediction_hash"],
                "evaluation_hash": evaluation["report_hash"],
                "evaluation_file": f"evaluation_model-{index}.json",
                "metrics": evaluation["metrics"],
                "subgroup_metrics": evaluation["subgroup_metrics"],
                "evaluated_count": evaluation["evaluated_count"],
                "excluded_count": evaluation["excluded_count"],
                "limitations": evaluation["limitations"],
            }
        )
        rows = {row["image_id"]: row for row in evaluation["per_image_results"]}
        rows_by_model.append(rows)
        evaluated_ids.update(rows)
        predictions_by_model.append({row["image_id"]: row for row in bundle["images"]})
    # Validate/decode all requested pixels before creating a partially published output.
    pixels: dict[str, Image.Image] = {}
    records = [record for record in manifest["images"] if record["image_id"] in evaluated_ids]
    for record in records:
        asset = load_asset(
            data_root,
            record["original_asset_ref"],
            expected_hash=record["asset_sha256"],
            expected_size=(record["image_width"], record["image_height"]),
        )
        pixels[record["image_id"]] = Image.fromarray(asset.rgb)
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "overlays").mkdir()
    (output_dir / "prediction_overlays").mkdir()
    (output_dir / "errors_collection").mkdir()
    for index, evaluation in enumerate(evaluation_reports):
        write_json_new(output_dir / f"evaluation_model-{index}.json", evaluation)
    images: list[JSONDict] = []
    overlays: list[str] = []
    prediction_overlays: list[str] = []
    errors: list[str] = []
    collage_tiles: list[Image.Image] = []
    for record_index, record in enumerate(records):
        image_id = record["image_id"]
        entry: JSONDict = {
            "image_id": image_id,
            "width": record["image_width"],
            "height": record["image_height"],
            "image_data": _image_data(pixels[image_id]),
            "gt": record.get("objects"),
            "gt_status": record["gt_status"],
            "visible_count": record["visible_count"],
            "scene_metadata": record["scene_metadata"],
            "source_authority": record["source_authority"],
            "source_asset_hash": record["asset_sha256"],
            "reference_record_hash": record.get("record_hash"),
            "annotation_version": record["annotation_version"],
            "label_definition_version": record["label_definition_version"],
            "models": [],
        }
        for model_index, model in enumerate(models):
            prediction = predictions_by_model[model_index].get(
                image_id,
                {
                    "status": "MISSING_PREDICTION",
                    "detected_objects": None,
                    "predicted_visible_fruit_count": None,
                },
            )
            row = rows_by_model[model_index].get(image_id, {})
            image_model: JSONDict = {
                "model_index": model_index,
                "model_name": model["model_name"],
                "prediction": prediction,
                "gt_count": row.get("gt_count", record["visible_count"]),
                "pred_count": row.get("pred_count"),
                "signed_error": row.get("signed_count_error"),
                "absolute_error": row.get("absolute_count_error"),
                "fp": row.get("fp"),
                "fn": row.get("fn"),
                "tp": row.get("tp"),
                "status": row.get("status", "NOT_EVALUATED"),
                "reason_code": row.get("reason_code"),
            }
            entry["models"].append(image_model)
            overlay = _overlay(pixels[image_id], record, image_model)
            relative = f"overlays/image-{record_index:04d}-model-{model_index}.png"
            overlay.save(output_dir / relative, optimize=False, compress_level=9)
            overlays.append(relative)
            predicted_relative = (
                f"prediction_overlays/image-{record_index:04d}-model-{model_index}.png"
            )
            _overlay(pixels[image_id], record, image_model, show_gt=False).save(
                output_dir / predicted_relative, optimize=False, compress_level=9
            )
            prediction_overlays.append(predicted_relative)
            if row and (
                row.get("status") != "EVALUATED"
                or row.get("fp")
                or row.get("fn")
                or row.get("absolute_count_error")
            ):
                relative_error = (
                    f"errors_collection/image-{record_index:04d}-model-{model_index}.png"
                )
                overlay.save(output_dir / relative_error, optimize=False, compress_level=9)
                errors.append(relative_error)
            if model_index == 0:
                thumb = overlay.copy()
                thumb.thumbnail((220, 190))
                tile = Image.new("RGB", (230, 220), "#101923")
                tile.paste(thumb, ((230 - thumb.width) // 2, 0))
                ImageDraw.Draw(tile).text(
                    (4, 195),
                    str(record["scene_metadata"].get("scene_type", "unknown"))[:30],
                    fill="white",
                )
                collage_tiles.append(tile)
        images.append(entry)
    collage = Image.new("RGB", (920, max(220, ((len(collage_tiles) + 3) // 4) * 220)), "#101923")
    for index, tile in enumerate(collage_tiles):
        collage.paste(tile, ((index % 4) * 230, (index // 4) * 220))
    collage.save(output_dir / "scene_collage.png", optimize=False, compress_level=9)
    _summary(models).save(output_dir / "metrics_summary.png", optimize=False, compress_level=9)
    data = seal(
        {
            "schema_version": REPORT_VERSION,
            "SYNTHETIC": True,
            "warning": WARNING,
            "dataset_manifest_hash": manifest["manifest_hash"],
            "count_unit": "visible_fruit_per_image",
            "models": models,
            "images": images,
        },
        "report_hash",
    )
    write_json_new(output_dir / "report.json", data)
    template = Path(__file__).with_name("review_ui.html").read_text(encoding="utf-8")
    encoded = json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    # Script-embedded JSON must never create markup, even for attacker-controlled labels.
    encoded = encoded.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    encoded = encoded.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    (output_dir / "report.html").write_text(
        template.replace("__REPORT_JSON__", encoded), encoding="utf-8"
    )
    lines = [
        f"# {WARNING}",
        "",
        "All metrics are synthetic engineering results. Visible fruit counts are not kg.",
        "",
        f"Dataset hash: `{manifest['manifest_hash']}`",
        f"Report hash: `{data['report_hash']}`",
        "",
    ]
    for model in models:
        source_rows = list(rows_by_model[model["model_index"]].values())
        failures = sum(row["status"] != "EVALUATED" for row in source_rows)
        error_images = sum(
            row["status"] == "EVALUATED"
            and bool(row.get("fp") or row.get("fn") or row.get("absolute_count_error"))
            for row in source_rows
        )
        lines.extend(
            [
                f"## {model['model_name']}",
                "",
                f"Evaluated: {model['evaluated_count']}; excluded: {model['excluded_count']}; "
                f"missing/failed: {failures}; evaluated images with errors: {error_images}.",
                "",
                "| Scalar metric | Value |",
                "| --- | --- |",
                *[
                    f"| {key} | {value} |"
                    for key, value in model["metrics"].items()
                    if value is None or isinstance(value, str | int | float | bool)
                ],
                "",
                f"Full original evaluator artifact, including AP curves, strata and failure cases: "
                f"[{model['evaluation_file']}]({model['evaluation_file']}).",
                f"Evaluator artifact hash: `{model['evaluation_hash']}`.",
                "",
            ]
        )
    lines.extend(
        [
            f"All {len(errors)} failed/error overlays are retained in `errors_collection/`.",
            "Full review data and all per-image outcomes: [report.json](report.json).",
            "Open `report.html` locally. Export creates candidate JSON; GT is immutable.",
        ]
    )
    (output_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return seal(
        {
            "schema_version": REPORT_VERSION,
            "report_path": "report.json",
            "html_path": "report.html",
            "markdown_path": "report.md",
            "overlay_paths": overlays,
            "prediction_overlay_paths": prediction_overlays,
            "error_paths": errors,
            "image_count": len(images),
            "report_hash": data["report_hash"],
            "artifacts": {
                str(path.relative_to(output_dir)): file_hash(path)
                for path in sorted(output_dir.rglob("*"))
                if path.is_file()
            },
            "input_binding_hash": canonical_hash(
                [
                    manifest["manifest_hash"],
                    *[bundle["prediction_hash"] for bundle in prediction_bundles],
                ]
            ),
        },
        "artifact_manifest_hash",
    )
