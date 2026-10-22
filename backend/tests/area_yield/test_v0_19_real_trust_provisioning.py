"""Enrollment/decision checks use fresh fictional keys, never private real inputs."""

import base64
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from backend.research import v019_real_phase_a_adapter as file_io
from backend.research import v019_research_authorization as auth
from backend.research import v019_research_cohort as cohort
from backend.research.v019_daily_curve import canonical_bytes
from backend.research.v019_synthetic_validation import digest

pytestmark = [pytest.mark.unit, pytest.mark.contract]


@pytest.fixture
def enrollment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    owner, reviewer = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    config = {
        "version": 1,
        "mode": "REAL",
        "task_id": "V0_19_S3_FORMAL_C0_AND_TRUST_PROVISIONING_R1",
        "issued_at": "2020-01-01T00:00:00+00:00",
        "expires_at": "2099-01-01T00:00:00+00:00",
        "scope": "V0_19_SOURCE002_OWNER_RESEARCH_SCOPE_R1",
        "custody": "FICTIONAL_TEST_ONLY",
        "authorization_source": "FICTIONAL_TEST_ONLY",
        "keys": {
            role.lower(): {
                "role": role,
                "public_key_hex": key.public_key().public_bytes_raw().hex(),
                "allowed_decisions": sorted(auth.REAL_ENROLLMENT_DECISIONS[role]),
            }
            for role, key in (("OWNER", owner), ("REVIEWER", reviewer))
        },
    }
    path = tmp_path / "real-trust-config.json"

    def save(value: dict[str, Any], *, repin: bool = True) -> None:
        raw = canonical_bytes(value)
        path.write_bytes(raw)
        if repin:
            monkeypatch.setattr(auth, "REAL_TRUST_CONFIG_SHA256", file_io._hash(raw))

    save(config)
    return dict(
        config=config,
        save=save,
        path=path,
        owner=owner,
        reviewer=reviewer,
        ctx=auth.Context("REAL", real_trust_config=path),
    )


def decision(e: dict[str, Any], kind: str, subject: str, role: str = "owner") -> dict[str, Any]:
    payload = {
        "version": 1,
        "mode": "REAL",
        "kind": kind,
        "subject": subject,
        "code_sha256": auth.code_identity(),
        "key_id": role,
        "issued_at": "2020-01-01T00:00:00+00:00",
        "expires_at": "2099-01-01T00:00:00+00:00",
        "decision_id": "FICTIONAL-ONLY",
        "restrictions": auth.restrictions(),
    }
    return {
        "payload": payload,
        "signature": base64.b64encode(e[role].sign(canonical_bytes(payload))).decode(),
    }


def test_enrollment_and_valid_owner_decision(enrollment: dict[str, Any]) -> None:
    e = enrollment
    assert len(auth.roots(e["ctx"])) == 2
    grant = decision(e, "FORMAL_C0", "review-hash")
    assert auth.require(e["ctx"], {"FORMAL_C0": grant}, "FORMAL_C0", "review-hash")
    # Actual fixed enrollment remains pinned independently of these fictional keys.
    assert auth.Context("REAL").real_trust_config is None
    with pytest.raises(PermissionError):
        auth.roots(auth.Context("REAL", auth.roots(e["ctx"])))


@pytest.mark.parametrize("kind", ["A_EXECUTION", "B_LABEL_READ", "B_SCORING"])
def test_even_owner_signature_cannot_enable_execution(
    enrollment: dict[str, Any], kind: str
) -> None:
    grant = decision(enrollment, kind, "scope")
    with pytest.raises(PermissionError, match="SCOPE_ROLE_OR_CODE"):
        auth.require(enrollment["ctx"], {kind: grant}, kind, "scope")


@pytest.mark.parametrize("change", ["subject", "code_sha256", "key_id", "expires_at", "signature"])
def test_forged_expired_wrong_identity_decisions_rejected(
    enrollment: dict[str, Any], change: str
) -> None:
    grant = decision(enrollment, "FORMAL_C0", "scope")
    if change == "signature":
        grant["signature"] = base64.b64encode(b"x" * 64).decode()
    else:
        grant["payload"][change] = {
            "subject": "other",
            "code_sha256": "0" * 64,
            "key_id": "reviewer",
            "expires_at": "2020-01-02T00:00:00+00:00",
        }[change]
    with pytest.raises(PermissionError):
        auth.require(enrollment["ctx"], {"FORMAL_C0": grant}, "FORMAL_C0", "scope")


def test_validly_signed_but_expired_decision(enrollment: dict[str, Any]) -> None:
    g = decision(enrollment, "FORMAL_C0", "scope")
    g["payload"]["expires_at"] = "2020-01-02T00:00:00+00:00"
    g["signature"] = base64.b64encode(
        enrollment["owner"].sign(canonical_bytes(g["payload"]))
    ).decode()
    with pytest.raises(PermissionError, match="EXPIRED"):
        auth.require(enrollment["ctx"], {"FORMAL_C0": g}, "FORMAL_C0", "scope")


@pytest.mark.parametrize("change", ["duplicate_key", "expired", "role", "capability", "mode"])
def test_enrollment_semantics_fail_closed(enrollment: dict[str, Any], change: str) -> None:
    e = enrollment
    c = deepcopy(e["config"])
    if change == "duplicate_key":
        c["keys"]["reviewer"]["public_key_hex"] = c["keys"]["owner"]["public_key_hex"]
    elif change == "expired":
        c["expires_at"] = "2020-01-02T00:00:00+00:00"
    elif change == "role":
        c["keys"]["reviewer"]["role"] = "OWNER"
    elif change == "capability":
        c["keys"]["owner"]["allowed_decisions"].append("A_EXECUTION")
    else:
        c["mode"] = "SYNTHETIC"
    e["save"](c)
    with pytest.raises(PermissionError):
        auth.roots(e["ctx"])


def test_config_hash_and_symlink_rejected(enrollment: dict[str, Any], tmp_path: Path) -> None:
    e = enrollment
    c = deepcopy(e["config"])
    c["custody"] = "UNAPPROVED_SUBSTITUTION"
    e["save"](c, repin=False)
    with pytest.raises(ValueError):
        auth.roots(e["ctx"])
    e["save"](e["config"])
    link = tmp_path / "link"
    link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        auth.roots(auth.Context("REAL", real_trust_config=link / "real-trust-config.json"))


def test_roles_are_not_interchangeable(enrollment: dict[str, Any]) -> None:
    g = decision(enrollment, "FORMAL_C0", "scope", "reviewer")
    with pytest.raises(PermissionError):
        auth.require(enrollment["ctx"], {"FORMAL_C0": g}, "FORMAL_C0", "scope")
    g = decision(enrollment, "IMPLEMENTATION_REVIEW", auth.code_identity(), "owner")
    with pytest.raises(PermissionError):
        auth.require(
            enrollment["ctx"],
            {"IMPLEMENTATION_REVIEW": g},
            "IMPLEMENTATION_REVIEW",
            auth.code_identity(),
        )


def test_missing_decision_is_not_enrollment(enrollment: dict[str, Any]) -> None:
    with pytest.raises(PermissionError, match="SIGNED_DECISION_REQUIRED"):
        auth.require(enrollment["ctx"], {}, "FORMAL_C0", "scope")


def test_complete_c0_rechecks_members_and_preserves_input(enrollment: dict[str, Any]) -> None:
    e = enrollment
    members = [
        {
            "candidate_id": str(i),
            "window": w,
            "admission_status": "CANDIDATE",
            "failure_reason": None,
        }
        for i, w in enumerate(("H7_PREFIX", "H15_LOCAL"))
    ]
    candidate = auth.sealed(
        {
            "data_class": "REAL",
            "members": members,
            "inputs": {},
            "support": ["2025-07-01", "2026-04-15"],
            "code_sha256": auth.code_identity(),
            "restrictions": auth.restrictions(),
        }
    )
    before = canonical_bytes(candidate)
    review = cohort.review_candidates(
        candidate, {str(i): {"status": "ADMIT", "reason": ""} for i in range(2)}
    )
    grants = {
        "PROTOCOL": decision(e, "PROTOCOL", digest(auth.restrictions())),
        "FORMAL_C0": decision(e, "FORMAL_C0", review["sha256"]),
    }
    formal = cohort.formalize(candidate, review, e["ctx"], grants)
    assert formal["payload"]["approved"] == {"H7_PREFIX": ["0"], "H15_LOCAL": ["1"]}
    assert canonical_bytes(candidate) == before
    bad = deepcopy(review)
    bad["payload"]["members"].pop()
    bad = auth.sealed(bad["payload"])
    with pytest.raises(PermissionError, match="SCOPE_ROLE_OR_CODE"):
        cohort.formalize(candidate, bad, e["ctx"], grants)
    # Even a new signature cannot excuse dropping a registered member.
    grants["FORMAL_C0"] = decision(e, "FORMAL_C0", bad["sha256"])
    with pytest.raises(ValueError):
        cohort.formalize(candidate, bad, e["ctx"], grants)


def test_cli_default_real_still_denies_before_data_reads(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "backend.research.v019_research_cli",
            "stage-a",
            "--mode",
            "REAL",
            "--grants",
            str(tmp_path / "NO_GRANTS"),
            "--output",
            str(tmp_path / "NO_OUTPUT"),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert "TRUST_ANCHOR_NOT_PROVISIONED" in result.stderr
    assert "FileNotFoundError" not in result.stderr
    assert not (tmp_path / "NO_OUTPUT").exists()


def test_public_receipt_has_no_execution_or_independent_review_claim() -> None:
    path = Path(__file__).resolve().parents[3] / (
        "docs/v0-19/evidence/v0.19-s3-formal-c0-trust-provisioning-r1.json"
    )
    evidence = json.loads(path.read_text())
    # Enrollment pins the original compact JSON bytes, not a re-rendered seal.
    enrollment_raw = json.dumps(
        evidence["enrollment"], sort_keys=True, separators=(",", ":")
    ).encode()
    assert file_io._hash(enrollment_raw) == evidence["trust_config_sha256"]
    assert evidence["formally_admitted_count"] == evidence["h7"] + evidence["h15"] == 19032
    assert evidence["base_count"] == 39
    assert evidence["independent_human_review"] == "PENDING"
    assert evidence["independent_key_custody"] is False
    assert evidence["reviewer_decisions_signed"] == 0
    assert set(evidence["issued_grant_kinds"]) == {"PROTOCOL", "FORMAL_C0", "A_INPUT_READ"}
    for flag in (
        "real_a_execution_authorized",
        "real_b_label_read_authorized",
        "real_b_scoring_authorized",
        "real_prediction_generated",
        "real_scoring_performed",
        "real_label_read_performed",
        "model_training_performed",
        "s3_formal_complete",
        "strict_pit",
        "production_eligible",
        "ready_authorized",
        "merge_authorized",
    ):
        assert evidence[flag] is False
    assert evidence["prediction_scoring_calls"] == []
    assert "PRIVATE KEY" not in path.read_text()
