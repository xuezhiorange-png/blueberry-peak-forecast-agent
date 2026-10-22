"""Owner-operated local route, real-shaped fictional inputs, unchanged math."""

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from backend.research import v019_owner_replay as owner
from backend.research import v019_real_phase_a_adapter as file_io
from backend.research import v019_research_authorization as auth
from backend.research import v019_research_cohort as cohort
from backend.research import v019_research_execution as execution
from backend.research.v019_synthetic_validation import digest
from backend.tests.area_yield.build_v019_real_shape_fixture import build, write

pytestmark = [pytest.mark.unit, pytest.mark.contract]


@pytest.fixture(scope="module")
def prepared(tmp_path_factory: pytest.TempPathFactory) -> tuple[Any, ...]:
    root = tmp_path_factory.mktemp("owner-replay")
    mp, mh, lp, lh, signer, grants = build(root / "inputs")
    inputs = owner.load_inputs(mp, mh, "SYNTHETIC")
    c = cohort.candidates(inputs, signer.context)
    r = cohort.review_candidates(
        c, {m["candidate_id"]: {"status": "ADMIT", "reason": ""} for m in c["payload"]["members"]}
    )
    grants.update(
        PROTOCOL=signer.decision("PROTOCOL", digest(auth.restrictions())),
        FORMAL_C0=signer.decision("FORMAL_C0", r["sha256"]),
    )
    old = cohort.formalize(c, r, signer.context, grants)
    path = root / "old.json"
    oh = write(path, old)
    return root, inputs, old, mp, mh, lp, lh, path, oh


def call(*args: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "backend.research.v019_owner_replay", *map(str, args)],
        capture_output=True,
        text=True,
        timeout=180,
    )


def test_three_process_end_to_end(prepared: tuple[Any, ...]) -> None:
    root, inputs, old, mp, mh, lp, lh, path, oh = prepared
    shared = ["--owner-command", owner.TASK, "--data-class", "SYNTHETIC"]
    # A accepts no label argument and can complete while labels are unavailable.
    hidden = lp.with_suffix(".not-readable-by-a")
    lp.rename(hidden)
    try:
        a = call(
            "stage-a",
            *shared,
            "--inputs",
            mp,
            "--inputs-hash",
            mh,
            "--historical-c0",
            path,
            "--historical-c0-file-hash",
            oh,
            "--output",
            root / "a",
        )
        assert a.returncode == 0, a.stderr
        ap = root / "a/phase-a.json"
        ah = file_io._hash(ap.read_bytes())
        v = call("verify-a", *shared, "--seal", ap, "--seal-file-hash", ah, "--output", root / "v")
        assert v.returncode == 0, v.stderr
    finally:
        hidden.rename(lp)
    vp = root / "v/phase-a-verification.json"
    b = call(
        "stage-b",
        *shared,
        "--seal",
        ap,
        "--seal-file-hash",
        ah,
        "--verification",
        vp,
        "--verification-file-hash",
        file_io._hash(vp.read_bytes()),
        "--labels",
        lp,
        "--labels-hash",
        lh,
        "--output",
        root / "b",
    )
    assert b.returncode == 0, b.stderr
    report = json.loads((root / "b/report.json").read_text())
    seal = json.loads(ap.read_text())
    c = seal["payload"]["content"]
    assert len(c["full_curves"]) == 39
    assert len(c["members"]) == report["admitted_count"] == 19032
    assert len(report["actual_daily"]) == 9906
    assert report["failures"] == []
    assert c["labels_read"] is False
    assert seal["payload"]["historical_issued_at"] is None
    assert report["real_scoring_performed"] is False
    assert c["full_support_calculation_count"] == 39
    expected = execution.calculate(
        *cohort.numerical_inputs(inputs), auth.unseal(old["payload"]["review"])["members"]
    )
    assert all(c[k] == v for k, v in expected.items())
    again = owner.stage_a(inputs, old, "SYNTHETIC")
    assert again["payload"]["prediction_sha256"] == seal["payload"]["prediction_sha256"]
    for w, n in (("H7_PREFIX", 9672), ("H15_LOCAL", 9360)):
        m = report["groups"][w]["metrics"]
        assert len(m) == 10
        assert m["DAILY_WAPE"]["common_count"] == n
        assert m["DAILY_WAPE"]["baseline"]["value"] is not None
        assert m["SEASON_TOTAL_WAPE"]["common_count"] == 0
        assert m["SINGLE_DAY_PEAK_DATE_MAE"]["not_computable_count"] > 0
    for folder in (root / "a", root / "v", root / "b"):
        assert folder.stat().st_mode & 0o777 == 0o700
        assert all(f.stat().st_mode & 0o777 == 0o600 for f in folder.iterdir())


def test_real_relabel_and_changed_manifest_rejected(prepared: tuple[Any, ...]) -> None:
    _, _, _, mp, mh, *_ = prepared
    with pytest.raises(PermissionError, match="FROZEN_MANIFEST"):
        owner.load_inputs(mp, mh, "REAL")
    with pytest.raises(ValueError, match="HASH"):
        owner.load_inputs(mp, "0" * 64, "SYNTHETIC")


def test_changed_c0_and_real_c0_spoof_rejected(prepared: tuple[Any, ...]) -> None:
    _, inputs, old, *_ = prepared
    bad = deepcopy(old)
    bad["payload"]["candidate"]["payload"]["members"][0]["base_id"] = "OTHER"
    bad["payload"]["candidate"] = auth.sealed(bad["payload"]["candidate"]["payload"])
    bad = auth.sealed(bad["payload"])
    with pytest.raises(ValueError, match="EXACT_HISTORICAL"):
        owner.rebind(inputs, bad, "SYNTHETIC")
    with pytest.raises(ValueError, match="EXACT_HISTORICAL"):
        owner.rebind(inputs, old, "REAL")


def test_missing_owner_command_and_a_labels_rejected(tmp_path: Path) -> None:
    r = call("stage-a", "--data-class", "SYNTHETIC", "--output", tmp_path / "a")
    assert r.returncode != 0 and "--owner-command" in r.stderr
    r = call(
        "stage-a",
        "--owner-command",
        owner.TASK,
        "--data-class",
        "SYNTHETIC",
        "--labels",
        tmp_path / "labels.json",
        "--output",
        tmp_path / "a",
    )
    assert r.returncode != 0 and "no label" in r.stderr


def test_writer_refuses_overwrite(tmp_path: Path) -> None:
    owner.write_bundle(tmp_path / "out", {"ok.json": b"{}"}, {})
    with pytest.raises(FileExistsError):
        owner.write_bundle(tmp_path / "out", {"ok.json": b"changed"}, {})


def test_numerical_tamper_rejected(prepared: tuple[Any, ...]) -> None:
    _, inputs, old, *_ = prepared
    seal = owner.stage_a(inputs, old, "SYNTHETIC")
    c = seal["payload"]["content"]
    bid = next(iter(c["full_curves"]))
    c["full_curves"][bid]["baseline"][0]["kg"] = "999999.000000"
    seal["payload"]["content_sha256"] = digest(c)
    seal["payload"]["prediction_sha256"] = execution.prediction_hash(c)
    seal = auth.sealed(seal["payload"])
    with pytest.raises(ValueError, match="RECOMPUTATION"):
        owner.verify_a(seal, "SYNTHETIC")


def test_daily_adapter_metadata_mismatch_and_missing_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import csv
    import io

    day = {"base_id": "SYNTHETIC-ONLY", "date": "2026-01-01", "authority_eligible_daily": "true"}
    content = {"day_authorities": [day]}

    def check(rows: list[dict[str, str]]) -> dict[str, Any]:
        stream = io.StringIO()
        w = csv.DictWriter(stream, fieldnames=[*day, "new_quantity_kg"])
        w.writeheader()
        w.writerows(rows)
        raw = stream.getvalue().encode()
        path = tmp_path / "daily.csv"
        path.write_bytes(raw)
        monkeypatch.setattr(owner, "DAILY", file_io._hash(raw))
        return owner.real_labels(path, content)

    good = {**day, "new_quantity_kg": "1.250000"}
    assert check([good])["rows"][0]["kg"] == "1.250000"
    with pytest.raises(ValueError, match="INCOMPLETE"):
        check([])
    with pytest.raises(ValueError, match="DUPLICATE"):
        check([good, good])
    with pytest.raises(ValueError, match="AUTHORITY_MISMATCH"):
        check([{**good, "authority_eligible_daily": "false"}])
