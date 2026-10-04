"""Sealed S3 temporal scoring and an explicitly nondeployable weather oracle."""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import TracebackType
from typing import Any

from backend.app.area_yield.data import digest, fixed
from backend.app.area_yield.gdd_features import sha256
from backend.app.area_yield.research_records import score_curve
from backend.app.area_yield.v013_feature_value_experiment import ExecutionGuard
from backend.app.area_yield.weather_aware_backtest import BASE_FEATURES, FEATURE_NAMES_B

ORACLE_ID = "V0_13_O1_TARGET_DATE_ANCHORED_FUTURE_REALIZED_WEATHER"
ORACLE_FEATURES = BASE_FEATURES + tuple("oracle_" + k for k in FEATURE_NAMES_B[10:])
CONTRACT = dict(
    anchor="TARGET_DATE_PLUS_1_LOCAL_DAY_START",
    timezone="Asia/Shanghai",
    feature_count=28,
    gdd=False,
    alpha="10.000000",
    train_cohort="FROZEN_S3",
    labels="SAME_AS_S3",
    cohort_loss_allowed=False,
    peak_tie="EARLIEST",
    rolling_tie="EARLIEST_START",
    combined="POOLED_WINDOW_ERRORS",
    shape="POOLED_RAW_NORMALIZED_TOTAL_ERROR",
    zero_mass="NOT_COMPUTABLE",
    timing_support="BOTH_DATES_EVERY_FOLD_AND_SHAPE",
    summary="ONE_NAMED_FAMILY",
    deployable=False,
    primary_lane=False,
    post_result_tuning=False,
    solver="numpy.linalg.solve",
    standardization="TRAIN_ONLY_STANDARD_SCALER_POPULATION_STD",
    zero_std_policy="SCALE_1",
    clip=True,
    windows=[7, 14, 30],
)
S3_HASHES = dict(
    report_hash="8bb56ca765518c8f60ffd62ffdaf3154e89fda782557e5907ac156360e444dd5",
    score_hash="2141b14c7f07516f702aa7d805b3418b74f86bf144ca25c826a56ee3bb004463",
    comparison_hash="42ff58137e597d085428d28cb36c910baa932b0b6aa98e059ed195cf655cbc27",
    support_gate_hash="8274ab9f4ba7ec5dea3c68d27ace945b90d6edacb1b6f2f86292a70cbebb50bb",
)
S3_SEALS = dict(
    fold_a="a19ca7435594a156856352610c22b42db6c586a05bb52fad236da33c34153f05",
    fold_b="7afc70540d5d4391f28111b923b58ed8e6f472ccb13af2fceb7463bb2a815973",
)


class TemporalError(ValueError):
    """Fail-closed authority or sequencing violation."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise TemporalError(code)


def validate_contract(contract: Mapping[str, Any]) -> None:
    require(contract == CONTRACT, "S4_CONTRACT_CHANGED")


def verify_oracle_window(target: date, anchor: datetime, weather: Any) -> None:
    require(
        str(anchor.tzinfo) == "Asia/Shanghai"
        and anchor.hour == anchor.minute == anchor.second == anchor.microsecond == 0
        and anchor.date() == target + timedelta(days=1)
        and weather.forecast_origin == anchor.isoformat()
        and weather.feature_window_end == target
        and weather.feature_window_start == target - timedelta(days=29),
        "ORACLE_ANCHOR_INVALID",
    )


def verify_s3(root: Path, public: Mapping[str, Any]) -> dict[str, Any]:
    report: dict[str, Any] = json.loads((root / "sanitized-evidence.json").read_text())
    require(
        all(report.get(k) == v == public.get(k) for k, v in S3_HASHES.items()),
        "S3_REPORT_AUTHORITY_MISMATCH",
    )
    require(
        digest({k: v for k, v in report.items() if k != "report_hash"}) == report["report_hash"],
        "S3_REPORT_SELF_HASH_MISMATCH",
    )
    for field, key in (("metrics", "score_hash"), ("comparisons", "comparison_hash")):
        require(digest(report[field]) == report[key], "S3_REPORT_COMPONENT_HASH_MISMATCH")
    require(
        digest({k: v["gate"] for k, v in report["comparisons"].items()})
        == report["support_gate_hash"],
        "S3_GATE_HASH_MISMATCH",
    )
    verify_s3_label_free(root, public)
    return report


def verify_s3_label_free(root: Path, public: Mapping[str, Any]) -> None:
    """Pre-seal authority: public aggregates and frozen label-free files only."""
    require(all(public.get(k) == v for k, v in S3_HASHES.items()), "S3_PUBLIC_AUTHORITY_MISMATCH")
    guard = ExecutionGuard(root)
    for fold in S3_SEALS:
        seal = guard.verify_seal(fold)
        require(
            seal["seal_hash"] == S3_SEALS[fold] == public["folds"][fold]["seal_hash"],
            "S3_SEAL_AUTHORITY_MISMATCH",
        )
        require(
            seal["prediction_hashes"] == public["folds"][fold]["prediction_hashes"],
            "S3_PREDICTION_AUTHORITY_MISMATCH",
        )
        rows = [
            json.loads(line)
            for line in (root / fold / "predictions-before-scoring.jsonl").read_text().splitlines()
        ]
        for model, expected in seal["prediction_hashes"].items():
            require(
                digest(
                    [dict(target_row_key=r["target_row_key"], prediction=r[model]) for r in rows]
                )
                == expected,
                "S3_PREDICTION_HASH_MISMATCH",
            )


def verify_oracle_artifact(artifact: Mapping[str, Any]) -> None:
    require(
        artifact.get("schema") == "V0_13_ORACLE_RIDGE_ARTIFACT_V1"
        and artifact.get("model_id") == ORACLE_ID
        and artifact.get("feature_names") == list(ORACLE_FEATURES)
        and artifact.get("alpha") == CONTRACT["alpha"]
        and artifact.get("solver") == CONTRACT["solver"]
        and artifact.get("standardization") == CONTRACT["standardization"]
        and artifact.get("zero_std_policy") == "SCALE_1"
        and artifact.get("nonnegative_output_clip") is True
        and artifact.get("intercept_unpenalized") is True
        and artifact.get("deployable") is False
        and artifact.get("future_realized_information") is True
        and digest({k: v for k, v in artifact.items() if k != "artifact_hash"})
        == artifact.get("artifact_hash"),
        "ORACLE_ARTIFACT_INVALID",
    )


class OracleGuard:
    """Oracle label/scoring barrier, independent of historical S3 seals."""

    def __init__(self, root: Path):
        self.root = root
        self.scoring_started = False

    def verify_seal(self, fold: str) -> dict[str, Any]:
        try:
            root = self.root / fold
            seal: dict[str, Any] = json.loads((root / "prediction-seal.json").read_text())
            require(
                seal["seal_hash"] == digest({k: v for k, v in seal.items() if k != "seal_hash"}),
                "ORACLE_SEAL_HASH_MISMATCH",
            )
            require(
                seal["fold_id"].lower() == fold
                and seal["sealed_before_validation_label_read"] is True
                and seal["oracle_lane_c"] is True
                and seal["future_realized_information"] is True
                and seal["feature_policy_hash"] == digest(CONTRACT),
                "ORACLE_SEAL_POLICY_MISMATCH",
            )
            require(
                set(seal["file_hashes"])
                == {"o1-artifact.json", "predictions-before-scoring.jsonl"},
                "ORACLE_SEAL_INVENTORY_INVALID",
            )
            for name, expected in seal["file_hashes"].items():
                require(sha256(root / name) == expected, "ORACLE_SEALED_FILE_CHANGED")
            artifact = json.loads((root / "o1-artifact.json").read_text())
            verify_oracle_artifact(artifact)
            require(
                artifact["artifact_hash"] == seal["artifact_hash"], "ORACLE_ARTIFACT_SEAL_MISMATCH"
            )
            return seal
        except (OSError, KeyError, TypeError, ValueError) as exc:
            raise TemporalError("ORACLE_SEAL_REQUIRED_OR_INVALID") from exc

    def allow_label_read(self, season: str) -> None:
        if season == "2024-2025":
            self.verify_seal("fold_a")
        elif season == "2025-2026":
            self.verify_seal("fold_a")
            self.verify_seal("fold_b")
        else:
            require(season == "2023-2024", "UNAUTHORIZED_LABEL_SEASON")

    def allow_fit(self) -> None:
        require(not self.scoring_started, "POST_RESULT_REFIT_FORBIDDEN")

    def begin_score(self) -> None:
        for fold in S3_SEALS:
            self.verify_seal(fold)
        self.scoring_started = True


class S4LabelAccessGuard:
    """Process-scoped byte and metadata barrier for registered label-bearing inputs.

    An audit hook intercepts open/os.open, including generic hash/read helpers.
    Scoped stat/lstat interception additionally enforces the metadata embargo.
    No filesystem resolution or stat is performed while classifying paths.
    The hook becomes inert on exit; stat/lstat are restored even on failure.
    This is an operator workflow guard, not an adversarial filesystem sandbox.
    """

    def __init__(self, oracle_root: Path, s3_root: Path, source24: Path, source25: Path):
        self.oracle = OracleGuard(oracle_root)
        self.s3_root = s3_root
        self.source24, self.source25 = source24, source25
        self.label_gate_open = False
        self.preseal_label_access_count = 0
        self.first_byte_accesses: set[str] = set()
        self.events: list[str] = []
        self.enabled = False
        self._stat = os.stat
        self._lstat = os.lstat
        self._protected = {self._key(self.scored_path(fold)): fold for fold in S3_SEALS}
        self._protected[self._key(source24)] = "TRAIN24"
        self._protected[self._key(source25)] = "VALIDATION25"

    @staticmethod
    def _key(path: Any) -> str:
        return os.path.abspath(os.fsdecode(os.fspath(path)))

    def scored_path(self, fold: str) -> Path:
        require(fold in S3_SEALS, "UNREGISTERED_LABEL_ARTIFACT")
        return self.s3_root / fold / "scored-rows.jsonl"

    def _check(self, path: Any, *, byte_access: bool) -> None:
        if not self.enabled or isinstance(path, int):
            return
        name = self._protected.get(self._key(path))
        if name is None:
            return
        if name == "TRAIN24":
            self.oracle.verify_seal("fold_a")
            return
        if not self.label_gate_open:
            self.preseal_label_access_count += 1
            raise TemporalError("PRESEAL_LABEL_BEARING_ARTIFACT_ACCESS_FORBIDDEN")
        for fold in S3_SEALS:
            self.oracle.verify_seal(fold)
        if byte_access and name in S3_SEALS and name not in self.first_byte_accesses:
            self.first_byte_accesses.add(name)
            self.events.append("FIRST_S3_SCORED_ROWS_BYTE_ACCESS:" + name)

    def _audit(self, event: str, args: tuple[Any, ...]) -> None:
        if event == "open":
            self._check(args[0], byte_access=True)

    def __enter__(self) -> S4LabelAccessGuard:
        self.enabled = True
        sys.addaudithook(self._audit)

        def checked_stat(path: Any, *args: Any, **kwargs: Any) -> os.stat_result:
            self._check(path, byte_access=False)
            return self._stat(path, *args, **kwargs)

        def checked_lstat(path: Any, *args: Any, **kwargs: Any) -> os.stat_result:
            self._check(path, byte_access=False)
            return self._lstat(path, *args, **kwargs)

        os.stat = checked_stat
        os.lstat = checked_lstat
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.enabled = False
        os.stat, os.lstat = self._stat, self._lstat

    def open_label_gate(self) -> None:
        require(self.enabled and not self.label_gate_open, "LABEL_GATE_STATE_INVALID")
        for fold in S3_SEALS:
            self.oracle.verify_seal(fold)
        self.events.append("BOTH_ORACLE_FOLDS_VERIFIED")
        self.label_gate_open = True
        self.events.append("LABEL_GATE_OPENED")

    def capture_s3_identity(self, fold: str) -> dict[str, Any]:
        require(self.enabled and self.label_gate_open, "PRESEAL_LABEL_IDENTITY_FORBIDDEN")
        path = self.scored_path(fold)
        stat = path.stat()
        return dict(sha256=sha256(path), size_bytes=stat.st_size, mtime_ns=stat.st_mtime_ns)

    def read_s3_scored_rows(self, fold: str) -> list[dict[str, Any]]:
        require(self.enabled and self.label_gate_open, "PRESEAL_LABEL_PARSE_FORBIDDEN")
        rows: list[dict[str, Any]] = [
            json.loads(line) for line in self.scored_path(fold).read_text().splitlines()
        ]
        return rows


def complete_windows(rows: Sequence[Mapping[str, Any]]) -> list[list[Mapping[str, Any]]]:
    groups: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["season"], row["base_id"], row["forecast_origin"])].append(row)
    result = []
    for key in sorted(groups):
        group = sorted(groups[key], key=lambda r: int(r["lead_day"]))
        require(
            len(group) == 15 and [int(r["lead_day"]) for r in group] == list(range(15)),
            "INCOMPLETE_OR_DUPLICATE_H15_WINDOW",
        )
        origin = datetime.fromisoformat(key[2]).date()
        require(
            all(
                date.fromisoformat(r["target_date"]) == origin + timedelta(days=i)
                and r["actual_status"] in {"KNOWN_MAPPED_SUBTOTAL", "CONFIRMED_ZERO"}
                for i, r in enumerate(group)
            ),
            "H15_WINDOW_AUTHORITY_INVALID",
        )
        result.append(group)
    return result


def temporal_metrics(windows: Sequence[Sequence[Mapping[str, Any]]], model: str) -> dict[str, Any]:
    totals = {
        k: Decimal(0)
        for k in (
            "single_date",
            "single_quantity",
            "rolling7_date",
            "rolling7_quantity",
            "shape",
            "actual",
        )
    }
    bad = 0
    for group in windows:
        actual = [Decimal(r["actual_daily_kg"]) for r in group]
        predicted = [Decimal(r[model]) for r in group]
        require(all(v.is_finite() and v >= 0 for v in actual + predicted), "INVALID_CURVE_QUANTITY")
        canonical = score_curve(
            [
                dict(date=r["target_date"], new_quantity_kg=str(a))
                for r, a in zip(group, actual, strict=True)
            ],
            dict(
                daily_curve=[
                    dict(date=r["target_date"], predicted_quantity_kg=str(p))
                    for r, p in zip(group, predicted, strict=True)
                ]
            ),
        )
        for label, values in (("actual", actual), ("predicted", predicted)):
            single = max(range(15), key=lambda i: values[i])
            rolling = [sum(values[i : i + 7], Decimal(0)) for i in range(9)]
            start = max(range(9), key=lambda i: rolling[i])
            require(
                canonical[label]["single_day_peak"]["date"] == group[single]["target_date"]
                and canonical[label]["rolling_7day_peak"]["start_date"]
                == group[start]["target_date"],
                "CANONICAL_PEAK_PRECISION_OR_TIE_MISMATCH",
            )
        totals["single_date"] += Decimal(canonical["single_day_peak_date_error_days"])
        totals["rolling7_date"] += Decimal(canonical["rolling_7day_window_shift_days"])
        totals["single_quantity"] += abs(max(predicted) - max(actual))
        totals["rolling7_quantity"] += abs(
            max(sum(predicted[i : i + 7], Decimal(0)) for i in range(9))
            - max(sum(actual[i : i + 7], Decimal(0)) for i in range(9))
        )
        q, p = sum(actual, Decimal(0)), sum(predicted, Decimal(0))
        if q <= 0 or p <= 0:
            bad += 1
            require(canonical["shape_absolute_error_kg"] is None, "CANONICAL_SHAPE_MISMATCH")
        else:
            error = sum(
                (abs(v * q / p - a) for v, a in zip(predicted, actual, strict=True)), Decimal(0)
            )
            require(
                fixed(error) == canonical["shape_absolute_error_kg"], "CANONICAL_SHAPE_MISMATCH"
            )
            totals["shape"] += error
            totals["actual"] += q
    n = len(windows)
    result: dict[str, Any] = dict(
        window_count=n, shape_not_computable_window_count=bad, canonical_semantics_parity=True
    )
    for key in ("single_date", "single_quantity", "rolling7_date", "rolling7_quantity"):
        result[key + "_mae"] = str(totals[key] / n) if n else None
        result[key + "_absolute_error_sum"] = str(totals[key])
    result.update(
        shape_error=str(totals["shape"] / totals["actual"])
        if n and not bad and totals["actual"] > 0
        else None,
        shape_error_numerator=str(totals["shape"]),
        shape_actual_denominator=str(totals["actual"]),
    )
    return result


def metric_delta(reference: Mapping[str, Any], new: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: str(Decimal(new[key]) - Decimal(reference[key]))
        if new[key] is not None and reference[key] is not None
        else None
        for key in (
            "single_date_mae",
            "single_quantity_mae",
            "rolling7_date_mae",
            "rolling7_quantity_mae",
            "shape_error",
        )
        if key in reference and key in new
    }


def timing_gates(scopes: Mapping[str, Any]) -> tuple[dict[str, Any], str, str]:
    gates: dict[str, Any] = {}
    for family, model in (
        ("WEATHER_TIMING", "M1"),
        ("GDD_TIMING", "M2"),
        ("COMBINED_TIMING", "M3"),
    ):
        deltas = {s: metric_delta(scopes[s]["M0"], scopes[s][model]) for s in scopes}
        enough = all(scopes[s][model]["window_count"] > 0 for s in scopes)
        shape = all(
            scopes[s][model]["shape_not_computable_window_count"] == 0
            and scopes[s]["M0"]["shape_not_computable_window_count"] == 0
            for s in scopes
        )
        all_dates = enough and all(
            deltas[s][k] is not None and Decimal(deltas[s][k]) < 0
            for s in scopes
            for k in ("single_date_mae", "rolling7_date_mae")
        )
        combined = deltas["combined"]
        supported = (
            all_dates
            and shape
            and combined["shape_error"] is not None
            and Decimal(combined["shape_error"]) <= 0
        )
        not_supported = (
            enough
            and shape
            and all(
                combined[k] is not None and Decimal(combined[k]) >= 0
                for k in ("single_date_mae", "rolling7_date_mae")
            )
            and not all_dates
        )
        gates[family] = dict(
            model=model,
            deltas=deltas,
            every_fold_and_combined_dates_improve=all_dates,
            shape_computable=shape,
            sufficient_authority=enough,
            status="SUPPORTED"
            if supported
            else "NOT_SUPPORTED"
            if not_supported
            else "INCONCLUSIVE",
        )
    supported_models = [g["model"] for g in gates.values() if g["status"] == "SUPPORTED"]
    summary = (
        "SUPPORTED"
        if supported_models
        else "NOT_SUPPORTED"
        if all(g["status"] == "NOT_SUPPORTED" for g in gates.values())
        else "INCONCLUSIVE"
    )
    return (
        gates,
        summary,
        "MULTIPLE"
        if len(supported_models) > 1
        else supported_models[0]
        if supported_models
        else "NONE",
    )
