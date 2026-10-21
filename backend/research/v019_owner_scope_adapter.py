"""Versioned, label-free review of the Owner's SOURCE_002 research scope.

R1's historical 75/9 contract and synthetic entry remain untouched. This entry
only authenticates metadata; neither valid hashes nor Owner mapping decisions
enable prediction generation, scoring, formal C0, or strict PIT admission.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from backend.research import v019_real_phase_a_adapter as r1
from backend.research.v019_daily_curve import canonical_bytes

SCOPE_VERSION = "V0_19_SOURCE002_OWNER_RESEARCH_SCOPE_R1"
SOURCE_SHA256 = "fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a"
DECISION_SHA256 = "7d15f85752bc57e3facc4d912aa1d89e3c1ce7e61ee85c52b432cfc8af952bf2"
H7_SHA256 = "fc047941cda320d12f5b4bc913cf5585ccbcae508f73e976b557c83a8892abea"
H15_SHA256 = "699f75d7543bbe2ef9bd0c8c991ada3bf2d61bc0c9cea2fed02790f35b5e281f"
METADATA_SHA256 = "bc1248835055c2488f9d5fa29351ef3d3605f3c91b36539f4c236f1ca584e572"
BINDINGS = {
    "文山古木农场": ("base_ffdc1ebe359436aa3f0fa834", "砚山盘龙基地"),
    "文山喜古农场": ("base_ffdc1ebe359436aa3f0fa834", "砚山盘龙基地"),
    "文山马塘农场": ("base_ffdc1ebe359436aa3f0fa834", "砚山盘龙基地"),
    "大理巍山农场（WRM)": ("base_f10df3ac242e4dbbf6c20b98", "大理巍山基地"),
    "弥勒朋普农场（MYM）": ("base_c51783e2ec7c16bba447d64e", "弥勒朋普基地"),
}
EXCLUDED = frozenset({"嘉果莓森", "曲靖师宗农场", "格莱莓农场", "老挝巴松一场"})
ZERO_CHANGES = {
    "base_ffdc1ebe359436aa3f0fa834": 17,
    "base_f10df3ac242e4dbbf6c20b98": 14,
    "base_c51783e2ec7c16bba447d64e": 14,
}
COUNTS = {
    "matched_farms": 80,
    "research_excluded_farms": 4,
    "unresolved_in_research_scope": 0,
    "included_rows": 231634,
    "excluded_rows": 1535,
    "included_rows_through_2026_04_15": 230166,
}
LIMITATIONS = {
    "strict_pit": False,
    "physical_basis_equivalence": "NOT_PROVEN",
    "historical_area_known_at": "NOT_PROVEN",
    "retrospective_protocol_effective": False,
    "formally_admitted_c0_count": 0,
    "production_eligible": False,
    "global_v08_authority_changed": False,
}
DAY_FIELDS = frozenset(
    {
        "base_id",
        "date",
        "new_quantity_status",
        "new_completeness_status",
        "zero_applied",
        "partial_resolved",
        "source_row_count",
        "member_expected_count",
        "member_observed_count",
        "identity_unresolved_conflict",
        "authority_eligible_daily",
        "source_coverage_status",
    }
)


def boundary() -> dict[str, Any]:
    return {
        **LIMITATIONS,
        **COUNTS,
        "scope_version": SCOPE_VERSION,
        "experiment_type": "RETROSPECTIVE_REPLAY",
        "historical_status": "EXPOSED_HISTORICAL_BENCHMARK",
        "protocol_status": "PROPOSED_NOT_EFFECTIVE",
        "real_execution_available": False,
        "real_scoring_available": False,
        "origin_time_and_cutoff": "NOT_REGISTERED_DATE_ONLY_NOT_HISTORICAL_ISSUANCE",
        "exclusion_scope": "THIS_RESEARCH_ONLY_NOT_GLOBAL_IDENTITY_AUTHORITY",
    }


@dataclass(frozen=True)
class OwnerScopeInputPaths:
    profile: Path
    registry: Path
    h7: Path
    h15: Path
    metadata: Path


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError(reason)


def _decision() -> dict[str, Any]:
    return {
        "task_id": "V0_19_S3_SOURCE002_OWNER_MAPPING_DECISION_R1",
        "mapping_version": SCOPE_VERSION,
        "source_sha256": SOURCE_SHA256,
        "season": "2025-2026",
        "target_window": [str(r1.START), str(r1.END)],
        "include_exact_names": {k: v[1] for k, v in BINDINGS.items()},
        "exclude_research_only": sorted(EXCLUDED),
        "global_v08_authority_unchanged": True,
        "does_not_grant_prediction_or_scoring": True,
    }


def _validate_sources(profile: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    """Same frozen source contract as R1; no curve generation or fitting."""
    _require(
        set(profile)
        == {
            "available_bins",
            "fold_id",
            "missing_bin_policy",
            "profile_kg_per_mu_by_7_day_bin",
            "reference_id",
            "train_row_set_hash",
            "validation_labels_used",
        }
        and profile["fold_id"] == "B"
        and profile["reference_id"] == "AREA_NORMALIZED_SEASON_WEEK_MEDIAN_V1"
        and profile["validation_labels_used"] is False
        and profile["train_row_set_hash"]
        == "c8b2da43696071648ac8280569fc2e28d7fa4b987f0a63b9edaae22122cc717e"
        and profile["missing_bin_policy"] == "NEAREST_AVAILABLE_TRAIN_BIN_EARLIER_TIE"
        and profile["available_bins"] == list(range(42))
        and set(profile["profile_kg_per_mu_by_7_day_bin"]) == {str(i) for i in range(42)},
        "FROZEN_PROFILE_MISMATCH",
    )
    for value in profile["profile_kg_per_mu_by_7_day_bin"].values():
        _require(type(value) in (str, int, float), "PROFILE_VALUE_INVALID")
        d = Decimal(str(value))
        _require(d.is_finite() and d >= 0, "PROFILE_VALUE_INVALID")
    _require(
        set(registry) == {"bases", "enrichment_hashes", "hash", "source_hash", "version"}
        and registry["version"] == "BASE_REGISTRY_V1"
        and registry["source_hash"] == r1.SOURCE_AREA_SHA256
        and r1._compact_hash({k: v for k, v in registry.items() if k != "hash"})
        == registry["hash"],
        "FROZEN_REGISTRY_MISMATCH",
    )
    bases = {b["base_id"]: b for b in registry["bases"]}
    _require(len(registry["bases"]) == len(bases) == 39, "REGISTRY_BASE_MEMBERSHIP")
    for b in bases.values():
        d = Decimal(str(b["productive_area_mu"]))
        _require(d.is_finite() and d > 0 and b["active"] is True, "REGISTRY_AREA_INVALID")
    return bases


def _validate_scope(meta: dict[str, Any], bases: dict[str, Any]) -> dict[str, Any]:
    _require(
        set(meta)
        == {
            "scope_version",
            "source_sha256",
            "decision",
            "decision_sha256",
            "mapping",
            "bases",
            "days",
            "previous_day_statuses",
            "source_counts",
            "limitations",
        }
        and meta["scope_version"] == SCOPE_VERSION
        and meta["source_sha256"] == SOURCE_SHA256
        and meta["decision"] == _decision()
        and r1._hash(canonical_bytes(meta["decision"]))
        == meta["decision_sha256"]
        == DECISION_SHA256
        and canonical_bytes(meta["source_counts"]) == canonical_bytes(COUNTS)
        and canonical_bytes(meta["limitations"]) == canonical_bytes(LIMITATIONS),
        "OWNER_SCOPE_OR_LIMITATION_MISMATCH",
    )
    mapping = meta["mapping"]
    _require(len(mapping) == 84, "SOURCE_FARM_COUNT")
    names: set[str] = set()
    identities: set[str] = set()
    members: dict[str, list[dict[str, str]]] = defaultdict(list)
    reused = 0
    for r in mapping:
        _require(
            set(r)
            == {
                "season",
                "source_farm_label",
                "source_identity_sha256",
                "original_global_status",
                "original_base_id",
                "research_status",
                "research_base_id",
                "research_base_name",
                "owner_decision_sha256",
                "source_sha256",
            }
            and all(type(v) is str for v in r.values())
            and r["source_farm_label"] not in names
            and r["source_identity_sha256"] not in identities
            and bool(r1.HEX.fullmatch(r["source_identity_sha256"]))
            and r["season"] == "2025-2026"
            and r["source_sha256"] == SOURCE_SHA256
            and r["owner_decision_sha256"] == DECISION_SHA256,
            "MAPPING_IDENTITY_MISMATCH",
        )
        name, bid = r["source_farm_label"], r["research_base_id"]
        names.add(name)
        identities.add(r["source_identity_sha256"])
        if name in EXCLUDED:
            _require(
                r["research_status"] == "OWNER_RESEARCH_EXCLUDE_ONLY"
                and not bid
                and not r["research_base_name"]
                and r["original_global_status"] == "UNRESOLVED"
                and not r["original_base_id"],
                "RESEARCH_EXCLUSION_NOT_GLOBAL",
            )
            continue
        _require(
            bid in bases and r["research_base_name"] == bases[bid]["canonical_base_name"],
            "EXACT_REGISTRY_IDENTITY_REQUIRED",
        )
        if name in BINDINGS:
            _require(
                (bid, r["research_base_name"]) == BINDINGS[name]
                and r["research_status"] == "OWNER_RESEARCH_INCLUDE"
                and r["original_global_status"] == "UNRESOLVED"
                and not r["original_base_id"],
                "OWNER_BINDING_MISMATCH",
            )
        else:
            _require(
                r["research_status"] == "REUSE_FROZEN_ACCEPTED_IDENTITY"
                and r["original_base_id"] == bid
                and r["original_global_status"]
                in {
                    "EXACT",
                    "AUTHORIZED_ALIAS",
                    "HISTORICALLY_PROVEN_ALIAS",
                    "BUSINESS_CONFIRMED_MAPPING",
                    "BUSINESS_CONFIRMED_REASSIGNMENT",
                },
                "FROZEN_IDENTITY_CHANGED",
            )
            reused += 1
        members[bid].append(r)
    _require(
        set(BINDINGS) | EXCLUDED <= names and reused == 75 and set(members) == set(bases),
        "INCOMPLETE_RESEARCH_UNIVERSE",
    )
    bmeta = {b["base_id"]: b for b in meta["bases"]}
    _require(
        len(meta["bases"]) == len(bmeta) == 39 and set(bmeta) == set(bases),
        "BASE_METADATA_MEMBERSHIP",
    )
    for bid, b in bmeta.items():
        _require(
            set(b)
            == {
                "base_id",
                "base_name",
                "member_count",
                "member_identity_sha256",
                "historical_area_authority_row_sha256",
                "area_unit",
                "historical_area_known_at",
                "area_parity",
            }
            and b["base_name"] == bases[bid]["canonical_base_name"]
            and type(b["member_count"]) is int
            and b["member_count"] == len(members[bid])
            and b["member_identity_sha256"]
            == r1._hash(
                canonical_bytes(sorted(members[bid], key=lambda r: r["source_identity_sha256"]))
            )
            and bool(r1.HEX.fullmatch(b["historical_area_authority_row_sha256"]))
            and b["area_unit"] == "mu"
            and b["historical_area_known_at"] == "NOT_PROVEN"
            and b["area_parity"] is True,
            "BASE_MEMBERS_OR_AREA_MISMATCH",
        )
    return bmeta


def _validate_days(meta: dict[str, Any], bmeta: dict[str, Any]) -> dict[tuple[str, str], Any]:
    days = {}
    expected = {(bid, str(r1.START + timedelta(days=i))) for bid in bmeta for i in range(254)}
    counts: Counter[str] = Counter()
    for r in meta["days"]:
        _require(
            set(r) == DAY_FIELDS and all(type(v) is str for v in r.values()),
            "DAY_METADATA_NO_LABEL_FIELDS",
        )
        key = r["base_id"], r["date"]
        _require(key in expected and key not in days, "DAY_MEMBERSHIP_MISMATCH")
        n, observed, records = (
            int(r[k])
            for k in ("member_expected_count", "member_observed_count", "source_row_count")
        )
        zero = records == 0
        _require(
            n == bmeta[key[0]]["member_count"]
            and 0 <= observed <= n
            and records >= observed
            and (observed == 0) == zero
            and r["identity_unresolved_conflict"] == "false"
            and r["authority_eligible_daily"] == "true"
            and r["source_coverage_status"] == "VERIFIED_SEASON_SOURCE_HASH"
            and r["new_quantity_status"] == ("CONFIRMED_ZERO" if zero else "KNOWN_MAPPED_SUBTOTAL")
            and r["new_completeness_status"]
            == ("AUTHORIZED_ZERO" if zero else "COMPLETE_MAPPED_MEMBERS")
            and r["zero_applied"] == str(zero).lower()
            and r["partial_resolved"] == str(0 < observed < n).lower(),
            "DAY_AUTHORITY_INVALID",
        )
        days[key] = r
        counts[r["new_quantity_status"]] += 1
    _require(
        set(days) == expected and counts == {"CONFIRMED_ZERO": 3490, "KNOWN_MAPPED_SUBTOTAL": 6416},
        "BASE_DAY_RECONCILIATION_MISMATCH",
    )
    previous = {}
    changes: Counter[str] = Counter()
    old_counts: Counter[str] = Counter()
    for r in meta["previous_day_statuses"]:
        _require(set(r) == {"base_id", "date", "old_status"}, "PREVIOUS_DAY_SCHEMA")
        key = r["base_id"], r["date"]
        _require(
            key in days
            and key not in previous
            and r["old_status"] in {"CONFIRMED_ZERO", "KNOWN_MAPPED_SUBTOTAL"},
            "PREVIOUS_DAY_MEMBERSHIP",
        )
        previous[key] = r
        old_counts[r["old_status"]] += 1
        if r["old_status"] != days[key]["new_quantity_status"]:
            _require(r["old_status"] == "CONFIRMED_ZERO", "UNEXPECTED_OBSERVATION_REMOVAL")
            changes[key[0]] += 1
    _require(
        set(previous) == expected
        and changes == ZERO_CHANGES
        and old_counts == {"CONFIRMED_ZERO": 3535, "KNOWN_MAPPED_SUBTOTAL": 6371},
        "ZERO_CHANGE_RECONCILIATION_MISMATCH",
    )
    return days


def _candidate_hash(row: dict[str, str], b: dict[str, Any]) -> str:
    return r1._hash(
        canonical_bytes(
            {
                **{k: v for k, v in row.items() if k != "candidate_id"},
                "source_sha256": SOURCE_SHA256,
                "research_scope_decision_sha256": DECISION_SHA256,
                "base_members_sha256": b["member_identity_sha256"],
                "area_authority_row_sha256": b["historical_area_authority_row_sha256"],
            }
        )
    )


def _review(
    profile: dict[str, Any],
    registry: dict[str, Any],
    meta: dict[str, Any],
    h7: list[dict[str, str]],
    h15: list[dict[str, str]],
    support: r1.SupportProposal,
) -> dict[str, Any]:
    support.validate()
    bases = _validate_sources(profile, registry)
    bmeta = _validate_scope(meta, bases)
    days = _validate_days(meta, bmeta)
    for rows, horizon, count in ((h7, 7, 9672), (h15, 15, 9360)):
        expected = {
            (bid, str(r1.START - timedelta(days=1) + timedelta(days=i)))
            for bid in bases
            for i in range(255 - horizon)
        }
        _require(
            len(rows) == count
            and len({r["candidate_id"] for r in rows}) == count
            and {(r["base_id"], r["origin_date"]) for r in rows} == expected
            and rows == sorted(rows, key=lambda r: (r["base_id"], r["origin_date"])),
            "CANDIDATE_MEMBERSHIP_MISMATCH",
        )
        for r in rows:
            _require(
                set(r) == set(r1.FIELDS)
                and r["status"] == "C0_CANDIDATE_ONLY"
                and r["season"] == "2025-2026"
                and r["window"] == ("H7_PREFIX" if horizon == 7 else "H15_LOCAL"),
                "CANDIDATE_IDENTITY_MISMATCH",
            )
            origin, start, end = (
                date.fromisoformat(r[k]) for k in ("origin_date", "target_start", "target_end")
            )
            dates = [str(start + timedelta(days=i)) for i in range(horizon)]
            _require(
                start == origin + timedelta(days=1)
                and end == origin + timedelta(days=horizon)
                and r1.START <= start <= end <= r1.END
                and support.start <= start <= end <= support.end
                and r["target_dates_sha256"] == r1._hash(canonical_bytes(dates))
                and r["day_authority_sha256"]
                == r1._hash(canonical_bytes([days[r["base_id"], d] for d in dates]))
                and r["candidate_id"] == _candidate_hash(r, bmeta[r["base_id"]]),
                "CANDIDATE_DATE_OR_AUTHORITY_SEAL_MISMATCH",
            )
    return {
        **boundary(),
        "base_count": 39,
        "base_day_count": len(days),
        "observed_base_days": 6416,
        "authorized_zero_base_days": 3490,
        "zero_changes_by_base": dict(ZERO_CHANGES),
        "h7_candidate_count": len(h7),
        "h15_candidate_count": len(h15),
        "status": "VALIDATED_CANDIDATE_ONLY_EXECUTION_BLOCKED",
    }


def validate_owner_scope_inputs(
    paths: OwnerScopeInputPaths, *, support: r1.SupportProposal
) -> dict[str, Any]:
    """Bounded explicit, read-only metadata review; no labels, discovery or execution."""
    if type(paths) is not OwnerScopeInputPaths or type(support) is not r1.SupportProposal:
        raise ValueError("EXPLICIT_OWNER_INPUTS_AND_SUPPORT_REQUIRED")
    support.validate()
    specs = (
        (paths.profile, r1.PROFILE_SHA256, "reference-B.json"),
        (paths.registry, r1.REGISTRY_SHA256, "base-registry-v1.json"),
        (paths.h7, H7_SHA256, "h7-candidates.csv"),
        (paths.h15, H15_SHA256, "h15-candidates.csv"),
        (paths.metadata, METADATA_SHA256, "owner-scope-metadata-r2.json"),
    )
    _require(len({p for p, _, _ in specs}) == 5, "INPUT_PATHS_NOT_DISTINCT")
    raw = [r1._read_pinned(p, h, n) for p, h, n in specs]
    registry = r1._object(raw[1])
    _require(registry.get("hash") == r1.REGISTRY_PAYLOAD_HASH, "REGISTRY_PAYLOAD_MISMATCH")
    review = _review(
        r1._object(raw[0]),
        registry,
        r1._object(raw[4]),
        r1._candidate_rows(raw[2]),
        r1._candidate_rows(raw[3]),
        support,
    )
    body = {
        **review,
        "input_sha256": {n: h for _, h, n in specs},
        "support_proposal": {k: str(v) for k, v in asdict(support).items()},
    }
    return {**body, "review_sha256": r1._hash(canonical_bytes(body))}


# The real execution path remains the same unconditional refusal as R1.
generate_real_predictions = r1.generate_real_predictions
