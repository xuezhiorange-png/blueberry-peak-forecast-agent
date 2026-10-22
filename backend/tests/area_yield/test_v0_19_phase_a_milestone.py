"""Phase A subject binding and independent-review gates; fictional keys only."""

import base64
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from backend.research import v019_real_phase_a_adapter as io
from backend.research import v019_research_authorization as auth
from backend.research import v019_research_cohort as cohort
from backend.research import v019_research_execution as execution
from backend.research.v019_daily_curve import canonical_bytes
from backend.tests.area_yield.build_v019_real_shape_fixture import Signer
from backend.tests.area_yield.test_v0_19_real_trust_provisioning import decision
from backend.tests.area_yield.test_v0_19_real_trust_provisioning import enrollment as enrollment

pytestmark = [pytest.mark.unit, pytest.mark.contract]


def test_phase_a_requires_both_reviews_and_owner_execution() -> None:
    signer = Signer()
    path = Path("/SYNTHETIC/input-manifest.json")
    subject = auth.phase_a_subject("1" * 64, path, "2" * 64)
    grants = {
        "IMPLEMENTATION_REVIEW": signer.decision("IMPLEMENTATION_REVIEW", auth.code_identity()),
        "C0_SEAL_REVIEW": signer.decision("C0_SEAL_REVIEW", subject),
        "A_EXECUTION": signer.decision("A_EXECUTION", subject),
    }
    auth.require_phase_a(signer.context, grants, "1" * 64, path, "2" * 64)
    for missing in grants:
        with pytest.raises(PermissionError):
            auth.require_phase_a(
                signer.context,
                {k: v for k, v in grants.items() if k != missing},
                "1" * 64,
                path,
                "2" * 64,
            )
    for c0, mp, mh in (
        ("3" * 64, path, "2" * 64),
        ("1" * 64, Path("/SYNTHETIC/other.json"), "2" * 64),
        ("1" * 64, path, "3" * 64),
    ):
        with pytest.raises(PermissionError):
            auth.require_phase_a(signer.context, grants, c0, mp, mh)


def test_real_independent_enrollment_not_inferred_from_local_keys() -> None:
    assert auth.REAL_PHASE_A_ENROLLMENT_SHA256 is None
    with pytest.raises(PermissionError, match="INDEPENDENT_REVIEWER_ENROLLMENT"):
        auth.require_phase_a(auth.Context("REAL"), {}, "1" * 64, Path("/not-opened.json"), "2" * 64)


@pytest.fixture
def extension(enrollment: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    e = enrollment
    key = Ed25519PrivateKey.generate()
    c = {
        "version": 1,
        "mode": "REAL",
        "scope": "V0_19_SOURCE002_OWNER_RESEARCH_SCOPE_R1",
        "parent_enrollment_sha256": auth.REAL_TRUST_CONFIG_SHA256,
        "issued_at": "2020-01-01T00:00:00+00:00",
        "expires_at": "2099-01-01T00:00:00+00:00",
        "owner_key_id": "owner",
        "reviewer_key_id": "independent-reviewer",
        "reviewer_public_key_hex": key.public_key().public_bytes_raw().hex(),
        "owner_custodian_id": "FICTIONAL-OWNER",
        "reviewer_custodian_id": "FICTIONAL-REVIEWER",
        "custody_evidence_sha256": "1" * 64,
    }
    path = e["path"].with_name("phase-a-enrollment.json")

    def save(value: dict[str, Any], *, repin: bool = True) -> None:
        raw = canonical_bytes(value)
        path.write_bytes(raw)
        if repin:
            monkeypatch.setattr(auth, "REAL_PHASE_A_ENROLLMENT_SHA256", io._hash(raw))

    def sign(kind: str, subject: str, *, expired: bool = False) -> dict[str, Any]:
        reviewer = kind in {"C0_SEAL_REVIEW", "IMPLEMENTATION_REVIEW"}
        g = decision(e, kind, subject)
        g["payload"]["key_id"] = "independent-reviewer" if reviewer else "owner"
        if expired:
            g["payload"]["expires_at"] = "2020-01-02T00:00:00+00:00"
        g["signature"] = base64.b64encode(
            (key if reviewer else e["owner"]).sign(canonical_bytes(g["payload"]))
        ).decode()
        return g

    save(c)
    ctx = auth.Context("REAL", real_trust_config=e["path"], real_phase_a_enrollment=path)
    mp, mh, c0 = Path("/FICTIONAL/input-manifest.json"), "2" * 64, "3" * 64
    subject = auth.phase_a_subject(c0, mp, mh)
    grants = {
        k: sign(k, auth.code_identity() if k == "IMPLEMENTATION_REVIEW" else subject)
        for k in ("IMPLEMENTATION_REVIEW", "C0_SEAL_REVIEW", "A_EXECUTION")
    }
    return dict(
        e=e,
        config=c,
        save=save,
        ctx=ctx,
        mp=mp,
        mh=mh,
        c0=c0,
        grants=grants,
        sign=sign,
        subject=subject,
        path=path,
    )


def test_reviewed_enrollment_and_correct_signatures_allow_a_gate_only(
    extension: dict[str, Any],
) -> None:
    x = extension
    auth.require_phase_a(x["ctx"], x["grants"], x["c0"], x["mp"], x["mh"])
    # No REAL numerical inputs opened; REAL label/scoring capability remains absent.
    for kind in ("B_LABEL_READ", "B_SCORING"):
        with pytest.raises(PermissionError):
            auth.require(x["ctx"], {kind: x["sign"](kind, x["subject"])}, kind, x["subject"])


@pytest.mark.parametrize(
    "change",
    [
        "same_custodian",
        "old_reviewer",
        "owner_key",
        "expired",
        "scope",
        "parent",
        "unreviewed_bytes",
    ],
)
def test_independent_enrollment_rejects_invalid_custody_or_pin(
    extension: dict[str, Any], change: str
) -> None:
    x = extension
    c = deepcopy(x["config"])
    if change == "same_custodian":
        c["reviewer_custodian_id"] = c["owner_custodian_id"]
    elif change in {"old_reviewer", "owner_key"}:
        c["reviewer_public_key_hex"] = x["e"]["config"]["keys"][
            "reviewer" if change == "old_reviewer" else "owner"
        ]["public_key_hex"]
    elif change == "expired":
        c["expires_at"] = "2020-01-02T00:00:00+00:00"
    elif change == "parent":
        c["parent_enrollment_sha256"] = "0" * 64
    elif change == "scope":
        c["scope"] = "OTHER"
    else:
        c["custody_evidence_sha256"] = "0" * 64
    x["save"](c, repin=change != "unreviewed_bytes")
    with pytest.raises((PermissionError, ValueError)):
        auth.require_phase_a(x["ctx"], x["grants"], x["c0"], x["mp"], x["mh"])


@pytest.mark.parametrize(
    "change",
    [
        "missing_review",
        "old_reviewer",
        "wrong_code",
        "expired_owner",
        "expired_reviewer",
        "forged",
        "c0",
        "manifest",
    ],
)
def test_real_gate_rejects_before_input_or_calculation(
    extension: dict[str, Any], monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    x = extension
    g = deepcopy(x["grants"])
    c0, mh = x["c0"], x["mh"]
    if change == "missing_review":
        del g["C0_SEAL_REVIEW"]
    elif change == "old_reviewer":
        g["C0_SEAL_REVIEW"] = decision(x["e"], "C0_SEAL_REVIEW", x["subject"], "reviewer")
    elif change == "wrong_code":
        g["A_EXECUTION"]["payload"]["code_sha256"] = "0" * 64
    elif change.startswith("expired"):
        kind = "A_EXECUTION" if change == "expired_owner" else "C0_SEAL_REVIEW"
        g[kind] = x["sign"](kind, x["subject"], expired=True)
    elif change == "forged":
        g["A_EXECUTION"]["signature"] = base64.b64encode(b"x" * 64).decode()
    elif change == "c0":
        c0 = "4" * 64
    else:
        mh = "4" * 64

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("INPUT_OR_COMPUTATION_REACHED")

    monkeypatch.setattr(cohort, "load_inputs", forbidden)
    monkeypatch.setattr(execution, "calculate", forbidden)
    with pytest.raises(PermissionError):
        execution.run_a(x["mp"], mh, {"sha256": c0}, x["ctx"], g)


def test_no_enrollment_via_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REAL_PHASE_A_ENROLLMENT_SHA256", "1" * 64)
    monkeypatch.setenv("A_EXECUTION", "true")
    with pytest.raises(PermissionError, match="INDEPENDENT_REVIEWER_ENROLLMENT"):
        auth.require_phase_a(auth.Context("REAL"), {}, "1" * 64, Path("/no-read"), "2" * 64)
