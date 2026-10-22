"""One full-support calculation per Base, compact windows, durable Phase A seal."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
from decimal import Context, Decimal, localcontext
from pathlib import Path
from typing import Any

from backend.app.forecast_quality.operational_peak import (
    BASELINE_ID,
    _daily_row,
    load_frozen_reference_profile,
)
from backend.research import v019_research_authorization as auth
from backend.research import v019_research_cohort as cohort
from backend.research import v019_retrospective_engine as old_engine
from backend.research import v019_retrospective_scoring as old_scoring
from backend.research.v019_daily_curve import CurveInput, DailyKg, generate_candidate, method_config
from backend.research.v019_synthetic_validation import digest


def curve_rows(raw: list[dict[str, str]]) -> tuple[DailyKg, ...]:
    result = tuple(DailyKg(date.fromisoformat(r["date"]), Decimal(r["kg"])) for r in raw)
    if any(set(r) != {"date", "kg"} for r in raw):
        raise ValueError("CURVE_SCHEMA")
    return result


def _serialize(rows: tuple[DailyKg, ...]) -> list[dict[str, str]]:
    return [{"date": str(r.day), "kg": str(r.kg)} for r in rows]


def prediction_hash(content: dict[str, Any]) -> str:
    """Numerical/source identity independent of input locations and run clocks."""
    return digest(
        {
            k: content[k]
            for k in (
                "data_class",
                "formal_c0",
                "input_identities",
                "support",
                "config",
                "code_sha256",
                "restrictions",
                "full_curves",
                "members",
                "base_failures",
                "failures",
                "full_support_calculation_count",
                "labels_read",
                "real_prediction_generated",
            )
        }
    )


def calculate(
    profile_payload: dict[str, Any], registry: dict[str, Any], members: list[dict[str, Any]]
) -> dict[str, Any]:
    """Label-free deterministic core; no file, clock, environment or approval I/O."""
    profile = load_frozen_reference_profile(profile_payload)
    start, end = cohort.SUPPORT.start, cohort.SUPPORT.end
    calendar = tuple(start + timedelta(days=i) for i in range((end - start).days + 1))
    admitted_bases = {m["base_id"] for m in members if m["admission_status"] == "ADMIT"}
    execution_bases = [b for b in registry["bases"] if b["base_id"] in admitted_bases]
    full, base_failures = {}, {}
    with localcontext(Context(prec=50)):
        for b in sorted(execution_bases, key=lambda b: b["base_id"]):
            bid = b["base_id"]
            try:
                area = Decimal(str(b["productive_area_mu"]))
                old = tuple(
                    DailyKg(d, _daily_row(d, start, area, profile).predicted_kg) for d in calendar
                )
                new = generate_candidate(
                    CurveInput(
                        start,
                        start,
                        end,
                        old,
                        digest(profile_payload),
                        BASELINE_ID,
                        "Asia/Shanghai",
                    )
                ).rows
                full[bid] = {"baseline": _serialize(old), "candidate": _serialize(new)}
            except (ValueError, ArithmeticError) as exc:
                base_failures[bid] = "CALCULATION_FAILED:" + type(exc).__name__
        lookups = {
            bid: {side: {r["date"]: r for r in rr} for side, rr in v.items()}
            for bid, v in full.items()
        }
        results = []
        for m in members:
            reason = (
                "C0_NOT_ADMITTED:" + str(m["failure_reason"])
                if m["admission_status"] != "ADMIT"
                else base_failures.get(m["base_id"])
            )
            r: dict[str, Any] = {
                "candidate_id": m["candidate_id"],
                "base_id": m["base_id"],
                "window": m["window"],
                "status": "FAILED" if reason else "COMPLETED",
                "failure_reason": reason,
            }
            if not reason:
                first, last = (date.fromisoformat(m[k]) for k in ("target_start", "target_end"))
                dates = [str(first + timedelta(days=i)) for i in range((last - first).days + 1)]
                for side in ("baseline", "candidate"):
                    rr = [lookups[m["base_id"]][side][d] for d in dates]
                    view = old_scoring._view(curve_rows(rr))
                    r[side] = {
                        "window_hash": digest(rr),
                        "single_day_peak": view["single_day_peak"],
                        "rolling7_peak": view["rolling7_peak"],
                    }
            results.append(r)
    return {
        "full_curves": full,
        "members": results,
        "base_failures": base_failures,
        "full_support_calculation_count": len(execution_bases),
        "failures": [r for r in results if r["failure_reason"]],
    }


def run_a(
    manifest_path: Path,
    manifest_sha256: str,
    formal: dict[str, Any],
    ctx: auth.Context,
    grants: object,
) -> dict[str, Any]:
    auth.require(ctx, grants, "IMPLEMENTATION_REVIEW", auth.code_identity())
    auth.require(ctx, grants, "A_EXECUTION", formal["sha256"])
    f = auth.unseal(formal)
    if cohort.formalize(f["candidate"], f["review"], ctx, grants) != formal:
        raise ValueError("FORMAL_C0_SEAL_MISMATCH")
    inputs = cohort.load_inputs(manifest_path, ctx, grants, manifest_sha256)
    if cohort.candidates(inputs, ctx) != f["candidate"]:
        raise ValueError("APPROVED_C0_INPUT_DRIFT")
    members = auth.unseal(f["review"])["members"]
    profile, registry = cohort.numerical_inputs(inputs)
    content = {
        "data_class": ctx.mode,
        "formal_c0": formal,
        "manifest_identity": {"manifest_path": str(manifest_path), "sha256": manifest_sha256},
        "input_manifest": inputs.manifest,
        "input_manifest_utf8": inputs.manifest_utf8,
        "input_snapshots_utf8": inputs.raw_files,
        "day_authorities": inputs.metadata["days"],
        "input_identities": f["candidate"]["payload"]["inputs"],
        "profile": profile,
        "registry": registry,
        "support": inputs.manifest["support"],
        "config": method_config(),
        "code_sha256": auth.code_identity(),
        "restrictions": auth.restrictions(),
        **calculate(profile, registry, members),
        "labels_read": False,
        "real_prediction_generated": ctx.mode == "REAL",
    }
    auth.require(ctx, grants, "A_EXECUTION", formal["sha256"])
    return auth.sealed(
        {
            "content": content,
            "content_sha256": digest(content),
            "prediction_sha256": prediction_hash(content),
            "executed_at": auth.now(),
            "historical_issued_at": None,
            "grant_evidence": deepcopy(grants),
            "trust_identity": digest(auth.roots(ctx)),
        }
    )


def verify_a(value: dict[str, Any], ctx: auth.Context) -> dict[str, Any]:
    p = auth.unseal(value)
    content: dict[str, Any] = p["content"]
    if (
        content["data_class"] != ctx.mode
        or p["trust_identity"] != digest(auth.roots(ctx))
        or content["code_sha256"] != auth.code_identity()
        or p["content_sha256"] != digest(content)
        or p["prediction_sha256"] != prediction_hash(content)
        or p["historical_issued_at"] is not None
        or content["restrictions"] != auth.restrictions()
        or content["labels_read"] is not False
        or content["config"] != method_config()
        or content["support"] != ["2025-07-01", "2026-04-15"]
    ):
        raise ValueError("A_SCOPE_CODE_CONFIG_OR_CONTENT_MISMATCH")
    executed = auth.aware(p["executed_at"])
    if executed > auth.aware(auth.now()):
        raise ValueError("FUTURE_EXECUTION_TIME")
    formal = content["formal_c0"]
    f = auth.unseal(formal)
    if cohort.formalize(f["candidate"], f["review"], ctx, p["grant_evidence"]) != formal:
        raise ValueError("A_FORMAL_C0_INVALID")
    auth.require(ctx, p["grant_evidence"], "A_EXECUTION", formal["sha256"], at=p["executed_at"])
    auth.require(
        ctx, p["grant_evidence"], "IMPLEMENTATION_REVIEW", auth.code_identity(), at=p["executed_at"]
    )
    auth.require(
        ctx,
        p["grant_evidence"],
        "A_INPUT_READ",
        digest(content["manifest_identity"]),
        at=p["executed_at"],
    )
    if content["input_identities"] != f["candidate"]["payload"]["inputs"]:
        raise ValueError("A_INPUT_IDENTITY_DRIFT")
    inputs = cohort.from_snapshot(
        content["input_manifest"],
        content["input_snapshots_utf8"],
        ctx,
        content["input_manifest_utf8"],
        content["manifest_identity"]["sha256"],
    )
    profile, registry = cohort.numerical_inputs(inputs)
    if (
        cohort.candidates(inputs, ctx) != f["candidate"]
        or profile != content["profile"]
        or registry != content["registry"]
        or inputs.metadata["days"] != content["day_authorities"]
    ):
        raise ValueError("A_SNAPSHOT_C0_PROFILE_REGISTRY_OR_DAY_DRIFT")
    expected = calculate(
        content["profile"], content["registry"], auth.unseal(f["review"])["members"]
    )
    if any(content[k] != v for k, v in expected.items()):
        raise ValueError("A_NUMERICAL_RECOMPUTATION_MISMATCH")
    return content


def write_artifacts(
    output: Path, files: dict[str, bytes], *, ctx: auth.Context, phase: str
) -> None:
    auth.roots(ctx)
    if ctx.mode == "SYNTHETIC":
        # Preserve the existing synthetic writer and its truthful false flags.
        old_engine._write_bundle(output, files)
        return
    import os

    from backend.research.v019_daily_curve import canonical_bytes
    from backend.research.v019_real_phase_a_adapter import _hash

    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    manifest = {
        "data_class": ctx.mode,
        "phase": phase,
        "completed_at": auth.now(),
        "file_sha256": {n: _hash(b) for n, b in files.items()},
        "real_prediction_generated": phase == "stage-a",
        "real_scoring_performed": phase == "stage-b",
    }
    for name, raw in {**files, "manifest.json": canonical_bytes(manifest)}.items():
        if Path(name).name != name:
            raise ValueError("ARTIFACT_FILENAME_REQUIRED")
        fd = os.open(output / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(raw)
