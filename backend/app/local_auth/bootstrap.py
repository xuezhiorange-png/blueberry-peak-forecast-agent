"""Trusted interactive bootstrap; never registered as an HTTP endpoint."""

import asyncio
import getpass

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.local_auth.models import AuthAccount
from backend.app.local_auth.passwords import hash_password, username
from backend.app.local_auth.service import audit
from backend.app.local_auth.sessions import AuthError, now


async def bootstrap(
    factory: async_sessionmaker[AsyncSession],
    login: str,
    password: str,
    *,
    trusted_operator_approved: bool = False,
) -> str:
    if not trusted_operator_approved:
        raise AuthError("FORBIDDEN")
    async with factory() as db, db.begin():
        if db.bind is None or db.bind.dialect.name != "postgresql":
            raise AuthError("AUTHORIZATION_UNAVAILABLE", 503)
        await db.execute(text("SELECT pg_advisory_xact_lock(1801001)"))
        if await db.scalar(
            select(func.count()).select_from(AuthAccount).where(AuthAccount.role == "ADMIN")
        ):
            raise AuthError("BOOTSTRAP_ALREADY_COMPLETED", 409)
        account = AuthAccount(
            username_normalized=username(login),
            password_hash=hash_password(password),
            role="ADMIN",
            created_at=now(),
            updated_at=now(),
            must_change_password=True,
        )
        db.add(account)
        await db.flush()
        audit(db, "BOOTSTRAP", actor=account.principal_id, target=account.account_id)
        return account.principal_id


def main() -> None:
    # Invocation itself is not approval. A named operator must receive independent
    # Owner authorization, then type the explicit confirmation at the trusted CLI.
    if (
        input("Type OWNER_APPROVED_TRUSTED_BOOTSTRAP to confirm authorization: ")
        != "OWNER_APPROVED_TRUSTED_BOOTSTRAP"
    ):
        raise SystemExit("Bootstrap not authorized")
    from backend.app.db.session import AsyncSessionMaker

    login = input("Username: ")
    password = getpass.getpass("Temporary password (not echoed): ")
    asyncio.run(bootstrap(AsyncSessionMaker, login, password, trusted_operator_approved=True))


if __name__ == "__main__":
    main()
