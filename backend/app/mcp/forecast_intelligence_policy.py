"""Trusted local-filesystem policy authority; no client policy publishing endpoint.

Workers on one POSIX host share a stable lock inode. A publisher's exclusive lock
linearizes revocation against the shared lock held through actual ASGI sends.
This is NOT a distributed/multi-host policy store or an end-user delegation.
"""

import hashlib
import json
import os
import stat
import tempfile
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import anyio
from pydantic import Field, field_validator, model_validator

from backend.app.forecast_intelligence.read_schemas import Identifier, ReadModel
from backend.app.mcp.forecast_intelligence_auth import MCPServiceConfig

MAX_POLICY_BYTES = 2097152


class PolicyDocument(ReadModel):
    revision: int = Field(strict=True, ge=1)
    valid_until: datetime
    config: MCPServiceConfig
    disabled_principals: frozenset[Identifier] = frozenset()

    @model_validator(mode="after")
    def mandatory_tls(self) -> "PolicyDocument":
        if not self.config.require_https:
            raise ValueError("AUTHORIZATION_UNAVAILABLE")
        if not self.disabled_principals.issubset({a.principal_id for a in self.config.accounts}):
            raise ValueError("AUTHORIZATION_UNAVAILABLE")
        return self

    @field_validator("valid_until")
    @classmethod
    def explicit_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("AUTHORIZATION_UNAVAILABLE")
        return value


@dataclass(frozen=True)
class PolicySnapshot:
    document: PolicyDocument
    digest: str


class FilePolicy:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        if not self.path.is_absolute():
            raise ValueError("AUTHORIZATION_UNAVAILABLE")

    def _trusted(self, path: Path, *, directory: bool = False) -> None:
        info = path.lstat()
        if (
            info.st_uid != os.getuid()
            or stat.S_ISLNK(info.st_mode)
            or (info.st_mode & 0o077)
            or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
        ):
            raise ValueError("AUTHORIZATION_UNAVAILABLE")

    @contextmanager
    def _descriptor(self) -> Iterator[int]:
        self._trusted(self.path.parent, directory=True)
        lock = self.path.with_suffix(".lock")
        descriptor = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            self._trusted(lock)
            if os.fstat(descriptor).st_ino != lock.lstat().st_ino:
                raise ValueError("AUTHORIZATION_UNAVAILABLE")
            yield descriptor
        finally:
            os.close(descriptor)

    def _read(self, *, allow_expired: bool = False) -> PolicySnapshot:
        self._trusted(self.path)
        with self.path.open("rb") as stream:
            raw = stream.read(MAX_POLICY_BYTES + 1)
        if len(raw) > MAX_POLICY_BYTES:
            raise ValueError("AUTHORIZATION_UNAVAILABLE")
        document = PolicyDocument.model_validate_json(raw)
        if not allow_expired and document.valid_until <= datetime.now(UTC):
            raise ValueError("AUTHORIZATION_UNAVAILABLE")
        return PolicySnapshot(document, hashlib.sha256(raw).hexdigest())

    @asynccontextmanager
    async def _shared(self) -> AsyncIterator[None]:
        # Unsupported platforms fail closed. Never pretend an in-memory mutex is
        # sufficient for independent workers. No blocking flock on the event loop.
        import fcntl

        with self._descriptor() as descriptor:
            with anyio.fail_after(2):
                while True:
                    try:
                        fcntl.flock(descriptor, fcntl.LOCK_SH | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        await anyio.sleep(0.01)
            try:
                yield
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)

    async def snapshot(self) -> PolicySnapshot:
        async with self._shared():
            return self._read()

    @asynccontextmanager
    async def release(self, snapshot: PolicySnapshot) -> AsyncIterator[None]:
        async with self._shared():
            current = self._read()
            if current.digest != snapshot.digest:
                raise ValueError("AUTHORIZATION_CHANGED")
            yield

    def publish(self, document: PolicyDocument) -> None:
        """Trusted operator only. Remove grants/accounts or replace keys; never mutate.

        A successful return is the revocation commit boundary. Policy files must
        not be edited outside this publisher. Shared storage across hosts is NOT
        supported. Policy expiration denies all calls, including quality.
        """
        import fcntl

        # SecretStr's public serialization intentionally redacts credentials;
        # only this private, owner-readable authority file carries actual keys.
        document = PolicyDocument.model_validate(document.model_dump())
        payload = document.model_dump(mode="json")
        payload["disabled_principals"] = sorted(document.disabled_principals)
        for row, account in zip(
            payload["config"]["accounts"], document.config.accounts, strict=True
        ):
            row["secret"] = account.secret.get_secret_value()
            row["permissions"] = sorted(account.permissions)
        raw = (json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode()
        if len(raw) > MAX_POLICY_BYTES:
            raise ValueError("AUTHORIZATION_UNAVAILABLE")
        with self._descriptor() as descriptor:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            temporary: str | None = None
            try:
                if self.path.exists():
                    self._trusted(self.path)
                    previous = self._read(allow_expired=True).document
                    if document.revision <= previous.revision:
                        raise ValueError("AUTHORIZATION_CHANGED")
                fd, temporary = tempfile.mkstemp(dir=self.path.parent, prefix=".policy-")
                try:
                    remaining = memoryview(raw)
                    while remaining:
                        written = os.write(fd, remaining)
                        if written <= 0:
                            raise ValueError("AUTHORIZATION_UNAVAILABLE")
                        remaining = remaining[written:]
                    os.fsync(fd)
                finally:
                    os.close(fd)
                os.replace(temporary, self.path)
                temporary = None
                parent = os.open(self.path.parent, os.O_RDONLY)
                try:
                    os.fsync(parent)
                finally:
                    os.close(parent)
            finally:
                if temporary is not None:
                    os.unlink(temporary)
                fcntl.flock(descriptor, fcntl.LOCK_UN)
