"""Independent hand geometry and provenance tests for R3 candidate annotation work."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from research.blueberry_vision.r2_common import JSONDict, canonical_hash, seal
from research.blueberry_vision.r3.annotations import (
    AnnotationError,
    adjudicate_annotations,
    annotation_bundle,
    compare_annotations,
    create_draft,
    export_coco,
    import_annotations,
    reference_eligibility,
    save_snapshot,
    transition_review,
    validate_snapshot,
)


def image(*, synthetic: bool = False) -> JSONDict:
    return {
        "image_id": "external-1",
        "asset_sha256": "a" * 64,
        "image_width": 100,
        "image_height": 80,
        "exif_orientation": 1,
        "image_coordinate_frame": "EXIF_NORMALIZED_RGB_HALF_OPEN_XYXY",
        "source_id": "public-source",
        "purpose": "SYNTHETIC_ENGINEERING" if synthetic else "PUBLIC_EXTERNAL_BENCHMARK",
        "SYNTHETIC": synthetic,
    }


def obj(
    number: int = 1, box: list[int | float] | None = None, disposition: str = "TARGET"
) -> JSONDict:
    return {
        "object_id": f"fruit-{number}",
        "class_label": "CANDIDATE_VISIBLE_BLUEBERRY",
        "bbox_xyxy": box or [10, 10, 20, 20],
        "disposition": disposition,
    }


def draft(
    objects: list[JSONDict] | None = None,
    author: str = "annotator-A",
    version: str = "draft-1",
    **kwargs: Any,
) -> JSONDict:
    return create_draft(
        image(), annotation_version=version, annotator_id=author, objects=objects, **kwargs
    )


def pending(author: str, version: str, objects: list[JSONDict]) -> JSONDict:
    a = draft(objects, author, version)
    return transition_review(
        transition_review(a, "SUBMITTED", actor_id=author), "REVIEW_PENDING", actor_id=author
    )


def dataset() -> JSONDict:
    return seal(
        {
            "dataset_id": "external-dataset",
            "purpose": "PUBLIC_EXTERNAL_BENCHMARK",
            "SYNTHETIC": False,
            "images": [image()],
        },
        "manifest_hash",
    )


def publisher_provenance() -> JSONDict:
    return {
        "kind": "DOCUMENTED_PUBLISHER_ANNOTATION",
        "annotation_origin": "HUMAN",
        "evidence_status": "VERIFIED",
        "evidence_refs": ["https://publisher.example/annotation-method"],
        "source_annotation_version": "publisher-v1",
        "source_annotation_hash": "b" * 64,
    }


def test_unannotated_is_null_but_true_empty_is_zero() -> None:
    missing, empty = draft(), draft([])
    assert (
        missing["gt_status"] == "UNANNOTATED"
        and missing["visible_count"] is None
        and missing["objects"] is None
    )
    assert empty["gt_status"] == "COMPLETE" and empty["visible_count"] == 0
    assert empty["count_unit"] == "visible_fruit_per_image"


def test_dispositions_only_target_enters_visible_reference() -> None:
    snapshot = draft([obj(), obj(2, disposition="IGNORE"), obj(3, disposition="UNCERTAIN")])
    assert snapshot["visible_count"] == 1
    assert snapshot["uncertain_count"] == 1 and snapshot["ignore_count"] == 1
    assert snapshot["business_approved"] is False and snapshot["identity_authenticated"] is False


@pytest.mark.parametrize(
    "box",
    [
        [0, 0, 0, 2],
        [-1, 0, 5, 5],
        [1, 1, 101, 8],
        [1, 1, 2, 81],
        [False, 0, 4, 4],
        [0, 0, float("nan"), 2],
    ],
)
def test_invalid_geometry_rejected(box: list[int | float]) -> None:
    with pytest.raises(AnnotationError):
        draft([obj(box=box)])


def test_duplicate_object_ids_rejected() -> None:
    with pytest.raises(AnnotationError, match="DUPLICATE_OBJECT_ID"):
        draft([obj(), obj()])


def test_target_label_not_business_or_maturity_label() -> None:
    target = obj()
    target["class_label"] = "RIPE_BUSINESS_APPROVED"
    with pytest.raises(AnnotationError, match="CANDIDATE_LABEL_REQUIRED"):
        draft([target])


def test_prediction_cannot_import_as_reference() -> None:
    with pytest.raises(AnnotationError, match="PREDICTION_IS_NOT_GT"):
        draft([obj()], provenance={"kind": "MODEL_PREDICTION", "annotation_origin": "MODEL"})


def test_asset_binding_and_hash_tampering_rejected() -> None:
    snapshot = draft([obj()])
    changed = copy.deepcopy(snapshot)
    changed["objects"][0]["bbox_xyxy"][0] = 11
    with pytest.raises(AnnotationError, match="SNAPSHOT_HASH_MISMATCH"):
        validate_snapshot(changed)
    wrong = image()
    wrong["asset_sha256"] = "b" * 64
    with pytest.raises(AnnotationError, match="IMAGE_ASSET_MISMATCH"):
        validate_snapshot(snapshot, wrong)


@pytest.mark.parametrize("state", ["SEALED", "ADJUDICATED", "REVIEW_PENDING", "approved"])
def test_skipped_states_rejected(state: str) -> None:
    with pytest.raises(AnnotationError, match="ILLEGAL_REVIEW_TRANSITION"):
        transition_review(draft([]), state, actor_id="reviewer")


def test_missing_annotation_cannot_be_submitted() -> None:
    with pytest.raises(AnnotationError, match="UNANNOTATED_CANNOT_SUBMIT"):
        transition_review(draft(), "SUBMITTED", actor_id="A")


def test_review_history_is_new_append_only_snapshot(tmp_path: Path) -> None:
    original = draft([obj()])
    original_hash = canonical_hash(original)
    submitted = transition_review(original, "SUBMITTED", actor_id="A", at="2026-10-13T12:00:00Z")
    assert original_hash == canonical_hash(original)
    assert submitted["history"][-1]["prior_snapshot_hash"] == original["snapshot_hash"]
    assert submitted["history"][-1]["identity_authenticated"] is False
    save_snapshot(tmp_path, original)
    with pytest.raises(FileExistsError):
        save_snapshot(tmp_path, original)
    save_snapshot(tmp_path, submitted)
    assert len(list(tmp_path.glob("*.json"))) == 2


def test_naive_or_invalid_operation_clock_rejected() -> None:
    with pytest.raises(AnnotationError, match="OPERATION_TIME_INVALID"):
        transition_review(draft([]), "SUBMITTED", actor_id="A", at="2026-10-13T12:00:00")


def test_manual_iou_and_count_difference_golden() -> None:
    a, b = draft([obj(), obj(2, [40, 10, 50, 20])]), draft([obj(box=[15, 10, 25, 20])], "B", "b-v1")
    comparison = compare_annotations(a, b, iou_threshold=0.3)
    assert comparison["signed_count_difference"] == -1
    assert comparison["matched_target_count"] == 1
    assert comparison["matched_target_ratio"] == pytest.approx(2 / 3)
    assert comparison["mean_matched_bbox_iou"] == pytest.approx(1 / 3)
    assert comparison["disagreement_target_count"] == 1
    assert comparison["human_independence_verified"] is False


def test_empty_comparison_no_fake_agreement_iou() -> None:
    report = compare_annotations(draft([]), draft([], "B", "b"))
    assert report["mean_matched_bbox_iou"] is None
    assert report["matched_target_ratio"] is None
    assert report["signed_count_difference"] == 0


def test_unannotated_comparison_not_evaluable() -> None:
    assert compare_annotations(draft(), draft([]))["status"] == "NOT_EVALUABLE"


def test_duplicate_predictions_one_to_one_annotation_matching() -> None:
    report = compare_annotations(draft([obj()]), draft([obj(), obj(2)], "B", "b"))
    assert report["matched_target_count"] == 1 and report["disagreement_target_count"] == 1


def test_same_author_or_wrong_state_rejected_for_adjudication() -> None:
    with pytest.raises(AnnotationError, match="INDEPENDENT_ANNOTATOR_IDS_REQUIRED"):
        adjudicate_annotations(
            pending("A", "a", [obj()]),
            pending("A", "b", [obj()]),
            [obj()],
            adjudicator_id="C",
            annotation_version="arb-1",
        )
    with pytest.raises(AnnotationError, match="REVIEW_PENDING_REQUIRED"):
        adjudicate_annotations(
            draft([obj()]),
            draft([obj()], "B", "b"),
            [obj()],
            adjudicator_id="C",
            annotation_version="arb-1",
        )


def test_simulated_review_complete_but_never_real_reference() -> None:
    kwargs = {"workflow_mode": "SIMULATED_ENGINEERING"}
    a, b = draft([obj()], "A", "a", **kwargs), draft([obj()], "B", "b", **kwargs)
    for_snapshot = []
    for snapshot in (a, b):
        for_snapshot.append(
            transition_review(
                transition_review(snapshot, "SUBMITTED", actor_id=snapshot["annotator_id"]),
                "REVIEW_PENDING",
                actor_id="coordinator",
            )
        )
    adjudicated = adjudicate_annotations(
        for_snapshot[0],
        for_snapshot[1],
        [obj()],
        adjudicator_id="C",
        annotation_version="arb-1",
        workflow_mode="SIMULATED_ENGINEERING",
    )
    sealed = transition_review(adjudicated, "SEALED", actor_id="C")
    assert sealed["review_status"] == "SEALED"
    assert sealed["adjudication"]["independent_human_review_verified"] is False
    assert "SIMULATED_REVIEW_NOT_REAL_REFERENCE" in reference_eligibility(sealed)["reason_codes"]


def test_self_asserted_seal_does_not_invent_human_evidence() -> None:
    a, b = pending("A", "a", [obj()]), pending("B", "b", [obj()])
    sealed = transition_review(
        adjudicate_annotations(a, b, [obj()], adjudicator_id="C", annotation_version="arb"),
        "SEALED",
        actor_id="C",
    )
    assert reference_eligibility(sealed)["eligible"] is False
    assert sealed["identity_authenticated"] is False and sealed["business_approved"] is False


def test_documented_publisher_provenance_is_preserved_and_exposed() -> None:
    snapshot = draft([obj()], provenance=publisher_provenance())
    qualification = reference_eligibility(snapshot)
    assert (
        qualification["eligible"] is True
        and qualification["exposure_status"] == "EXPOSED_PUBLIC_BENCHMARK"
    )
    assert snapshot["review_status"] == "DRAFT" and snapshot["business_approved"] is False


def test_publisher_without_evidence_is_not_qualified() -> None:
    provenance = publisher_provenance()
    provenance["evidence_status"] = "UNVERIFIED"
    assert reference_eligibility(draft([obj()], provenance=provenance))["eligible"] is False


def test_coco_roundtrip_preserves_geometry_disposition_version_and_empty() -> None:
    d = dataset()
    snapshots = [draft([obj(), obj(2, disposition="IGNORE"), obj(3, disposition="UNCERTAIN")])]
    bundled = annotation_bundle(d, snapshots)
    coco = export_coco(bundled)
    imported = import_annotations(d, coco)
    assert imported["snapshots"] == snapshots
    assert coco["research_provenance"]["business_approved"] is False
    assert (
        import_annotations(d, export_coco(annotation_bundle(d, [draft([])])))["snapshots"][0][
            "visible_count"
        ]
        == 0
    )


def test_plain_coco_requires_external_provenance_and_explicit_class_mapping() -> None:
    raw = {
        "images": [{"id": 1, "file_name": "one.jpg", "width": 100, "height": 80}],
        "categories": [{"id": 4, "name": "blueberry"}],
        "annotations": [{"id": 9, "image_id": 1, "category_id": 4, "bbox": [10, 10, 10, 10]}],
    }
    with pytest.raises(AnnotationError, match="EXTERNAL_PROVENANCE_REQUIRED"):
        import_annotations(dataset(), raw)
    imported = import_annotations(
        dataset(),
        raw,
        annotation_version="public-v1",
        category_mapping={4: "CANDIDATE_VISIBLE_BLUEBERRY"},
        image_mapping={1: "external-1"},
        provenance=publisher_provenance(),
    )
    assert imported["snapshots"][0]["objects"][0]["bbox_xyxy"] == [10, 10, 20, 20]
    assert imported["snapshots"][0]["visible_count"] == 1


@pytest.mark.parametrize("bad_id", [True, 1.0, 0, -1])
def test_coco_strict_numeric_ids(bad_id: object) -> None:
    coco = export_coco(annotation_bundle(dataset(), [draft([obj()])]))
    coco["annotations"][0]["id"] = bad_id
    with pytest.raises(AnnotationError):
        import_annotations(dataset(), coco)


def test_coco_geometry_tampering_does_not_preserve_old_snapshot_hash() -> None:
    coco = export_coco(annotation_bundle(dataset(), [draft([obj()])]))
    coco["annotations"][0]["bbox"][0] = 11
    with pytest.raises(AnnotationError, match="COCO_SNAPSHOT_GEOMETRY_MISMATCH"):
        import_annotations(dataset(), coco)


def test_bundle_image_identity_binding() -> None:
    d = dataset()
    d["images"][0]["image_width"] = 90
    d = seal(d, "manifest_hash")
    with pytest.raises(AnnotationError, match="IMAGE_DIMENSIONS_MISMATCH"):
        annotation_bundle(d, [draft([obj()])])


def test_review_state_cannot_be_resealed_without_valid_history() -> None:
    snapshot = draft([obj()])
    snapshot["review_status"] = "SEALED"
    snapshot = seal(snapshot, "snapshot_hash")
    with pytest.raises(AnnotationError, match="REVIEW_HISTORY_STATE_MISMATCH"):
        validate_snapshot(snapshot)


def test_history_times_cannot_move_backwards() -> None:
    submitted = transition_review(
        draft([obj()]), "SUBMITTED", actor_id="A", at="2026-10-13T13:00:00Z"
    )
    with pytest.raises(AnnotationError, match="OPERATION_TIME_ORDER_INVALID"):
        transition_review(submitted, "REVIEW_PENDING", actor_id="A", at="2026-10-13T12:00:00Z")


def test_adjudication_requires_new_annotation_version() -> None:
    with pytest.raises(AnnotationError, match="NEW_ANNOTATION_VERSION_REQUIRED"):
        adjudicate_annotations(
            pending("A", "a", [obj()]),
            pending("B", "b", [obj()]),
            [obj()],
            adjudicator_id="C",
            annotation_version="a",
        )


def test_synthetic_review_not_mislabelled_as_external() -> None:
    with pytest.raises(AnnotationError, match="PURPOSE_SYNTHETIC_MISMATCH"):
        create_draft(
            image(synthetic=True),
            annotation_version="a",
            annotator_id="A",
            objects=[],
            purpose="PUBLIC_EXTERNAL_BENCHMARK",
            workflow_mode="SIMULATED_ENGINEERING",
        )


def test_malformed_coco_research_provenance_rejected() -> None:
    coco = export_coco(annotation_bundle(dataset(), [draft([])]))
    coco["research_provenance"] = []
    with pytest.raises(AnnotationError, match="PROVENANCE_INVALID"):
        import_annotations(dataset(), coco)


def test_unannotated_coco_roundtrip_preserves_nulls() -> None:
    missing = draft()
    roundtrip = import_annotations(dataset(), export_coco(annotation_bundle(dataset(), [missing])))
    assert roundtrip["snapshots"] == [missing]
    assert roundtrip["snapshots"][0]["visible_count"] is None


def test_modified_coco_provenance_cannot_upgrade_authority() -> None:
    coco = export_coco(annotation_bundle(dataset(), [draft([])]))
    coco["research_provenance"]["business_approved"] = True
    with pytest.raises(AnnotationError, match="OFFLINE_AUTHORITY_UPGRADE_FORBIDDEN"):
        import_annotations(dataset(), coco)


def test_coco_integrity_hash_is_verified() -> None:
    coco = export_coco(annotation_bundle(dataset(), [draft([])]))
    coco["adapter_hash"] = "c" * 64
    with pytest.raises(AnnotationError, match="COCO_ADAPTER_HASH_MISMATCH"):
        import_annotations(dataset(), coco)


def test_snapshot_list_export_rejects_synthetic_external_mixture() -> None:
    synth = create_draft(
        image(synthetic=True),
        annotation_version="s",
        annotator_id="engine",
        objects=[],
        workflow_mode="SIMULATED_ENGINEERING",
    )
    with pytest.raises(AnnotationError, match="PURPOSE_SYNTHETIC_MISMATCH"):
        export_coco([draft([]), synth])


def test_dataset_duplicate_image_ids_are_not_collapsed() -> None:
    d = dataset()
    d["images"].append(copy.deepcopy(d["images"][0]))
    d = seal(d, "manifest_hash")
    with pytest.raises(AnnotationError, match="DUPLICATE_DATASET_IMAGE_ID"):
        annotation_bundle(d, [draft([])])


def raw_coco(info: JSONDict | None = None, *, disposition: str | None = None) -> JSONDict:
    data: JSONDict = {
        "images": [{"id": 1, "width": 100, "height": 80}],
        "categories": [{"id": 1, "name": "blueberry"}],
        "annotations": [
            {"id": 1, "image_id": 1, "category_id": 1, "bbox": [10, 10, 10, 10], "iscrowd": 0}
        ],
    }
    if info is not None:
        data["info"] = info
    if disposition is not None:
        data["annotations"][0]["disposition"] = disposition
    return data


def plain_import(coco: JSONDict, provenance: JSONDict | None = None) -> JSONDict:
    return import_annotations(
        dataset(),
        coco,
        annotation_version="candidate-v1",
        category_mapping={1: "CANDIDATE_VISIBLE_BLUEBERRY"},
        image_mapping={1: "external-1"},
        provenance=provenance
        or {
            "kind": "SELF_ASSERTED_LOCAL_DRAFT",
            "annotation_origin": "UNVERIFIED",
            "evidence_status": "UNVERIFIED",
            "evidence_refs": [],
        },
    )


@pytest.mark.parametrize(
    "info",
    [
        {"candidate": True},
        {"annotation_status": "DRAFT"},
        {"annotation_status": "SUBMITTED"},
        {"annotation_status": "REVIEW_PENDING"},
        {"annotation_origin": "SEMI_AUTOMATIC", "human_review_status": "UNKNOWN"},
        {"annotation_method": "semi-automatic annotation", "human_review_status": "UNVERIFIED"},
    ],
)
def test_known_candidate_or_unreviewed_semi_auto_cannot_be_upgraded_by_caller(
    info: JSONDict,
) -> None:
    with pytest.raises(AnnotationError, match="ANNOTATION_PROVENANCE_AUTHORITY_UPGRADE"):
        plain_import(raw_coco(info), publisher_provenance())


@pytest.mark.parametrize("origin", ["MODEL", "AI", "MODEL_PREDICTION", "AUTOMATIC"])
def test_known_model_coco_not_promoted_by_claimed_publisher(origin: str) -> None:
    with pytest.raises(AnnotationError, match="PREDICTION_IS_NOT_GT"):
        plain_import(raw_coco({"annotation_origin": origin}), publisher_provenance())


def test_plain_coco_uncertain_disposition_preserved() -> None:
    imported = plain_import(
        raw_coco(
            {"candidate": True, "annotation_status": "DRAFT", "gt_status": "COMPLETE"},
            disposition="UNCERTAIN",
        )
    )
    snapshot = imported["snapshots"][0]
    assert snapshot["visible_count"] == 0 and snapshot["uncertain_count"] == 1
    assert snapshot["objects"][0]["disposition"] == "UNCERTAIN"
    assert reference_eligibility(snapshot)["eligible"] is False


def test_candidate_coco_unknown_coverage_not_guessed_complete() -> None:
    imported = plain_import(raw_coco({"candidate": True, "annotation_status": "DRAFT"}))
    snapshot = imported["snapshots"][0]
    assert (
        snapshot["gt_status"] == "UNANNOTATED"
        and snapshot["objects"] is None
        and snapshot["visible_count"] is None
    )
    assert len(imported["draft_geometry"]["external-1"]) == 1


def test_source_candidate_restriction_survives_resealed_provenance_claim() -> None:
    imported = plain_import(raw_coco({"candidate": True, "gt_status": "COMPLETE"}))
    snapshot = imported["snapshots"][0]
    restrictions = snapshot["provenance"]["imported_source_quality"]
    snapshot["provenance"] = {**publisher_provenance(), "imported_source_quality": restrictions}
    snapshot = seal(snapshot, "snapshot_hash")
    eligibility = reference_eligibility(snapshot)
    assert eligibility["eligible"] is False
    assert "SOURCE_ANNOTATION_QUALITY_NOT_REFERENCE" in eligibility["reason_codes"]


def test_coco_crowd_disposition_conflict_rejected() -> None:
    coco = raw_coco(disposition="TARGET")
    coco["annotations"][0]["iscrowd"] = 1
    with pytest.raises(AnnotationError, match="ISCROWD_DISPOSITION_CONFLICT"):
        plain_import(coco)


def test_plain_coco_ignore_and_uncertain_not_inferred_from_prediction() -> None:
    coco = raw_coco(disposition="UNKNOWN_DISPOSITION")
    with pytest.raises(AnnotationError, match="DISPOSITION_INVALID"):
        plain_import(coco)


def test_known_unreviewed_semi_auto_snapshot_provenance_not_qualified() -> None:
    claimed = {
        **publisher_provenance(),
        "annotation_method": "SEMI_AUTOMATIC",
        "human_review_status": "UNKNOWN",
    }
    eligibility = reference_eligibility(draft([obj()], provenance=claimed))
    assert eligibility["eligible"] is False
    assert "SOURCE_ANNOTATION_QUALITY_NOT_REFERENCE" in eligibility["reason_codes"]


def test_known_ui_candidate_source_hash_must_match_image() -> None:
    coco = raw_coco({"candidate": True, "source_asset_hash": "f" * 64, "gt_status": "COMPLETE"})
    with pytest.raises(AnnotationError, match="IMAGE_ASSET_MISMATCH"):
        plain_import(coco)


def test_external_coco_does_not_mix_source_purpose() -> None:
    with pytest.raises(AnnotationError, match="PURPOSE_SYNTHETIC_MISMATCH"):
        plain_import(raw_coco({"purpose": "SYNTHETIC_ENGINEERING", "SYNTHETIC": True}))


def test_stripped_adapter_metadata_does_not_hide_known_draft_snapshot() -> None:
    coco = export_coco(annotation_bundle(dataset(), [draft([obj()])]))
    coco.pop("research_provenance")
    with pytest.raises(AnnotationError, match="ANNOTATION_PROVENANCE_AUTHORITY_UPGRADE"):
        plain_import(coco, publisher_provenance())


def test_nested_source_model_provenance_is_not_gt() -> None:
    coco = raw_coco()
    coco["annotations"][0]["provenance"] = {"annotation_origin": "MODEL"}
    with pytest.raises(AnnotationError, match="PREDICTION_IS_NOT_GT"):
        plain_import(coco, publisher_provenance())


def test_nontrivial_exif_orientation_raw_coco_coordinates_rejected() -> None:
    d = dataset()
    d["images"][0]["exif_orientation"] = 2
    d["images"][0]["image_coordinate_frame"] = "EXIF_NORMALIZED_RGB_HALF_OPEN_XYXY"
    d = seal(d, "manifest_hash")
    with pytest.raises(AnnotationError, match="ANNOTATION_COORDINATE_FRAME_UNVERIFIED"):
        import_annotations(
            d,
            raw_coco(),
            annotation_version="publisher-v1",
            category_mapping={1: "CANDIDATE_VISIBLE_BLUEBERRY"},
            image_mapping={1: "external-1"},
            provenance=publisher_provenance(),
        )


def test_exif_normalized_coordinate_evidence_explicitly_required() -> None:
    d = dataset()
    d["images"][0]["exif_orientation"] = 2
    d["images"][0]["image_coordinate_frame"] = "EXIF_NORMALIZED_RGB_HALF_OPEN_XYXY"
    d = seal(d, "manifest_hash")
    provenance = {
        **publisher_provenance(),
        "annotation_coordinate_frame": "EXIF_NORMALIZED_RGB_HALF_OPEN_XYXY",
        "coordinate_frame_evidence_status": "VERIFIED",
        "coordinate_frame_evidence_refs": ["https://publisher.example/exif-coordinate-convention"],
    }
    imported = import_annotations(
        d,
        raw_coco(),
        annotation_version="publisher-v1",
        category_mapping={1: "CANDIDATE_VISIBLE_BLUEBERRY"},
        image_mapping={1: "external-1"},
        provenance=provenance,
    )
    assert imported["snapshots"][0]["objects"][0]["bbox_xyxy"] == [10, 10, 20, 20]


def test_nontrivial_exif_frame_name_alone_not_verified() -> None:
    d = dataset()
    d["images"][0]["exif_orientation"] = 2
    d = seal(d, "manifest_hash")
    provenance = {
        **publisher_provenance(),
        "annotation_coordinate_frame": "EXIF_NORMALIZED_RGB_HALF_OPEN_XYXY",
    }
    with pytest.raises(AnnotationError, match="ANNOTATION_COORDINATE_FRAME_UNVERIFIED"):
        import_annotations(
            d,
            raw_coco(),
            annotation_version="publisher-v1",
            category_mapping={1: "CANDIDATE_VISIBLE_BLUEBERRY"},
            image_mapping={1: "external-1"},
            provenance=provenance,
        )


@pytest.mark.parametrize("field", ["asset_sha256", "source_asset_hash"])
def test_plain_coco_declared_image_byte_hash_reconciled(field: str) -> None:
    coco = raw_coco()
    coco["images"][0][field] = "a" * 64
    assert plain_import(coco)["snapshots"][0]["source_asset_hash"] == "a" * 64
    coco["images"][0][field] = "f" * 64
    with pytest.raises(AnnotationError, match="IMAGE_ASSET_MISMATCH"):
        plain_import(coco)


def test_plain_coco_conflicting_declared_byte_hashes_rejected() -> None:
    coco = raw_coco()
    coco["images"][0].update(asset_sha256="f" * 64, source_asset_hash="a" * 64)
    with pytest.raises(AnnotationError, match="IMAGE_ASSET_MISMATCH"):
        plain_import(coco)


def test_plain_coco_absent_hash_keeps_explicit_id_and_dimension_binding() -> None:
    imported = plain_import(raw_coco())
    assert imported["snapshots"][0]["source_asset_hash"] == "a" * 64


def actual_pending_quality_info() -> JSONDict:
    return {
        "annotation_quality_status": "DRAFT",
        "label_approval": "CANDIDATE_ONLY",
        "annotation_origin": "UNVERIFIED",
        "evidence_status": "PENDING_QUALITY_REVIEW",
    }


def test_actual_pending_quality_source_cannot_be_upgraded_by_publisher_argument() -> None:
    with pytest.raises(AnnotationError, match="ANNOTATION_PROVENANCE_AUTHORITY_UPGRADE"):
        plain_import(raw_coco(actual_pending_quality_info()), publisher_provenance())


def test_actual_pending_quality_geometry_remains_draft_unless_explicitly_complete() -> None:
    imported = plain_import(raw_coco(actual_pending_quality_info()))
    snapshot = imported["snapshots"][0]
    assert snapshot["objects"] is None and snapshot["visible_count"] is None
    assert snapshot["gt_status"] == "UNANNOTATED"
    assert len(imported["draft_geometry"]["external-1"]) == 1
    quality = snapshot["provenance"]["imported_source_quality"]
    assert quality["candidate"] and quality["not_reference"]


@pytest.mark.parametrize(
    "info",
    [
        {"annotation_quality_status": "DRAFT"},
        {"label_approval": "CANDIDATE_ONLY"},
        {"annotation_origin": "UNVERIFIED"},
        {"evidence_status": "PENDING_QUALITY_REVIEW"},
        {"annotation_quality_status": "UNREVIEWED"},
        {"evidence_status": "UNKNOWN"},
    ],
)
def test_known_pending_source_aliases_never_upgraded(info: JSONDict) -> None:
    with pytest.raises(AnnotationError, match="ANNOTATION_PROVENANCE_AUTHORITY_UPGRADE"):
        plain_import(raw_coco(info), publisher_provenance())


def test_explicit_complete_pending_candidate_still_not_real_reference() -> None:
    info = {**actual_pending_quality_info(), "gt_status": "COMPLETE"}
    snapshot = plain_import(raw_coco(info))["snapshots"][0]
    assert snapshot["visible_count"] == 1
    assert reference_eligibility(snapshot)["eligible"] is False
