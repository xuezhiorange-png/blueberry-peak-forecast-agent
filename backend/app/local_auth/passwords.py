"""Bounded Argon2id operations; passwords are never normalized or logged."""

import re

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from argon2.low_level import Type

HASHER = PasswordHasher(
    time_cost=2, memory_cost=19456, parallelism=1, salt_len=16, hash_len=32, type=Type.ID
)


def username(value: str) -> str:
    normalized = value.lower()
    if re.fullmatch(r"[a-z0-9._-]{3,64}", normalized) is None:
        raise ValueError("INVALID_REQUEST")
    return normalized


def password(value: str) -> str:
    if not 15 <= len(value) <= 128:
        raise ValueError("INVALID_REQUEST")
    return value


def hash_password(value: str) -> str:
    return HASHER.hash(password(value))


def verify_password(encoded: str, value: str) -> bool:
    if not 15 <= len(value) <= 128:
        return False
    try:
        return HASHER.verify(encoded, value)
    except (VerificationError, InvalidHashError):
        return False
