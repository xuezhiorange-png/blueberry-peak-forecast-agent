"""CLI commands for V0.6-S2 shadow forecasts."""

from __future__ import annotations

import json
from argparse import ArgumentParser, Namespace, _SubParsersAction
from typing import TextIO

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.core_forecast.cli import CoreForecastCliError
from backend.app.pit.shadow_forecast import (
    ShadowForecastError,
    ShadowForecastRequest,
    run_shadow_forecast,
    run_shadow_forecast_batch,
    shadow_execution_payload,
)


def register_shadow_forecast_parsers(
    parsers: _SubParsersAction[ArgumentParser],
) -> None:
    single = parsers.add_parser("shadow-forecast")
    single.add_argument("--base-id")
    single.add_argument("--base-name")
    single.add_argument("--area-mu")
    single.add_argument("--season", required=True)
    single.add_argument("--output", default="-")

    batch = parsers.add_parser("shadow-forecast-batch")
    batch.add_argument("--season", required=True)
    batch.add_argument("--output", default="-")


def _write(payload: object, *, output: str, stdout: TextIO) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if output == "-":
        stdout.write(text)
        stdout.flush()
        return
    try:
        with open(output, "w", encoding="utf-8") as file:
            file.write(text)
    except OSError as exc:
        raise CoreForecastCliError(
            "SHADOW_FORECAST_OUTPUT_UNAVAILABLE",
            "OUTPUT_DOCUMENT_UNWRITABLE",
            exit_code=2,
        ) from exc


async def dispatch_shadow_forecast(
    args: Namespace,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    stdout: TextIO,
) -> None:
    try:
        async with session_factory() as session:
            async with session.begin():
                if args.resource == "shadow-forecast-batch":
                    result = await run_shadow_forecast_batch(
                        session,
                        target_season=args.season,
                    )
                    payload = {
                        "target_season": args.season,
                        "total_base_count": result.total_base_count,
                        "success_count": result.success_count,
                        "blocked_count": result.blocked_count,
                        "failed_count": result.failed_count,
                        "items": [
                            {
                                "base_id": item.base_id,
                                "status": item.status,
                                "error_code": item.error_code,
                                "execution": (
                                    shadow_execution_payload(item.execution)
                                    if item.execution is not None
                                    else None
                                ),
                            }
                            for item in result.items
                        ],
                    }
                else:
                    request = ShadowForecastRequest(
                        base_id=args.base_id,
                        base_name=args.base_name,
                        target_area_mu=args.area_mu,
                        target_season=args.season,
                    )
                    execution = await run_shadow_forecast(session, request)
                    payload = shadow_execution_payload(execution)
        _write(payload, output=args.output, stdout=stdout)
    except ShadowForecastError as exc:
        raise CoreForecastCliError(
            exc.code,
            exc.reason,
            exit_code=3 if exc.status_code >= 500 else 2,
        ) from exc
    except (ValueError, OSError) as exc:
        raise CoreForecastCliError(
            "SHADOW_FORECAST_REQUEST_INVALID",
            "INVALID_SHADOW_FORECAST_REQUEST",
            exit_code=2,
        ) from exc
    except SQLAlchemyError as exc:
        raise CoreForecastCliError(
            "SHADOW_FORECAST_WRITE_FAILURE",
            "DATABASE_UNAVAILABLE",
            exit_code=3,
        ) from exc


__all__ = ["dispatch_shadow_forecast", "register_shadow_forecast_parsers"]
