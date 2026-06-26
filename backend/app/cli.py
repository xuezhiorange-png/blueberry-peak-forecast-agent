from __future__ import annotations

import argparse
import asyncio
import json
import sys
import threading
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TextIO

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.db.session import AsyncSessionMaker
from backend.app.harvest_state.application import (
    HarvestStateDeliveryConflictError,
    HarvestStateDeliveryError,
    HarvestStateDeliveryInputError,
    HarvestStateDeliveryIntegrityError,
    HarvestStateRunNotFoundError,
    execute_harvest_state_run,
    get_harvest_state_run_by_id,
    get_harvest_state_run_by_result_hash,
)
from backend.app.harvest_state.canonical import canonical_json_dumps
from backend.app.harvest_state.reports import (
    render_harvest_state_csv_report,
    render_harvest_state_json_report,
)


def _input_file_error() -> HarvestStateDeliveryInputError:
    return HarvestStateDeliveryInputError("Harvest-state input file could not be read.")


def _output_file_error() -> HarvestStateDeliveryIntegrityError:
    return HarvestStateDeliveryIntegrityError("Harvest-state output file could not be written.")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Task 9C harvest-state delivery")
    subparsers = parser.add_subparsers(dest="resource", required=True)
    harvest_state = subparsers.add_parser("harvest-state")
    harvest_state_subparsers = harvest_state.add_subparsers(dest="command", required=True)

    run_parser = harvest_state_subparsers.add_parser("run")
    run_parser.add_argument("--input", required=True)
    run_parser.add_argument("--output", default="-")

    get_parser = harvest_state_subparsers.add_parser("get")
    locator = get_parser.add_mutually_exclusive_group(required=True)
    locator.add_argument("--run-id", type=int)
    locator.add_argument("--result-hash")
    get_parser.add_argument("--output", default="-")

    report_parser = harvest_state_subparsers.add_parser("report")
    report_parser.add_argument("--run-id", required=True, type=int)
    report_parser.add_argument("--format", required=True, choices=("json", "csv"))
    report_parser.add_argument("--output", required=True)
    return parser


def _read_json_input(path: str, stdin: TextIO) -> Mapping[str, object]:
    try:
        if path == "-":
            text = stdin.read()
        else:
            text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise _input_file_error() from exc
    payload = json.loads(text)
    if not isinstance(payload, Mapping):
        raise HarvestStateDeliveryInputError("Harvest-state request root must be a JSON object.")
    return payload


def _write_text_output(path: str, content: str, stdout: TextIO) -> None:
    if path == "-":
        stdout.write(content)
        stdout.flush()
        return
    try:
        Path(path).write_text(content, encoding="utf-8")
    except OSError as exc:
        raise _output_file_error() from exc


def _write_binary_output(path: str, content: bytes) -> None:
    try:
        Path(path).write_bytes(content)
    except OSError as exc:
        raise _output_file_error() from exc


def _delivery_error_exit_code(exc: HarvestStateDeliveryError) -> int:
    if isinstance(exc, HarvestStateDeliveryInputError):
        return 2
    if isinstance(exc, HarvestStateRunNotFoundError):
        return 4
    if isinstance(exc, HarvestStateDeliveryConflictError):
        return 9
    if isinstance(exc, HarvestStateDeliveryIntegrityError):
        return 10
    return 10


async def _run_command(
    args: argparse.Namespace,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    stdin: TextIO,
    stdout: TextIO,
) -> None:
    payload = _read_json_input(args.input, stdin)
    async with session_factory() as session:
        envelope = await execute_harvest_state_run(session, request=payload)
    _write_text_output(
        args.output,
        f"{canonical_json_dumps(envelope.model_dump(mode='json'))}\n",
        stdout,
    )


async def _get_command(
    args: argparse.Namespace,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    stdout: TextIO,
) -> None:
    async with session_factory() as session:
        if args.run_id is not None:
            envelope = await get_harvest_state_run_by_id(session, run_id=args.run_id)
        else:
            envelope = await get_harvest_state_run_by_result_hash(
                session,
                result_hash=args.result_hash,
            )
    _write_text_output(
        args.output,
        f"{canonical_json_dumps(envelope.model_dump(mode='json'))}\n",
        stdout,
    )


async def _report_command(
    args: argparse.Namespace,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    stdout: TextIO,
) -> None:
    async with session_factory() as session:
        envelope = await get_harvest_state_run_by_id(session, run_id=args.run_id)
    if args.format == "json":
        payload = render_harvest_state_json_report(
            run_id=envelope.run_id,
            created_at=envelope.created_at,
            output=envelope.output,
        )
        if args.output == "-":
            stdout.write(payload.decode("utf-8"))
            stdout.flush()
            return
        _write_binary_output(args.output, payload)
        return
    payload = render_harvest_state_csv_report(
        run_id=envelope.run_id,
        created_at=envelope.created_at,
        output=envelope.output,
    )
    _write_binary_output(args.output, payload)


async def _dispatch(
    args: argparse.Namespace,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    stdin: TextIO,
    stdout: TextIO,
) -> None:
    if args.resource != "harvest-state":
        raise HarvestStateDeliveryInputError("Unsupported CLI resource.")
    if args.command == "run":
        await _run_command(args, session_factory=session_factory, stdin=stdin, stdout=stdout)
        return
    if args.command == "get":
        await _get_command(args, session_factory=session_factory, stdout=stdout)
        return
    if args.command == "report":
        await _report_command(args, session_factory=session_factory, stdout=stdout)
        return
    raise HarvestStateDeliveryInputError("Unsupported CLI command.")


def run_cli(
    argv: Sequence[str] | None = None,
    *,
    session_factory: async_sessionmaker[AsyncSession] = AsyncSessionMaker,
    stdin: TextIO = sys.stdin,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    try:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(
                _dispatch(
                    args,
                    session_factory=session_factory,
                    stdin=stdin,
                    stdout=stdout,
                )
            )
        else:
            result: dict[str, BaseException | None] = {"error": None}

            def _runner() -> None:
                try:
                    asyncio.run(
                        _dispatch(
                            args,
                            session_factory=session_factory,
                            stdin=stdin,
                            stdout=stdout,
                        )
                    )
                except BaseException as exc:  # noqa: BLE001
                    result["error"] = exc

            thread = threading.Thread(target=_runner)
            thread.start()
            thread.join()
            if result["error"] is not None:
                raise result["error"]
    except (HarvestStateDeliveryError, ValidationError, json.JSONDecodeError) as exc:
        if isinstance(exc, HarvestStateDeliveryError):
            error = exc
        elif isinstance(exc, ValidationError):
            error = HarvestStateDeliveryInputError("Harvest-state request failed validation.")
        else:
            error = HarvestStateDeliveryInputError("Harvest-state request body is not valid JSON.")
        stderr.write(f"{error.code}: {error}\n")
        stderr.flush()
        return _delivery_error_exit_code(error)
    return 0


def main() -> None:
    raise SystemExit(run_cli())
