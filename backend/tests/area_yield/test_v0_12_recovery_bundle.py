"""Public hand-specified fixtures only; disaster recovery never fits a model."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from backend.app.area_yield import artifact_registration as e2
from backend.app.area_yield import prospective_validation as e1
from backend.app.area_yield import recovery_bundle as e3
from backend.app.area_yield.data import digest
from backend.app.area_yield.research_records import file_hash, read
from backend.tests.area_yield.test_v0_12_artifact_registration import case as case


def write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")


@pytest.fixture
def packed(case: dict[str, Any], tmp_path: Path) -> dict[str, Any]:
    fold = read(case["public"])["fold"]
    case["receipt"] = tmp_path / "run-receipt.json"
    case["seal"] = tmp_path / "prediction-seal.json"
    case["contract"] = tmp_path / "execution-contract.json"
    write(
        case["receipt"],
        {
            "fold": fold,
            "scientific_result": "RESEARCH_CANDIDATE_NO_STABLE_GAIN",
            "stable_gain": False,
        },
    )
    write(case["seal"], fold)
    config = (
        Path(__file__).resolve().parents[3] / "configs/next_area_size_experiment_20261002_r1.json"
    )
    write(case["contract"], read(config))
    case["bundle"] = tmp_path / "bundle"
    e3.pack(
        case["candidate"],
        case["baseline"],
        case["receipt"],
        case["seal"],
        case["contract"],
        case["public"],
        case["bundle"],
    )
    case["restore"] = tmp_path / "restored"
    return case


def test_portable_identity_and_e1_chain(packed: dict[str, Any], tmp_path: Path) -> None:
    c = packed
    before = [p.read_bytes() for p in (c["candidate"], c["baseline"])]
    verified = e3.verify(c["bundle"])
    restored = e3.restore(c["bundle"], c["restore"])
    assert verified["bundle_content_hash"] == restored["bundle_content_hash"]
    assert before == [p.read_bytes() for p in (c["candidate"], c["baseline"])]
    registry = tmp_path / "restored-registry.json"
    e2.register_pair(
        c["restore"] / e3.CANDIDATE, c["restore"] / e3.BASELINE, c["restore"] / e3.PUBLIC, registry
    )
    e3.verify_runtime(c["restore"], registry)
    entries = read(registry)["entries"]
    assert all(str(c["restore"].resolve()) in e["artifact_path"] for e in entries)
    request = dict(c["request"])
    request.update(
        candidate_model_id=entries[0]["registry_id"],
        candidate_artifact_hash=entries[0]["artifact_hash"],
        candidate_config_hash=entries[0]["config_hash"],
        comparator_id=entries[1]["registry_id"],
        comparator_artifact_or_policy_hash=entries[1]["artifact_hash"],
    )
    source, auth = tmp_path / "source.json", tmp_path / "auth.json"
    write(source, e1.request_source_payload(request))
    request["request_source_hash"] = file_hash(source)
    write(
        auth,
        {
            "authorization_id": request["authorization_id"],
            "status": "TEST_ONLY",
            "request_hash": digest(request),
            "operator": "SYNTHETIC_E3",
        },
    )
    store = tmp_path / "records"
    forecast = e1.create_research_forecast(
        store, registry, file_hash(registry), request, source, auth, clock=c["issue_clock"]
    )
    assert (
        e1.verify_research_forecast(store, forecast["id"])["record_hash"] == forecast["record_hash"]
    )
    request["request_mode"] = "REAL_PROSPECTIVE"
    with pytest.raises(ValueError, match="REAL_PROSPECTIVE_NOT_AUTHORIZED"):
        e1.create_research_forecast(
            store, registry, file_hash(registry), request, source, auth, clock=c["issue_clock"]
        )
    result = e3.drill_result(c["restore"], registry, store, forecast["id"])
    result_path = tmp_path / "drill.json"
    write(result_path, result)
    audit = e3.audit_export(
        c["bundle"], c["restore"], registry, result_path, store, tmp_path / "audit.json"
    )
    assert audit["test_only_issuance_result"] == "PASS"
    assert audit["real_issuance_enabled"] is False
    assert str(tmp_path) not in json.dumps(audit)
    assert "training_bases" not in json.dumps(audit)
    assert not any("path" in k for k in audit)


def test_identity_excludes_clock_and_root(packed: dict[str, Any], tmp_path: Path) -> None:
    c = packed
    other = tmp_path / "other"
    e3.pack(
        c["candidate"], c["baseline"], c["receipt"], c["seal"], c["contract"], c["public"], other
    )
    assert (
        read(c["bundle"] / "manifest.json")["bundle_content_hash"]
        == read(other / "manifest.json")["bundle_content_hash"]
    )
    assert e3.verify(other)["bundle_verify"] == "PASS"


@pytest.mark.parametrize(
    "relative", [e3.CANDIDATE, e3.BASELINE, e3.PUBLIC, "README.txt", e3.RECEIPT, "manifest.json"]
)
def test_modified_byte(packed: dict[str, Any], relative: str) -> None:
    with (packed["bundle"] / relative).open("ab") as stream:
        stream.write(b" ")
    with pytest.raises(ValueError):
        e3.verify(packed["bundle"])


@pytest.mark.parametrize(
    "mutation",
    [
        "hash",
        "inventory",
        "duplicate",
        "absolute",
        "traversal",
        "role",
        "clock",
        "mapping",
        "public_hash",
        "training_count",
    ],
)
def test_manifest_rejection(packed: dict[str, Any], mutation: str) -> None:
    p = packed["bundle"] / "manifest.json"
    m = read(p)
    if mutation == "hash":
        m["bundle_content_hash"] = "0" * 64
    elif mutation == "inventory":
        m["file_inventory"][0]["size_bytes"] += 1
    elif mutation == "duplicate":
        m["file_inventory"].append(m["file_inventory"][0])
    elif mutation == "absolute":
        m["file_inventory"][0]["relative_path"] = "/etc/passwd"
    elif mutation == "traversal":
        m["file_inventory"][0]["relative_path"] = "../outside.json"
    elif mutation == "role":
        m["file_inventory"][0]["role"] = "PRODUCTION"
    elif mutation == "clock":
        m["created_at"] = datetime.now().isoformat()
    elif mutation == "mapping":
        m["role_mapping"] = "PRODUCTION"
    elif mutation == "public_hash":
        m["public_evidence_sha256"] = "0" * 64
    else:
        m["training_sample_count"] = 16
    write(p, m)
    if mutation != "clock":
        m["manifest_hash"] = digest({k: v for k, v in m.items() if k != "manifest_hash"})
        write(p, m)
    with pytest.raises(ValueError):
        e3.verify(packed["bundle"])
    assert not packed["restore"].exists()


@pytest.mark.parametrize("relative", [e3.CANDIDATE, e3.BASELINE])
def test_missing(packed: dict[str, Any], relative: str) -> None:
    (packed["bundle"] / relative).unlink()
    with pytest.raises(ValueError):
        e3.verify(packed["bundle"])


def test_unexpected_file(packed: dict[str, Any]) -> None:
    (packed["bundle"] / "extra-artifact.json").write_text("{}")
    with pytest.raises(ValueError):
        e3.verify(packed["bundle"])


def test_symlink_escape(packed: dict[str, Any], tmp_path: Path) -> None:
    (packed["bundle"] / e3.CANDIDATE).unlink()
    (packed["bundle"] / e3.CANDIDATE).symlink_to(packed["candidate"])
    with pytest.raises(ValueError, match="SYMLINK"):
        e3.verify(packed["bundle"])
    assert not packed["restore"].exists()


def test_swapped_artifacts(packed: dict[str, Any]) -> None:
    c, b = packed["bundle"] / e3.CANDIDATE, packed["bundle"] / e3.BASELINE
    cb, bb = c.read_bytes(), b.read_bytes()
    c.write_bytes(bb)
    b.write_bytes(cb)
    with pytest.raises(ValueError):
        e3.verify(packed["bundle"])


def test_create_only(packed: dict[str, Any]) -> None:
    c = packed
    e3.restore(c["bundle"], c["restore"])
    before = (c["restore"] / e3.CANDIDATE).read_bytes()
    with pytest.raises(FileExistsError):
        e3.restore(c["bundle"], c["restore"])
    assert before == (c["restore"] / e3.CANDIDATE).read_bytes()
    with pytest.raises(FileExistsError):
        e3.pack(
            c["candidate"],
            c["baseline"],
            c["receipt"],
            c["seal"],
            c["contract"],
            c["public"],
            c["bundle"],
        )


def test_nonempty_destination(packed: dict[str, Any]) -> None:
    packed["restore"].mkdir()
    (packed["restore"] / "keep").write_text("keep")
    with pytest.raises(FileExistsError):
        e3.restore(packed["bundle"], packed["restore"])
    assert (packed["restore"] / "keep").read_text() == "keep"


@pytest.mark.parametrize("phase", ["pack", "restore"])
def test_partial_publication(
    packed: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    def reject(*args: Any) -> None:
        raise OSError("INJECTED_PUBLICATION_FAILURE")

    monkeypatch.setattr(e3, "_publish", reject)
    out = tmp_path / "failed"
    c = packed
    with pytest.raises(OSError):
        if phase == "pack":
            e3.pack(
                c["candidate"],
                c["baseline"],
                c["receipt"],
                c["seal"],
                c["contract"],
                c["public"],
                out,
            )
        else:
            e3.restore(c["bundle"], out)
    assert not out.exists()


@pytest.mark.parametrize(
    "failure", ["old_registry", "stale_path", "wrong_role", "post_registration_tamper"]
)
def test_restored_runtime_rejection(packed: dict[str, Any], tmp_path: Path, failure: str) -> None:
    c = packed
    e3.restore(c["bundle"], c["restore"])
    registry = tmp_path / "registry.json"
    e2.register_pair(
        c["restore"] / e3.CANDIDATE, c["restore"] / e3.BASELINE, c["restore"] / e3.PUBLIC, registry
    )
    r = read(registry)
    if failure == "old_registry":
        r["entries"][0]["artifact_path"] = str(c["candidate"])
    elif failure == "stale_path":
        r["entries"][0]["artifact_path"] = str(tmp_path / "lost.json")
    elif failure == "wrong_role":
        r["entries"][1]["model_role"] = "RESEARCH_CANDIDATE"
    else:
        (c["restore"] / e3.CANDIDATE).write_text("{}")
    write(registry, r)
    r["record_hash"] = digest({k: v for k, v in r.items() if k != "record_hash"})
    write(registry, r)
    with pytest.raises(ValueError):
        e3.verify_runtime(c["restore"], registry)


def test_source_absolute_reference_rejected(packed: dict[str, Any], tmp_path: Path) -> None:
    c = packed
    write(c["receipt"], {"source": str(tmp_path / "secret")})
    with pytest.raises(ValueError, match="NONPORTABLE"):
        e3.pack(
            c["candidate"],
            c["baseline"],
            c["receipt"],
            c["seal"],
            c["contract"],
            c["public"],
            tmp_path / "bad",
        )


def test_fresh_process_restored_predict(packed: dict[str, Any]) -> None:
    e3.restore(packed["bundle"], packed["restore"])
    code = (
        "from pathlib import Path; "
        "from backend.app.area_yield.artifact_registration import guarded_predict; "
        "import sys,json; print(json.dumps(guarded_predict(Path(sys.argv[1])),sort_keys=True))"
    )
    args = [sys.executable, "-c", code, str(packed["restore"] / e3.CANDIDATE)]
    first = subprocess.run(args, check=True, capture_output=True, text=True).stdout
    assert first == subprocess.run(args, check=True, capture_output=True, text=True).stdout


@pytest.mark.parametrize("phase", ["pack", "restore"])
def test_partial_copy_not_published(
    packed: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    c = packed
    out = tmp_path / "incomplete"

    def broken_copy(*args: Any, **kwargs: Any) -> None:
        destination = Path(args[1])
        if phase == "pack":
            destination.write_bytes(b"PARTIAL_TEST_ONLY_COPY")
        else:
            destination.mkdir()
            (destination / "PARTIAL_TEST_ONLY_COPY").write_text("interrupted")
        raise OSError("INJECTED_MID_COPY_FAILURE")

    attribute = "copyfile" if phase == "pack" else "copytree"
    monkeypatch.setattr(f"backend.app.area_yield.recovery_bundle.shutil.{attribute}", broken_copy)
    with pytest.raises(OSError):
        if phase == "pack":
            e3.pack(
                c["candidate"],
                c["baseline"],
                c["receipt"],
                c["seal"],
                c["contract"],
                c["public"],
                out,
            )
        else:
            e3.restore(c["bundle"], out)
    assert not out.exists()


def test_atomic_rename_cannot_replace_empty_target(tmp_path: Path) -> None:
    staged, existing = tmp_path / "staged", tmp_path / "existing"
    staged.mkdir()
    existing.mkdir()
    (staged / "payload").write_text("new")
    with pytest.raises(FileExistsError):
        e3._publish(staged, existing)
    assert list(existing.iterdir()) == []
    assert (staged / "payload").read_text() == "new"


def test_duplicate_json_key(packed: dict[str, Any]) -> None:
    p = packed["bundle"] / "manifest.json"
    p.write_text('{"bundle_schema":"one", "bundle_schema":"two"}')
    with pytest.raises(ValueError, match="DUPLICATE_JSON_KEY"):
        e3.verify(packed["bundle"])


def test_audit_wrong_drill_rejected(packed: dict[str, Any], tmp_path: Path) -> None:
    c = packed
    e3.restore(c["bundle"], c["restore"])
    registry = tmp_path / "registry.json"
    e2.register_pair(
        c["restore"] / e3.CANDIDATE, c["restore"] / e3.BASELINE, c["restore"] / e3.PUBLIC, registry
    )
    result = tmp_path / "bad-result.json"
    write(result, {"forecast_id": "MISSING_FORECAST"})
    with pytest.raises((ValueError, FileNotFoundError)):
        e3.audit_export(
            c["bundle"],
            c["restore"],
            registry,
            result,
            tmp_path / "records",
            tmp_path / "audit.json",
        )
    assert not (tmp_path / "audit.json").exists()


def test_cli_verify_and_restore(
    packed: dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from backend.app.area_yield.prospective_validation_cli import main

    monkeypatch.setattr(
        sys, "argv", ["cli", "v0-12-research", "verify-bundle", "--bundle", str(packed["bundle"])]
    )
    main()
    assert json.loads(capsys.readouterr().out)["bundle_verify"] == "PASS"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cli",
            "v0-12-research",
            "restore-bundle",
            "--bundle",
            str(packed["bundle"]),
            "--output",
            str(packed["restore"]),
        ],
    )
    main()
    assert json.loads(capsys.readouterr().out)["restore_verify"] == "PASS"
