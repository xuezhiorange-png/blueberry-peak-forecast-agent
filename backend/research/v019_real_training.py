"""Frozen V0.8 sources -> exact S4 training bins -> two temporal fits.

Only the explicit local Owner CLI loads real inputs. No network, discovery,
production integration, synthetic relabel switch or new approval system.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import defaultdict
from datetime import date, timedelta
from decimal import Context, Decimal, localcontext
from pathlib import Path
from typing import Any

from backend.app.forecast_quality.operational_peak import _daily_row, load_frozen_reference_profile
from backend.research import v019_accuracy_models as models
from backend.research import v019_owner_replay as owner
from backend.research.v019_daily_curve import (
    BASELINE_POLICY,
    CurveInput,
    DailyKg,
    _micro,
    generate_candidate,
)
from backend.research.v019_synthetic_validation import digest

TASK = "V0_19_S4_REAL_TRAINING_AND_FOUR_MODEL_EVALUATION_R1"
SEASONS = ("2023-2024", "2024-2025")
SOURCES = {
    "2023-2024": "8fa003b4abdea0b0bd9c50a9fbd619ad15ea5c9a2e790faa5e5b3353a2a01d20",
    "2024-2025": "f4ffba4b10a3129c768871bc5f3dfa2845534bc0e7eb04e166ba97211fa92dd6",
}
S6_DIR = "v0-8-s6-no-record-zero-season-total-rebuild-r1-final-r2"
S1_DIR = "v0-8-cross-season-identity-authority-r1"
AREA_DIR = "v0-8-s4-user-confirmed-three-season-area-authority-r1"
PROFILE_DIR = "s3-known-support-no-weather-baseline-r1/replay-1"
PINS = dict(
    [
        (
            f"{S6_DIR}/artifact-manifest.json",
            "d23ed98beccb98b11d7ca43800d19a6491deed6ff705513531a927139bab7cd7",
        ),
        (
            f"{S6_DIR}/strict-training-eligibility-r2.csv",
            "22ea38dac6afa917677fb87d555a3f53b1894096ec257ae4310aad96d121b494",
        ),
        (
            f"{S6_DIR}/base-season-quantity-completeness-r2.csv",
            "9e8ea52f1257b347ec462259f0bddd74fcc3890299744f467dc027d04a5430ed",
        ),
        (
            f"{S6_DIR}/canonical-daily-harvest-zero-semantics-overlay-r1.csv",
            "d0f94ea143cc44c555cc3299a8ea0b3073ab96173fa7927b53104a45c904a8e0",
        ),
        (
            f"{S1_DIR}/artifact-manifest.json",
            "acc3104a3dcef8224905a45b1f7f3d74d9b5ac36916d3e377acd8310742644d6",
        ),
        (
            f"{S1_DIR}/canonical-base-daily-ledger-r1.csv",
            "be948dee9a7789e90ee60fc42277e8e978ecdc897c519686f3cc36d798d5bd75",
        ),
        (
            f"{S1_DIR}/cross-season-base-identity-authority-r1.csv",
            "7054c4168fac8342022527ab3ba017eb8e0b2c57409eb0e6dba166e6f181c61b",
        ),
        (
            f"{AREA_DIR}/artifact-manifest.json",
            "a52a8342693eb9ce1731e2487e8c23fcf029c198d3fe66193552e4d7f58a27ff",
        ),
        (
            f"{AREA_DIR}/three-season-historical-area-authority-r1.csv",
            "40a0e1e6a96cb9d612c51fe7790c03bf9bf7ffe9f865f96d710e4d8c2e96d4d9",
        ),
        ("historical-primary-source-replay-r1/23~24.xls", SOURCES["2023-2024"]),
        ("historical-primary-source-replay-r1/24~25.xls", SOURCES["2024-2025"]),
        (
            "shape-r3/input_manifest.json",
            "506b901fe467bd8dd1717293054ba40f6892df34620552d5af44a6566381a5b6",
        ),
        (
            f"{PROFILE_DIR}/artifact-manifest.json",
            "5a6b1e574d0477a057f6f42b0db9a37ddf1213d645d8a0cb6175fc83e5c6dfeb",
        ),
        (
            f"{PROFILE_DIR}/reference-A.json",
            "49a28e4b2d4571352ba4574d0d018b56082a12920977a48cb5c13c1eea9d1562",
        ),
        (
            f"{PROFILE_DIR}/reference-B.json",
            "a0a5cbc3c3ca5bd2b0b8860328eee73840499b38da89c11a104f83d02fd77c5b",
        ),
        (
            "base-registry-s1-r2/base-registry-v1.json",
            "502c73fecdf68e91e4aa35982a2207d224204390597eaf59420ebd1101539904",
        ),
    ]
)


def _csv(raw: bytes) -> list[dict[str, str]]:
    # Mixed authority files are hash-checked bytewise. Target-season quantities
    # are NEVER selected or converted to numbers by the training adapter.
    return [
        r
        for r in csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
        if r.get("season") in SEASONS
    ]


def _index(
    rows: list[dict[str, str]], keys: tuple[str, ...]
) -> dict[tuple[str, ...], dict[str, str]]:
    out = {}
    for r in rows:
        key = tuple(r[k] for k in keys)
        if key in out:
            raise ValueError("DUPLICATE_AUTHORITY_KEY:" + str(key))
        out[key] = r
    return out


def _authorized_zero(r: dict[str, str], z: dict[str, str], kg: Decimal) -> bool:
    if kg or int(z["source_row_count"]):
        return False
    if z["zero_basis"] == "EXPLICIT_BUSINESS_RULE_NO_HARVEST_RECORD_MEANS_ZERO":
        return True
    return (
        z["resolution_reason"] == "UNCHANGED_EXISTING_AUTHORITY"
        and r["quantity_status"] == "CONFIRMED_ZERO"
        and r["quantity_completeness_status"] == "AUTHORIZED_ZERO"
        and r["confirmed_zero_basis"] == "REUSED_UNCHANGED_MEMBERSHIP_ZERO"
        and Decimal(r["mapped_observed_subtotal_kg"]) == 0
    )


def admit(
    ledger: list[dict[str, str]],
    overlay: list[dict[str, str]],
    identity: list[dict[str, str]],
    areas: list[dict[str, str]],
    eligibility: list[dict[str, str]],
    completeness: list[dict[str, str]],
    registry: dict[str, Any],
    physical: dict[str, dict[str, str]],
) -> dict[str, Any]:
    """Exact-key join; deterministic pre-outcome rules, with every exclusion retained."""
    ld = _index(ledger, ("base_id", "season", "date"))
    ov = _index(overlay, ("base_id", "season", "date"))
    ar = _index(areas, ("base_id", "season"))
    comp = _index(completeness, ("base_id", "season"))
    reg = {b["base_id"]: b for b in registry["bases"]}
    groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for r in identity:
        if r["mapping_status"] in {"EXACT", "AUTHORIZED_ALIAS", "BUSINESS_CONFIRMED_MAPPING"}:
            groups[r["canonical_base_id"], r["season"]].append(r)
    inventory, daily = [], []
    for e in sorted(eligibility, key=lambda e: (e["season"], e["base_id"])):
        if e["season"] not in SEASONS:
            continue
        bid, season = e["base_id"], e["season"]
        item: dict[str, Any] = {
            "base_id": bid,
            "season": season,
            "s6_candidate": e["strict_training_eligible"] == "true",
        }
        reason = None
        accepted = []
        try:
            if not item["s6_candidate"]:
                raise ValueError("S6_NOT_ELIGIBLE:" + e["exclusion_reason"])
            c, area = comp[bid, season], ar[bid, season]
            members = sorted(groups[bid, season], key=lambda r: r["source_identity_sha256"])
            source = physical.get(season)
            if (
                not source
                or source.get("event") != "RECORDED_INBOUND_WEIGHT"
                or source.get("unit") != "kg"
            ):
                raise ValueError("PHYSICAL_EVENT_OR_UNIT_UNIDENTIFIED")
            if source.get("sha256") != SOURCES[season]:
                raise ValueError("RAW_SOURCE_IDENTITY")
            if not members or any(r["raw_source_sha256"] != SOURCES[season] for r in members):
                raise ValueError("MEMBER_SOURCE_IDENTITY")
            if len({r["source_identity_sha256"] for r in members}) != len(members):
                raise ValueError("DUPLICATE_MEMBER_IDENTITY")
            area_mu = Decimal(area["historical_actual_area_mu"])
            if (
                area["authority_eligible"] != "true"
                or not area_mu.is_finite()
                or area_mu <= 0
                or Decimal(reg[bid]["productive_area_mu"]) != area_mu
                or Decimal(e["area_mu"]) != area_mu
                or area["identity_authority_sha256"]
                != PINS[
                    "v0-8-cross-season-identity-authority-r1/cross-season-base-identity-authority-r1.csv"
                ]
            ):
                raise ValueError("AREA_OR_BASE_IDENTITY")
            start, end = (
                date.fromisoformat(c["season_start_date"]),
                date.fromisoformat(c["season_end_date"]),
            )
            if (
                start != date(int(season[:4]), 7, 1)
                or end != date(int(season[:4]) + 1, 4, 15)
                or c["daily_curve_evaluation_eligible"] != "true"
                or c["source_identity_status"] != "IDENTITY_CONFIRMED"
                or c["member_coverage_complete"] != "true"
                or int(c["unresolved_member_label_count"]) != 0
                or int(c["accepted_source_label_count"]) != len(members)
            ):
                raise ValueError("SEASON_CALENDAR_OR_MEMBER_COMPLETENESS")
            dates = [str(start + timedelta(days=i)) for i in range((end - start).days + 1)]
            if {d for b, s, d in ld if (b, s) == (bid, season)} != set(dates):
                raise ValueError("MISSING_OR_EXTRA_LEDGER_DATE")
            for day in dates:
                r, z = ld[bid, season, day], ov[bid, season, day]
                if (
                    r["source_sha256"] != SOURCES[season]
                    or z["authority_eligible_daily"] != "true"
                    or z["identity_unresolved_conflict"] != "false"
                    or int(z["member_expected_count"]) != len(members)
                    or z["new_completeness_status"]
                    not in {"AUTHORIZED_ZERO", "COMPLETE_MAPPED_MEMBERS"}
                    or z["new_quantity_status"] not in {"CONFIRMED_ZERO", "KNOWN_MAPPED_SUBTOTAL"}
                    or z["source_coverage_status"] != "VERIFIED_SEASON_SOURCE_HASH"
                ):
                    raise ValueError("DAILY_COMPLETENESS_OR_SOURCE")
                kg = Decimal(z["new_quantity_kg"])
                _micro(kg)
                if z["new_quantity_status"] == "CONFIRMED_ZERO":
                    if not _authorized_zero(r, z, kg):
                        raise ValueError("UNAUTHORIZED_ZERO")
                elif kg != Decimal(r["mapped_observed_subtotal_kg"]):
                    raise ValueError("OBSERVED_QUANTITY_CHANGED")
                row = {
                    "base_id": bid,
                    "season": season,
                    "date": day,
                    "kg": str(kg),
                    "area_mu": str(area_mu),
                    "raw_source_sha256": SOURCES[season],
                    "physical_event": source["event"],
                    "status": z["new_quantity_status"],
                    "members_sha256": digest([m["source_identity_sha256"] for m in members]),
                    "authority_row_sha256": digest({"ledger": r, "overlay": z, "area": area}),
                    "historical_known_at": "NOT_PROVEN",
                }
                accepted.append({**row, "row_sha256": digest(row)})
            if sum((Decimal(r["kg"]) for r in accepted), Decimal(0)) != Decimal(
                c["complete_daily_sum_kg"]
            ):
                raise ValueError("SEASON_TOTAL_RECONCILIATION")
            item.update(
                start=str(start),
                end=str(end),
                area_mu=str(area_mu),
                members=[m["source_identity_sha256"] for m in members],
                member_identity_records=[
                    {
                        k: m[k]
                        for k in (
                            "source_identity_sha256",
                            "source_farm_label",
                            "raw_source_sha256",
                            "canonical_base_id",
                            "season",
                        )
                    }
                    for m in members
                ],
                physical_basis=source,
            )
        except (ValueError, KeyError, ArithmeticError) as exc:
            reason = str(exc)
            accepted = []
        item.update(
            status="REJECT" if reason else "ADMIT",
            reason=reason,
            normalized_daily_sha256=digest(accepted),
            daily_count=len(accepted),
        )
        inventory.append(item)
        daily.extend(accepted)
    body = {
        "inventory": inventory,
        "daily": daily,
        "daily_sha256": digest(daily),
        "candidate_base_seasons": sum(r["s6_candidate"] for r in inventory),
        "admitted_base_seasons": sum(r["status"] == "ADMIT" for r in inventory),
        "admitted_unique_bases": len({r["base_id"] for r in inventory if r["status"] == "ADMIT"}),
        "units": {"quantity": "kg", "area": "mu", "calendar": "Asia/Shanghai business date"},
        "physical_basis": "CONDITIONAL_CROSS_SOURCE_RECORDED_INBOUND_WEIGHT",
        "strict_pit": False,
        "evaluation_labels_selected": False,
    }
    return {**body, "sha256": digest(body)}


def load_training(root: Path) -> dict[str, Any]:
    raw = {name: owner.read_bytes(root / name, sha) for name, sha in PINS.items()}

    def rows(suffix: str) -> list[dict[str, str]]:
        return _csv(next(v for k, v in raw.items() if k.endswith("/" + suffix)))

    source_metadata = json.loads(raw["shape-r3/input_manifest.json"])
    physical = {}
    for season, sha in SOURCES.items():
        s = next(s for s in source_metadata["sources"] if s["sha256"] == sha)
        if s["quantity_column"] == "入库公斤数" and s["quantity_unit"] == "KG":
            physical[season] = {
                "event": "RECORDED_INBOUND_WEIGHT",
                "unit": "kg",
                "sha256": sha,
                "field": "入库公斤数",
                "equivalence_to_source002": "NOT_PROVEN",
            }
    registry = json.loads(raw["base-registry-s1-r2/base-registry-v1.json"], parse_float=str)
    body = admit(
        rows("canonical-base-daily-ledger-r1.csv"),
        rows("canonical-daily-harvest-zero-semantics-overlay-r1.csv"),
        rows("cross-season-base-identity-authority-r1.csv"),
        rows("three-season-historical-area-authority-r1.csv"),
        rows("strict-training-eligibility-r2.csv"),
        rows("base-season-quantity-completeness-r2.csv"),
        registry,
        physical,
    )
    if body["candidate_base_seasons"] != 37:
        raise ValueError("FROZEN_37_BASE_SEASON_CANDIDATES_CHANGED")
    return {
        "source_root": str(root),
        "admission": body,
        "input_pins": PINS,
        "registry": registry,
        "profiles": {
            f: json.loads(
                raw[f"s3-known-support-no-weather-baseline-r1/replay-1/reference-{f}.json"],
                parse_float=str,
            )
            for f in ("A", "B")
        },
    }


def make_bins(
    daily: list[dict[str, Any]], profile: dict[str, Any], seasons: tuple[str, ...]
) -> tuple[tuple[models.TrainingBin, ...], list[dict[str, Any]]]:
    reference = load_frozen_reference_profile(profile)
    grouped: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for r in daily:
        if r["season"] in seasons:
            start = date(int(r["season"][:4]), 7, 1)
            grouped[
                r["base_id"], r["season"], (date.fromisoformat(r["date"]) - start).days // 7
            ].append(r)
    bins, inventory = [], []
    with localcontext(Context(prec=50)):
        for (bid, season, number), rr in sorted(grouped.items()):
            rr.sort(key=lambda r: r["date"])
            start = date(int(season[:4]), 7, 1)
            days = [date.fromisoformat(r["date"]) for r in rr]
            record = {
                "base_id": bid,
                "season": season,
                "bin": number,
                "dates": [str(d) for d in days],
                "daily_rows_sha256": digest(rr),
                "profile_sha256": digest(profile),
                "area_mu": rr[0]["area_mu"],
                "raw_source_sha256": SOURCES[season],
                "reason": None
                if len(rr) == 7
                and days[0] == start + timedelta(days=7 * number)
                and days == [days[0] + timedelta(days=i) for i in range(7)]
                else "PARTIAL_SEASON_BIN_NOT_TRAINED",
            }
            record["sha256"] = digest(record)
            inventory.append(record)
            if record["reason"]:
                continue
            area = Decimal(rr[0]["area_mu"])
            bins.append(
                models.TrainingBin(
                    bid,
                    start,
                    days[0],
                    area,
                    tuple(_daily_row(d, start, area, reference).predicted_kg for d in days),
                    tuple(Decimal(r["kg"]) for r in rr),
                    record["sha256"],
                )
            )
    return tuple(bins), inventory


def fit_verified(bundle: dict[str, Any], experiment: str) -> dict[str, Any]:
    if (
        not isinstance(bundle.get("source_root"), str)
        or not Path(bundle["source_root"]).is_absolute()
        or bundle != load_training(Path(bundle["source_root"]))
    ):
        raise ValueError("VERIFIED_TRAINING_FILES_REQUIRED")
    admission = bundle["admission"]
    if (
        digest({k: v for k, v in admission.items() if k != "sha256"}) != admission["sha256"]
        or bundle["input_pins"] != PINS
        or experiment not in {"A", "B"}
    ):
        raise ValueError("VERIFIED_TRAINING_BUNDLE_REQUIRED")
    seasons = SEASONS[:1] if experiment == "A" else SEASONS
    bins, inventory = make_bins(admission["daily"], bundle["profiles"][experiment], seasons)
    fitted = models._fit_bins(
        bins, evaluation_start=date(2024 if experiment == "A" else 2025, 7, 1), data_class="REAL"
    )
    body = {
        "experiment": experiment,
        "training_seasons": list(seasons),
        "training_admission_sha256": admission["sha256"],
        "input_pins_sha256": digest(PINS),
        "fitted": fitted,
        "fit_implementation_sha256": digest(
            {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (Path(__file__), Path(models.__file__))
            }
        ),
        "bin_inventory": inventory,
        "normalized_training_rows": [
            {
                "base_id": b.base_id,
                "season_start": str(b.season_start),
                "start": str(b.start),
                "area_mu": str(b.area_mu),
                "baseline": [str(v) for v in b.baseline],
                "actual": [str(v) for v in b.actual],
                "source_sha256": b.source_sha256,
            }
            for b in bins
        ],
    }
    return {**body, "sha256": digest(body)}


def curves(
    profile: dict[str, Any], registry: dict[str, Any], base_ids: set[str], start: date, end: date
) -> dict[str, dict[str, tuple[DailyKg, ...]]]:
    reference = load_frozen_reference_profile(profile)
    result: dict[str, dict[str, tuple[DailyKg, ...]]] = {"baseline": {}, "S2": {}}
    for b in registry["bases"]:
        if b["base_id"] not in base_ids:
            continue
        area = Decimal(b["productive_area_mu"])
        with localcontext(Context(prec=50)):
            rr = tuple(
                DailyKg(
                    start + timedelta(days=i),
                    _daily_row(start + timedelta(days=i), start, area, reference).predicted_kg,
                )
                for i in range((end - start).days + 1)
            )
        result["baseline"][b["base_id"]] = rr
        result["S2"][b["base_id"]] = generate_candidate(
            CurveInput(start, start, end, rr, digest(profile), BASELINE_POLICY, "Asia/Shanghai")
        ).rows
    return result


def predict_verified(
    bundle: dict[str, Any], fitted: dict[str, Any], baseline: dict[str, Any]
) -> dict[str, Any]:
    if not fitted or fitted != fit_verified(bundle, fitted.get("experiment", "")):
        raise ValueError("FIT_SOURCE_OR_PARAMETER_DRIFT")
    result = {k: dict(v) for k, v in baseline.items()}
    result.update({m: {} for m in ("VOLUME_CALIBRATION_V1", "VOLUME_TIMING_V1")})
    failures = []
    start = date.fromisoformat(fitted["fitted"]["evaluation_start"])
    for bid, rr in baseline["baseline"].items():
        try:
            for m, values in models._predict_curve(fitted["fitted"], bid, start, rr).items():
                result[m][bid] = values
        except (ValueError, ArithmeticError) as exc:
            failures.append({"base_id": bid, "reason": type(exc).__name__ + ":" + str(exc)})
    return {"curves": result, "failures": failures}
