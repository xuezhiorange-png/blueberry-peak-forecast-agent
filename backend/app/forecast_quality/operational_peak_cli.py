"""Subcommands for persisted S6 operational peak runs in the existing CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TextIO

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.core_forecast.cli import CoreForecastCliError
from backend.app.forecast_quality.operational_peak import (
    OperationalPeakForecastError,
    OperationalPeakForecastRequest,
)
from backend.app.forecast_quality.operational_peak_application import (
    execute_operational_peak_forecast_run,
)
from backend.app.forecast_quality.operational_peak_authority import (
    OperationalPeakAuthorityError,
)
from backend.app.forecast_quality.operational_peak_persistence import (
    OperationalPeakPersistenceConflictError,
    OperationalPeakPersistenceIntegrityError,
    OperationalPeakRerunScopeMismatch,
    OperationalPeakRunNotFoundError,
    OperationalPeakRunRepository,
    OperationalPeakWriteFailure,
)
from backend.app.forecast_quality.operational_peak_schemas import (
    CreateOperationalPeakRun,
)


def register_operational_peak_parser(
    parsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    root = parsers.add_parser("operational-peak-run")
    subs = root.add_subparsers(dest="command", required=True)
    create = subs.add_parser("create")
    create.add_argument("--input", required=True)
    for name in ("get", "daily"):
        parser = subs.add_parser(name)
        parser.add_argument("--run-id", type=int, required=True)
    history = subs.add_parser("list")
    history.add_argument("--base-id")
    history.add_argument("--target-season")
    history.add_argument("--policy-version")
    history.add_argument("--limit", type=int, default=20)
    history.add_argument("--cursor")


def _read(path: str, stdin: TextIO) -> str:
    try:
        return stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise CoreForecastCliError(
            "INVALID_REQUEST", "INPUT_DOCUMENT_UNREADABLE", exit_code=2
        ) from exc


async def dispatch_operational_peak(
    args: argparse.Namespace,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    stdin: TextIO,
    stdout: TextIO,
) -> None:
    try:
        async with session_factory() as session:
            if args.command == "create":
                body = CreateOperationalPeakRun.model_validate_json(_read(args.input, stdin))
                request = OperationalPeakForecastRequest.from_mapping(body.model_dump())
                async with session.begin():
                    payload = (
                        await execute_operational_peak_forecast_run(
                            session,
                            request,
                            rerun_of_run_id=body.rerun_of_run_id,
                        )
                    ).model_dump(mode="json")
            elif args.command == "get":
                payload = (await OperationalPeakRunRepository(session).get(args.run_id)).model_dump(
                    mode="json"
                )
            elif args.command == "daily":
                payload = (
                    await OperationalPeakRunRepository(session).daily(args.run_id)
                ).model_dump(mode="json")
            else:
                payload = (
                    await OperationalPeakRunRepository(session).history(
                        base_id=args.base_id,
                        target_season=args.target_season,
                        policy_version=args.policy_version,
                        limit=args.limit,
                        cursor=args.cursor,
                    )
                ).model_dump(mode="json")
    except OperationalPeakAuthorityError as exc:
        raise CoreForecastCliError(exc.code, exc.code, exit_code=3) from exc
    except OperationalPeakForecastError as exc:
        raise CoreForecastCliError(exc.code, exc.reason, exit_code=2) from exc
    except (
        OperationalPeakRerunScopeMismatch,
        OperationalPeakPersistenceConflictError,
        OperationalPeakPersistenceIntegrityError,
        OperationalPeakRunNotFoundError,
        OperationalPeakWriteFailure,
    ) as exc:
        raise CoreForecastCliError(exc.code, exc.code, exit_code=3) from exc
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        raise CoreForecastCliError("INVALID_REQUEST", "INVALID_RUN_REQUEST", exit_code=2) from exc
    except SQLAlchemyError as exc:
        raise CoreForecastCliError(
            "OPERATIONAL_PEAK_WRITE_FAILURE", "DATABASE_UNAVAILABLE", exit_code=3
        ) from exc
    stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


__all__ = ["dispatch_operational_peak", "register_operational_peak_parser"]
