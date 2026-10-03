"""Synthetic registration identities only; no private artifact dependency or fit."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from backend.app.area_yield import area_size_r1
from backend.app.area_yield import artifact_registration as e2
from backend.app.area_yield import prospective_validation as e1
from backend.app.area_yield.data import digest
from backend.app.area_yield.research_records import file_hash, read
from backend.app.area_yield.v0_12_e1_fixtures import make_fixture


def write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")


@pytest.fixture
def case(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    c = make_fixture(tmp_path / "SYNTHETIC")
    c["root"] = tmp_path / "SYNTHETIC"
    monkeypatch.setattr(area_size_r1, "fit", lambda *a, **k: pytest.fail("FIT_FORBIDDEN"))
    public: dict[str, Any] = {
        "execution_id": e2.EXECUTION,
        "base_sha": e2.CODE_SHA,
        "coverage": {"source_hashes": {"training_source": "1" * 64, "daily_source": "2" * 64}},
        "fold": {
            "train_seasons": ["2023-2024"],
            "train_sample_count": 15,
            "test_season": "2024-2025",
            "test_sample_count": 22,
            "created_at": "2026-10-02T02:32:09.140307+00:00",
            "artifact_file_hashes": {},
        },
        "example": {},
    }
    identity = {
        "base_sha": e2.CODE_SHA,
        "training_source": "1" * 64,
        "daily_source": "2" * 64,
        "configuration_hash": e2.CONFIG_FILE_HASH,
        "code_hash": e2.CODE_FILE_HASH,
        "scope": e2.SOURCE_SCOPE,
    }
    for kind in ("candidate", "baseline"):
        p = c["root"] / f"SYNTHETIC-{kind}.json"
        m = read(p)
        m.update(
            model_id=f"{e2.EXECUTION}_{kind.upper()}",
            training_identity=identity,
            training_sample_count=15,
            created_at=public["fold"]["created_at"],
        )
        m.pop("artifact_hash")
        m["artifact_hash"] = digest(m)
        write(p, m)
        public["fold"]["artifact_file_hashes"][kind] = file_hash(p)
        if kind == "candidate":
            public["example"]["artifact_hash"] = m["artifact_hash"]
        c[kind] = p
    c["public"] = c["root"] / "SYNTHETIC-public.json"
    write(c["public"], public)
    # Test-only replacement of the pinned authority. CLI has no bypass option.
    monkeypatch.setattr(e2, "PUBLIC_FILE_HASH", file_hash(c["public"]))
    c["output"] = c["root"] / "verified.json"
    return c


def register(c: dict[str, Any]) -> dict[str, Any]:
    return e2.register_pair(c["candidate"], c["baseline"], c["public"], c["output"])


def reauthorize(c: dict[str, Any], kind: str, model: dict[str, Any]) -> None:
    model.pop("artifact_hash")
    model["artifact_hash"] = digest(model)
    write(c[kind], model)
    public = read(c["public"])
    public["fold"]["artifact_file_hashes"][kind] = file_hash(c[kind])
    if kind == "candidate":
        public["example"]["artifact_hash"] = model["artifact_hash"]
    write(c["public"], public)
    e2.PUBLIC_FILE_HASH = file_hash(c["public"])


def test_pair_and_legacy_mapping(case: dict[str, Any]) -> None:
    before = [p.read_bytes() for p in (case["candidate"], case["baseline"])]
    result = register(case)
    entries = read(case["output"])["entries"]
    assert [e["model_role"] for e in entries] == ["RESEARCH_CANDIDATE", "COMPARATOR_BASELINE"]
    assert all(
        e["content_verified"]
        and e["active_for_research"]
        and not e["synthetic"]
        and not e["production_approved"]
        for e in entries
    )
    assert result["temporal_shape_shared"] is True
    assert result["legacy_baseline_internal_role"] == "RESEARCH_CANDIDATE"
    assert result["comparator_public_content_hash_previously_frozen"] is False
    assert before == [p.read_bytes() for p in (case["candidate"], case["baseline"])]


@pytest.mark.parametrize("kind", ["candidate", "baseline"])
def test_file_hash_mismatch(case: dict[str, Any], kind: str) -> None:
    with case[kind].open("a") as stream:
        stream.write(" ")
    with pytest.raises(ValueError, match="FILE_HASH"):
        register(case)
    assert not case["output"].exists()


@pytest.mark.parametrize("kind", ["candidate", "baseline"])
def test_self_hash_mismatch(case: dict[str, Any], kind: str) -> None:
    m = read(case[kind])
    m["artifact_hash"] = "0" * 64
    write(case[kind], m)
    p = read(case["public"])
    p["fold"]["artifact_file_hashes"][kind] = file_hash(case[kind])
    write(case["public"], p)
    e2.PUBLIC_FILE_HASH = file_hash(case["public"])
    with pytest.raises(ValueError, match="CONTENT_HASH"):
        register(case)
    assert not case["output"].exists()


@pytest.mark.parametrize(
    "kind,key,value",
    [
        ("candidate", "model_id", "WRONG"),
        ("baseline", "model_id", "WRONG"),
        ("candidate", "model_family", "baseline"),
        ("baseline", "model_family", "candidate"),
        ("candidate", "training_seasons", ["2024-2025"]),
        ("candidate", "training_sample_count", 14),
        ("candidate", "training_area_range_mu", ["1", "2548"]),
        ("candidate", "model_role", "PRODUCTION"),
        ("baseline", "model_role", "PRODUCTION"),
        ("candidate", "features", []),
        ("baseline", "features", ["log_area_mu"]),
        ("candidate", "weather_used", True),
        ("baseline", "holdout_used_for_fit", True),
        ("candidate", "quantity_precision", "1kg"),
        ("candidate", "model_version", "2"),
        ("candidate", "target_definition", "OTHER"),
    ],
)
def test_semantic_mismatch(case: dict[str, Any], kind: str, key: str, value: Any) -> None:
    m = read(case[kind])
    m[key] = value
    reauthorize(case, kind, m)
    with pytest.raises(ValueError):
        register(case)
    assert not case["output"].exists()


@pytest.mark.parametrize(
    "change", ["training_identity", "curve", "penalty", "parameter", "config", "execution"]
)
def test_parity_mismatch(case: dict[str, Any], change: str) -> None:
    m = read(case["candidate"])
    if change == "training_identity":
        m["training_identity"]["daily_source"] = "4" * 64
    elif change == "curve":
        m["curve_parameters"]["07-01"] += 0.01
    elif change == "penalty":
        m["parameters"]["penalty"] = 2.0
    elif change == "parameter":
        m["parameters"]["beta"] += 0.01
    elif change == "config":
        m["training_identity"]["configuration_hash"] = "4" * 64
    else:
        m["training_identity"]["base_sha"] = "4" * 40
    reauthorize(case, "candidate", m)
    with pytest.raises(ValueError):
        register(case)
    assert not case["output"].exists()


def test_swap_and_overwrite(case: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        e2.register_pair(case["baseline"], case["candidate"], case["public"], case["output"])
    register(case)
    before = case["output"].read_bytes()
    with pytest.raises(FileExistsError):
        register(case)
    assert before == case["output"].read_bytes()


def test_pinned_public_identity(case: dict[str, Any]) -> None:
    with case["public"].open("a") as stream:
        stream.write(" ")
    with pytest.raises(ValueError, match="PUBLIC_EVIDENCE_IDENTITY"):
        register(case)
    assert not case["output"].exists()


def test_e1_issue_real_rejection_tamper_and_unverified(case: dict[str, Any]) -> None:
    register(case)
    entries = read(case["output"])["entries"]
    request = case["request"]
    request.update(
        candidate_model_id=entries[0]["registry_id"],
        candidate_artifact_hash=entries[0]["artifact_hash"],
        candidate_config_hash=entries[0]["config_hash"],
        comparator_id=entries[1]["registry_id"],
        comparator_artifact_or_policy_hash=entries[1]["artifact_hash"],
    )
    write(case["source"], e1.request_source_payload(request))
    request["request_source_hash"] = file_hash(case["source"])
    auth = read(case["authorization"])
    auth["request_hash"] = digest(request)
    write(case["authorization"], auth)

    def issue() -> dict[str, Any]:
        return e1.create_research_forecast(
            case["store"],
            case["output"],
            file_hash(case["output"]),
            request,
            case["source"],
            case["authorization"],
            clock=case["issue_clock"],
        )

    f = issue()
    assert e1.verify_research_forecast(case["store"], f["id"])["test_only"]
    request["request_mode"] = "REAL_PROSPECTIVE"
    with pytest.raises(ValueError, match="REAL_PROSPECTIVE_NOT_AUTHORIZED"):
        issue()
    request["request_mode"] = "TEST_ONLY"
    request["request_id"] = "SECOND"
    write(case["source"], e1.request_source_payload(request))
    request["request_source_hash"] = file_hash(case["source"])
    auth["request_hash"] = digest(request)
    write(case["authorization"], auth)
    with case["candidate"].open("a") as stream:
        stream.write(" ")
    with pytest.raises(ValueError, match="ARTIFACT_FILE_HASH"):
        issue()
    public_registry = Path("configs/v0_12_e1_reported_artifact_registry.json")
    with pytest.raises(ValueError):
        e1.create_research_forecast(
            case["store"],
            public_registry,
            file_hash(public_registry),
            request,
            case["source"],
            case["authorization"],
            clock=case["issue_clock"],
        )


def test_atomic_failure_no_output(case: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "backend.app.area_yield.artifact_registration.os.link",
        lambda *a: (_ for _ in ()).throw(OSError("INJECTED")),
    )
    with pytest.raises(OSError):
        register(case)
    assert not case["output"].exists()


def test_fresh_process_guarded_prediction(case: dict[str, Any]) -> None:
    command = [
        sys.executable,
        "-c",
        "from backend.app.area_yield import artifact_registration as a; "
        "from pathlib import Path; import json,sys; "
        "print(json.dumps(a.guarded_predict(Path(sys.argv[1]))))",
        str(case["candidate"]),
    ]
    first = subprocess.run(command, check=True, capture_output=True, text=True)
    second = subprocess.run(command, check=True, capture_output=True, text=True)
    assert first.stdout == second.stdout
    assert json.loads(first.stdout)["mode"] == "TEST_ONLY"


@pytest.mark.parametrize("position", [0, 1])
def test_wrong_runtime_role(case: dict[str, Any], position: int) -> None:
    register(case)
    registry = read(case["output"])
    entry = registry["entries"][position]
    role = entry["model_role"]
    entry["model_role"] = "PRODUCTION_APPROVED"
    with pytest.raises(ValueError, match="ROLE_OR_CONTENT"):
        e1._resolve(registry, entry["registry_id"], role, case["issue_clock"])


def test_guard_rejects_fit_even_if_prediction_accidentally_calls_it(
    case: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        area_size_r1,
        "predict",
        lambda *a, **k: area_size_r1.fit([], [], kind="candidate", identity={}, created_at=""),
    )
    with pytest.raises(RuntimeError, match="MODEL_TRAINING_FORBIDDEN"):
        e2.guarded_predict(case["candidate"])


def test_missing_baseline_leaves_no_registry(case: dict[str, Any]) -> None:
    case["baseline"] = case["root"] / "MISSING.json"
    with pytest.raises(FileNotFoundError):
        register(case)
    assert not case["output"].exists()
