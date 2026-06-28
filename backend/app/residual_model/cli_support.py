from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TextIO

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.app.harvest_state.canonical import canonical_json_dumps
from backend.app.repositories.residual_model import (
    get_residual_prediction_run,
    get_residual_training_run,
)
from backend.app.residual_model.application import (
    execute_residual_prediction,
    execute_residual_training,
)
from backend.app.residual_model.config import load_residual_model_config
from backend.app.residual_model.persistence import (
    load_residual_prediction_run_by_id,
    load_residual_training_artifacts,
    load_residual_training_run_by_id,
)
from backend.app.residual_model.reporting import (
    render_residual_prediction_csv_report,
    render_residual_prediction_json_report,
    render_residual_training_csv_report,
    render_residual_training_json_report,
)
from backend.app.residual_model.schemas import (
    ResidualPredictionRequest,
    ResidualTrainingSampleSpec,
)
from backend.app.residual_model.training_manifest import build_residual_training_manifest


class ResidualModelCliError(RuntimeError):
    code = "RESIDUAL_MODEL_CLI_ERROR"
    exit_code = 10

    def __init__(self, message: str) -> None:
        super().__init__(message)


class ResidualModelCliInputError(ResidualModelCliError):
    code = "RESIDUAL_MODEL_INPUT_ERROR"
    exit_code = 2


class ResidualModelCliNotFoundError(ResidualModelCliError):
    code = "RESIDUAL_MODEL_NOT_FOUND"
    exit_code = 4


class ResidualModelCliIntegrityError(ResidualModelCliError):
    code = "RESIDUAL_MODEL_INTEGRITY_ERROR"
    exit_code = 10


def _default_config_path() -> Path:
    return Path(__file__).resolve().parents[3] / "configs" / "residual_model.yaml"


def register_residual_model_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    residual_model = subparsers.add_parser("residual-model")
    residual_subparsers = residual_model.add_subparsers(dest="command", required=True)

    manifest_parser = residual_subparsers.add_parser("build-manifest")
    manifest_parser.add_argument("--input", required=True)
    manifest_parser.add_argument("--output", default="-")

    train_parser = residual_subparsers.add_parser("train")
    train_parser.add_argument("--input", required=True)
    train_parser.add_argument("--config", default=str(_default_config_path()))
    train_parser.add_argument("--output", default="-")

    inspect_training = residual_subparsers.add_parser("inspect-training")
    inspect_training.add_argument("--run-id", required=True, type=int)
    inspect_training.add_argument("--output", default="-")

    predict_parser = residual_subparsers.add_parser("predict")
    predict_parser.add_argument("--input", required=True)
    predict_parser.add_argument("--output", default="-")

    inspect_prediction = residual_subparsers.add_parser("inspect-prediction")
    inspect_prediction.add_argument("--run-id", required=True, type=int)
    inspect_prediction.add_argument("--output", default="-")

    report_parser = residual_subparsers.add_parser("report")
    report_parser.add_argument("--kind", required=True, choices=("training", "prediction"))
    report_parser.add_argument("--run-id", required=True, type=int)
    report_parser.add_argument("--format", required=True, choices=("json", "csv"))
    report_parser.add_argument("--output", required=True)


def _read_json_input(path: str, stdin: TextIO) -> Mapping[str, object]:
    try:
        if path == "-":
            text = stdin.read()
        else:
            text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ResidualModelCliInputError("Residual-model input file could not be read.") from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ResidualModelCliInputError("Residual-model request body is not valid JSON.") from exc
    if not isinstance(payload, Mapping):
        raise ResidualModelCliInputError("Residual-model request root must be a JSON object.")
    return payload


def _write_text_output(path: str, content: str, stdout: TextIO) -> None:
    if path == "-":
        stdout.write(content)
        stdout.flush()
        return
    try:
        Path(path).write_text(content, encoding="utf-8")
    except OSError as exc:
        raise ResidualModelCliIntegrityError(
            "Residual-model output file could not be written."
        ) from exc


def _write_binary_output(path: str, payload: bytes) -> None:
    try:
        Path(path).write_bytes(payload)
    except OSError as exc:
        raise ResidualModelCliIntegrityError(
            "Residual-model output file could not be written."
        ) from exc


def _parse_training_samples(payload: Mapping[str, object]) -> list[ResidualTrainingSampleSpec]:
    raw_samples = payload.get("samples")
    if not isinstance(raw_samples, Sequence) or isinstance(raw_samples, (str, bytes, bytearray)):
        raise ResidualModelCliInputError("Residual-model samples must be a JSON array.")
    return [ResidualTrainingSampleSpec.model_validate(item) for item in raw_samples]


def _training_envelope(*, run_id: int, created_at: object, output: object) -> str:
    return canonical_json_dumps(
        {
            "run_id": run_id,
            "created_at": created_at,
            "output": output,
        }
    )


def _training_output_payload(result: object) -> object:
    if not hasattr(result, "model_dump"):
        return result
    payload = result.model_dump(mode="python", exclude={"artifacts"})
    artifacts = getattr(result, "artifacts", ())
    payload["artifacts"] = [
        {
            "quantile_label": artifact.quantile_label,
            "metadata": artifact.metadata.model_dump(mode="json"),
        }
        for artifact in artifacts
    ]
    return payload


async def dispatch_residual_model(
    args: argparse.Namespace,
    *,
    session_factory: async_sessionmaker[AsyncSession],
    stdin: TextIO,
    stdout: TextIO,
) -> None:
    if args.command == "build-manifest":
        payload = _read_json_input(args.input, stdin)
        samples = _parse_training_samples(payload)
        async with session_factory() as session:
            rows = await build_residual_training_manifest(session, samples=samples)
        _write_text_output(
            args.output,
            f"{canonical_json_dumps([row.model_dump(mode='json') for row in rows])}\n",
            stdout,
        )
        return

    if args.command == "train":
        training_payload = _read_json_input(args.input, stdin)
        samples = _parse_training_samples(training_payload)
        config = load_residual_model_config(Path(args.config))
        async with session_factory() as session:
            training_result, training_run_id = await execute_residual_training(
                session,
                samples=samples,
                config=config,
            )
            training_row = await get_residual_training_run(
                session,
                run_id=training_run_id,
            )
        if training_row is None:
            raise ResidualModelCliIntegrityError("Residual training run could not be reloaded.")
        training_envelope = _training_envelope(
            run_id=training_run_id,
            created_at=training_row.created_at,
            output=_training_output_payload(training_result),
        )
        _write_text_output(
            args.output,
            f"{training_envelope}\n",
            stdout,
        )
        return

    if args.command == "inspect-training":
        async with session_factory() as session:
            training_row = await get_residual_training_run(session, run_id=args.run_id)
            maybe_training_result = await load_residual_training_run_by_id(
                session,
                run_id=args.run_id,
            )
        if training_row is None or maybe_training_result is None:
            raise ResidualModelCliNotFoundError("Residual training run was not found.")
        training_result = maybe_training_result
        training_envelope = _training_envelope(
            run_id=training_row.id,
            created_at=training_row.created_at,
            output=_training_output_payload(training_result),
        )
        _write_text_output(
            args.output,
            f"{training_envelope}\n",
            stdout,
        )
        return

    if args.command == "predict":
        prediction_payload = _read_json_input(args.input, stdin)
        prediction_request = ResidualPredictionRequest.model_validate(prediction_payload)
        async with session_factory() as session:
            prediction_result, prediction_run_id = await execute_residual_prediction(
                session,
                request=prediction_request,
            )
            prediction_row = await get_residual_prediction_run(
                session,
                run_id=prediction_run_id,
            )
        if prediction_row is None:
            raise ResidualModelCliIntegrityError("Residual prediction run could not be reloaded.")
        prediction_envelope = canonical_json_dumps(
            {
                "run_id": prediction_run_id,
                "created_at": prediction_row.created_at,
                "output": prediction_result.model_dump(mode="json"),
            }
        )
        _write_text_output(
            args.output,
            f"{prediction_envelope}\n",
            stdout,
        )
        return

    if args.command == "inspect-prediction":
        async with session_factory() as session:
            prediction_row = await get_residual_prediction_run(session, run_id=args.run_id)
            maybe_prediction_result = await load_residual_prediction_run_by_id(
                session,
                run_id=args.run_id,
            )
        if prediction_row is None or maybe_prediction_result is None:
            raise ResidualModelCliNotFoundError("Residual prediction run was not found.")
        prediction_result = maybe_prediction_result
        prediction_envelope = canonical_json_dumps(
            {
                "run_id": prediction_row.id,
                "created_at": prediction_row.created_at,
                "output": prediction_result.model_dump(mode="json"),
            }
        )
        _write_text_output(
            args.output,
            f"{prediction_envelope}\n",
            stdout,
        )
        return

    if args.command == "report":
        async with session_factory() as session:
            if args.kind == "training":
                training_row = await get_residual_training_run(
                    session,
                    run_id=args.run_id,
                )
                maybe_training_result = await load_residual_training_run_by_id(
                    session,
                    run_id=args.run_id,
                )
                training_artifacts = await load_residual_training_artifacts(
                    session,
                    run_id=args.run_id,
                )
                if training_row is None or maybe_training_result is None:
                    raise ResidualModelCliNotFoundError("Residual training run was not found.")
                training_result = maybe_training_result
                if args.format == "json":
                    training_report_bytes = render_residual_training_json_report(
                        run_id=training_row.id,
                        created_at=training_row.created_at,
                        output=training_result,
                        manifest_snapshot=training_row.manifest_snapshot,
                    )
                    _write_binary_output(args.output, training_report_bytes)
                    return
                training_report_bytes = render_residual_training_csv_report(
                    run_id=training_row.id,
                    created_at=training_row.created_at,
                    output=training_result,
                    manifest_snapshot=training_row.manifest_snapshot,
                    artifacts=training_artifacts,
                )
                _write_binary_output(args.output, training_report_bytes)
                return

            prediction_row = await get_residual_prediction_run(
                session,
                run_id=args.run_id,
            )
            maybe_prediction_result = await load_residual_prediction_run_by_id(
                session,
                run_id=args.run_id,
            )
            if prediction_row is None or maybe_prediction_result is None:
                raise ResidualModelCliNotFoundError("Residual prediction run was not found.")
            prediction_result = maybe_prediction_result
            if args.format == "json":
                prediction_report_bytes = render_residual_prediction_json_report(
                    run_id=prediction_row.id,
                    created_at=prediction_row.created_at,
                    output=prediction_result,
                )
                _write_binary_output(args.output, prediction_report_bytes)
                return
            prediction_report_bytes = render_residual_prediction_csv_report(
                run_id=prediction_row.id,
                created_at=prediction_row.created_at,
                output=prediction_result,
            )
            _write_binary_output(args.output, prediction_report_bytes)
            return

    raise ResidualModelCliInputError("Unsupported residual-model command.")
