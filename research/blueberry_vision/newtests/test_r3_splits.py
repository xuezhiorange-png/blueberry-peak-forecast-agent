"""Independent graph/seal goldens, including negative admission cases."""

from copy import deepcopy
from pathlib import Path

import pytest

from research.blueberry_vision.r2_common import JSONDict, canonical_hash, seal
from research.blueberry_vision.r3.annotations import (
    adjudicate_annotations,
    annotation_bundle,
    create_draft,
    transition_review,
)
from research.blueberry_vision.r3.splits import (
    SplitError,
    append_exposure_event,
    build_split,
    check_admission,
    load_exposure_ledger,
    seal_test,
)


def dataset() -> JSONDict:
    return seal(
        {
            "schema_version": "blueberry-vision-external-dataset/3.0.0",
            "dataset_id": "public-golden",
            "dataset_version": "1",
            "purpose": "PUBLIC_EXTERNAL_BENCHMARK",
            "SYNTHETIC": False,
            "sources": [
                {
                    "source_id": "source-a",
                    "license_status": "LICENSE_VERIFIED",
                    "research_use": True,
                    "purpose": "PUBLIC_EXTERNAL_BENCHMARK",
                    "SYNTHETIC": False,
                    "license_id": "CC0-1.0",
                    "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
                }
            ],
            "images": [
                {
                    "image_id": name,
                    "asset_sha256": canonical_hash(name),
                    "rgb_sha256": canonical_hash("rgb" + name),
                    "source_id": "source-a",
                    "image_width": 40,
                    "image_height": 30,
                    "observed_at": None,
                    "base_identity": {"status": "UNRESOLVED"},
                }
                for name in ["a", "b", "c"]
            ],
        },
        "manifest_hash",
    )


def annotations(data: JSONDict) -> JSONDict:
    return annotation_bundle(
        data,
        [
            create_draft(
                row,
                annotation_version="publisher-v1",
                annotator_id="test-fixture-publisher",
                purpose="PUBLIC_EXTERNAL_BENCHMARK",
                synthetic=False,
                provenance={
                    "kind": "DOCUMENTED_PUBLISHER_ANNOTATION",
                    "annotation_origin": "HUMAN",
                    "evidence_status": "VERIFIED",
                    "evidence_refs": ["https://example.org/golden-fixture-not-actual-data"],
                    "source_annotation_version": "v1",
                    "source_annotation_hash": canonical_hash("publisher-annotation-fixture"),
                },
                objects=[
                    {
                        "object_id": "fruit-1",
                        "class_label": "CANDIDATE_VISIBLE_BLUEBERRY",
                        "bbox_xyxy": [1, 1, 10, 10],
                        "disposition": "TARGET",
                    }
                ],
            )
            for row in data["images"]
        ],
    )


def frozen(data: JSONDict) -> JSONDict:
    return seal(
        {
            "dataset_manifest_hash": data["manifest_hash"],
            "config_hash": canonical_hash("config"),
            "model_hash": canonical_hash("model"),
            "training_data_hash": canonical_hash("synthetic-only"),
            "evaluation_protocol_hash": canonical_hash("protocol"),
            "configuration_frozen": True,
        },
        "freeze_hash",
    )


def test_unassigned_default_and_unknowns_do_not_join() -> None:
    result = build_split(dataset(), {"a": "TRAIN", "b": "TEST"})
    assert {row["image_id"]: row["split"] for row in result["records"]} == {
        "a": "TRAIN",
        "b": "TEST",
        "c": "UNASSIGNED",
    }
    assert len(result["groups"]) == 3
    assert result["holdout_verification"]["cross_base"]["status"] == "UNVERIFIED"
    assert result["holdout_verification"]["cross_date"]["status"] == "UNVERIFIED"


@pytest.mark.parametrize(
    "field",
    [
        "capture_session_id",
        "sampling_unit_id",
        "video_id",
        "source_batch_id",
        "multiview_group_id",
    ],
)
def test_declared_groups_cannot_cross_split(field: str) -> None:
    data = dataset()
    for row in data["images"][:2]:
        row[field] = "group-1"
    data = seal(data, "manifest_hash")
    with pytest.raises(SplitError, match="GROUP_CROSS_SPLIT"):
        build_split(data, {"a": "TRAIN", "b": "TEST"})


def test_transitive_graph_leakage() -> None:
    data = dataset()
    data["images"][0]["capture_session_id"] = "session"
    data["images"][1]["capture_session_id"] = "session"
    data["images"][2]["parent_image_id"] = "b"
    data = seal(data, "manifest_hash")
    with pytest.raises(SplitError, match="GROUP_CROSS_SPLIT"):
        build_split(data, {"a": "TRAIN", "c": "OUT_OF_DOMAIN"})


@pytest.mark.parametrize("status", ["PENDING", "CONFIRMED"])
def test_near_duplicate_candidates_conservatively_join(status: str) -> None:
    report = {
        "candidate_edges": [
            {"image_id_a": "a", "image_id_b": "b", "relation": "DHASH", "status": status}
        ]
    }
    with pytest.raises(SplitError, match="GROUP_CROSS_SPLIT"):
        build_split(dataset(), {"a": "TRAIN", "b": "TEST"}, report)


def test_rejected_candidate_requires_human_review() -> None:
    edge = {"image_id_a": "a", "image_id_b": "b", "relation": "DHASH", "status": "REJECTED"}
    with pytest.raises(SplitError, match="DUPLICATE_REJECTION_REVIEW_REQUIRED"):
        build_split(dataset(), {"a": "TRAIN", "b": "TEST"}, {"candidate_edges": [edge]})
    edge.update(
        {
            "reviewer_id": "asserted-reviewer",
            "reviewed_at": "2026-01-01T00:00:00Z",
            "review_reason": "different photos",
        }
    )
    assert build_split(dataset(), {"a": "TRAIN", "b": "TEST"}, {"candidate_edges": [edge]})[
        "split_hash"
    ]


def test_exact_pixel_duplicate_cannot_be_rejected() -> None:
    data = dataset()
    data["images"][1]["rgb_sha256"] = data["images"][0]["rgb_sha256"]
    data = seal(data, "manifest_hash")
    with pytest.raises(SplitError, match="GROUP_CROSS_SPLIT"):
        build_split(data, {"a": "TRAIN", "b": "TEST"})


@pytest.mark.parametrize("assignments", [{"a": "bad"}, {"unknown": "TRAIN"}])
def test_assignment_integrity(assignments: JSONDict) -> None:
    with pytest.raises(SplitError):
        build_split(dataset(), assignments)


def test_unknown_parent_is_not_silently_ignored() -> None:
    data = dataset()
    data["images"][0]["parent_image_id"] = "not-imported"
    data = seal(data, "manifest_hash")
    with pytest.raises(SplitError, match="PARENT_IMAGE_UNKNOWN"):
        build_split(data, {})


def test_split_hash_stable_reordered_inputs() -> None:
    data = dataset()
    one = build_split(data, {"a": "TRAIN", "b": "TEST"})
    assert one == build_split(data, {"b": "TEST", "a": "TRAIN"})


def test_public_qualified_gt_seal_is_exposed_not_blind() -> None:
    data = dataset()
    split = build_split(data, {"a": "TRAIN", "b": "TEST"})
    result = seal_test(data, split, annotations(data), frozen(data))
    assert result["status"] == "SEALED_RESEARCH_INTEGRITY"
    assert result["test_exposure"] == "EXPOSED_PUBLIC_BENCHMARK"
    assert result["independent_access_control"] is False
    assert result["sealed_images"][0]["image_id"] == "b"


def test_missing_gt_returns_not_evaluable_not_zero() -> None:
    data = dataset()
    split = build_split(data, {"a": "TEST"})
    result = seal_test(data, split, None, frozen(data))
    assert result["status"] == "NOT_EVALUABLE"
    assert "GT_MISSING" in result["reason_codes"]


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("reference_kind", "MODEL_PREDICTION", "PREDICTION_CANNOT_BE_GT"),
        ("provenance", {}, "GT_QUALITY_INSUFFICIENT"),
        ("simulated", True, "SIMULATED_REFERENCE_NOT_REAL_GT"),
        ("source_asset_hash", canonical_hash("wrong"), "GT_ASSET_IDENTITY_MISMATCH"),
        ("annotation_version", "", "ANNOTATION_VERSION_MISSING"),
    ],
)
def test_gt_negative_admission(field: str, value: object, reason: str) -> None:
    data = dataset()
    refs = annotations(data)
    refs["snapshots"][0][field] = value
    refs["snapshots"][0] = seal(refs["snapshots"][0], "snapshot_hash")
    refs = seal(refs, "annotations_hash")
    report = check_admission(data, build_split(data, {"a": "TEST"}), refs, freeze=frozen(data))
    assert reason in report["reason_codes"]
    assert report["status"] == "NOT_EVALUABLE"


def test_license_unverified_blocks() -> None:
    data = dataset()
    data["sources"][0]["license_status"] = "LICENSE_UNVERIFIED"
    data = seal(data, "manifest_hash")
    report = check_admission(
        data, build_split(data, {"a": "TEST"}), annotations(data), freeze=frozen(data)
    )
    assert "LICENSE_UNVERIFIED" in report["reason_codes"]


def test_config_not_frozen_blocks() -> None:
    data = dataset()
    report = check_admission(data, build_split(data, {"a": "TEST"}), annotations(data), freeze=None)
    assert "CONFIG_NOT_FROZEN" in report["reason_codes"]


def test_changed_gt_after_seal_blocks() -> None:
    data = dataset()
    split = build_split(data, {"a": "TEST"})
    refs = annotations(data)
    frozen_config = frozen(data)
    sealed = seal_test(data, split, refs, frozen_config)
    changed = deepcopy(refs)
    changed["snapshots"][0]["objects"][0]["bbox_xyxy"] = [2, 2, 12, 12]
    changed["snapshots"][0] = seal(changed["snapshots"][0], "snapshot_hash")
    changed = seal(changed, "annotations_hash")
    report = check_admission(data, split, changed, freeze=frozen_config, test_seal=sealed)
    assert "SEALED_TEST_CHANGED" in report["reason_codes"]


def test_no_test_scope_is_not_evaluable() -> None:
    data = dataset()
    result = seal_test(data, build_split(data, {"a": "TRAIN"}), annotations(data), frozen(data))
    assert result["status"] == "NOT_EVALUABLE"
    assert "TEST_SCOPE_EMPTY" in result["reason_codes"]


def test_immutable_ledger_orders_config_prediction_gt(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger"
    config_hash = canonical_hash("config")
    prediction_hash = canonical_hash("prediction")
    append_exposure_event(ledger_path, "CONFIG_FROZEN", {"freeze_hash": config_hash})
    append_exposure_event(
        ledger_path,
        "PREDICTIONS_FIXED",
        {"freeze_hash": config_hash, "prediction_hash": prediction_hash},
    )
    append_exposure_event(
        ledger_path,
        "GT_SCORE_READ",
        {
            "freeze_hash": config_hash,
            "prediction_hash": prediction_hash,
            "annotations_hash": canonical_hash("GT"),
        },
    )
    ledger = load_exposure_ledger(ledger_path)
    assert [item["event"] for item in ledger["events"]] == [
        "CONFIG_FROZEN",
        "PREDICTIONS_FIXED",
        "GT_SCORE_READ",
    ]
    assert len(list(ledger_path.glob("*.json"))) == 3


def test_gt_cannot_be_scored_before_predictions_fixed(tmp_path: Path) -> None:
    with pytest.raises(SplitError, match="EXPOSURE_ORDER_INVALID"):
        append_exposure_event(tmp_path / "ledger", "GT_SCORE_READ", {})


def test_ledger_tamper_is_detected(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger"
    append_exposure_event(ledger_path, "CONFIG_FROZEN", {"freeze_hash": canonical_hash("freeze")})
    first = next(ledger_path.glob("*.json"))
    first.write_text('{"event":"FAKE"}', encoding="utf-8")
    with pytest.raises(SplitError, match="EXPOSURE_LEDGER_INVALID"):
        load_exposure_ledger(ledger_path)


def test_mixed_label_versions_are_rejected() -> None:
    data = dataset()
    refs = annotations(data)
    refs["snapshots"][1]["label_definition_version"] = "another-definition"
    refs["snapshots"][1] = seal(refs["snapshots"][1], "snapshot_hash")
    refs = seal(refs, "annotations_hash")
    result = check_admission(
        data, build_split(data, {"a": "TEST", "b": "TEST"}), refs, freeze=frozen(data)
    )
    assert "LABEL_DEFINITION_VERSION_CONFLICT" in result["reason_codes"]


@pytest.mark.parametrize("key", ["training_image_ids", "training_asset_hashes"])
def test_training_scope_cannot_consume_test(key: str) -> None:
    data = dataset()
    config = frozen(data)
    config[key] = ["a" if key == "training_image_ids" else data["images"][0]["asset_sha256"]]
    config = seal(config, "freeze_hash")
    result = check_admission(
        data, build_split(data, {"a": "TEST"}), annotations(data), freeze=config
    )
    assert "TRAINING_TEST_LEAKAGE" in result["reason_codes"]


def test_current_dataset_training_requires_train_only_scope() -> None:
    data = dataset()
    config = frozen(data)
    config["training_dataset_manifest_hash"] = data["manifest_hash"]
    config["training_image_ids"] = ["b"]
    config = seal(config, "freeze_hash")
    split = build_split(data, {"a": "TEST", "b": "VALIDATION"})
    result = check_admission(data, split, annotations(data), freeze=config)
    assert "TRAINING_SCOPE_INVALID" in result["reason_codes"]


def test_current_dataset_training_missing_scope_is_not_assumed_safe() -> None:
    data = dataset()
    config = frozen(data)
    config["training_dataset_manifest_hash"] = data["manifest_hash"]
    config = seal(config, "freeze_hash")
    result = check_admission(
        data, build_split(data, {"a": "TEST"}), annotations(data), freeze=config
    )
    assert "TRAINING_SCOPE_NOT_DECLARED" in result["reason_codes"]


def test_resealed_split_cannot_hide_declared_session_connection() -> None:
    data = dataset()
    for row in data["images"][:2]:
        row["capture_session_id"] = "session"
    data = seal(data, "manifest_hash")
    split = build_split(data, {"a": "TEST", "b": "TEST"})
    split["records"][1]["split"] = "TRAIN"
    split["records"][1]["group_id"] = canonical_hash("forged-disconnected-group")
    split["association_edges"] = []
    split = seal(split, "split_hash")
    result = check_admission(data, split, annotations(data), freeze=frozen(data))
    assert "GROUP_CROSS_SPLIT" in result["reason_codes"]


def test_changed_split_after_seal_is_blocked() -> None:
    data = dataset()
    refs = annotations(data)
    config = frozen(data)
    original = build_split(data, {"a": "TEST", "b": "TRAIN"})
    sealed = seal_test(data, original, refs, config)
    changed = build_split(data, {"a": "OUT_OF_DOMAIN", "b": "TRAIN"})
    result = check_admission(data, changed, refs, freeze=config, test_seal=sealed)
    assert "SEALED_TEST_CHANGED" in result["reason_codes"]


def test_prediction_score_requires_matching_gt_read_event(tmp_path: Path) -> None:
    data = dataset()
    refs = annotations(data)
    config = frozen(data)
    split = build_split(data, {"a": "TEST"})
    sealed = seal_test(data, split, refs, config)
    prediction = seal(
        {
            "dataset_manifest_hash": data["manifest_hash"],
            "freeze_hash": config["freeze_hash"],
            **{key: config[key] for key in ["config_hash", "model_hash", "training_data_hash"]},
        },
        "prediction_hash",
    )
    ledger_dir = tmp_path / "ledger"
    details = {
        "freeze_hash": config["freeze_hash"],
        "prediction_hash": prediction["prediction_hash"],
    }
    append_exposure_event(ledger_dir, "CONFIG_FROZEN", details)
    append_exposure_event(ledger_dir, "PREDICTIONS_FIXED", details)
    append_exposure_event(
        ledger_dir, "GT_SCORE_READ", {**details, "annotations_hash": canonical_hash("wrong_GT")}
    )
    result = check_admission(
        data,
        split,
        refs,
        freeze=config,
        test_seal=sealed,
        predictions=prediction,
        ledger=ledger_dir,
    )
    assert "GT_SCORE_READ_NOT_RECORDED" in result["reason_codes"]


def test_prediction_hash_bindings_must_match_freeze() -> None:
    data = dataset()
    config = frozen(data)
    refs = annotations(data)
    split = build_split(data, {"a": "TEST"})
    sealed = seal_test(data, split, refs, config)
    prediction = seal(
        {
            "dataset_manifest_hash": data["manifest_hash"],
            "freeze_hash": config["freeze_hash"],
            "config_hash": canonical_hash("changed-config"),
            "model_hash": config["model_hash"],
            "training_data_hash": config["training_data_hash"],
        },
        "prediction_hash",
    )
    result = check_admission(
        data, split, refs, freeze=config, test_seal=sealed, predictions=prediction
    )
    assert "PREDICTION_FREEZE_MISMATCH" in result["reason_codes"]


def test_simulated_review_remains_engineering_only() -> None:
    data = dataset()
    data["purpose"], data["SYNTHETIC"] = "SYNTHETIC_ENGINEERING", True
    source = data["sources"][0]
    source.update(
        {
            "purpose": "SYNTHETIC_ENGINEERING",
            "SYNTHETIC": True,
            "license_status": "SYNTHETIC_AUTHORITY",
        }
    )
    data = seal(data, "manifest_hash")
    draft = create_draft(
        data["images"][0],
        annotation_version="simulated-v1",
        annotator_id="simulator",
        purpose=data["purpose"],
        synthetic=True,
        workflow_mode="SIMULATED_ENGINEERING",
        objects=[],
    )
    peer = create_draft(
        data["images"][0],
        annotation_version="simulated-peer-v1",
        annotator_id="simulator-peer",
        purpose=data["purpose"],
        synthetic=True,
        workflow_mode="SIMULATED_ENGINEERING",
        objects=[],
    )
    reviews = [draft, peer]
    for index, row in enumerate(reviews):
        submitted = transition_review(row, "SUBMITTED", actor_id="simulator")
        reviews[index] = transition_review(submitted, "REVIEW_PENDING", actor_id="simulator")
    final = adjudicate_annotations(
        reviews[0],
        reviews[1],
        [],
        adjudicator_id="simulator-arbitrator",
        annotation_version="simulated-final-v1",
    )
    final = transition_review(final, "SEALED", actor_id="simulator-arbitrator")
    refs = annotation_bundle(data, [final])
    split = build_split(data, {"a": "TEST"})
    result = seal_test(data, split, refs, frozen(data))
    assert result["test_exposure"] == "SIMULATED_ENGINEERING"
    assert result["real_orchard_accuracy_approved"] is False
    assert (
        check_admission(data, split, refs, freeze=frozen(data))["status"]
        == "ADMITTED_SYNTHETIC_ENGINEERING"
    )


def test_ledger_symlink_is_rejected(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    with pytest.raises(SplitError, match="EXPOSURE_LEDGER_PATH_INVALID"):
        load_exposure_ledger(alias)


def test_missing_ledger_event_file_is_detected(tmp_path: Path) -> None:
    directory = tmp_path / "ledger"
    config_hash = canonical_hash("config")
    append_exposure_event(directory, "CONFIG_FROZEN", {"freeze_hash": config_hash})
    append_exposure_event(
        directory,
        "PREDICTIONS_FIXED",
        {"freeze_hash": config_hash, "prediction_hash": canonical_hash("prediction")},
    )
    (directory / "000001_CONFIG_FROZEN.json").unlink()
    with pytest.raises(SplitError, match="EXPOSURE_LEDGER_INVALID"):
        load_exposure_ledger(directory)


@pytest.mark.parametrize("objects", [{"wrong": "mapping"}, [1], [None]])
def test_malformed_object_rows_are_not_an_implicit_empty_reference(objects: object) -> None:
    data = dataset()
    refs = annotations(data)
    refs["snapshots"][0]["objects"] = objects
    refs["snapshots"][0] = seal(refs["snapshots"][0], "snapshot_hash")
    refs = seal(refs, "annotations_hash")
    result = check_admission(data, build_split(data, {"a": "TEST"}), refs, freeze=frozen(data))
    assert result["status"] == "NOT_EVALUABLE"
    assert "GT_OBJECTS_INVALID" in result["reason_codes"]


def test_source_research_authority_is_separate_from_license_name() -> None:
    data = dataset()
    data["sources"][0]["research_use"] = False
    data = seal(data, "manifest_hash")
    result = check_admission(
        data, build_split(data, {"a": "TEST"}), annotations(data), freeze=frozen(data)
    )
    assert "RESEARCH_USE_NOT_AUTHORIZED" in result["reason_codes"]


def test_unknown_capture_clock_not_replaced_with_import_clock() -> None:
    data = dataset()
    for row in data["images"]:
        row["observed_at"] = None
        row["imported_at"] = "2026-01-01T12:00:00Z"
    data = seal(data, "manifest_hash")
    result = build_split(data, {"a": "TRAIN", "b": "TEST"})
    assert result["holdout_verification"]["cross_date"]["status"] == "UNVERIFIED"


@pytest.mark.parametrize("field", ["capture_session_id", "source_batch_id", "video_id"])
def test_explicit_unknown_associations_do_not_join(field: str) -> None:
    data = dataset()
    for row in data["images"]:
        row[field] = "UNKNOWN"
    data = seal(data, "manifest_hash")
    assert len(build_split(data, {"a": "TRAIN", "b": "TEST"})["groups"]) == 3


def test_declared_import_batch_is_not_a_capture_association() -> None:
    data = dataset()
    for row in data["images"]:
        row["import_batch_id"] = "import-operation-1"
    data = seal(data, "manifest_hash")
    assert len(build_split(data, {"a": "TRAIN", "b": "TEST"})["groups"]) == 3


def test_exact_asset_duplicate_survives_false_candidate_rejection() -> None:
    data = dataset()
    data["images"][1]["asset_sha256"] = data["images"][0]["asset_sha256"]
    data = seal(data, "manifest_hash")
    report = {
        "candidate_edges": [
            {
                "image_id_a": "a",
                "image_id_b": "b",
                "relation": "DHASH",
                "status": "REJECTED",
                "reviewer_id": "self-asserted",
                "reviewed_at": "2026-01-01T00:00:00Z",
                "review_reason": "false positive",
            }
        ]
    }
    with pytest.raises(SplitError, match="GROUP_CROSS_SPLIT"):
        build_split(data, {"a": "TRAIN", "b": "TEST"}, report)


def test_orchard_authority_requires_owner_evidence_even_with_public_license() -> None:
    data = dataset()
    data["purpose"] = "AUTHORIZED_ORCHARD_PILOT"
    source = data["sources"][0]
    source.update({"purpose": data["purpose"], "license_status": "AUTHORITY_VERIFIED"})
    data = seal(data, "manifest_hash")
    result = check_admission(data, build_split(data, {"a": "TEST"}), None, freeze=frozen(data))
    assert "ORCHARD_AUTHORIZATION_EVIDENCE_MISSING" in result["reason_codes"]


def test_zero_gt_remains_qualified_only_when_explicitly_annotated() -> None:
    data = dataset()
    refs = annotations(data)
    row = refs["snapshots"][0]
    row["objects"], row["visible_count"] = [], 0
    refs["snapshots"][0] = seal(row, "snapshot_hash")
    refs = seal(refs, "annotations_hash")
    result = check_admission(data, build_split(data, {"a": "TEST"}), refs, freeze=frozen(data))
    assert result["qualified_reference_count"] == 1
    assert not result["reason_codes"]


@pytest.mark.parametrize("field,value", [("source_id", "another-source"), ("image_width", 41)])
def test_snapshot_source_and_dimensions_are_bound_to_actual_asset(
    field: str, value: object
) -> None:
    data = dataset()
    refs = annotations(data)
    refs["snapshots"][0][field] = value
    refs["snapshots"][0] = seal(refs["snapshots"][0], "snapshot_hash")
    refs = seal(refs, "annotations_hash")
    result = check_admission(data, build_split(data, {"a": "TEST"}), refs, freeze=frozen(data))
    assert result["status"] == "NOT_EVALUABLE"
    assert "GT_QUALITY_INSUFFICIENT" in result["reason_codes"]


def test_confirmed_perceptual_edges_survive_pending_view() -> None:
    """Human-confirmed non-exact edges leave candidate_edges but remain isolation links."""
    report = {
        "edges": [
            {
                "image_id_a": "a",
                "image_id_b": "b",
                "relation": "PERCEPTUAL_SIMILARITY",
                "status": "CONFIRMED",
            }
        ],
        "candidate_edges": [],
    }
    with pytest.raises(SplitError, match="GROUP_CROSS_SPLIT"):
        build_split(dataset(), {"a": "TRAIN", "b": "TEST"}, report)


def test_hashed_duplicate_report_must_bind_current_dataset() -> None:
    report = seal(
        {"edges": [], "candidate_edges": [], "dataset_manifest_hash": "a" * 64}, "duplicate_hash"
    )
    with pytest.raises(SplitError, match="DUPLICATE_DATASET_MISMATCH"):
        build_split(dataset(), {"a": "TEST"}, report)


def test_tampered_hashed_duplicate_report_is_rejected() -> None:
    data = dataset()
    report = seal(
        {"edges": [], "candidate_edges": [], "dataset_manifest_hash": data["manifest_hash"]},
        "duplicate_hash",
    )
    report["threshold"] = 100
    with pytest.raises(SplitError, match="DUPLICATE_REPORT_HASH_INVALID"):
        build_split(data, {"a": "TEST"}, report)
