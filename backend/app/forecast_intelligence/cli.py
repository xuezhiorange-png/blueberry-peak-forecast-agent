"""CLI adapter registered in the existing application CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TextIO

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.core_forecast.cli import CoreForecastCliError
from backend.app.forecast_intelligence.application import execute_hierarchical_run
from backend.app.forecast_intelligence.errors import HierarchicalForecastError
from backend.app.forecast_intelligence.persistence import HierarchicalRunRepository
from backend.app.forecast_intelligence.schemas import (
    CreateHierarchicalRun,
    HierarchicalHistoryQuery,
)


def register_hierarchical_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    *,
    frozen_root_bridge: bool = False,
) -> None:
    resource = subparsers.add_parser("hierarchical-forecast-run")
    if frozen_root_bridge:
        # The root CLI is hash-pinned by historical V0.11 evidence. Use its
        # existing registration/dispatch hook without changing those frozen bytes.
        resource.set_defaults(resource="operational-peak-run", hierarchical_forecast_adapter=True)
    commands = resource.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("--input", required=True)
    for command in ("get", "daily"):
        child = commands.add_parser(command)
        child.add_argument("--run-id", type=int, required=True)
    history = commands.add_parser("list")
    for name in (
        "target-entity-type",
        "target-entity-id",
        "target-season",
        "origin-date",
        "reconciliation-policy-version",
        "cursor",
    ):
        history.add_argument("--" + name)
    history.add_argument("--limit", type=int, default=20)
    for child in commands.choices.values():
        child.add_argument("--output", default="-")


async def dispatch_hierarchical(
    args: argparse.Namespace,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    stdin: TextIO,
    stdout: TextIO,
) -> None:
    try:
        saved: BaseModel
        async with session_factory() as session:
            repository = HierarchicalRunRepository(session)
            if args.command == "create":
                raw = stdin.read() if args.input == "-" else _read_file(args.input)
                body = CreateHierarchicalRun.model_validate_json(raw)
                async with session.begin():
                    saved = await execute_hierarchical_run(session, body)
            elif args.command == "get":
                saved = await repository.get(args.run_id)
            elif args.command == "daily":
                saved = await repository.daily(args.run_id)
            else:
                query = HierarchicalHistoryQuery.model_validate(
                    {
                        k: v
                        for k, v in vars(args).items()
                        if k in HierarchicalHistoryQuery.model_fields
                    }
                )
                saved = await repository.history(query)
            text = (
                json.dumps(saved.model_dump(mode="json"), ensure_ascii=False, sort_keys=True) + "\n"
            )
            if args.output == "-":
                stdout.write(text)
            else:
                _write_file(args.output, text)
    except HierarchicalForecastError as exc:
        raise CoreForecastCliError(
            exc.code, exc.code, exit_code=2 if exc.status_code < 500 else 3
        ) from exc
    except (ValidationError, ValueError, OSError):
        raise CoreForecastCliError("INVALID_REQUEST", "INVALID_REQUEST", exit_code=2) from None
    except Exception:
        raise CoreForecastCliError(
            "HIERARCHICAL_FORECAST_WRITE_FAILURE", "PERSISTENCE_SERVICE_UNAVAILABLE", exit_code=3
        ) from None


def _read_file(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _write_file(path: str, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8")
