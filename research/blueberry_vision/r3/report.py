"""Compact offline review of provenance-bound external, orchard, and synthetic images.

Public export never embeds pixels without explicit redistribution permission.
Local controlled reports may embed authorized research pixels and must remain local.
This module performs no network requests and never upgrades drafts into reference GT.
"""

from __future__ import annotations

import base64
import io
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image

from ..r2_common import JSONDict, canonical_hash, seal, verify_seal, write_json_new
from .annotations import AnnotationError, reference_eligibility, validate_snapshot
from .contracts import DatasetError, validate_manifest
from .evaluation import compact_metrics, evaluation_protocol, match_reference, research_ap50
from .ingestion import secure_load_asset, verify_coordinate_metadata

VERSION = "blueberry-vision-real-review/3.0.0"
PURPOSES = {
    "SYNTHETIC_ENGINEERING": "SYNTHETIC ENGINEERING — NOT REAL BLUEBERRY ACCURACY",
    "PUBLIC_EXTERNAL_BENCHMARK": "PUBLIC EXTERNAL BENCHMARK — NOT ORCHARD APPROVAL",
    "AUTHORIZED_ORCHARD_PILOT": "AUTHORIZED ORCHARD PILOT — RESEARCH ONLY",
}
METRIC_KEYS = (
    "precision",
    "recall",
    "f1",
    "tp",
    "fp",
    "fn",
    "RESEARCH_AP50",
    "count_mae",
    "count_bias",
    "total_overcount",
    "total_undercount",
    "empty_image_false_positives",
    "evaluated_count",
    "excluded_count",
    "missing_count",
    "missing_prediction_count",
    "failed_count",
)
COVERAGE_KEYS = {
    "evaluated_count",
    "excluded_count",
    "missing_count",
    "missing_prediction_count",
    "failed_count",
}


class ReportError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _list(value: JSONDict | list[JSONDict] | None) -> list[JSONDict]:
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    return value


def _check_seal(value: JSONDict, key: str, code: str) -> None:
    if not verify_seal(value, key):
        raise ReportError(code)


def _box_valid(box: Any, width: int, height: int) -> bool:
    if not isinstance(box, list) or len(box) != 4:
        return False
    if any(type(n) not in (int, float) or not math.isfinite(n) for n in box):
        return False
    x1, y1, x2, y2 = box
    return bool(0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height)


def _objects(value: Any, width: int, height: int) -> list[JSONDict]:
    if not isinstance(value, list):
        raise ReportError("OBJECT_LIST_REQUIRED")
    result = []
    for obj in value:
        if not isinstance(obj, dict) or not _box_valid(obj.get("bbox_xyxy"), width, height):
            raise ReportError("BBOX_GEOMETRY_INVALID")
        result.append(
            {
                key: obj[key]
                for key in (
                    "object_id",
                    "class_label",
                    "bbox_xyxy",
                    "score",
                    "score_type",
                    "disposition",
                )
                if key in obj
            }
        )
    return result


def _bind(
    dataset: JSONDict,
    predictions: list[JSONDict],
    evaluations: list[JSONDict],
    annotations: list[JSONDict],
) -> tuple[dict[str, JSONDict], dict[str, JSONDict]]:
    _check_seal(dataset, "manifest_hash", "DATASET_MANIFEST_HASH_MISMATCH")
    try:
        validate_manifest(dataset)
    except DatasetError as exc:
        code = (
            "SOURCE_RESEARCH_PERMISSION_REQUIRED"
            if exc.code.startswith("SOURCE_")
            else "DATASET_INVALID:" + exc.code
        )
        raise ReportError(code) from exc
    purpose = dataset.get("purpose")
    if purpose not in PURPOSES or dataset.get("SYNTHETIC") is not (
        purpose == "SYNTHETIC_ENGINEERING"
    ):
        raise ReportError("DOMAIN_MISMATCH")
    records = {record["image_id"]: record for record in dataset["images"]}
    if len(records) != len(dataset["images"]):
        raise ReportError("DUPLICATE_IMAGE_ID")
    sources = {source["source_id"]: source for source in dataset["sources"]}
    if len(sources) != len(dataset["sources"]):
        raise ReportError("DUPLICATE_SOURCE_ID")
    permitted = {
        "PUBLIC_EXTERNAL_BENCHMARK": {"LICENSE_VERIFIED"},
        "AUTHORIZED_ORCHARD_PILOT": {"AUTHORITY_VERIFIED"},
        "SYNTHETIC_ENGINEERING": {"SYNTHETIC_AUTHORITY"},
    }
    for record in records.values():
        source = sources.get(record.get("source_id"))
        if source is None:
            raise ReportError("SOURCE_ID_UNKNOWN")
        if (
            source.get("research_use") is not True
            or source.get("license_status") not in permitted[purpose]
        ):
            raise ReportError("SOURCE_RESEARCH_PERMISSION_REQUIRED")
        if (
            source.get("purpose", purpose) != purpose
            or source.get("SYNTHETIC", dataset["SYNTHETIC"]) is not dataset["SYNTHETIC"]
        ):
            raise ReportError("DOMAIN_MISMATCH")
    if not predictions or len(predictions) != len(evaluations):
        raise ReportError("MODEL_REPORT_COUNT_MISMATCH")
    for prediction, evaluation in zip(predictions, evaluations, strict=True):
        _check_seal(prediction, "prediction_hash", "PREDICTION_HASH_MISMATCH")
        _check_seal(evaluation, "report_hash", "EVALUATION_HASH_MISMATCH")
        if any(
            value.get("purpose") != purpose
            or value.get("SYNTHETIC", dataset["SYNTHETIC"]) is not dataset["SYNTHETIC"]
            for value in (prediction, evaluation)
        ):
            raise ReportError("DOMAIN_MISMATCH")
        if (
            prediction.get("dataset_manifest_hash") != dataset["manifest_hash"]
            or evaluation.get("dataset_manifest_hash") != dataset["manifest_hash"]
            or evaluation.get("prediction_hash") != prediction["prediction_hash"]
        ):
            raise ReportError("REPORT_PROVENANCE_BINDING_MISMATCH")
        for key in ("model_hash", "selected_model_hash", "config_hash"):
            if key in evaluation and evaluation[key] != prediction.get(key):
                raise ReportError("MODEL_CONFIG_BINDING_MISMATCH")
        pred_ids: set[str] = set()
        for row in prediction.get("images", []):
            record = records.get(row.get("image_id"))
            if record is None or row.get("source_asset_hash") != record["asset_sha256"]:
                raise ReportError("PREDICTION_IMAGE_BINDING_MISMATCH")
            if row["image_id"] in pred_ids:
                raise ReportError("DUPLICATE_PREDICTION_IMAGE")
            pred_ids.add(row["image_id"])
            objects = _objects(
                row.get("detected_objects") or [], record["image_width"], record["image_height"]
            )
            count = row.get("predicted_visible_fruit_count")
            if row.get("status") == "ok" and (type(count) is not int or count != len(objects)):
                raise ReportError("PREDICTION_COUNT_MISMATCH")
            if row.get("status") != "ok" and count is not None:
                raise ReportError("FAILED_PREDICTION_COUNT_MUST_BE_NULL")
        evaluated = []
        row_ids: set[str] = set()
        for row in evaluation.get("per_image_results", []):
            if row.get("image_id") not in records or row["image_id"] in row_ids:
                raise ReportError("EVALUATION_IMAGE_BINDING_MISMATCH")
            row_ids.add(row["image_id"])
            if row.get("status") == "EVALUATED":
                count = row.get("reference_count")
                if type(count) is not int or count < 0:
                    raise ReportError("REFERENCE_COUNT_INVALID")
                predicted = row.get("predicted_count")
                if type(predicted) is not int or predicted < 0:
                    raise ReportError("PREDICTION_COUNT_INVALID")
                if row.get("signed_count_error") != predicted - count or row.get(
                    "absolute_count_error"
                ) != abs(predicted - count):
                    raise ReportError("COUNT_ERROR_INCONSISTENT")
                evaluated.append(row)
            elif any(
                row.get(key) is not None
                for key in (
                    "reference_count",
                    "signed_count_error",
                    "absolute_count_error",
                    "tp",
                    "fp",
                    "fn",
                )
            ):
                raise ReportError("METRICS_WITHOUT_REFERENCE")
        if not evaluated and any(
            value is not None
            for key, value in evaluation.get("metrics", {}).items()
            if key in METRIC_KEYS and key not in COVERAGE_KEYS
        ):
            raise ReportError("METRICS_WITHOUT_REFERENCE")
    annotation_map: dict[str, JSONDict] = {}
    for annotation in annotations:
        _check_seal(annotation, "snapshot_hash", "ANNOTATION_HASH_MISMATCH")
        record = records.get(annotation.get("image_id"))
        if record is None or annotation.get("source_asset_hash") != record["asset_sha256"]:
            raise ReportError("ANNOTATION_IMAGE_BINDING_MISMATCH")
        if (
            annotation.get("purpose", purpose) != purpose
            or annotation.get("SYNTHETIC", dataset["SYNTHETIC"]) is not dataset["SYNTHETIC"]
        ):
            raise ReportError("DOMAIN_MISMATCH")
        if annotation["image_id"] in annotation_map:
            raise ReportError("ANNOTATION_VERSION_AMBIGUOUS")
        try:
            validate_snapshot(annotation, record)
        except AnnotationError as exc:
            raise ReportError("ANNOTATION_INVALID:" + exc.code) from exc
        _objects(annotation.get("objects") or [], record["image_width"], record["image_height"])
        annotation_map[annotation["image_id"]] = annotation
    for prediction, evaluation in zip(predictions, evaluations, strict=True):
        _validate_evaluation_math(prediction, evaluation, annotation_map, purpose, records)
    return sources, annotation_map


def _validate_evaluation_math(
    prediction: JSONDict,
    evaluation: JSONDict,
    annotations: dict[str, JSONDict],
    purpose: str,
    records: dict[str, JSONDict],
) -> None:
    """Recompute visible-count and matching evidence, without trusting display scores."""
    if evaluation.get("evaluation_protocol") != evaluation_protocol():
        raise ReportError("EVALUATION_PROTOCOL_MISMATCH")
    if evaluation.get("evaluation_protocol_hash") != canonical_hash(evaluation_protocol()):
        raise ReportError("EVALUATION_PROTOCOL_HASH_MISMATCH")
    predictions = {row["image_id"]: row for row in prediction["images"]}
    truths: dict[str, list[JSONDict]] = {}
    candidates: dict[str, list[JSONDict]] = {}
    ignored: dict[str, set[int]] = {}
    rows = evaluation.get("per_image_results", [])
    for row in rows:
        if "scene_metadata" in row and row["scene_metadata"] != (
            records[row["image_id"]].get("scene_metadata") or {}
        ):
            raise ReportError("SCENE_BINDING_MISMATCH")
        predicted = predictions.get(row["image_id"])
        if predicted is None:
            if (
                row.get("status") != "NOT_EVALUABLE"
                or row.get("predicted_count") is not None
                or "PREDICTION_MISSING" not in row.get("reason_codes", [])
            ):
                raise ReportError("EVALUATION_PREDICTION_COUNT_MISMATCH")
        elif "PREDICTION_MISSING" in row.get("reason_codes", []) or row.get(
            "predicted_count"
        ) != predicted.get("predicted_visible_fruit_count"):
            raise ReportError("EVALUATION_PREDICTION_COUNT_MISMATCH")
        snapshot = annotations.get(row["image_id"])
        if row.get("reference_hash") != (snapshot.get("snapshot_hash") if snapshot else None):
            raise ReportError("EVALUATION_REFERENCE_HASH_MISMATCH")
        if row.get("status") != "EVALUATED":
            continue
        if snapshot is None or snapshot.get("objects") is None:
            raise ReportError("METRICS_WITHOUT_REFERENCE")
        if purpose != "SYNTHETIC_ENGINEERING" and not reference_eligibility(snapshot)["eligible"]:
            raise ReportError("REFERENCE_QUALITY_NOT_ELIGIBLE")
        targets = [obj for obj in snapshot["objects"] if obj["disposition"] == "TARGET"]
        regions = [
            obj["bbox_xyxy"] for obj in snapshot["objects"] if obj["disposition"] != "TARGET"
        ]
        if predicted is None:
            raise ReportError("METRICS_WITHOUT_PREDICTION")
        detected = predicted.get("detected_objects") or []
        if row.get("reference_count") != len(targets):
            raise ReportError("REFERENCE_COUNT_MISMATCH")
        matched = match_reference(targets, detected, regions)
        for key, value in matched.items():
            if row.get(key) != value:
                raise ReportError("MATCHING_EVIDENCE_MISMATCH")
        truths[row["image_id"]] = targets
        candidates[row["image_id"]] = detected
        ignored[row["image_id"]] = set(matched["ignored_prediction_indices"])
    computed = compact_metrics(rows)
    computed["RESEARCH_AP50"] = research_ap50(truths, candidates, ignored)
    for key in METRIC_KEYS:
        if evaluation.get("metrics", {}).get(key) != computed.get(key):
            raise ReportError("METRICS_RECOMPUTATION_MISMATCH")
    for dimension, group in evaluation.get("subgroup_metrics", {}).items():
        if dimension not in {"density", "occlusion", "lighting"}:
            continue
        for name, subgroup in group.items():
            matched_rows = [
                row
                for row in rows
                if (records[row["image_id"]].get("scene_metadata", {}).get(dimension) or "UNKNOWN")
                == name
            ]
            subgroup_computed = compact_metrics(matched_rows)
            subgroup_metrics = subgroup.get("metrics", subgroup)
            for key in METRIC_KEYS:
                if key == "RESEARCH_AP50":
                    continue
                if subgroup_metrics.get(key) != subgroup_computed.get(key):
                    raise ReportError("SUBGROUP_METRICS_RECOMPUTATION_MISMATCH")


def _preview(data_root: Path, record: JSONDict, max_edge: int) -> str:
    try:
        asset = secure_load_asset(
            data_root,
            record["asset_ref"],
            expected_hash=record["asset_sha256"],
            expected_size=(record["image_width"], record["image_height"]),
        )
        verify_coordinate_metadata(record, asset)
    except ValueError as exc:
        raise ReportError(f"ASSET_LOAD_FAILED:{getattr(exc, 'code', str(exc))}") from exc
    image = Image.fromarray(asset.rgb)
    image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    stream = io.BytesIO()
    image.save(stream, format="JPEG", quality=82, optimize=False, progressive=False, subsampling=0)
    return "data:image/jpeg;base64," + base64.b64encode(stream.getvalue()).decode("ascii")


def _compact_metrics(metrics: JSONDict) -> JSONDict:
    return {key: metrics.get(key) for key in METRIC_KEYS}


def _charts(models: list[JSONDict], reports: list[JSONDict]) -> JSONDict:
    histograms = []
    for index, model in enumerate(models):
        counter = Counter(
            row["signed_count_error"]
            for row in reports[index]["per_image_results"]
            if row.get("signed_count_error") is not None
        )
        histograms.append(
            {
                "model_name": model["model_name"],
                "status": "AVAILABLE" if counter else "NOT_EVALUABLE",
                "bins": [{"error": key, "count": counter[key]} for key in sorted(counter)],
            }
        )
    return {
        "count_error_histogram": histograms,
        "precision_recall": [
            {
                "model_name": model["model_name"],
                "precision": model["metrics"].get("precision"),
                "recall": model["metrics"].get("recall"),
            }
            for model in models
        ],
        "count_mae_bias": [
            {
                "model_name": model["model_name"],
                "mae": model["metrics"].get("count_mae"),
                "bias": model["metrics"].get("count_bias"),
            }
            for model in models
        ],
        "subgroups": [
            {
                "model_name": model["model_name"],
                "density": model["subgroup_metrics"].get("density", {}),
                "occlusion": model["subgroup_metrics"].get("occlusion", {}),
            }
            for model in models
        ],
        "coverage": [
            {
                "model_name": model["model_name"],
                **{key: model["metrics"].get(key) for key in COVERAGE_KEYS},
            }
            for model in models
        ],
    }


def render_report(
    dataset: JSONDict,
    data_root: Path,
    predictions: JSONDict | list[JSONDict],
    evaluations: JSONDict | list[JSONDict],
    annotations: JSONDict | list[JSONDict] | None,
    output_dir: Path,
    *,
    public_export: bool = False,
    max_images: int = 50,
    max_embedded_bytes: int = 10_000_000,
    max_preview_edge: int = 900,
) -> JSONDict:
    """Render actual outputs; public assets require research AND redistribution authority.

    Missing-reference counts/scores stay null. Candidate annotation drafts are displayed
    separately from evaluation reference counts. All paths remain research-only; images
    are embedded as bounded previews rather than converted into public local-file URLs.
    """
    if output_dir.exists():
        raise ReportError("OUTPUT_ALREADY_EXISTS")
    if type(public_export) is not bool or type(max_images) is not int or not 1 <= max_images <= 50:
        raise ReportError("REPORT_POLICY_INVALID")
    if (
        type(max_embedded_bytes) is not int
        or not 1 <= max_embedded_bytes <= 10_000_000
        or type(max_preview_edge) is not int
        or not 64 <= max_preview_edge <= 1200
    ):
        raise ReportError("REPORT_POLICY_INVALID")
    bundles, reports = _list(predictions), _list(evaluations)
    if isinstance(annotations, dict) and "snapshots" in annotations:
        _check_seal(annotations, "annotations_hash", "ANNOTATION_BUNDLE_HASH_MISMATCH")
        annotation_versions = annotations["snapshots"]
    else:
        annotation_versions = _list(annotations)
    sources, annotation_map = _bind(dataset, bundles, reports, annotation_versions)
    pending_geometry: dict[str, list[JSONDict]] = {}
    if isinstance(annotations, dict):
        candidate_geometry = annotations.get("draft_geometry", {})
        if not isinstance(candidate_geometry, dict):
            raise ReportError("PENDING_GEOMETRY_INVALID")
        records = {record["image_id"]: record for record in dataset["images"]}
        for image_id, candidates in candidate_geometry.items():
            record = records.get(image_id)
            if record is None or image_id not in annotation_map:
                raise ReportError("PENDING_GEOMETRY_IMAGE_BINDING_MISMATCH")
            candidates = _objects(candidates, record["image_width"], record["image_height"])
            for candidate in candidates:
                if (
                    candidate.get("disposition") not in {"TARGET", "IGNORE", "UNCERTAIN"}
                    or candidate.get("class_label")
                    not in {
                        "CANDIDATE_VISIBLE_BLUEBERRY",
                        "UNRESOLVED_FRUIT_CLUSTER",
                        "NON_TARGET_DISTRACTOR",
                    }
                    or candidate.get("disposition") == "TARGET"
                    and candidate.get("class_label") != "CANDIDATE_VISIBLE_BLUEBERRY"
                ):
                    raise ReportError("PENDING_GEOMETRY_CANDIDATE_LABEL_INVALID")
            if any(
                not isinstance(candidate.get("object_id"), str)
                or not candidate["object_id"].strip()
                for candidate in candidates
            ) or len({candidate.get("object_id") for candidate in candidates}) != len(candidates):
                raise ReportError("PENDING_GEOMETRY_OBJECT_ID_INVALID")
            pending_geometry[image_id] = candidates
    models = []
    pred_maps = []
    eval_maps = []
    for bundle, evaluation in zip(bundles, reports, strict=True):
        subgroup = {
            key: {
                name: _compact_metrics(value.get("metrics", value)) for name, value in group.items()
            }
            for key, group in evaluation.get("subgroup_metrics", {}).items()
            if key in {"density", "occlusion", "lighting"}
        }
        models.append(
            {
                "model_name": bundle.get("model_name", bundle.get("model_key", "UNKNOWN")),
                "model_key": bundle.get("model_key"),
                "model_hash": bundle.get("model_hash"),
                "selected_model_hash": bundle.get("selected_model_hash"),
                "config_hash": bundle.get("config_hash"),
                "freeze_hash": bundle.get("freeze_hash"),
                "prediction_hash": bundle["prediction_hash"],
                "evaluation_hash": evaluation["report_hash"],
                "status": evaluation.get("status", "NOT_EVALUABLE"),
                "reason_codes": evaluation.get("reason_codes", []),
                "metrics": _compact_metrics(evaluation.get("metrics", {})),
                "subgroup_metrics": subgroup,
                "COCO_MAP50": evaluation.get("coco", {}).get("COCO_MAP50"),
                "COCO_MAP50_95": evaluation.get("coco", {}).get("COCO_MAP50_95"),
                "COCO_status": evaluation.get("coco", {}).get("status", "NOT_RUN"),
                "failure_count": evaluation.get(
                    "failure_count",
                    sum(
                        row.get("status") != "EVALUATED"
                        or bool(row.get("fp"))
                        or bool(row.get("fn"))
                        or bool(row.get("absolute_count_error"))
                        for row in evaluation.get("per_image_results", [])
                    ),
                ),
            }
        )
        pred_maps.append({row["image_id"]: row for row in bundle.get("images", [])})
        eval_maps.append({row["image_id"]: row for row in evaluation.get("per_image_results", [])})
    rows = []
    embedded_bytes = 0
    embedded_count = 0
    for record in sorted(dataset["images"], key=lambda item: item["image_id"])[:max_images]:
        source = sources[record["source_id"]]
        attribution_complete = source.get("attribution_required") is not True or all(
            isinstance(source.get(key), str) and source[key].strip()
            for key in ("creator", "official_url", "license_url")
        )
        permitted = not public_export or (
            source.get("redistribution") is True and attribution_complete
        )
        access_reason = (
            "ATTRIBUTION_INCOMPLETE"
            if not attribution_complete
            else "REDISTRIBUTION_NOT_AUTHORIZED"
        )
        preview = _preview(data_root, record, max_preview_edge) if permitted else None
        if preview:
            embedded_bytes += len(preview.encode("ascii"))
            embedded_count += 1
            if embedded_bytes > max_embedded_bytes:
                raise ReportError("EMBEDDED_BYTE_LIMIT")
        annotation = annotation_map.get(record["image_id"])
        image_models = []
        for prediction_map, evaluation_map in zip(pred_maps, eval_maps, strict=True):
            prediction = prediction_map.get(record["image_id"], {})
            evaluation = evaluation_map.get(record["image_id"], {})
            is_evaluated = evaluation.get("status") == "EVALUATED"
            image_models.append(
                {
                    "predicted_count": prediction.get("predicted_visible_fruit_count"),
                    "reference_count": evaluation.get("reference_count") if is_evaluated else None,
                    "signed_count_error": evaluation.get("signed_count_error")
                    if is_evaluated
                    else None,
                    "absolute_count_error": evaluation.get("absolute_count_error")
                    if is_evaluated
                    else None,
                    "tp": evaluation.get("tp") if is_evaluated else None,
                    "fp": evaluation.get("fp") if is_evaluated else None,
                    "fn": evaluation.get("fn") if is_evaluated else None,
                    "false_positive_indices": evaluation.get("false_positive_indices", [])
                    if is_evaluated
                    else [],
                    "false_negative_indices": evaluation.get("false_negative_indices", [])
                    if is_evaluated
                    else [],
                    "prediction_status": prediction.get("status", "MISSING"),
                    "evaluation_status": "EVALUATED" if is_evaluated else "NOT_EVALUABLE",
                    "reason_codes": evaluation.get("reason_codes", ["GT_MISSING"]),
                    "detected_objects": _objects(
                        prediction.get("detected_objects") or [],
                        record["image_width"],
                        record["image_height"],
                    ),
                }
            )
        rows.append(
            {
                "image_id": record["image_id"],
                "purpose": dataset["purpose"],
                "SYNTHETIC": dataset["SYNTHETIC"],
                "source_id": record["source_id"],
                "asset_sha256": record["asset_sha256"],
                "image_width": record["image_width"],
                "image_height": record["image_height"],
                "observed_at": record.get("observed_at"),
                "capture_time_status": record.get("capture_time_status", "UNKNOWN"),
                "base_identity": record.get("base_identity", {"status": "UNRESOLVED"}),
                "variety": record.get("variety") or "UNKNOWN",
                "scene": {
                    key: record.get("scene_metadata", {}).get(key) or "UNKNOWN"
                    for key in ("density", "occlusion", "lighting")
                },
                "source": {
                    key: source.get(key)
                    for key in (
                        "name",
                        "creator",
                        "official_url",
                        "license_id",
                        "license_url",
                        "license_status",
                        "research_use",
                        "redistribution",
                        "attribution_required",
                        "share_alike_derivatives",
                        "license_conditions",
                    )
                },
                "preview": preview,
                "image_access_status": "EMBEDDED_RESEARCH_PREVIEW" if permitted else access_reason,
                "preview_modifications": (
                    "EXIF normalized, RGB converted, resized, JPEG encoded; boxes are view layers. "
                    "BY-SA image derivatives retain source BY-SA license."
                )
                if preview
                else None,
                "annotation": {
                    key: annotation.get(key)
                    for key in (
                        "annotation_version",
                        "label_definition_version",
                        "snapshot_hash",
                        "review_status",
                        "gt_status",
                        "visible_count",
                        "identity_authenticated",
                    )
                }
                if annotation
                else None,
                "pending_candidate_objects": pending_geometry.get(record["image_id"], []),
                "pending_candidate_status": "UNREVIEWED_NOT_GT"
                if pending_geometry.get(record["image_id"])
                else "NONE",
                "annotation_objects": _objects(
                    annotation.get("objects") or [], record["image_width"], record["image_height"]
                )
                if annotation
                else [],
                "models": image_models,
            }
        )
    compact_rows = [{key: value for key, value in row.items() if key != "preview"} for row in rows]
    report = seal(
        {
            "report_version": VERSION,
            "dataset_id": dataset.get("dataset_id"),
            "dataset_manifest_hash": dataset["manifest_hash"],
            "purpose": dataset["purpose"],
            "SYNTHETIC": dataset["SYNTHETIC"],
            "distribution_mode": "PUBLIC_AUTHORIZED_INDEX"
            if public_export
            else "LOCAL_CONTROLLED_ONLY",
            "models": models,
            "images": compact_rows,
            "charts": _charts(models, reports),
            "dataset_coverage": {
                "total_images": len(dataset["images"]),
                "displayed_images": len(rows),
                "embedded_images": embedded_count,
                "not_displayed_images": max(0, len(dataset["images"]) - len(rows)),
            },
            "limitations": [
                "Visible fruit counts are not kg.",
                "Public external images do not approve real orchard accuracy.",
                "Unknown GT stays NOT_EVALUABLE; annotation drafts are not GT.",
                "Offline reviewer IDs are self-asserted and not authenticated.",
                "Test seals provide integrity, not access control.",
                "No COCO mAP claimed unless the recorded formal evaluator ran.",
            ],
        },
        "report_hash",
    )
    payload = {**report, "images": rows, "banner": PURPOSES[dataset["purpose"]]}
    encoded = (
        json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False)
        .replace("<", "\\u003c")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    template = Path(__file__).with_name("review_ui.html").read_text(encoding="utf-8")
    html = template.replace("__REPORT_JSON__", encoded).replace(
        "__DOMAIN_BANNER__", PURPOSES[dataset["purpose"]]
    )
    if len(html.encode("utf-8")) > 12_000_000:
        raise ReportError("REPORT_TOTAL_BYTE_LIMIT")
    output_dir.mkdir(parents=True, exist_ok=False)
    write_json_new(output_dir / "report.json", report)
    (output_dir / "report.html").write_text(html, encoding="utf-8")
    lines = [
        f"# {PURPOSES[dataset['purpose']]}",
        "",
        f"Distribution: {report['distribution_mode']}",
        "",
        "Counts are visible_fruit_per_image; no kg conversion. Unknown GT is NOT_EVALUABLE.",
        "",
        "| Model | Status | Precision | Recall | Count MAE | Count Bias |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for model in models:
        metric = model["metrics"]
        lines.append(
            f"| {model['model_name']} | {model['status']} | {metric['precision']} | "
            f"{metric['recall']} | {metric['count_mae']} | {metric['count_bias']} |"
        )
    lines.extend(
        [
            "",
            f"Coverage: {report['dataset_coverage']}",
            "",
            "Source attribution and derivative terms:",
        ]
    )
    for source in sources.values():
        lines.append(
            f"- {source.get('name')}: {source.get('creator')} — {source.get('official_url')} — "
            f"{source.get('license_id')} {source.get('license_url')}; modifications: resized "
            "RGB/JPEG preview, view-only boxes. Retain BY-SA terms where applicable."
        )
    (output_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return seal(
        {
            "report_version": VERSION,
            "report_hash": report["report_hash"],
            "distribution_mode": report["distribution_mode"],
            "embedded_count": embedded_count,
            "embedded_bytes": embedded_bytes,
            "html_path": "report.html",
            "json_path": "report.json",
            "markdown_path": "report.md",
            "dataset_manifest_hash": dataset["manifest_hash"],
            "payload_hash": canonical_hash(report),
        },
        "artifact_hash",
    )
