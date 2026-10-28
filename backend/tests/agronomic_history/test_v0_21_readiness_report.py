"""S4 derives reports from executions; no synthetic result proves real authority."""

import copy
import hashlib
import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from backend.research import v021_cycle_features as cycle
from backend.research import v021_readiness_report as report
from backend.research.v021_readiness_cli import run
from backend.tests.agronomic_history.v0_21_readiness_fixture import AS_OF, case, catalog, execute

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def test_chain_executes_and_exposes_both_equal_priority_targets(monkeypatch):
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: pytest.fail("NETWORK_READ"))
    result = report.build_report([execute()], None)
    assert (
        result["goals"]["season_peak"]["priority"]
        == result["goals"]["origin_h7_h15"]["priority"]
        == "EQUAL"
    )
    assert result["datasets"][0]["source_identity"]["prediction_seal_sha256"]
    s3 = result["datasets"][0]["s3"]
    assert len(s3["groups"]) == 4
    full = s3["groups"]["SYNTHETIC_VALIDATION:FULL_SEASON_PEAK"]
    assert full["diagnosis"] == "MIXED"
    assert s3["interpretation"] == "SYNTHETIC_ARITHMETIC_DEMONSTRATION"
    text = report.render_markdown(result)
    for heading in (
        "版本与范围",
        "两个同优先级",
        "功能与覆盖",
        "研究准入缺口",
        "公平研究",
        "工程版本收口",
    ):
        assert heading in text
    assert "92.000000" in text and "67.000000" in text


@pytest.mark.parametrize(
    "stage,scenario",
    [
        ("S2", "UNPROVEN_CONTINUITY"),
        ("S2", "CONFLICTING_EFFECTIVE_INTERVALS"),
        ("S2", "MISSING_AREA"),
        ("S3", "IMMATURE_LABELS"),
        ("S3", "MISSING_DAY"),
        ("S3", "COMMON_COHORT_FAILURES"),
    ],
)
def test_failures_and_partial_coverage_are_not_flattened_to_pass(stage, scenario):
    value = report.build_report([execute(stage, scenario)], None)
    dataset = value["datasets"][0]
    assert dataset["blockers"]
    assert dataset["real_evidence_status"] == "NOT_PROVEN"
    assert value["closeout"]["formal_complete"] is False
    assert all(gap["status"] == "NOT_PROVEN" for gap in value["real_data_gaps"])


def test_area_axes_and_s1_features_remain_separate():
    result = report.build_report(
        [execute("S1", "CYCLE_EXAMPLE"), execute("S2", "BUSINESS_EXAMPLE")], None
    )
    s1, s2 = result["datasets"][0]["s1"], result["datasets"][1]["s2"]
    assert s1["base_count"] == 3 and s1["cycle_count"] == 6
    assert s1["snapshot_count"] == 8
    comparison = s2["comparisons"][0]
    assert comparison["area_changes"]["PLANTED"]["delta_mu"] == "20.000000"
    assert comparison["area_changes"]["PRODUCTIVE"]["delta_mu"] == "-10.000000"
    assert comparison["area_changes"]["EFFECTIVE"]["delta_mu"] == "-5.000000"
    assert s2["component_counts"]["density"]["NOT_PROVEN"] == 3
    assert s2["component_counts"]["replant"]["NOT_PROVEN"] == 3
    assert result["coverage_policy"] == "PER_DATASET_NO_BUSINESS_POPULATION_SUM"


def test_s3_r2_gate_and_zero_actual_are_preserved():
    gap = execute("S3", "R2_H15_PREFIX_MISSING_D8")
    for family in ("ORIGIN_H7_PREFIX", "ORIGIN_H15_LOCAL"):
        m = gap["s3"]["groups"]["SYNTHETIC_VALIDATION:" + family]["metrics"]["DAILY_MAE"]
        assert (m["candidate_count"], m["common_count"], m["not_computable_count"]) == (2, 1, 1)
    zero = execute("S3", "ZERO_ACTUAL")
    for g in zero["s3"]["groups"].values():
        assert g["metrics"]["SINGLE_DAY_PEAK_DATE_MAE"]["common_count"] == 0
        assert g["metrics"]["DAILY_MAE"]["common_count"] == g["candidate_count"]


def test_seal_is_not_changed_by_labels():
    spec, values = case()
    a = report.prepare_case(
        spec, values["package"], values["cycles"], values["structure"], values["protocol"]
    )
    a = report.seal_case(a, values["predictions"])
    seal = copy.deepcopy(a.seal)
    values["labels"]["labels"][0]["rows"][0]["kg"] = "999.000000"
    result = report.finish_case(a, values["labels"], as_of=AS_OF)
    assert a.seal == seal
    assert result["source_identity"]["prediction_seal_sha256"] == seal["seal_sha256"]


def test_html_and_markdown_escape_external_text_without_remote_resources():
    title = '<script src="https://bad.invalid/x">bad</script> | [x](javascript:alert(1))'
    result = report.build_report([execute()], None, title=title)
    html, md = report.render_html(result), report.render_markdown(result)
    assert "<script" not in html and "<script" not in md
    assert "&lt;script" in html and "&lt;script" in md
    assert "<link" not in html and "<img" not in html and "<iframe" not in html
    assert 'href="javascript:' not in html and 'src="https://' not in html
    assert "width=device-width" in html and "Content-Security-Policy" in html
    assert "[x](javascript:" not in md


def test_report_keeps_detailed_ledgers_under_separate_dataset_sections():
    value = report.build_report([execute(), execute("S3", "MISSING_DAY")], None)
    html = report.render_html(value)
    assert html.count('<details class="dataset">') == 2
    assert all(f'id="chapter-{i}"' in html for i in range(1, 7))
    assert "合成数值示例" in html and "独立阻断账本" in html
    assert "INCOMPLETE_CALENDAR" in html
    assert "overflow-wrap:anywhere" in html


def test_published_execution_files_match_actual_manifest_and_stage_contracts():
    root = Path(__file__).resolve().parents[3]
    folder = root / "docs/v0-21/s4/examples"
    manifest = json.loads((folder / "manifest.json").read_text())
    value = json.loads((folder / "research-readiness.json").read_text())
    for name, expected in manifest["business_files_sha256"].items():
        assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == expected
    assert value["result_sha256"] == manifest["business_result_sha256"]
    assert len(value["datasets"]) == 39
    assert len(value["scenario_coverage"]["S2"]["input_identity_verified_ids"]) == 15
    # The 22 registered S3 scenarios plus the R2 prefix regression.
    assert len(value["scenario_coverage"]["S3"]["input_identity_verified_ids"]) == 23
    assert all(not v for v in value["restrictions"].values())
    assert report.render_markdown(value).encode() == (folder / "report.md").read_bytes()
    assert report.render_html(value).encode() == (folder / "report.html").read_bytes()


def test_closeout_cannot_be_claimed_from_hashes_or_synthetic_success():
    value = report.build_report([execute()], None)
    c = value["closeout"]
    assert c["formal_complete"] is False and c["independent_review_status"] == "NOT_PROVEN"
    assert c["owner_merge_authorized"] is False and c["post_merge_main_ci"] == "NOT_EXECUTED_FOR_S4"
    assert c["release_authorized"] is False and c["deploy_authorized"] is False
    assert value["historical_deliveries"]["status"] == "NOT_PROVEN"
    for gap in value["real_data_gaps"]:
        assert gap["status"] == "NOT_PROVEN" and not gap["evidence_refs"]


def test_real_marker_rejected_before_referenced_files_are_opened(monkeypatch, tmp_path):
    from backend.research import v021_readiness_cli as cli

    path = tmp_path / "catalog.json"
    path.write_text('{"data_class":"REAL"}')
    calls = []
    original = cli._read_json

    def read(file):
        calls.append(file.name)
        return original(file)

    monkeypatch.setattr(cli, "_read_json", read)
    with pytest.raises(ValueError, match="SYNTHETIC_ONLY"):
        run(path, tmp_path / "output")
    assert calls == ["catalog.json"] and not (tmp_path / "output").exists()


def test_cli_two_processes_are_deterministic_and_outputs_are_private(tmp_path):
    inputs = catalog(tmp_path / "input")
    folders = [tmp_path / "first", tmp_path / "second"]
    for folder in folders:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "backend.research.v021_readiness_cli",
                "--catalog",
                str(inputs),
                "--output",
                str(folder),
            ],
            check=True,
            capture_output=True,
        )
        assert folder.stat().st_mode & 0o777 == 0o700
        assert {p.name for p in folder.iterdir()} == {
            "research-readiness.json",
            "report.md",
            "report.html",
            "manifest.json",
        }
        assert all(p.stat().st_mode & 0o777 == 0o600 for p in folder.iterdir())
    for filename in ("research-readiness.json", "report.md", "report.html"):
        assert (folders[0] / filename).read_bytes() == (folders[1] / filename).read_bytes()
    before = {p.name: p.read_bytes() for p in folders[0].iterdir()}
    with pytest.raises(ValueError, match="OUTPUT_ALREADY_EXISTS"):
        run(inputs, folders[0])
    assert before == {p.name: p.read_bytes() for p in folders[0].iterdir()}


@pytest.mark.parametrize("defect", ["duplicate_key", "hash", "path", "symlink", "schema"])
def test_explicit_input_contract_and_path_guards(tmp_path, defect):
    inputs = catalog(tmp_path / "input")
    value = json.loads(inputs.read_text())
    if defect == "duplicate_key":
        inputs.write_text('{"data_class":"SYNTHETIC_TEST_FIXTURE","data_class":"REAL"}')
    elif defect == "schema":
        value["schema_version"] = "UNSUPPORTED"
        inputs.write_text(json.dumps(value))
    else:
        ref = value["datasets"][0]["inputs"]["package"]
        if defect == "hash":
            ref["sha256"] = "0" * 64
        if defect == "path":
            ref["path"] = "../private.json"
        if defect == "symlink":
            source = inputs.parent / ref["path"]
            source.rename(source.with_suffix(".backup"))
            source.symlink_to(source.with_suffix(".backup"))
        inputs.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        run(inputs, tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_full_matrix_executes_all_15_and_22_scenarios_without_population_merging(tmp_path):
    path = catalog(tmp_path / "input", full_matrix=True)
    result = run(path, tmp_path / "output")
    assert len(result["datasets"]) == 39
    assert result["scenario_coverage"]["S2"]["executed_count"] == 15
    assert result["scenario_coverage"]["S3"]["executed_count"] == 22
    assert result["scenario_coverage"]["S3"]["extra_scenario_ids"] == ["R2_H15_PREFIX_MISSING_D8"]
    rejected = next(d for d in result["datasets"] if d["scenario_id"] == "PREFIX_MISMATCH")
    assert rejected["synthetic_validation_status"] == "REJECTED_INPUT"
    assert rejected["source_identity"]["labels_read"] is False


def test_report_tampering_rejected_by_renderers():
    value = report.build_report([execute()], None)
    value["closeout"]["formal_complete"] = True
    with pytest.raises(ValueError):
        report.render_html(value)


@pytest.mark.parametrize(
    "field,value",
    [
        ("formal_complete", True),
        ("owner_merge_authorized", True),
        ("independent_review_status", "APPROVED"),
        ("post_merge_main_ci", "SUCCESS"),
        ("release_authorized", True),
        ("deploy_authorized", True),
    ],
)
def test_self_resigning_a_report_cannot_enable_formal_closeout(field, value):
    result = report.build_report([execute()], None)
    result["closeout"][field] = value
    result["result_sha256"] = cycle.digest(
        {k: v for k, v in result.items() if k != "result_sha256"}
    )
    for render in (report.render_html, report.render_markdown):
        with pytest.raises(ValueError, match="S4_FORMAL_COMPLETION_NOT_AUTHORIZED"):
            render(result)


def test_missing_primary_pruning_and_clocks_remain_visible():
    spec, values = case("S1", "CYCLE_EXAMPLE")
    values["cycles"]["members"][0]["primary_pruning"] = []
    values["cycles"]["record_clocks"] = {}
    a = report.prepare_case(spec, values["package"], values["cycles"])
    result = report.finish_case(a, as_of=AS_OF)
    assert result["s1"]["feature_reasons"]
    assert result["s1"]["origin_decision_reasons"]
    assert result["blockers"] and result["real_evidence_status"] == "NOT_PROVEN"


def test_cli_rejection_happens_before_label_file_read(tmp_path):
    path = catalog(tmp_path / "input", full_matrix=True)
    raw = json.loads(path.read_text())
    bad = next(d for d in raw["datasets"] if d["scenario_id"] == "PREFIX_MISMATCH")
    bad["inputs"]["labels"] = {"path": "UNREADABLE-NOT-SYNTHETIC.json", "sha256": "0" * 64}
    raw["datasets"] = [bad]
    path.write_text(json.dumps(raw))
    result = run(path, tmp_path / "output")
    assert result["datasets"][0]["synthetic_validation_status"] == "REJECTED_INPUT"
    assert result["datasets"][0]["source_identity"]["labels_read"] is False


def test_whitespace_changes_only_raw_file_manifest_hashes(tmp_path):
    path = catalog(tmp_path / "input")
    first = run(path, tmp_path / "first")
    catalog_value = json.loads(path.read_text())
    ref = catalog_value["datasets"][0]["inputs"]["package"]
    file = path.parent / ref["path"]
    file.write_text(json.dumps(json.loads(file.read_text()), ensure_ascii=False, indent=3) + "\n")
    ref["sha256"] = hashlib.sha256(file.read_bytes()).hexdigest()
    path.write_text(json.dumps(catalog_value, indent=2))
    second = run(path, tmp_path / "second")
    assert first == second
    for name in ("research-readiness.json", "report.md", "report.html"):
        assert (tmp_path / "first" / name).read_bytes() == (tmp_path / "second" / name).read_bytes()
    assert (
        json.loads((tmp_path / "first/manifest.json").read_text())["explicit_input_file_sha256"]
        != json.loads((tmp_path / "second/manifest.json").read_text())["explicit_input_file_sha256"]
    )


@pytest.mark.parametrize(
    "defect", ["missing_refs", "wrong_hash", "wrong_commit", "incomplete_predecessors"]
)
def test_unverifiable_public_evidence_is_rejected(tmp_path, defect):
    root = Path(__file__).resolve().parents[3]
    evidence = json.loads(
        (root / "docs/v0-21/evidence/v0.21-s4-readiness-closeout-r1.json").read_text()
    )
    if defect == "missing_refs":
        evidence["frozen_source_refs"] = []
    if defect == "wrong_hash":
        evidence["frozen_source_refs"][0]["sha256"] = "0" * 64
    if defect == "wrong_commit":
        evidence["frozen_source_refs"][0]["commit"] = "0" * 40
    if defect == "incomplete_predecessors":
        evidence["predecessors"].pop()
    path = catalog(tmp_path / "input", evidence=evidence)
    with pytest.raises(ValueError):
        run(path, tmp_path / "output")
    assert not (tmp_path / "output").exists()


def test_public_evidence_and_recipe_input_identities_are_checked(tmp_path):
    root = Path(__file__).resolve().parents[3]
    evidence = json.loads(
        (root / "docs/v0-21/evidence/v0.21-s4-readiness-closeout-r1.json").read_text()
    )
    path = catalog(tmp_path / "input", evidence=evidence)
    result = run(path, tmp_path / "output")
    assert result["historical_deliveries"]["status"] == "MERGES_RECORDED_IN_PINNED_PUBLIC_EVIDENCE"
    assert result["scenario_coverage"]["S3"]["input_identity_verified_ids"] == ["COMPLETE"]
    assert result["closeout"]["formal_complete"] is False
    manifest = json.loads((tmp_path / "output/manifest.json").read_text())
    assert manifest["frozen_git_refs_verified"] is True
    assert not any("/Users/" in p or "/tmp/" in p for p in manifest["explicit_input_file_sha256"])


def test_tampered_case_execution_and_duplicate_datasets_are_rejected():
    value = execute()
    bad = copy.deepcopy(value)
    bad["synthetic_validation_status"] = "PASS"
    with pytest.raises(ValueError, match="REPORT_EXECUTION_HASH_MISMATCH"):
        report.build_report([bad], None)
    with pytest.raises(ValueError, match="DUPLICATE_DATASET_ID"):
        report.build_report([value, value], None)


def test_absent_evaluation_scopes_are_not_marked_synthetically_validated():
    value = report.build_report([execute("S1", "CYCLE_EXAMPLE")], None)
    for goal in value["goals"].values():
        assert goal["synthetic_validation_status"] == "NOT_PROVEN_NO_SCOPE_EXECUTION"
        assert goal["execution_refs"] == []


def test_upstream_published_outputs_are_recomputed_with_original_identities():
    root = Path(__file__).resolve().parents[3]
    one = root / "docs/v0-21/s1/examples/cycle-features-r1"

    def read(path):
        return json.loads(path.read_text())

    spec = dict(dataset_id="SYN-PUBLISHED-S1", stage="S1", scenario_id="CYCLE_EXAMPLE")
    prepared = report.prepare_case(
        spec, read(one / "synthetic-v020-package.json"), read(one / "synthetic-declarations.json")
    )
    assert prepared.s1 == read(one / "cycle-features.json")
    two = root / "docs/v0-21/s2/examples/business-r1"
    s1 = read(two / "s1-cycle-features.json")
    spec.update(dataset_id="SYN-PUBLISHED-S2", stage="S2", scenario_id="BUSINESS_EXAMPLE")
    prepared = report.prepare_case(
        spec,
        s1["original_package"],
        s1["original_declarations"],
        read(two / "structure-declarations.json"),
    )
    assert prepared.s2 == read(two / "structure-scenarios.json")
    three = root / "docs/v0-21/s3/examples"
    s1, s2 = read(three / "s1.json"), read(three / "s2.json")
    spec.update(dataset_id="SYN-PUBLISHED-S3", stage="S3", scenario_id="COMPLETE")
    prepared = report.prepare_case(
        spec,
        s1["original_package"],
        s1["original_declarations"],
        s2["original_declarations"],
        read(three / "protocol.json"),
    )
    prepared = report.seal_case(prepared, read(three / "predictions.json"))
    result = report.finish_case(prepared, read(three / "labels.json"), as_of=AS_OF)
    assert (
        result["source_identity"]["evaluation_result_sha256"]
        == read(three / "evaluation.json")["result_sha256"]
    )


def test_referenced_json_is_parsed_from_the_hashed_bytes_once(monkeypatch, tmp_path):
    from backend.research.v021_readiness_cli import _read_json

    file = tmp_path / "SYNTHETIC.json"
    raw = b'{"data_class":"SYNTHETIC_TEST_FIXTURE","kg":"1.000000"}'
    file.write_bytes(raw)
    monkeypatch.setattr(Path, "read_bytes", lambda _: pytest.fail("SECOND_UNBOUND_FILE_READ"))
    value, sha = _read_json(file)
    assert value["kg"] == "1.000000" and sha == hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize("raw", ['{"n":NaN}', '{"n":1.5}', '{"a":1,"a":2}', "[]"])
def test_strict_json_reader_rejects_unsupported_values(tmp_path, raw):
    from backend.research.v021_readiness_cli import _read_json

    file = tmp_path / "SYNTHETIC.json"
    file.write_text(raw)
    with pytest.raises(ValueError):
        _read_json(file)
