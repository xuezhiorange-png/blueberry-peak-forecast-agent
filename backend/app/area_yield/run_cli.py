"""Saved-run subcommands in the existing CLI framework."""

from __future__ import annotations

import argparse
import json
from typing import TextIO

from anyio import Path
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.area_yield.product import AreaDrivenForecastRequest
from backend.app.area_yield.product_errors import (
    AreaForecastAuthorityError,
    AreaForecastRequestError,
)
from backend.app.area_yield.run_application import execute_area_forecast_run
from backend.app.area_yield.run_persistence import (
    AreaForecastPersistenceConflictError,
    AreaForecastPersistenceIntegrityError,
    AreaForecastRunNotFoundError,
    AreaForecastRunRepository,
    AreaForecastWriteFailure,
)
from backend.app.area_yield.run_schemas import CreateAreaForecastRun
from backend.app.core_forecast.cli import CoreForecastCliError


def register_area_run_parser(parsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    root = parsers.add_parser("area-forecast-run")
    subs = root.add_subparsers(dest="command", required=True)
    create = subs.add_parser("create")
    create.add_argument("--input", required=True)
    for name in ("get", "daily"):
        p = subs.add_parser(name)
        p.add_argument("--run-id", type=int, required=True)
    history = subs.add_parser("list")
    history.add_argument("--farm")
    history.add_argument("--target-season")
    history.add_argument("--forecast-policy-version")
    history.add_argument("--limit", type=int, default=20)
    history.add_argument("--cursor")


async def dispatch_area_run(
    args: argparse.Namespace,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    stdin: TextIO,
    stdout: TextIO,
) -> None:
    try:
        async with session_factory() as session:
            async with session.begin():
                repository = AreaForecastRunRepository(session)
                if args.command == "create":
                    raw = stdin.read() if args.input == "-" else await Path(args.input).read_text()
                    body = CreateAreaForecastRun.model_validate_json(raw)
                    request = AreaDrivenForecastRequest.model_validate(
                        body.model_dump(exclude={"rerun_of_run_id"})
                    )
                    payload = (
                        await execute_area_forecast_run(
                            session, request, rerun_of_run_id=body.rerun_of_run_id
                        )
                    ).model_dump(mode="json")
                elif args.command == "list":
                    payload = (
                        await repository.history(
                            canonical_farm=args.farm,
                            target_season=args.target_season,
                            forecast_policy_version=args.forecast_policy_version,
                            limit=args.limit,
                            cursor=args.cursor,
                        )
                    ).model_dump(mode="json")
                else:
                    saved = await repository.get(args.run_id)
                    payload = (
                        saved.model_dump(mode="json")
                        if args.command == "get"
                        else {
                            "daily_forecast": [
                                r.model_dump(mode="json") for r in saved.result.daily_forecast
                            ]
                        }
                    )
        stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    except (AreaForecastRequestError, AreaForecastAuthorityError) as exc:
        raise CoreForecastCliError(
            exc.code, exc.reason, exit_code=3 if exc.status_code == 503 else 2
        ) from exc
    except (
        AreaForecastPersistenceIntegrityError,
        AreaForecastPersistenceConflictError,
        AreaForecastRunNotFoundError,
        AreaForecastWriteFailure,
    ) as exc:
        raise CoreForecastCliError(exc.code, exc.code, exit_code=3) from exc
    except (ValueError, OSError) as exc:
        raise CoreForecastCliError(
            "AREA_FORECAST_REQUEST_INVALID", "INVALID_RUN_REQUEST", exit_code=2
        ) from exc
    except SQLAlchemyError as exc:
        raise CoreForecastCliError(
            "AREA_FORECAST_WRITE_FAILURE", "DATABASE_UNAVAILABLE", exit_code=3
        ) from exc
