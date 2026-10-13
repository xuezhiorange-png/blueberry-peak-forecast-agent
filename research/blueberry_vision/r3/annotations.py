"""Immutable candidate annotation snapshots and offline, self-asserted review.

No identity authentication or business approval is conferred by this workbench.
Publisher evidence is an explicit source-review assertion, not network verification.
"""

from __future__ import annotations

import copy
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from research.blueberry_vision.evaluator import match_boxes
from research.blueberry_vision.r2_common import JSONDict, seal, verify_seal, write_json_new

SCHEMA_VERSION = "blueberry-vision-annotation-snapshot/3.0.0"
BUNDLE_VERSION = "blueberry-vision-annotations/3.0.0"
COCO_VERSION = "blueberry-vision-coco-annotations/3.0.0"
LABEL_DEFINITION_VERSION = "candidate-visible-blueberry/3.0.0"
CANDIDATE_LABEL = "CANDIDATE_VISIBLE_BLUEBERRY"
PURPOSES = {"PUBLIC_EXTERNAL_BENCHMARK", "AUTHORIZED_ORCHARD_PILOT", "SYNTHETIC_ENGINEERING"}
WORKFLOW_MODES = {"OFFLINE_SELF_ASSERTED", "SIMULATED_ENGINEERING"}
STATES = {"DRAFT", "SUBMITTED", "REVIEW_PENDING", "ADJUDICATED", "SEALED"}
TRANSITIONS = {"DRAFT": "SUBMITTED", "SUBMITTED": "REVIEW_PENDING", "ADJUDICATED": "SEALED"}


class AnnotationError(ValueError):
    """Stable reason code; never include complete image or personal records."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AnnotationError(code)
    return value


def _hash(value: Any, code: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise AnnotationError(code)
    return value


def _records(value: Any, code: str) -> list[JSONDict]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise AnnotationError(code)
    return value


def _time(at: str | None) -> str | None:
    if at is not None:
        try:
            if (
                not isinstance(at, str)
                or datetime.fromisoformat(at.replace("Z", "+00:00")).utcoffset() is None
            ):
                raise ValueError
        except (TypeError, ValueError):
            raise AnnotationError("OPERATION_TIME_INVALID") from None
    return at


def _bbox(box: Any, width: int, height: int) -> list[int | float]:
    if (
        not isinstance(box, list)
        or len(box) != 4
        or any(type(x) not in (int, float) or not math.isfinite(x) for x in box)
    ):
        raise AnnotationError("INVALID_BBOX")
    x1, y1, x2, y2 = box
    if x2 <= x1 or y2 <= y1:
        raise AnnotationError("INVALID_BBOX")
    if x1 < 0 or y1 < 0 or x2 > width or y2 > height:
        raise AnnotationError("BBOX_OUT_OF_BOUNDS")
    return list(box)


def _objects(objects: list[JSONDict] | None, width: int, height: int) -> None:
    if objects is None:
        return
    seen: set[str] = set()
    for obj in _records(objects, "OBJECTS_REQUIRED"):
        oid = _text(obj.get("object_id"), "OBJECT_ID_REQUIRED")
        if oid in seen:
            raise AnnotationError("DUPLICATE_OBJECT_ID")
        seen.add(oid)
        disposition = obj.get("disposition")
        if disposition not in {"TARGET", "IGNORE", "UNCERTAIN"}:
            raise AnnotationError("DISPOSITION_INVALID")
        label = _text(obj.get("class_label"), "CLASS_LABEL_REQUIRED")
        if disposition == "TARGET" and label != CANDIDATE_LABEL:
            raise AnnotationError("CANDIDATE_LABEL_REQUIRED")
        if label not in {CANDIDATE_LABEL, "UNRESOLVED_FRUIT_CLUSTER", "NON_TARGET_DISTRACTOR"}:
            raise AnnotationError("CANDIDATE_LABEL_REQUIRED")
        if obj.get("segmentation") is not None or obj.get("mask_polygon") is not None:
            raise AnnotationError("SEGMENTATION_NOT_SUPPORTED")
        _bbox(obj.get("bbox_xyxy"), width, height)


def _operation(operation: str, actor_id: str, at: str | None, prior_hash: str | None) -> JSONDict:
    return {
        "operation": operation,
        "actor_id": _text(actor_id, "ACTOR_ID_REQUIRED"),
        "identity_authenticated": False,
        "at": _time(at),
        "operation_time_status": "UNKNOWN" if at is None else "SELF_ASSERTED",
        "prior_snapshot_hash": prior_hash,
    }


def _source_quality(coco: JSONDict) -> JSONDict:
    """Retain known source assertions; caller provenance cannot erase them."""
    containers = [coco]
    for key in ("info", "research_provenance", "provenance"):
        metadata = coco.get(key)
        if metadata is not None:
            if not isinstance(metadata, dict):
                raise AnnotationError("PROVENANCE_INVALID")
            containers.append(metadata)
    for key in ("images", "annotations"):
        containers.extend(_records(coco.get(key), f"{key.upper()}_REQUIRED"))
    for _ in range(2):
        nested: list[JSONDict] = []
        for item in containers:
            for key in ("research_snapshot", "research_record", "research_object", "provenance"):
                value = item.get(key)
                if isinstance(value, dict) and value not in containers and value not in nested:
                    nested.append(value)
        containers.extend(nested)
    origins: set[str] = set()
    methods: set[str] = set()
    statuses: set[str] = set()
    human_reviews: set[str] = set()
    evidence_statuses: set[str] = set()
    label_approvals: set[str] = set()
    candidate = False
    prediction = False
    for item in containers:
        candidate = candidate or item.get("candidate") is True
        prediction = (
            prediction
            or bool(item.get("model_provenance"))
            or item.get("record_kind") == "model_prediction"
        )
        for key, values in (
            ("annotation_origin", origins),
            ("annotation_method", methods),
            ("annotation_status", statuses),
            ("annotation_quality_status", statuses),
            ("human_review_status", human_reviews),
            ("evidence_status", evidence_statuses),
            ("label_approval", label_approvals),
            ("label_approval_status", label_approvals),
        ):
            value = item.get(key)
            if isinstance(value, str):
                values.add(value.strip().upper().replace("-", "_").replace(" ", "_"))
        review_status = item.get("review_status")
        if isinstance(review_status, str):
            statuses.add(review_status.strip().upper())
    candidate = candidate or bool(
        statuses & {"DRAFT", "SUBMITTED", "REVIEW_PENDING", "CANDIDATE", "UNREVIEWED"}
    )
    candidate = (
        candidate
        or bool(label_approvals & {"CANDIDATE_ONLY", "DRAFT", "UNREVIEWED"})
        or bool(origins & {"UNVERIFIED", "UNKNOWN", "UNREVIEWED"})
        or any(
            value in {"UNVERIFIED", "UNKNOWN", "UNREVIEWED", "DENIED"}
            or value.startswith("PENDING")
            for value in evidence_statuses
        )
    )
    prediction = prediction or bool(
        origins & {"MODEL", "AI", "MODEL_PREDICTION", "AUTOMATIC", "AUTO", "MACHINE"}
    )
    semi_automatic = any(
        "SEMI_AUTOMATIC" in value or value == "SEMI_AUTO" for value in origins | methods
    )
    reviewed = bool(human_reviews) and human_reviews <= {
        "VERIFIED",
        "REVIEWED",
        "ADJUDICATED",
        "SEALED",
    }
    return {
        "candidate": candidate,
        "model_prediction": prediction,
        "semi_automatic": semi_automatic,
        "human_review_verified_in_source": reviewed,
        "source_annotation_origins": sorted(origins),
        "source_annotation_methods": sorted(methods),
        "source_annotation_statuses": sorted(statuses),
        "source_human_review_statuses": sorted(human_reviews),
        "source_annotation_evidence_statuses": sorted(evidence_statuses),
        "source_label_approval_statuses": sorted(label_approvals),
        "not_reference": candidate or prediction or semi_automatic and not reviewed,
    }


def create_draft(
    image_record: JSONDict,
    *,
    annotation_version: str,
    annotator_id: str,
    objects: list[JSONDict] | None = None,
    purpose: str | None = None,
    synthetic: bool | None = None,
    workflow_mode: str = "OFFLINE_SELF_ASSERTED",
    provenance: JSONDict | None = None,
    at: str | None = None,
) -> JSONDict:
    """Create candidate geometry; ``objects=None`` explicitly means unannotated."""
    if image_record.get("record_kind") == "model_prediction" or image_record.get(
        "model_provenance"
    ):
        raise AnnotationError("PREDICTION_IS_NOT_GT")
    origin = copy.deepcopy(
        provenance
        or {
            "kind": "SELF_ASSERTED_LOCAL_DRAFT",
            "annotation_origin": "UNVERIFIED",
            "evidence_status": "UNVERIFIED",
            "evidence_refs": [],
        }
    )
    if origin.get("kind") == "MODEL_PREDICTION" or origin.get("annotation_origin") in {
        "MODEL",
        "AI",
    }:
        raise AnnotationError("PREDICTION_IS_NOT_GT")
    selected_purpose = purpose if purpose is not None else image_record.get("purpose")
    selected_synthetic = synthetic if synthetic is not None else image_record.get("SYNTHETIC")
    if (
        selected_purpose not in PURPOSES
        or type(selected_synthetic) is not bool
        or selected_synthetic != (selected_purpose == "SYNTHETIC_ENGINEERING")
    ):
        raise AnnotationError("PURPOSE_SYNTHETIC_MISMATCH")
    if workflow_mode not in WORKFLOW_MODES:
        raise AnnotationError("WORKFLOW_MODE_INVALID")
    if selected_synthetic and workflow_mode != "SIMULATED_ENGINEERING":
        raise AnnotationError("SYNTHETIC_REQUIRES_SIMULATED_WORKFLOW")
    width, height = image_record.get("image_width"), image_record.get("image_height")
    if type(width) is not int or type(height) is not int or width <= 0 or height <= 0:
        raise AnnotationError("IMAGE_DIMENSIONS_INVALID")
    _objects(objects, width, height)
    rows = copy.deepcopy(objects)
    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "image_id": _text(image_record.get("image_id"), "IMAGE_ID_REQUIRED"),
        "source_asset_hash": _hash(
            image_record.get("asset_sha256", image_record.get("source_asset_hash")),
            "SOURCE_ASSET_HASH_REQUIRED",
        ),
        "source_id": _text(image_record.get("source_id"), "SOURCE_ID_REQUIRED"),
        "image_width": width,
        "image_height": height,
        "purpose": selected_purpose,
        "SYNTHETIC": selected_synthetic,
        "annotation_version": _text(annotation_version, "ANNOTATION_VERSION_REQUIRED"),
        "label_definition_version": LABEL_DEFINITION_VERSION,
        "label_approval_status": "CANDIDATE",
        "count_unit": "visible_fruit_per_image",
        "objects": rows,
        "visible_count": None
        if rows is None
        else sum(obj["disposition"] == "TARGET" for obj in rows),
        "ignore_count": None
        if rows is None
        else sum(obj["disposition"] == "IGNORE" for obj in rows),
        "uncertain_count": None
        if rows is None
        else sum(obj["disposition"] == "UNCERTAIN" for obj in rows),
        "gt_status": "UNANNOTATED" if rows is None else "COMPLETE",
        "annotator_id": _text(annotator_id, "ANNOTATOR_ID_REQUIRED"),
        "workflow_mode": workflow_mode,
        "review_status": "DRAFT",
        "identity_authenticated": False,
        "business_approved": False,
        "provenance": origin,
        "parent_snapshot_hashes": [],
        "history": [_operation("CREATE_DRAFT", annotator_id, at, None)],
    }
    return seal(snapshot, "snapshot_hash")


def validate_snapshot(snapshot: JSONDict, image: JSONDict | None = None) -> None:
    """Check semantic constraints and bindings, without authenticating human claims."""
    if not isinstance(snapshot, dict) or not verify_seal(snapshot, "snapshot_hash"):
        raise AnnotationError("SNAPSHOT_HASH_MISMATCH")
    if snapshot.get("schema_version") != SCHEMA_VERSION:
        raise AnnotationError("ANNOTATION_SCHEMA_INVALID")
    if snapshot.get("record_kind") == "model_prediction" or snapshot.get("model_provenance"):
        raise AnnotationError("PREDICTION_IS_NOT_GT")
    if (
        snapshot.get("purpose") not in PURPOSES
        or type(snapshot.get("SYNTHETIC")) is not bool
        or snapshot["SYNTHETIC"] != (snapshot["purpose"] == "SYNTHETIC_ENGINEERING")
    ):
        raise AnnotationError("PURPOSE_SYNTHETIC_MISMATCH")
    if (
        snapshot.get("workflow_mode") not in WORKFLOW_MODES
        or snapshot["SYNTHETIC"]
        and snapshot["workflow_mode"] != "SIMULATED_ENGINEERING"
    ):
        raise AnnotationError("WORKFLOW_MODE_INVALID")
    if snapshot.get("review_status") not in STATES:
        raise AnnotationError("REVIEW_STATUS_INVALID")
    if (
        snapshot.get("identity_authenticated") is not False
        or snapshot.get("business_approved") is not False
        or snapshot.get("label_approval_status") != "CANDIDATE"
    ):
        raise AnnotationError("OFFLINE_AUTHORITY_UPGRADE_FORBIDDEN")
    if (
        snapshot.get("count_unit") != "visible_fruit_per_image"
        or snapshot.get("label_definition_version") != LABEL_DEFINITION_VERSION
    ):
        raise AnnotationError("LABEL_DEFINITION_OR_UNIT_INVALID")
    for key in ("image_id", "source_id", "annotation_version", "annotator_id"):
        _text(snapshot.get(key), f"{key.upper()}_REQUIRED")
    _hash(snapshot.get("source_asset_hash"), "SOURCE_ASSET_HASH_REQUIRED")
    width, height = snapshot.get("image_width"), snapshot.get("image_height")
    if type(width) is not int or type(height) is not int or width <= 0 or height <= 0:
        raise AnnotationError("IMAGE_DIMENSIONS_INVALID")
    rows = snapshot.get("objects")
    if snapshot.get("gt_status") == "UNANNOTATED":
        if rows is not None or any(
            snapshot.get(key) is not None
            for key in ("visible_count", "ignore_count", "uncertain_count")
        ):
            raise AnnotationError("MISSING_GT_IS_NOT_ZERO")
        if snapshot["review_status"] != "DRAFT":
            raise AnnotationError("UNANNOTATED_CANNOT_SUBMIT")
    elif snapshot.get("gt_status") == "COMPLETE":
        rows = _records(rows, "OBJECTS_REQUIRED")
        _objects(rows, width, height)
        for key, disposition in (
            ("visible_count", "TARGET"),
            ("ignore_count", "IGNORE"),
            ("uncertain_count", "UNCERTAIN"),
        ):
            if type(snapshot.get(key)) is not int or snapshot[key] != sum(
                obj["disposition"] == disposition for obj in rows
            ):
                raise AnnotationError("ANNOTATION_COUNT_MISMATCH")
    else:
        raise AnnotationError("GT_STATUS_INVALID")
    provenance = snapshot.get("provenance")
    if not isinstance(provenance, dict):
        raise AnnotationError("PROVENANCE_REQUIRED")
    if provenance.get("kind") == "MODEL_PREDICTION" or provenance.get("annotation_origin") in {
        "MODEL",
        "AI",
    }:
        raise AnnotationError("PREDICTION_IS_NOT_GT")
    events = _records(snapshot.get("history"), "HISTORY_REQUIRED")
    history_state: str | None = None
    previous_clock: datetime | None = None
    for event_index, event in enumerate(events):
        _text(event.get("actor_id"), "ACTOR_ID_REQUIRED")
        if event.get("identity_authenticated") is not False:
            raise AnnotationError("OFFLINE_AUTHORITY_UPGRADE_FORBIDDEN")
        _time(event.get("at"))
        if event.get("at") is not None:
            clock = datetime.fromisoformat(event["at"].replace("Z", "+00:00"))
            if previous_clock is not None and clock < previous_clock:
                raise AnnotationError("OPERATION_TIME_ORDER_INVALID")
            previous_clock = clock
        if event_index == 0:
            if (
                event.get("operation") != "CREATE_DRAFT"
                or event.get("prior_snapshot_hash") is not None
            ):
                raise AnnotationError("REVIEW_HISTORY_STATE_MISMATCH")
            history_state = "DRAFT"
        elif event.get("operation") == "ADJUDICATE" and history_state == "REVIEW_PENDING":
            history_state = "ADJUDICATED"
        elif TRANSITIONS.get(history_state or "") == event.get("operation"):
            history_state = event["operation"]
        else:
            raise AnnotationError("REVIEW_HISTORY_STATE_MISMATCH")
        if event.get("prior_snapshot_hash") is not None:
            _hash(event["prior_snapshot_hash"], "HISTORY_HASH_INVALID")
    if not events:
        raise AnnotationError("HISTORY_REQUIRED")
    if history_state != snapshot["review_status"]:
        raise AnnotationError("REVIEW_HISTORY_STATE_MISMATCH")
    if snapshot["review_status"] in {"ADJUDICATED", "SEALED"}:
        adjudication = snapshot.get("adjudication")
        if (
            not isinstance(adjudication, dict)
            or len(adjudication.get("source_snapshot_hashes", [])) != 2
        ):
            raise AnnotationError("ADJUDICATION_REQUIRED")
    if image is not None:
        if (
            snapshot["image_id"] != image.get("image_id")
            or snapshot["source_id"] != image.get("source_id")
            or snapshot["source_asset_hash"]
            != image.get("asset_sha256", image.get("source_asset_hash"))
        ):
            raise AnnotationError("IMAGE_ASSET_MISMATCH")
        if (width, height) != (image.get("image_width"), image.get("image_height")):
            raise AnnotationError("IMAGE_DIMENSIONS_MISMATCH")
        if (
            "purpose" in image
            and snapshot["purpose"] != image["purpose"]
            or "SYNTHETIC" in image
            and snapshot["SYNTHETIC"] != image["SYNTHETIC"]
        ):
            raise AnnotationError("PURPOSE_SYNTHETIC_MISMATCH")


def _next(snapshot: JSONDict, operation: str, actor_id: str, at: str | None) -> JSONDict:
    value = copy.deepcopy(snapshot)
    value.pop("snapshot_hash")
    value["history"].append(_operation(operation, actor_id, at, snapshot["snapshot_hash"]))
    value["parent_snapshot_hashes"] = [snapshot["snapshot_hash"]]
    return value


def transition_review(
    snapshot: JSONDict, target_state: str, *, actor_id: str, at: str | None = None
) -> JSONDict:
    """Advance valid states into a new record; adjudication needs two snapshots."""
    validate_snapshot(snapshot)
    if TRANSITIONS.get(snapshot["review_status"]) != target_state:
        raise AnnotationError("ILLEGAL_REVIEW_TRANSITION")
    if snapshot["gt_status"] == "UNANNOTATED":
        raise AnnotationError("UNANNOTATED_CANNOT_SUBMIT")
    if target_state == "SEALED" and not isinstance(snapshot.get("adjudication"), dict):
        raise AnnotationError("ADJUDICATION_REQUIRED")
    result = _next(snapshot, target_state, actor_id, at)
    result["review_status"] = target_state
    result = seal(result, "snapshot_hash")
    validate_snapshot(result)
    return result


def compare_annotations(a: JSONDict, b: JSONDict, *, iou_threshold: float = 0.5) -> JSONDict:
    """One-to-one same-class matching; IDs assert separation, not human identity."""
    validate_snapshot(a)
    validate_snapshot(b)
    if any(
        a[key] != b[key]
        for key in (
            "image_id",
            "source_asset_hash",
            "image_width",
            "image_height",
            "purpose",
            "SYNTHETIC",
            "label_definition_version",
        )
    ):
        raise AnnotationError("ANNOTATION_SCOPE_MISMATCH")
    base = {
        "schema_version": "blueberry-vision-annotation-agreement/3.0.0",
        "image_id": a["image_id"],
        "snapshot_a_hash": a["snapshot_hash"],
        "snapshot_b_hash": b["snapshot_hash"],
        "iou_threshold": iou_threshold,
        "human_independence_verified": False,
        "business_approved": False,
        "purpose": a["purpose"],
        "SYNTHETIC": a["SYNTHETIC"],
    }
    if a["gt_status"] == "UNANNOTATED" or b["gt_status"] == "UNANNOTATED":
        return seal(
            {
                **base,
                "status": "NOT_EVALUABLE",
                "reason_codes": ["ANNOTATION_MISSING"],
                "signed_count_difference": None,
                "matched_target_count": None,
                "matched_target_ratio": None,
                "mean_matched_bbox_iou": None,
                "disagreement_target_count": None,
                "uncertain_ratio": None,
            },
            "agreement_hash",
        )
    first = [obj for obj in a["objects"] if obj["disposition"] == "TARGET"]
    second = [{**obj, "score": 1.0} for obj in b["objects"] if obj["disposition"] == "TARGET"]
    matched = match_boxes(first, second, iou_threshold)
    total = len(first) + len(second)
    all_rows = a["objects"] + b["objects"]
    uncertain = sum(row["disposition"] == "UNCERTAIN" for row in all_rows)
    return seal(
        {
            **base,
            "status": "COMPUTED_OFFLINE_ASSERTED",
            "reason_codes": [],
            "signed_count_difference": len(second) - len(first),
            "absolute_count_difference": abs(len(second) - len(first)),
            "matched_target_count": matched["tp"],
            "matched_target_ratio": 2 * matched["tp"] / total if total else None,
            "mean_matched_bbox_iou": sum(match["iou"] for match in matched["matches"])
            / matched["tp"]
            if matched["tp"]
            else None,
            "disagreement_target_count": matched["fp"] + matched["fn"],
            "unmatched_a_object_ids": [
                first[i]["object_id"] for i in matched["false_negative_indices"]
            ],
            "unmatched_b_object_ids": [
                second[i]["object_id"] for i in matched["false_positive_indices"]
            ],
            "matches": matched["matches"],
            "uncertain_ratio": uncertain / len(all_rows) if all_rows else None,
        },
        "agreement_hash",
    )


def adjudicate_annotations(
    a: JSONDict,
    b: JSONDict,
    objects: list[JSONDict],
    *,
    adjudicator_id: str,
    annotation_version: str,
    workflow_mode: str | None = None,
    provenance: JSONDict | None = None,
    at: str | None = None,
) -> JSONDict:
    """Record an asserted adjudication. Never automatically certify human reviews."""
    comparison = compare_annotations(a, b)
    if a["review_status"] != "REVIEW_PENDING" or b["review_status"] != "REVIEW_PENDING":
        raise AnnotationError("REVIEW_PENDING_REQUIRED")
    if a["annotator_id"] == b["annotator_id"] or a["snapshot_hash"] == b["snapshot_hash"]:
        raise AnnotationError("INDEPENDENT_ANNOTATOR_IDS_REQUIRED")
    if annotation_version in {a["annotation_version"], b["annotation_version"]}:
        raise AnnotationError("NEW_ANNOTATION_VERSION_REQUIRED")
    if adjudicator_id in {a["annotator_id"], b["annotator_id"]}:
        raise AnnotationError("INDEPENDENT_ADJUDICATOR_ID_REQUIRED")
    mode = workflow_mode or a["workflow_mode"]
    if a["workflow_mode"] != b["workflow_mode"] or mode != a["workflow_mode"]:
        raise AnnotationError("WORKFLOW_MODE_MISMATCH")
    image_record = {
        key: a[key]
        for key in ("image_id", "source_id", "image_width", "image_height", "purpose", "SYNTHETIC")
    }
    image_record["asset_sha256"] = a["source_asset_hash"]
    value = create_draft(
        image_record,
        annotation_version=annotation_version,
        annotator_id=adjudicator_id,
        objects=objects,
        workflow_mode=mode,
        provenance=provenance,
        at=at,
    )
    value["review_status"] = "ADJUDICATED"
    value["history"] = copy.deepcopy(a["history"]) + [
        _operation("ADJUDICATE", adjudicator_id, at, a["snapshot_hash"])
    ]
    value["parent_snapshot_hashes"] = [a["snapshot_hash"], b["snapshot_hash"]]
    total = len([row for row in a["objects"] + b["objects"] if row["disposition"] == "TARGET"])
    value["adjudication"] = {
        "source_snapshot_hashes": [a["snapshot_hash"], b["snapshot_hash"]],
        "asserted_annotator_ids": [a["annotator_id"], b["annotator_id"]],
        "independent_human_review_verified": False,
        "source_annotation_origins": [
            a["provenance"].get("annotation_origin"),
            b["provenance"].get("annotation_origin"),
        ],
        "comparison_hash": comparison["agreement_hash"],
        "disagreement_target_count": comparison["disagreement_target_count"],
        "adjudication_ratio": comparison["disagreement_target_count"] / total if total else None,
        "uncertain_ratio": comparison["uncertain_ratio"],
    }
    value = seal(value, "snapshot_hash")
    validate_snapshot(value)
    return value


def reference_eligibility(snapshot: JSONDict) -> JSONDict:
    """Research reference qualification, based on explicit external evidence claims.

    This does not check websites, authenticate people, or approve business labels.
    Caller must verify and retain evidence before asserting evidence_status=VERIFIED.
    """
    validate_snapshot(snapshot)
    reasons: list[str] = []
    provenance = snapshot["provenance"]
    imported_quality = provenance.get("imported_source_quality")
    declared_quality = _source_quality({"info": provenance, "images": [], "annotations": []})
    if declared_quality["not_reference"] or (
        isinstance(imported_quality, dict) and imported_quality.get("not_reference") is True
    ):
        reasons.append("SOURCE_ANNOTATION_QUALITY_NOT_REFERENCE")
    if snapshot["gt_status"] != "COMPLETE":
        reasons.append("ANNOTATION_MISSING")
    if snapshot["SYNTHETIC"] or snapshot["workflow_mode"] == "SIMULATED_ENGINEERING":
        reasons.append("SIMULATED_REVIEW_NOT_REAL_REFERENCE")
    evidence = (
        provenance.get("evidence_status") == "VERIFIED"
        and isinstance(provenance.get("evidence_refs"), list)
        and bool(provenance["evidence_refs"])
        and all(isinstance(ref, str) and ref.strip() for ref in provenance["evidence_refs"])
    )
    publisher = (
        provenance.get("kind") == "DOCUMENTED_PUBLISHER_ANNOTATION"
        and provenance.get("annotation_origin") == "HUMAN"
        and evidence
        and isinstance(provenance.get("source_annotation_version"), str)
        and bool(provenance["source_annotation_version"])
        and isinstance(provenance.get("source_annotation_hash"), str)
        and bool(re.fullmatch(r"[0-9a-f]{64}", provenance["source_annotation_hash"]))
    )
    adjudication = snapshot.get("adjudication", {})
    human = (
        provenance.get("kind") == "INDEPENDENT_HUMAN_ADJUDICATION"
        and provenance.get("annotation_origin") == "HUMAN"
        and evidence
        and provenance.get("human_attestation") == "CONFIRMED_INDEPENDENT_HUMAN_ANNOTATION"
        and snapshot["review_status"] == "SEALED"
        and adjudication.get("source_annotation_origins") == ["HUMAN", "HUMAN"]
        and len(set(adjudication.get("asserted_annotator_ids", []))) == 2
    )
    if not (publisher or human):
        reasons.append("REFERENCE_HUMAN_EVIDENCE_NOT_VERIFIED")
    return {
        "eligible": not reasons,
        "reason_codes": reasons,
        "quality_basis": "DOCUMENTED_PUBLISHER_REFERENCE"
        if publisher
        else "INDEPENDENT_HUMAN_ADJUDICATION"
        if human
        else "UNVERIFIED_CANDIDATE",
        "exposure_status": "EXPOSED_PUBLIC_BENCHMARK"
        if snapshot["purpose"] == "PUBLIC_EXTERNAL_BENCHMARK"
        else "OFFLINE_RESEARCH_REFERENCE",
        "identity_authenticated": False,
        "business_approved": False,
    }


def annotation_bundle(dataset: JSONDict, snapshots: list[JSONDict]) -> JSONDict:
    if not verify_seal(dataset, "manifest_hash"):
        raise AnnotationError("DATASET_HASH_MISMATCH")
    dataset_images = _records(dataset.get("images"), "IMAGES_REQUIRED")
    images = {row["image_id"]: row for row in dataset_images}
    if len(images) != len(dataset_images):
        raise AnnotationError("DUPLICATE_DATASET_IMAGE_ID")
    seen: set[str] = set()
    for snapshot in snapshots:
        if snapshot.get("image_id") not in images:
            raise AnnotationError("UNKNOWN_IMAGE_ID")
        if snapshot["image_id"] in seen:
            raise AnnotationError("DUPLICATE_ANNOTATION_IMAGE_ID")
        seen.add(snapshot["image_id"])
        image_record = {
            **images[snapshot["image_id"]],
            "purpose": dataset["purpose"],
            "SYNTHETIC": dataset["SYNTHETIC"],
        }
        validate_snapshot(snapshot, image_record)
    return seal(
        {
            "schema_version": BUNDLE_VERSION,
            "dataset_manifest_hash": dataset["manifest_hash"],
            "purpose": dataset["purpose"],
            "SYNTHETIC": dataset["SYNTHETIC"],
            "snapshots": copy.deepcopy(snapshots),
        },
        "annotations_hash",
    )


def save_snapshot(output_dir: Path, snapshot: JSONDict) -> Path:
    """Content-addressed immutable history, never overwrite a former GT version."""
    validate_snapshot(snapshot)
    path = output_dir / f"{snapshot['snapshot_hash']}.json"
    write_json_new(path, snapshot)
    return path


def export_coco(annotations: JSONDict | list[JSONDict]) -> JSONDict:
    if isinstance(annotations, dict):
        if not verify_seal(annotations, "annotations_hash"):
            raise AnnotationError("ANNOTATIONS_HASH_MISMATCH")
        snapshots = _records(annotations.get("snapshots"), "SNAPSHOTS_REQUIRED")
    else:
        snapshots = _records(annotations, "SNAPSHOTS_REQUIRED")
    labels: set[str] = set()
    ids: set[str] = set()
    purposes: set[tuple[str, bool]] = set()
    for snapshot in snapshots:
        validate_snapshot(snapshot)
        purposes.add((snapshot["purpose"], snapshot["SYNTHETIC"]))
        if len(purposes) > 1:
            raise AnnotationError("PURPOSE_SYNTHETIC_MISMATCH")
        if snapshot["image_id"] in ids:
            raise AnnotationError("DUPLICATE_ANNOTATION_IMAGE_ID")
        ids.add(snapshot["image_id"])
        labels.update(obj["class_label"] for obj in snapshot["objects"] or [])
    categories = {label: index + 1 for index, label in enumerate(sorted(labels))}
    images: list[JSONDict] = []
    rows: list[JSONDict] = []
    for index, snapshot in enumerate(snapshots, 1):
        images.append(
            {
                "id": index,
                "research_image_id": snapshot["image_id"],
                "width": snapshot["image_width"],
                "height": snapshot["image_height"],
                "research_snapshot": copy.deepcopy(snapshot),
            }
        )
        for obj in snapshot["objects"] or []:
            x1, y1, x2, y2 = obj["bbox_xyxy"]
            rows.append(
                {
                    "id": len(rows) + 1,
                    "image_id": index,
                    "category_id": categories[obj["class_label"]],
                    "bbox": [x1, y1, x2 - x1, y2 - y1],
                    "area": (x2 - x1) * (y2 - y1),
                    "iscrowd": int(obj["disposition"] != "TARGET"),
                    "research_object": copy.deepcopy(obj),
                }
            )
    return seal(
        {
            "images": images,
            "annotations": rows,
            "categories": [{"id": index, "name": label} for label, index in categories.items()],
            "research_provenance": {
                "schema_version": COCO_VERSION,
                "business_approved": False,
                "identity_authenticated": False,
                "count_unit": "visible_fruit_per_image",
                "label_approval_status": "CANDIDATE",
            },
        },
        "adapter_hash",
    )


def _id(value: Any, code: str) -> int:
    if type(value) is not int or value <= 0:
        raise AnnotationError(code)
    return value


def import_annotations(
    dataset: JSONDict,
    coco: JSONDict,
    *,
    annotation_version: str | None = None,
    category_mapping: dict[int, str] | None = None,
    image_mapping: dict[int, str] | None = None,
    provenance: JSONDict | None = None,
    annotator_id: str = "external-import",
    workflow_mode: str = "OFFLINE_SELF_ASSERTED",
) -> JSONDict:
    """Strict COCO conversion. Ordinary imports require explicit source evidence.

    Controlled round trips preserve snapshots exactly and reject altered geometry.
    Edits belong in fresh create_draft snapshots, not reused reference versions.
    """
    if coco.get("record_kind") == "model_prediction" or coco.get("model_provenance"):
        raise AnnotationError("PREDICTION_IS_NOT_GT")
    research_provenance = coco.get("research_provenance", {})
    if not isinstance(research_provenance, dict):
        raise AnnotationError("PROVENANCE_INVALID")
    controlled = research_provenance.get("schema_version") == COCO_VERSION
    if controlled and (
        research_provenance.get("business_approved") is not False
        or research_provenance.get("identity_authenticated") is not False
        or research_provenance.get("label_approval_status") != "CANDIDATE"
        or research_provenance.get("count_unit") != "visible_fruit_per_image"
    ):
        raise AnnotationError("OFFLINE_AUTHORITY_UPGRADE_FORBIDDEN")
    if not controlled and (
        annotation_version is None or provenance is None or category_mapping is None
    ):
        raise AnnotationError("EXTERNAL_PROVENANCE_REQUIRED")
    quality = _source_quality(coco) if not controlled else None
    imported_provenance = copy.deepcopy(provenance)
    if quality is not None:
        if quality["model_prediction"]:
            raise AnnotationError("PREDICTION_IS_NOT_GT")
        assert imported_provenance is not None
        if quality["not_reference"] and (
            imported_provenance.get("kind")
            in {"DOCUMENTED_PUBLISHER_ANNOTATION", "INDEPENDENT_HUMAN_ADJUDICATION"}
            or imported_provenance.get("annotation_origin") == "HUMAN"
            and imported_provenance.get("evidence_status") == "VERIFIED"
        ):
            raise AnnotationError("ANNOTATION_PROVENANCE_AUTHORITY_UPGRADE")
        imported_provenance["imported_source_quality"] = quality
        source_info = coco.get("info", {})
        if (
            "purpose" in source_info
            and source_info["purpose"] != dataset.get("purpose")
            or "SYNTHETIC" in source_info
            and source_info["SYNTHETIC"] != dataset.get("SYNTHETIC")
        ):
            raise AnnotationError("PURPOSE_SYNTHETIC_MISMATCH")
    indexed = {row["image_id"]: row for row in _records(dataset.get("images"), "IMAGES_REQUIRED")}
    categories: dict[int, str] = {}
    for category_record in _records(coco.get("categories"), "CATEGORIES_REQUIRED"):
        cid = _id(category_record.get("id"), "INVALID_CATEGORY_ID")
        if cid in categories:
            raise AnnotationError("DUPLICATE_CATEGORY_ID")
        categories[cid] = _text(category_record.get("name"), "CATEGORY_NAME_REQUIRED")
    images: dict[int, tuple[JSONDict, JSONDict | None]] = {}
    image_ids: set[str] = set()
    for row in _records(coco.get("images"), "IMAGES_REQUIRED"):
        cid = _id(row.get("id"), "INVALID_COCO_IMAGE_ID")
        if cid in images:
            raise AnnotationError("DUPLICATE_COCO_IMAGE_ID")
        mapped = row.get("research_image_id") if controlled else (image_mapping or {}).get(cid)
        if mapped not in indexed or mapped in image_ids:
            raise AnnotationError("UNKNOWN_OR_DUPLICATE_IMAGE_ID")
        assert isinstance(mapped, str)
        image_ids.add(mapped)
        image_record = {
            **indexed[mapped],
            "purpose": dataset["purpose"],
            "SYNTHETIC": dataset["SYNTHETIC"],
        }
        if not controlled:
            source_info = coco.get("info", {})
            declared_asset_hashes = [
                row[key] for key in ("source_asset_hash", "asset_sha256") if key in row
            ]
            if len(coco["images"]) == 1:
                declared_asset_hashes.extend(
                    source_info[key]
                    for key in ("source_asset_hash", "asset_sha256")
                    if key in source_info
                )
            if any(
                declared_hash != image_record.get("asset_sha256")
                for declared_hash in declared_asset_hashes
            ):
                raise AnnotationError("IMAGE_ASSET_MISMATCH")
            if (
                row.get("source_image_id") is not None
                and row["source_image_id"] != image_record["image_id"]
            ):
                raise AnnotationError("IMAGE_ASSET_MISMATCH")
            orientation = image_record.get("exif_orientation")
            if orientation is not None and (
                type(orientation) is not int or orientation not in range(1, 9)
            ):
                raise AnnotationError("EXIF_METADATA_INVALID")
            if orientation != 1:
                assert imported_provenance is not None
                frame = imported_provenance.get(
                    "coordinate_frame", imported_provenance.get("annotation_coordinate_frame")
                )
                frame_status = imported_provenance.get(
                    "coordinate_frame_status",
                    imported_provenance.get("coordinate_frame_evidence_status"),
                )
                frame_refs = imported_provenance.get("coordinate_frame_evidence_refs")
                if frame_refs is None and isinstance(
                    imported_provenance.get("coordinate_frame_evidence_ref"), str
                ):
                    frame_refs = [imported_provenance["coordinate_frame_evidence_ref"]]
                if (
                    frame != "EXIF_NORMALIZED_RGB_HALF_OPEN_XYXY"
                    or frame_status != "VERIFIED"
                    or not isinstance(frame_refs, list)
                    or not frame_refs
                    or any(not isinstance(ref, str) or not ref.strip() for ref in frame_refs)
                ):
                    raise AnnotationError("ANNOTATION_COORDINATE_FRAME_UNVERIFIED")
                if (
                    image_record.get("image_coordinate_frame")
                    != "EXIF_NORMALIZED_RGB_HALF_OPEN_XYXY"
                ):
                    raise AnnotationError("IMAGE_COORDINATE_FRAME_INVALID")
        if (
            type(row.get("width")) is not int
            or type(row.get("height")) is not int
            or (row["width"], row["height"])
            != (image_record["image_width"], image_record["image_height"])
        ):
            raise AnnotationError("IMAGE_DIMENSIONS_MISMATCH")
        snapshot = row.get("research_snapshot") if controlled else None
        if controlled:
            if not isinstance(snapshot, dict):
                raise AnnotationError("SNAPSHOT_REQUIRED")
            validate_snapshot(snapshot, image_record)
        images[cid] = (image_record, snapshot)
    objects: dict[int, list[JSONDict]] = {cid: [] for cid in images}
    annotation_ids: set[int] = set()
    for row in _records(coco.get("annotations"), "ANNOTATIONS_REQUIRED"):
        aid = _id(row.get("id"), "INVALID_ANNOTATION_ID")
        if aid in annotation_ids:
            raise AnnotationError("DUPLICATE_ANNOTATION_ID")
        annotation_ids.add(aid)
        iid = _id(row.get("image_id"), "INVALID_COCO_IMAGE_ID")
        category = _id(row.get("category_id"), "INVALID_CATEGORY_ID")
        if iid not in images or category not in categories:
            raise AnnotationError("UNKNOWN_IMAGE_OR_CATEGORY_ID")
        if row.get("segmentation") is not None:
            raise AnnotationError("SEGMENTATION_NOT_SUPPORTED")
        image_record, _ = images[iid]
        raw = row.get("bbox")
        if (
            not isinstance(raw, list)
            or len(raw) != 4
            or any(type(x) not in (int, float) or not math.isfinite(x) for x in raw)
        ):
            raise AnnotationError("INVALID_BBOX")
        x, y, width, height = raw
        box = _bbox(
            [x, y, x + width, y + height], image_record["image_width"], image_record["image_height"]
        )
        if type(row.get("iscrowd", 0)) is not int or row.get("iscrowd", 0) not in (0, 1):
            raise AnnotationError("INVALID_ISCROWD")
        if controlled:
            obj = row.get("research_object")
            if (
                not isinstance(obj, dict)
                or obj.get("bbox_xyxy") != box
                or obj.get("class_label") != categories[category]
                or row.get("iscrowd", 0) != int(obj.get("disposition") != "TARGET")
            ):
                raise AnnotationError("COCO_SNAPSHOT_GEOMETRY_MISMATCH")
            objects[iid].append(copy.deepcopy(obj))
        else:
            assert category_mapping is not None
            label = category_mapping.get(category)
            if label is None:
                raise AnnotationError("CATEGORY_MAPPING_REQUIRED")
            disposition = row.get("disposition", "IGNORE" if row.get("iscrowd", 0) else "TARGET")
            if disposition not in {"TARGET", "IGNORE", "UNCERTAIN"}:
                raise AnnotationError("DISPOSITION_INVALID")
            if row.get("iscrowd", 0) and disposition == "TARGET":
                raise AnnotationError("ISCROWD_DISPOSITION_CONFLICT")
            objects[iid].append(
                {
                    "object_id": f"coco-{aid}",
                    "class_label": label,
                    "bbox_xyxy": box,
                    "disposition": disposition,
                }
            )
    snapshots: list[JSONDict] = []
    draft_geometry: dict[str, list[JSONDict]] = {}
    for iid, (image_record, snapshot) in images.items():
        if snapshot is not None:
            if objects[iid] != (snapshot["objects"] or []):
                raise AnnotationError("COCO_SNAPSHOT_GEOMETRY_MISMATCH")
            snapshots.append(copy.deepcopy(snapshot))
        else:
            assert annotation_version is not None and imported_provenance is not None
            source_info = coco.get("info", {})
            source_objects: list[JSONDict] | None = objects[iid]
            if (
                quality is not None
                and quality["candidate"]
                and source_info.get("gt_status") != "COMPLETE"
            ):
                source_objects = None
                draft_geometry[image_record["image_id"]] = copy.deepcopy(objects[iid])
            snapshots.append(
                create_draft(
                    image_record,
                    annotation_version=annotation_version,
                    annotator_id=annotator_id,
                    objects=source_objects,
                    workflow_mode=workflow_mode,
                    provenance=imported_provenance,
                )
            )
    if controlled and not verify_seal(coco, "adapter_hash"):
        raise AnnotationError("COCO_ADAPTER_HASH_MISMATCH")
    result = annotation_bundle(dataset, snapshots)
    if draft_geometry:
        result = seal({**result, "draft_geometry": draft_geometry}, "annotations_hash")
    return result
