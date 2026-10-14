"""Strict cryptographic context validation; never a substitute for resource grants."""

from dataclasses import replace
from datetime import timedelta

import pytest

from backend.app.business_access import tokens
from backend.app.business_access.schemas import TokenClaims
from backend.app.business_access.tokens import Signer
from backend.app.local_auth.sessions import AuthError, Principal, now


def claims():
    stamp = int(now().timestamp())
    return TokenClaims(
        version=1,
        purpose="cursor",
        principal="SYNTHETIC_PRINCIPAL",
        session="SYNTHETIC_SESSION",
        auth_revision=1,
        grant_revision=1,
        grant_directory="a" * 64,
        catalog_snapshot="b" * 64,
        issued_at=stamp,
        expires_at=stamp + 900,
        filter_hash="c" * 64,
        last_key=(
            "2026-01-01",
            "OPERATIONAL_PEAK",
            "OPERATIONAL_PEAK_FORECAST_RUN_V1",
            1,
            "A1",
            "d" * 64,
        ),
    )


def principal():
    return Principal(
        "SYNTHETIC_ACCOUNT",
        "SYNTHETIC_PRINCIPAL",
        "SYNTHETIC_SESSION",
        "BUSINESS_USER",
        False,
        1,
        1,
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "signature",
        "padding",
        "extra",
        "overlong",
        "purpose",
        "principal",
        "session",
        "auth_revision",
        "grant_revision",
        "expiry",
        "future",
        "key",
    ],
)
def test_token_rejects_invalid_or_stale_context(monkeypatch, mutation):
    signer = Signer("SYNTHETIC_SERVER_ONLY_SIGNING_KEY" * 2)
    value = claims()
    token = signer.sign(value)
    actor = principal()
    purpose = "cursor"
    expected = 422
    if mutation == "signature":
        token = token[:-2] + ("A" if token[-2] != "A" else "B") + token[-1]
    elif mutation == "padding":
        token += "="
    elif mutation == "extra":
        token += ".extra"
    elif mutation == "overlong":
        token = "x" * 2049
    elif mutation == "purpose":
        purpose = "selection"
    elif mutation in {"principal", "session"}:
        actor = replace(actor, **{mutation + "_id": "SYNTHETIC_OTHER"})
        expected = 403
    elif mutation in {"auth_revision", "grant_revision"}:
        actor = replace(actor, **{mutation: 2})
        expected = 409
    elif mutation == "expiry":
        future = now() + timedelta(seconds=901)
        monkeypatch.setattr(tokens, "now", lambda: future)
    elif mutation == "future":
        token = signer.sign(
            value.model_copy(
                update={"issued_at": value.issued_at + 100, "expires_at": value.expires_at + 100}
            )
        )
    else:
        signer = Signer("SYNTHETIC_DIFFERENT_SERVER_KEY" * 2)
    with pytest.raises(AuthError) as exc:
        signer.verify(token, purpose, actor)
    assert exc.value.status == expected


def test_roundtrip_limits_and_missing_signer_fail_closed():
    signer = Signer("SYNTHETIC_SERVER_ONLY_SIGNING_KEY" * 2)
    value = claims()
    token = signer.sign(value)
    assert len(token.encode()) <= 2048
    assert signer.verify(token, "cursor", principal()) == value
    for key in ("", "short"):
        with pytest.raises(AuthError) as exc:
            Signer(key)
        assert exc.value.status == 503
