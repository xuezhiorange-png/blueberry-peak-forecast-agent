"""Contract-only integrity checks for V0.9-S1; no model code is exercised."""

import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
S0 = ROOT / "docs/v0-9/s0"
S1 = ROOT / "docs/v0-9/s1"
EVIDENCE_PATH = (
    ROOT / "docs/v0-9/evidence/s1-biological-state-and-management-event-contract-r1.json"
)

EXPECTED_S0_HASHES: dict[Path, str] = {
    S0 / "global-protected-blueberry-biology-and-management-authority-review-r1.md": (
        "827725a44094e5e15643186fe8f82095adbff0bfc2b2ac549aca6600d06a4c13"
    ),
    ROOT
    / "docs/v0-9/evidence"
    / "s0-global-protected-blueberry-biology-and-management-authority-review-r1.json": (
        "530106f7291ab3d92fe4b0a0d682efc0fc154149218acda71369f76e785449cf"
    ),
    S0 / "scientific-authority-matrix-r1.csv": (
        "1fecd24c4aa537d5617a960e15ab74ace260ad35e30e63d9fdbe89e59bf88294"
    ),
    S0 / "biological-causal-claim-register-r1.csv": (
        "0ee8959db03f1ac28b226df06c00bf08c2427949b2f1e9de69a772bbd805d55a"
    ),
    S0 / "evidence-conflict-and-uncertainty-register-r1.csv": (
        "e5c17df1d33e3ef9dcc1d5d149598fa6a602a5c65a09f99d47e8040d42d94a91"
    ),
    S0 / "literature-parameter-candidate-register-r1.csv": (
        "2d28f90e42eafeea14f252e96ed0c26e2bc6b78b1c8273263b5d2d32b1410325"
    ),
}


def _json(relative_path: str) -> tuple[dict[str, Any], bytes]:
    path = ROOT / relative_path
    raw = path.read_bytes()
    return json.loads(raw), raw


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
        assert reader.fieldnames
        assert all(None not in row for row in rows)
        return rows


def test_s0_authority_hashes_are_pinned_and_unchanged() -> None:
    for path, expected in EXPECTED_S0_HASHES.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected


def test_contract_registries_have_unique_ids_and_valid_units() -> None:
    state, state_bytes = _json("docs/v0-9/s1/biological-state-registry-r1.json")
    events, event_bytes = _json("docs/v0-9/s1/management-event-registry-r1.json")
    edges, edge_bytes = _json("docs/v0-9/s1/causal-edge-registry-r1.json")
    evidence, evidence_bytes = _json(
        "docs/v0-9/evidence/s1-biological-state-and-management-event-contract-r1.json"
    )

    assert json.loads(state_bytes) == state
    assert json.loads(event_bytes) == events
    assert json.loads(edge_bytes) == edges
    assert json.loads(evidence_bytes) == evidence

    state_ids = state["phenology_state_machine"]["state_ids"]
    assert len(state_ids) == len(set(state_ids)) == 21
    assert (
        len(state["production_systems"])
        == len({item["system_id"] for item in state["production_systems"]})
        == 3
    )

    unit_vocabulary = set(state["unit_vocabulary"])
    state_fields = (
        state["plant_state_fields"]
        + state["interseason_state_fields"]
        + state["source_sink_state_fields"]
    )
    field_ids = [item["field_id"] for item in state["plant_state_fields"]]
    assert len(field_ids) == len(set(field_ids)) == 27
    assert len(state["interseason_state_fields"]) == 3
    assert len(state["source_sink_state_fields"]) == 3
    for field in state_fields:
        assert field["nullable"] is True
        assert field["default_authority_type"] in state["parameter_authority_types"]
        assert field["observability_class"] in state["observability_classes"]
        unit = re.sub(r"\s*\([^)]*\)$", "", field["unit"])
        assert all(choice.strip() in unit_vocabulary for choice in unit.split(" or "))

    event_types = [item["event_type"] for item in events["event_types"]]
    assert len(event_types) == len(set(event_types)) == 29
    generic_field_ids = [item["field_id"] for item in events["generic_fields"]]
    assert len(generic_field_ids) == len(set(generic_field_ids))
    authority_field = next(
        item for item in events["generic_fields"] if item["field_id"] == "authority_level"
    )
    assert authority_field["values"] == events["event_authority_levels"]
    intensity_unit_field = next(
        item for item in events["generic_fields"] if item["field_id"] == "intensity_unit"
    )
    assert intensity_unit_field["type"] == "unit_id_or_null"
    environment_units = {item["unit"] for item in state["environment_input_contract"]["variables"]}
    assert environment_units <= unit_vocabulary

    claim_rows = _csv(S0 / "biological-causal-claim-register-r1.csv")
    claims = {row["claim_id"]: row for row in claim_rows}
    sources = {row["source_id"] for row in _csv(S0 / "scientific-authority-matrix-r1.csv")}
    admitted_claims = {item["claim_id"]: item for item in edges["mechanism_admission"]}
    assert set(admitted_claims) == set(claims)
    allowed_statuses = set(edges["admission_rule"]["allowed_statuses"])
    assert all(item["admission_status"] in allowed_statuses for item in admitted_claims.values())
    for claim_id, item in admitted_claims.items():
        assert item["source_evidence_class"] == claims[claim_id]["evidence_class"]
        assert item["s0_readiness"] == claims[claim_id]["s1_contract_readiness"]

    for event in events["event_types"]:
        claim_source_ids = {
            source_id
            for claim_id in event["claim_ids"]
            for source_id in claims[claim_id]["source_ids"].split(";")
        }
        assert set(event["source_ids"]) <= claim_source_ids
        assert set(event["claim_ids"]) <= set(claims)

    not_ready = {
        claim_id
        for claim_id, row in claims.items()
        if row["s1_contract_readiness"].startswith("NOT_READY")
    }
    quarantined = {item["claim_id"] for item in edges["quarantined_mechanisms"]}
    assert not_ready == quarantined
    assert all(
        admitted_claims[claim_id]["admission_status"] != "CONTRACT_READY"
        for claim_id in quarantined
    )

    all_edges = edges["causal_edges"]
    assert len(all_edges) == len({item["edge_id"] for item in all_edges}) == 33
    state_or_field_ids = set(state_ids) | {item["field_id"] for item in state_fields}
    environment_ids = {
        item["variable_id"] for item in state["environment_input_contract"]["variables"]
    }
    for edge in all_edges:
        assert edge["claim_ids"]
        assert edge["authority_source_ids"]
        assert set(edge["claim_ids"]) <= set(claims)
        claim_source_ids = {
            source_id
            for claim_id in edge["claim_ids"]
            for source_id in claims[claim_id]["source_ids"].split(";")
        }
        assert set(edge["authority_source_ids"]) <= claim_source_ids, edge["edge_id"]
        assert set(edge["authority_source_ids"]) <= sources
        assert edge["numeric_effect_authorized"] is False
        if edge["edge_type"] == "PHENOLOGY_TRANSITION":
            assert edge["source_state"] in state_ids
            assert edge["target_state"] in state_ids
            assert edge["required_condition"]
            assert edge["environment_drivers"] is not None
            assert edge["management_drivers"] is not None
            assert edge["cultivar_dependency"]
            assert edge["production_system_dependency"]
            assert edge["confidence_class"]
        elif edge["source_state"] not in {
            "MANAGEMENT_EVENT",
            "EnvironmentInput",
            "BloomCohort",
            "FruitCohort.thermal_age",
            "daily_newly_mature_quantity",
        }:
            assert edge["source_state"] in state_or_field_ids | environment_ids

    assert state["phenology_state_machine"]["production_default_chill_model"] == "UNBOUND"
    assert state["source_sink_contract"]["exact_formula"] == "UNBOUND"
    assert state["source_sink_contract"]["source_capacity_not_leaf_area_only"] is True
    assert state["source_sink_contract"]["sink_demand_not_fruit_number_only"] is True
    assert events["intensity_contract"]["numeric_response_authorized"] is False


def test_parameter_authority_and_benchmark_gates_fail_closed() -> None:
    evidence, _ = _json(
        "docs/v0-9/evidence/s1-biological-state-and-management-event-contract-r1.json"
    )
    state, _ = _json("docs/v0-9/s1/biological-state-registry-r1.json")
    assert set(state["parameter_authority_types"]) == {
        "BUSINESS_CONFIRMED",
        "DIRECT_OBSERVED",
        "DATA_CALIBRATED",
        "LITERATURE_PRIOR",
        "MODEL_ASSUMPTION",
        "UNBOUND",
    }
    for field in (
        state["plant_state_fields"]
        + state["interseason_state_fields"]
        + state["source_sink_state_fields"]
    ):
        assert field["default_authority_type"] in state["parameter_authority_types"]
    assert evidence["parameter_lifecycle"]["literature_prior_promoted_to_production_count"] == 0
    assert evidence["parameter_lifecycle"]["production_parameter_created"] is False
    assert evidence["benchmark_2025_2026"]["consumed"] is True
    assert evidence["benchmark_2025_2026"]["model_selection_allowed"] is False
    assert evidence["benchmark_2025_2026"]["parameter_selection_allowed"] is False
    assert evidence["benchmark_2025_2026"]["hyperparameter_selection_allowed"] is False
    assert evidence["benchmark_2025_2026"]["management_rule_selection_allowed"] is False
    assert evidence["benchmark_2025_2026"]["metrics_read_in_this_task"] is False
    assert evidence["task_boundary"]["V0_9_S2_STARTED"] is False
    assert evidence["task_boundary"]["V0_9_S3_STARTED"] is False
    assert evidence["task_boundary"]["V0_9_S4_STARTED"] is False


def test_declared_output_hashes_and_deterministic_json_match() -> None:
    evidence, evidence_bytes = _json(
        "docs/v0-9/evidence/s1-biological-state-and-management-event-contract-r1.json"
    )
    for entry in evidence["deliverables"]:
        path = ROOT / entry["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]
        if path.suffix == ".json":
            parsed = json.loads(path.read_bytes())
            canonical = (
                json.dumps(parsed, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
                + "\n"
            )
            assert path.read_text(encoding="utf-8") == canonical
    canonical_evidence = (
        json.dumps(evidence, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    )
    assert evidence_bytes.decode("utf-8") == canonical_evidence
