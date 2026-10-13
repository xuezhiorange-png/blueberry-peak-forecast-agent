"""R3 snapshot/task QC and additional externally verified human-reference gate.

No function invents reviewers, authenticates identities, signs approvals or upgrades
drafts. Hashes prove integrity only. A data owner must genuinely verify the human
and source evidence before supplying a research approval receipt; false receipts
cannot be detected solely from their self-consistent JSON/hash values.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

from ..assets import AssetPolicy, _read_authorized
from ..r2_common import JSONDict, seal, verify_seal
from ..r3.annotations import compare_annotations, reference_eligibility, validate_snapshot
from ..r3.ingestion import _guard_root
from .package import validate_package


def import_task(dataset: JSONDict, package: JSONDict, bundle: JSONDict, slot: str) -> JSONDict:
    validate_package(package, dataset)
    if slot not in {"A", "B"}:
        raise ValueError("ANNOTATION_TASK_ROLE_INVALID")
    if not verify_seal(bundle, "annotations_hash"):
        raise ValueError("ANNOTATION_BUNDLE_HASH_INVALID")
    if (
        bundle.get("dataset_manifest_hash") != dataset["manifest_hash"]
        or bundle.get("purpose") != dataset["purpose"]
        or bundle.get("SYNTHETIC") is not False
    ):
        raise ValueError("ANNOTATION_DATASET_BINDING_MISMATCH")
    binding = bundle.get("work_package_binding", {})
    if binding.get("full_resolution") is not True:
        raise ValueError("PREVIEW_NOT_ANNOTATION_SOURCE")
    expected = {
        "package_hash": package["package_hash"],
        "task_role": slot,
        "task_id": package["tasks"][slot]["task_id"],
        "label_rules_hash": package["label_rules_hash"],
        "full_resolution": True,
    }
    if binding != expected:
        raise ValueError("TASK_BINDING_MISMATCH")
    records = {record["image_id"]: record for record in dataset["images"]}
    snapshots = bundle.get("snapshots")
    if not isinstance(snapshots, list) or not snapshots:
        raise ValueError("SNAPSHOTS_REQUIRED")
    seen = set()
    rows = []
    for snapshot in snapshots:
        image_id = snapshot.get("image_id")
        if image_id not in records or image_id in seen:
            raise ValueError("SNAPSHOT_IMAGE_UNKNOWN_OR_DUPLICATE")
        seen.add(image_id)
        validate_snapshot(snapshot, records[image_id])
        targets = [obj for obj in snapshot.get("objects") or [] if obj["disposition"] == "TARGET"]
        if len({tuple(obj["bbox_xyxy"]) for obj in targets}) != len(targets):
            raise ValueError("DUPLICATE_TARGET_GEOMETRY")
        if any(
            obj["bbox_xyxy"][2] - obj["bbox_xyxy"][0] < 3
            or obj["bbox_xyxy"][3] - obj["bbox_xyxy"][1] < 3
            for obj in targets
        ):
            raise ValueError("TARGET_BELOW_REGISTERED_SIZE")
        reasons = []
        if snapshot["gt_status"] != "COMPLETE":
            reasons.append("ANNOTATION_INCOMPLETE")
        if any(
            obj["disposition"] == "UNCERTAIN" or obj["class_label"] == "UNRESOLVED_FRUIT_CLUSTER"
            for obj in snapshot.get("objects") or []
        ):
            reasons.append("VISIBLE_COUNT_SCOPE_UNRESOLVED")
        rows.append(
            {
                "image_id": image_id,
                "snapshot_hash": snapshot["snapshot_hash"],
                "candidate_count": snapshot["visible_count"],
                "reason_codes": reasons,
                "review_status": snapshot["review_status"],
                "qualified_gt": False,
            }
        )
    return seal(
        {
            "task_id": binding["task_id"],
            "package_hash": package["package_hash"],
            "annotations_hash": bundle["annotations_hash"],
            "per_image": rows,
            "missing_images": sorted(set(records) - seen),
            "identity_verified_by_tool": False,
            "qualified_gt": False,
        },
        "qc_hash",
    )


def review_pair(
    dataset: JSONDict, package: JSONDict, first: JSONDict | None, second: JSONDict | None
) -> JSONDict:
    validate_package(package, dataset)
    for slot, bundle in (("A", first), ("B", second)):
        if bundle is not None:
            import_task(dataset, package, bundle, slot)
    a = {row["image_id"]: row for row in (first or {}).get("snapshots", [])}
    b = {row["image_id"]: row for row in (second or {}).get("snapshots", [])}
    reasons = ["HUMAN_IDENTITY_AND_INDEPENDENCE_EVIDENCE_PENDING", "ADJUDICATION_PENDING"]
    rows = []
    for image in package["images"]:
        left, right = a.get(image["image_id"]), b.get(image["image_id"])
        if left and right and left["annotator_id"] == right["annotator_id"]:
            reasons.append("ANNOTATOR_ID_COLLISION")
        comparison = compare_annotations(left, right) if left and right else None
        rows.append(
            {
                "image_id": image["image_id"],
                "comparison": comparison,
                "status": "SELF_ASSERTED_DRAFT_COMPARISON_ONLY"
                if comparison
                else "HUMAN_REVIEW_PENDING",
                "reference_count": None,
            }
        )
    return seal(
        {
            "package_hash": package["package_hash"],
            "per_image": rows,
            "status": "HUMAN_REVIEW_PENDING",
            "reason_codes": sorted(set(reasons)),
            "independent_human_reviews_completed": 0,
            "adjudicated_reference_images": 0,
            "qualified_gt": False,
            "human_consistency_validated": False,
        },
        "review_hash",
    )


def qualify_reference(
    image: JSONDict,
    package: JSONDict,
    snapshot: JSONDict | None,
    *,
    approval: JSONDict | None = None,
    evidence_root: Path | None = None,
) -> JSONDict:
    """Consume a genuine data-owner verification receipt; never create one.

    Owner receipts and evidence are supplied explicitly from authorized storage.
    This verifies hash/scope/required attestations, not human authenticity. No real
    receipt was supplied in R4; absence always blocks real metrics.
    """
    reasons = []
    if not verify_seal(package, "package_hash"):
        raise ValueError("PACKAGE_HASH_INVALID")
    registered = next(
        (row for row in package["images"] if row["image_id"] == image["image_id"]), None
    )
    if (
        registered is None
        or registered["source_asset_hash"] != image["asset_sha256"]
        or image.get("SYNTHETIC") is not False
    ):
        reasons.append("REAL_IMAGE_SCOPE_MISMATCH")
    if snapshot is None:
        reasons.append("GT_MISSING")
    else:
        validate_snapshot(snapshot, image)
        targets = [obj for obj in snapshot.get("objects") or [] if obj["disposition"] == "TARGET"]
        if len({tuple(obj["bbox_xyxy"]) for obj in targets}) != len(targets):
            reasons.append("DUPLICATE_TARGET_GEOMETRY")
        if any(
            obj["bbox_xyxy"][2] - obj["bbox_xyxy"][0] < 3
            or obj["bbox_xyxy"][3] - obj["bbox_xyxy"][1] < 3
            for obj in targets
        ):
            reasons.append("TARGET_BELOW_REGISTERED_SIZE")
        eligibility = reference_eligibility(snapshot)
        reasons.extend(eligibility["reason_codes"])
        if snapshot["review_status"] != "SEALED":
            reasons.append("REFERENCE_NOT_SEALED")
        if any(
            obj["disposition"] == "UNCERTAIN" or obj["class_label"] == "UNRESOLVED_FRUIT_CLUSTER"
            for obj in snapshot.get("objects") or []
        ):
            reasons.append("VISIBLE_COUNT_SCOPE_UNRESOLVED")
    if approval is None:
        reasons.append("OWNER_HUMAN_APPROVAL_MISSING")
    elif (
        not verify_seal(approval, "approval_hash")
        or approval.get("schema_version") != "r4-human-reference-approval/1.0.0"
    ):
        reasons.append("OWNER_APPROVAL_INVALID")
    else:
        required = {
            "package_hash": package["package_hash"],
            "scope_hash": package["scope_hash"],
            "label_rules_hash": package["label_rules_hash"],
            "image_id": image["image_id"],
            "source_asset_hash": image["asset_sha256"],
            "reference_snapshot_hash": snapshot["snapshot_hash"] if snapshot else None,
            "verification_kind": "HUMAN_VERIFIED_BY_DATA_OWNER",
            "human_source_evidence_verified": True,
            "project_quality_accepted": True,
            "scope": "EXTERNAL_RESEARCH_ONLY",
            "business_approved": False,
        }
        if any(approval.get(key) != value for key, value in required.items()):
            reasons.append("OWNER_APPROVAL_SCOPE_OR_QUALITY_MISMATCH")
        basis = approval.get("approval_basis")
        roles = (
            {"A", "B", "ADJUDICATOR"}
            if basis == "INDEPENDENT_HUMAN_ADJUDICATION"
            else {"PROJECT_QUALITY_REVIEWER"}
            if basis == "DOCUMENTED_PUBLISHER_HUMAN_REFERENCE"
            else set()
        )
        participants = approval.get("participants", [])
        if (
            not roles
            or not isinstance(participants, list)
            or not all(
                isinstance(row, dict)
                and all(
                    isinstance(row.get(key), str) and row[key].strip()
                    for key in ("role", "person_id", "identity_verified_by")
                )
                for row in participants
            )
            or {row.get("role") for row in participants} != roles
            or len(participants) != len(roles)
            or len({row.get("person_id") for row in participants}) != len(roles)
            or not all(
                row.get("person_id")
                and row.get("human") is True
                and row.get("identity_verified_by")
                and row.get("independence_verified") is True
                and row.get("model_answers_consumed") is False
                for row in participants
            )
        ):
            reasons.append("INDEPENDENT_HUMAN_IDENTITIES_NOT_VERIFIED")
        if (
            snapshot
            and basis == "INDEPENDENT_HUMAN_ADJUDICATION"
            and isinstance(participants, list)
            and all(
                isinstance(row, dict)
                and isinstance(row.get("role"), str)
                and isinstance(row.get("person_id"), str)
                for row in participants
            )
        ):
            parents = snapshot.get("parent_snapshot_hashes", [])
            hashes = approval.get("source_annotation_hashes", [])
            ids = snapshot.get("adjudication", {}).get("asserted_annotator_ids", [])
            asserted_ids = [
                row.get("person_id") for row in participants if row.get("role") in {"A", "B"}
            ]
            if (
                not isinstance(hashes, list)
                or not all(isinstance(value, str) for value in hashes)
                or len(hashes) != 2
                or len(set(hashes)) != 2
                or set(hashes) != set(parents)
                or set(ids) != set(asserted_ids)
            ):
                reasons.append("HUMAN_SOURCE_VERSION_BINDING_MISMATCH")
        try:
            stamp = datetime.fromisoformat(
                str(approval.get("approved_at", "")).replace("Z", "+00:00")
            )
            if stamp.utcoffset() is None or not approval.get("approved_by"):
                raise ValueError("APPROVAL_TIME_OR_AUTHORITY_MISSING")
        except (ValueError, TypeError):
            reasons.append("APPROVAL_TIME_OR_AUTHORITY_MISSING")
        documents = approval.get("evidence_documents", [])
        expected_kinds = {
            "IDENTITY_VERIFICATION",
            "INDEPENDENCE_VERIFICATION",
            "PROJECT_QUALITY_REVIEW",
        }
        if basis == "DOCUMENTED_PUBLISHER_HUMAN_REFERENCE":
            expected_kinds.add("PUBLISHER_HUMAN_METHOD")
        if (
            evidence_root is None
            or not isinstance(documents, list)
            or not all(
                isinstance(doc, dict) and isinstance(doc.get("kind"), str) for doc in documents
            )
            or not expected_kinds <= {doc.get("kind") for doc in documents}
        ):
            reasons.append("HUMAN_EVIDENCE_DOCUMENTS_MISSING")
        else:
            try:
                _guard_root(evidence_root)
                for document in documents:
                    raw = _read_authorized(evidence_root, document["ref"], AssetPolicy())
                    if not raw.strip() or hashlib.sha256(raw).hexdigest() != document["sha256"]:
                        raise ValueError("HUMAN_EVIDENCE_HASH_MISMATCH")
            except (ValueError, OSError, KeyError):
                reasons.append("HUMAN_EVIDENCE_INTEGRITY_FAILED")
    return seal(
        {
            "image_id": image["image_id"],
            "qualified": not reasons,
            "status": "QUALIFIED_GT" if not reasons else "NOT_QUALIFIED",
            "reason_codes": sorted(set(reasons)),
            "reference_hash": snapshot["snapshot_hash"] if snapshot and not reasons else None,
            "reference_count": snapshot["visible_count"] if snapshot and not reasons else None,
            "approval_hash": approval.get("approval_hash") if approval else None,
            "identity_authenticated_by_tool": False,
            "business_approved": False,
            "limitation": (
                "Externally verified owner receipts are a trust boundary; "
                "hashes alone do not authenticate humans."
            ),
        },
        "qualification_hash",
    )
