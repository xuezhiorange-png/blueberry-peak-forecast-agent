"""Pre-register all eight complete images; never select ROIs from model errors.

R3 snapshots keep their physical meaning. The R4 guideline is an additional,
hash-bound research instruction, not a quiet replacement of the R3 label contract.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
from pathlib import Path

from ..assets import AssetPolicy, _read_authorized
from ..r2_common import JSONDict, canonical_hash, seal, verify_seal
from ..r3.contracts import validate_manifest
from ..r3.ingestion import secure_load_asset, verify_coordinate_metadata
from ..r3.report import _preview
from .sources import source_admission

LABEL_VERSION = "r4-visible-single-berry-research/1.0.0"
LABEL_RULES: JSONDict = {
    "version": LABEL_VERSION,
    "status": "PRE_REGISTERED_RESEARCH_CANDIDATE_NOT_BUSINESS_APPROVED",
    "target": "One individually distinguishable visible blueberry, any candidate color.",
    "bbox": "Tight visible extent, normalized full-resolution RGB, half-open xyxy.",
    "occlusion": "Count only if a separate fruit is identifiable; no inferred hidden fruit.",
    "touching": "Separate boxes only when distinct fruit boundaries are distinguishable.",
    "cropped_edge": "Count identifiable visible portions at image edges; clip to image.",
    "small_target": (
        "No inferred target below 3 pixels of visible extent on either axis; mark uncertain region."
    ),
    "ignore": "UNRESOLVED_FRUIT_CLUSTER / IGNORE for regions not individually separable.",
    "unknown": "UNCERTAIN for ambiguous fruit identity; cannot establish zero from missing labels.",
    "distractor": "NON_TARGET_DISTRACTOR / IGNORE; never a TARGET.",
    "completeness": (
        "Inspect full-resolution image; explicit COMPLETE required, empty only after review."
    ),
    "scoring": (
        "IoU .5; one-to-one; ignore overlap .5; "
        "raw predicted count includes ignored candidates (R3 protocol)."
    ),
    "unresolved_counts": (
        "Unresolved clusters or uncertain fruit counts block single-fruit count accuracy."
    ),
    "roi_policy": "ALL_ADMITTED_FULL_FRAMES_NO_ERROR_BASED_SELECTION",
    "independence": (
        "A/B work separately; no predictions, source candidate geometry or other reviewer answers."
    ),
}


def build_package(dataset: JSONDict) -> JSONDict:
    validate_manifest(dataset)
    if dataset["SYNTHETIC"] or dataset["purpose"] != "PUBLIC_EXTERNAL_BENCHMARK":
        raise ValueError("REAL_PUBLIC_IMAGES_REQUIRED")
    for source in dataset["sources"]:
        if not source_admission(source)["eligible"]:
            raise ValueError("SOURCE_NOT_AUTHORIZED")
    images = [
        {
            "image_id": image["image_id"],
            "source_asset_hash": image["asset_sha256"],
            "original_asset_hash": image.get("original_asset_sha256") or image["asset_sha256"],
            "source_id": image["source_id"],
            "license_id": image["license_id"],
            "image_width": image["image_width"],
            "image_height": image["image_height"],
            "roi_xyxy": [0, 0, image["image_width"], image["image_height"]],
            "roi_scale_to_image": [1, 1],
            "coordinate_frame": "EXIF_NORMALIZED_RGB_HALF_OPEN_XYXY",
            "reference_count": None,
            "gt_status": "HUMAN_ANNOTATION_PENDING",
        }
        for image in sorted(dataset["images"], key=lambda image: image["image_id"])
    ]
    scope_hash = canonical_hash(images)
    return seal(
        {
            "schema_version": "blueberry-human-work-package/4.0.0",
            "SYNTHETIC": False,
            "purpose": "PUBLIC_EXTERNAL_BENCHMARK",
            "dataset_manifest_hash": dataset["manifest_hash"],
            "label_rules": LABEL_RULES,
            "label_rules_hash": canonical_hash(LABEL_RULES),
            "images": images,
            "scope_hash": scope_hash,
            "tasks": {
                slot: {
                    "task_id": canonical_hash([scope_hash, slot]),
                    "role": slot,
                    "assigned_human_id": None,
                    "status": "UNASSIGNED",
                    "identity_verified": False,
                }
                for slot in ("A", "B", "ADJUDICATOR")
            },
            "snapshot_contract": "blueberry-vision-annotation-snapshot/3.0.0",
            "annotation_view": "NORMALIZED_FULL_RESOLUTION_REQUIRED_PREVIEWS_NOT_REFERENCE",
            "exposure": "EXPOSED_EXTERNAL_EVALUATION_R3_PREDICTIONS_ALREADY_PUBLIC",
            "qualified_gt": False,
            "production_vision_approved": False,
        },
        "package_hash",
    )


def validate_package(package: JSONDict, dataset: JSONDict) -> None:
    if not verify_seal(package, "package_hash"):
        raise ValueError("PACKAGE_HASH_INVALID")
    if package != build_package(dataset):
        raise ValueError("PACKAGE_REGISTRATION_MISMATCH")


def project_boxes(boxes: list[JSONDict], roi: list[int | float]) -> list[JSONDict]:
    """Fixed centroid-in-half-open ROI; clip and translate both GT and predictions.

    Current registered scope is full-frame, so no target or prediction is discarded.
    Partial ROI research would require its own prior registration and references.
    """
    if (
        len(roi) != 4
        or any(type(v) not in (int, float) or not math.isfinite(v) for v in roi)
        or not 0 <= roi[0] < roi[2]
        or not 0 <= roi[1] < roi[3]
    ):
        raise ValueError("ROI_INVALID")
    x1, y1, x2, y2 = roi
    result = []
    for obj in boxes:
        a, b, c, d = obj["bbox_xyxy"]
        if x1 <= (a + c) / 2 < x2 and y1 <= (b + d) / 2 < y2:
            result.append(
                {
                    **obj,
                    "bbox_xyxy": [
                        max(a, x1) - x1,
                        max(b, y1) - y1,
                        min(c, x2) - x1,
                        min(d, y2) - y1,
                    ],
                }
            )
    return result


def clean_editor(
    package: JSONDict,
    dataset: JSONDict,
    data_root: Path,
    output: Path,
    *,
    slot: str,
    preview_only: bool = False,
) -> JSONDict:
    """Reuse the R3 editor with no model/GT/candidate answers supplied at all.

    Full-resolution local views embed hash-verified original bytes (orientation 1).
    A small public preview is explicitly unusable as the final annotation source.
    No network, upload, authenticated-review claim, or GT creation happens here.
    """
    validate_package(package, dataset)
    if slot not in package["tasks"]:
        raise ValueError("TASK_ROLE_INVALID")
    if output.exists():
        raise ValueError("OUTPUT_ALREADY_EXISTS")
    html = Path(__file__).parents[1].joinpath("r3/review_ui.html").read_text()
    sources = {value["source_id"]: value for value in dataset["sources"]}
    rows = []
    for record in sorted(dataset["images"], key=lambda row: row["image_id"]):
        source = sources[record["source_id"]]
        permitted = source.get("redistribution") is True and (
            source.get("attribution_required") is not True
            or all(source.get(key) for key in ("creator", "official_url", "license_url"))
        )
        row = {
            key: record.get(key)
            for key in (
                "image_id",
                "source_id",
                "image_width",
                "image_height",
                "purpose",
                "SYNTHETIC",
                "observed_at",
                "base_identity",
                "asset_sha256",
                "variety",
                "capture_time_status",
            )
        }
        row.update(
            {
                "source": source,
                "annotation": None,
                "annotation_objects": [],
                "pending_candidate_objects": [],
                "pending_candidate_status": "NONE",
                "scene": dict.fromkeys(("density", "occlusion", "lighting"), "UNKNOWN"),
                "preview_modifications": "Preview resize; source license retained.",
                "image_access_status": "AUTHORIZED_ANNOTATION_VIEW"
                if permitted
                else "LOCAL_CONTROLLED_ONLY",
                "preview": _preview(data_root, record, 320)
                if not preview_only or permitted
                else None,
            }
        )
        rows.append(row)
    payload = {
        "images": rows,
        "dataset_manifest_hash": dataset["manifest_hash"],
        "purpose": dataset["purpose"],
        "SYNTHETIC": False,
        "distribution_mode": "PUBLIC_AUTHORIZED_INDEX" if preview_only else "LOCAL_CONTROLLED_ONLY",
        "dataset_coverage": {
            "displayed_images": len(rows),
            "total_images": len(rows),
            "embedded_images": sum(bool(row["preview"]) for row in rows),
        },
        "charts": {"count_error_histogram": [{"bins": []}]},
    }
    # Null UI slots allow the inherited editor to render; they are explicitly NOT
    # model inference, reference annotations, or algorithm evidence.
    blank = {
        "predicted_count": None,
        "reference_count": None,
        "signed_count_error": None,
        "detected_objects": [],
        "prediction_status": "NOT_RUN",
        "evaluation_status": "ANNOTATION_ONLY",
        "reason_codes": ["HUMAN_ANNOTATION_PENDING"],
    }
    metric_keys = (
        "precision",
        "recall",
        "count_mae",
        "count_bias",
        "failed_count",
        "missing_count",
        "missing_prediction_count",
    )
    payload["models"] = [
        {
            "model_name": "ANNOTATION_ONLY_NO_INFERENCE",
            "status": "ANNOTATION_ONLY",
            "reason_codes": [],
            "metrics": dict.fromkeys(metric_keys),
            "subgroup_metrics": {},
        }
    ]
    records = {row["image_id"]: row for row in dataset["images"]}
    for row in payload["images"]:
        row["models"] = [blank]
        if not preview_only:
            record = records[row["image_id"]]
            loaded = secure_load_asset(
                data_root,
                record["asset_ref"],
                expected_hash=record["asset_sha256"],
                expected_size=(record["image_width"], record["image_height"]),
            )
            verify_coordinate_metadata(record, loaded)
            if loaded.metadata["exif_orientation"] != 1:
                raise ValueError("FULL_RESOLUTION_ORIENTATION_ADAPTER_REQUIRED")
            # secure_load_asset already rejects symlinks; recheck via its second
            # read before embedding bytes to prevent replacement being accepted.
            raw = _read_authorized(data_root, record["asset_ref"], AssetPolicy())

            if hashlib.sha256(raw).hexdigest() != record["asset_sha256"]:
                raise ValueError("ASSET_CHANGED_DURING_VIEW_EXPORT")
            mime = "image/png" if raw.startswith(b"\x89PNG") else "image/jpeg"
            row["preview"] = "data:" + mime + ";base64," + base64.b64encode(raw).decode("ascii")
            row["preview_modifications"] = (
                "Original verified input bytes; normalized orientation 1."
            )
    payload["annotation_only"] = True
    payload["package_hash"] = package["package_hash"]
    payload["task_id"] = package["tasks"][slot]["task_id"]
    payload["task_role"] = slot
    payload["full_resolution"] = not preview_only
    payload["label_rules_hash"] = package["label_rules_hash"]
    payload["banner"] = (
        "PREVIEW ONLY — NOT A QUALIFIED ANNOTATION SOURCE"
        if preview_only
        else f"INDEPENDENT HUMAN TASK {slot} — NO MODEL ANSWERS — REVIEW PENDING"
    )
    payload["report_hash"] = canonical_hash(payload)
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c")
    html = html.replace("__REPORT_JSON__", encoded).replace("__DOMAIN_BANNER__", payload["banner"])
    style = "<style>.summary,.chart-grid,.count-grid,#exportAnalysis,#copyDraft{display:none}"
    style += ".control:has(#modelSelect),.control:has(#filterSelect),label:has(#showPred),"
    style += (
        "label:has(#showGT),label:has(#showErrors),label:has(#showCandidates){display:none}</style>"
    )
    html = html.replace("</head>", style + "</head>").replace(
        "Image admission, annotation &amp; model review", "Independent human annotation task"
    )
    html = html.replace("Independent vision research · R3", "Qualified reference preparation · R4")
    html = html.replace(
        "function draw(){",
        "$('showPred').checked=false;$('showCandidates').checked=false;function draw(){",
    )
    html = html.replace(
        "bundle.annotations_hash=await draftDigest(bundle);",
        "bundle.work_package_binding={package_hash:report.package_hash,"
        "task_id:report.task_id,task_role:report.task_role,"
        "label_rules_hash:report.label_rules_hash,full_resolution:report.full_resolution};"
        "bundle.annotations_hash=await draftDigest(bundle);",
    )
    if len(html.encode()) > 30_000_000:
        raise ValueError("WORK_PACKAGE_VIEW_SIZE_LIMIT")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        stream.write(html)
    return {
        "task_id": payload["task_id"],
        "package_hash": package["package_hash"],
        "preview_only": preview_only,
        "image_count": len(payload["images"]),
        "prediction_objects_supplied": 0,
        "source_candidate_objects_supplied": 0,
        "qualified_gt": False,
        "full_resolution": not preview_only,
    }
