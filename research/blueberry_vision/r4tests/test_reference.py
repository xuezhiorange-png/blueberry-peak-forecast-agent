"""Artificial geometry on a licensed photo tests contracts, never human GT."""

import copy
from typing import Any

import pytest

from research.blueberry_vision.r2_common import seal
from research.blueberry_vision.r3.annotations import annotation_bundle, create_draft
from research.blueberry_vision.r4.package import build_package
from research.blueberry_vision.r4.reference import import_task, qualify_reference, review_pair


def task_bundle(
    dataset: Any, package: Any, slot: Any = "A", objects: Any = None, actor: Any = None
) -> Any:
    image = dataset["images"][0]
    snapshot = create_draft(
        image,
        annotation_version="UNIT_GEOMETRY_NOT_HUMAN_" + slot,
        annotator_id=actor or "UNIT_TEST_NOT_HUMAN_" + slot,
        objects=objects,
    )
    bundle = annotation_bundle(dataset, [snapshot])
    bundle["work_package_binding"] = {
        "package_hash": package["package_hash"],
        "label_rules_hash": package["label_rules_hash"],
        "task_id": package["tasks"][slot]["task_id"],
        "task_role": slot,
        "full_resolution": True,
    }
    return seal(bundle, "annotations_hash")


def target(box: Any = (5, 5, 15, 15), oid: Any = "one") -> Any:
    return {
        "object_id": oid,
        "class_label": "CANDIDATE_VISIBLE_BLUEBERRY",
        "disposition": "TARGET",
        "bbox_xyxy": list(box),
    }


def test_missing_vs_explicit_candidate_zero(public_preview: Any) -> None:
    d, _ = public_preview
    p = build_package(d)
    assert import_task(d, p, task_bundle(d, p), "A")["per_image"][0]["candidate_count"] is None
    assert (
        import_task(d, p, task_bundle(d, p, objects=[]), "A")["per_image"][0]["candidate_count"]
        == 0
    )
    assert not qualify_reference(d["images"][0], p, None)["qualified"]


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("task_role", "B", "TASK_BINDING_MISMATCH"),
        ("package_hash", "0" * 64, "TASK_BINDING_MISMATCH"),
        ("full_resolution", False, "PREVIEW_NOT_ANNOTATION_SOURCE"),
        ("label_rules_hash", "0" * 64, "TASK_BINDING_MISMATCH"),
        ("task_id", "0" * 64, "TASK_BINDING_MISMATCH"),
    ],
)
def test_task_wrong_bindings(public_preview: Any, field: Any, value: Any, reason: Any) -> None:
    d, _ = public_preview
    p = build_package(d)
    b = task_bundle(d, p, objects=[])
    b["work_package_binding"][field] = value
    with pytest.raises(ValueError, match=reason):
        import_task(d, p, seal(b, "annotations_hash"), "A")


@pytest.mark.parametrize(
    "objects,reason",
    [
        ([target((1, 1, 2, 6))], "TARGET_BELOW_REGISTERED_SIZE"),
        ([target(), target(oid="two")], "DUPLICATE_TARGET_GEOMETRY"),
    ],
)
def test_geometry_quality_conflicts(public_preview: Any, objects: Any, reason: Any) -> None:
    d, _ = public_preview
    p = build_package(d)
    with pytest.raises(ValueError, match=reason):
        import_task(d, p, task_bundle(d, p, objects=objects), "A")


def test_sealed_or_manual_field_alone_never_qualifies(public_preview: Any) -> None:
    d, _ = public_preview
    p = build_package(d)
    s = task_bundle(d, p, objects=[target()])["snapshots"][0]
    s["provenance"]["annotation_origin"] = "HUMAN"
    s["provenance"]["evidence_status"] = "VERIFIED"
    assert (
        "OWNER_HUMAN_APPROVAL_MISSING"
        in qualify_reference(d["images"][0], p, seal(s, "snapshot_hash"))["reason_codes"]
    )


def test_two_ids_not_two_verified_humans(public_preview: Any) -> None:
    d, _ = public_preview
    p = build_package(d)
    a = task_bundle(d, p, "A", [target()])
    b = task_bundle(d, p, "B", [target(), target((30, 30, 40, 40), "two")])
    report = review_pair(d, p, a, b)
    assert report["independent_human_reviews_completed"] == 0
    assert report["per_image"][0]["comparison"]["signed_count_difference"] == 1
    assert not report["qualified_gt"]


def test_missing_pair_not_fake_agreement(public_preview: Any) -> None:
    d, _ = public_preview
    report = review_pair(d, build_package(d), None, None)
    assert report["status"] == "HUMAN_REVIEW_PENDING"
    assert report["per_image"][0]["comparison"] is None


def test_copied_operator_not_independent(public_preview: Any) -> None:
    d, _ = public_preview
    p = build_package(d)
    a = task_bundle(d, p, "A", [], actor="SAME_UNIT_OPERATOR")
    b = task_bundle(d, p, "B", [], actor="SAME_UNIT_OPERATOR")
    assert "ANNOTATOR_ID_COLLISION" in review_pair(d, p, a, b)["reason_codes"]


def test_snapshot_image_hash_mismatch(public_preview: Any) -> None:
    d, _ = public_preview
    p = build_package(d)
    b = task_bundle(d, p, objects=[])
    b["snapshots"][0]["source_asset_hash"] = "0" * 64
    b["snapshots"][0] = seal(b["snapshots"][0], "snapshot_hash")
    with pytest.raises(ValueError):
        import_task(d, p, seal(b, "annotations_hash"), "A")


def test_self_minted_approval_without_receipts_rejected(public_preview: Any) -> None:
    d, _ = public_preview
    p = build_package(d)
    s = task_bundle(d, p, objects=[])["snapshots"][0]
    approval = {"qualified_gt": True, "identity_verified": True, "manual": True}
    assert not qualify_reference(d["images"][0], p, s, approval=approval)["qualified"]


def test_model_origin_not_importable(public_preview: Any) -> None:
    d, _ = public_preview
    p = build_package(d)
    b = task_bundle(d, p, objects=[])
    b["snapshots"][0]["provenance"]["annotation_origin"] = "AI"
    b["snapshots"][0] = seal(b["snapshots"][0], "snapshot_hash")
    with pytest.raises(ValueError):
        import_task(d, p, seal(b, "annotations_hash"), "A")


def test_input_original_bundle_immutable(public_preview: Any) -> None:
    d, _ = public_preview
    p = build_package(d)
    b = task_bundle(d, p, objects=[])
    saved = copy.deepcopy(b)
    import_task(d, p, b, "A")
    assert b == saved


@pytest.mark.parametrize(
    "field,value",
    [
        ("participants", None),
        ("participants", [None]),
        ("participants", [{"role": []}]),
        ("source_annotation_hashes", None),
        ("approved_at", None),
        ("approved_at", 123),
        ("evidence_documents", [None]),
        ("evidence_documents", [{"kind": []}]),
    ],
)
def test_invalid_owner_receipts_fail_closed(public_preview: Any, field: str, value: Any) -> None:
    d, _ = public_preview
    p = build_package(d)
    s = task_bundle(d, p, objects=[])["snapshots"][0]
    approval = {
        "schema_version": "r4-human-reference-approval/1.0.0",
        "approval_basis": "INDEPENDENT_HUMAN_ADJUDICATION",
        field: value,
    }
    result = qualify_reference(d["images"][0], p, s, approval=seal(approval, "approval_hash"))
    assert result["qualified"] is False
    assert result["reference_count"] is None


def test_small_targets_fail_reference_guide_even_with_manual_claim(public_preview: Any) -> None:
    d, _ = public_preview
    p = build_package(d)
    s = task_bundle(d, p, objects=[target((5, 5, 6, 10))])["snapshots"][0]
    result = qualify_reference(d["images"][0], p, s)
    assert "TARGET_BELOW_REGISTERED_SIZE" in result["reason_codes"]
