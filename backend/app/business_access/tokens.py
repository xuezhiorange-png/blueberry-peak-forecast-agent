"""Versioned HMAC contexts; signatures protect integrity, never grant access."""

import base64
import hashlib
import hmac
import json
import re

from pydantic import ValidationError

from backend.app.business_access.schemas import TokenClaims
from backend.app.local_auth.sessions import AuthError, Principal, now


def canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode()


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


class Signer:
    def __init__(self, key: str):
        self.key = key.encode()
        if len(self.key) < 32:
            raise AuthError("SIGNING_UNAVAILABLE", 503)

    def sign(self, claims: TokenClaims) -> str:
        raw = canonical(claims.model_dump(mode="json", exclude_none=True))
        signature = hmac.digest(self.key, b"V0_18_BUSINESS_ACCESS_R1\0" + raw, "sha256")
        token = encode(raw) + "." + encode(signature)
        maximum = 2048 if claims.purpose == "cursor" else 8192
        if len(token.encode()) > maximum:
            raise AuthError("CONTEXT_SIZE_LIMIT", 503)
        return token

    def verify(self, token: str, purpose: str, principal: Principal) -> TokenClaims:
        maximum = 2048 if purpose == "cursor" else 8192
        if (
            len(token.encode()) > maximum
            or re.fullmatch(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", token) is None
        ):
            raise AuthError("INVALID_CONTEXT", 422)
        payload, supplied = token.split(".")
        try:
            raw = base64.b64decode(
                payload + "=" * (-len(payload) % 4), altchars=b"-_", validate=True
            )
            signature = base64.b64decode(
                supplied + "=" * (-len(supplied) % 4), altchars=b"-_", validate=True
            )
            if (
                encode(raw) != payload
                or encode(signature) != supplied
                or not hmac.compare_digest(
                    signature, hmac.digest(self.key, b"V0_18_BUSINESS_ACCESS_R1\0" + raw, "sha256")
                )
            ):
                raise AuthError("INVALID_CONTEXT", 422)
            claims = TokenClaims.model_validate_json(raw)
            if canonical(claims.model_dump(mode="json", exclude_none=True)) != raw:
                raise AuthError("INVALID_CONTEXT", 422)
        except (ValueError, ValidationError):
            raise AuthError("INVALID_CONTEXT", 422) from None
        lifetime = 900 if purpose == "cursor" else 300
        stamp = int(now().timestamp())
        if (
            claims.version != 1
            or claims.purpose != purpose
            or claims.expires_at - claims.issued_at != lifetime
            or claims.issued_at > stamp
            or claims.expires_at <= stamp
        ):
            raise AuthError("EXPIRED_OR_INVALID_CONTEXT", 422)
        if claims.principal != principal.principal_id or claims.session != principal.session_id:
            raise AuthError("FORBIDDEN")
        if (
            claims.auth_revision != principal.auth_revision
            or claims.grant_revision != principal.grant_revision
        ):
            raise AuthError("AUTHORITY_MISMATCH", 409)
        return claims
