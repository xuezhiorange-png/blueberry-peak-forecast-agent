"""Conservatively audit training-season source identity blockers for V0.8-S7.

This module creates a targeted identity-resolution overlay from already frozen
identity evidence. Candidate names, season transfer, and ``YES_ALL`` answers
without an explicit target never become accepted mappings.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

TRAINING_SEASONS = frozenset({"2023-2024", "2024-2025"})
ACCEPTED_RESOLUTION_BY_MAPPING_STATUS = {
    "EXACT": "ACCEPTED_EXACT",
    "AUTHORIZED_ALIAS": "ACCEPTED_AUTHORIZED_ALIAS",
    "HISTORICALLY_PROVEN_ALIAS": "ACCEPTED_HISTORICALLY_PROVEN_ALIAS",
    "BUSINESS_CONFIRMED_MAPPING": "ACCEPTED_BUSINESS_CONFIRMED_MAPPING",
    "BUSINESS_CONFIRMED_REASSIGNMENT": "ACCEPTED_BUSINESS_CONFIRMED_REASSIGNMENT",
}
HISTORICAL_ACCEPTED_MATCH_TYPES = {
    "EXACT": "ACCEPTED_EXACT",
    "AUTHORIZED_ALIAS": "ACCEPTED_AUTHORIZED_ALIAS",
    "HISTORICALLY_PROVEN_ALIAS": "ACCEPTED_HISTORICALLY_PROVEN_ALIAS",
}
EXPLICIT_PARENT_RELATION_STATUSES = {
    "AUTHORIZED_PARENT_MAPPING",
    "BUSINESS_CONFIRMED_PARENT_MAPPING",
}


class TrainingSourceIdentityClosureError(ValueError):
    """Raised when a frozen input cannot support a fail-closed S7 audit."""


@dataclass(frozen=True)
class IdentityResolution:
    status: str
    base_id: str = ""
    basis: str = ""
    evidence_ids: tuple[str, ...] = ()
    conflict_status: str = "NONE"


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _json_list(value: Any, *, field: str) -> list[Any]:
    if isinstance(value, list):
        result = value
    else:
        raw = _text(value)
        if not raw:
            return []
        try:
            result = json.loads(raw)
        except json.JSONDecodeError as error:
            raise TrainingSourceIdentityClosureError(f"INVALID_JSON_LIST:{field}") from error
    if not isinstance(result, list):
        raise TrainingSourceIdentityClosureError(f"INVALID_JSON_LIST:{field}")
    return result


def _base_ids(value: Any) -> tuple[str, ...]:
    if isinstance(value, (list, tuple, set, frozenset)):
        raw_values = value
    else:
        raw = _text(value)
        if not raw:
            return ()
        if raw.startswith("["):
            parsed = _json_list(raw, field="candidate_base_ids")
            raw_values = parsed
        else:
            raw_values = raw.split(";")
    if any(not isinstance(item, str) for item in raw_values):
        raise TrainingSourceIdentityClosureError("INVALID_BASE_ID_LIST")
    return tuple(sorted({_text(item) for item in raw_values if _text(item)}))


def _decimal(value: Any, *, field: str) -> Decimal:
    try:
        number = Decimal(_text(value) or "0")
    except (InvalidOperation, TypeError, ValueError) as error:
        raise TrainingSourceIdentityClosureError(f"INVALID_DECIMAL:{field}") from error
    if not number.is_finite():
        raise TrainingSourceIdentityClosureError(f"NONFINITE_DECIMAL:{field}")
    return number


def _decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    result = format(value, "f")
    return result.rstrip("0").rstrip(".") if "." in result else result


def _same_identity_key(
    row: Mapping[str, Any] | None, *, season: str, source_farm_label: str
) -> bool:
    return bool(
        row
        and _text(row.get("season")) == season
        and _text(row.get("source_farm_label")) == source_farm_label
    )


def _question_keys(group: Mapping[str, Any]) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for field in ("owned_label_keys", "unresolved_label_keys", "reference_label_keys"):
        for item in _json_list(group.get(field), field=field):
            if not isinstance(item, Mapping):
                raise TrainingSourceIdentityClosureError(f"INVALID_LABEL_KEY:{field}")
            season = _text(item.get("season"))
            farm = _text(item.get("source_farm_label"))
            if season and farm:
                keys.add((season, farm))
    return keys


def _explicit_business_targets(
    *,
    season: str,
    source_farm_label: str,
    decision_questions: str,
    decision_rows: Mapping[str, Mapping[str, Any]],
    decision_groups: Mapping[str, Mapping[str, Any]],
    base_name_to_id: Mapping[str, str],
) -> tuple[list[tuple[str, str, str]], str]:
    targets: list[tuple[str, str, str]] = []
    saw_yes_all = False
    for question in sorted(filter(None, (item.strip() for item in decision_questions.split(";")))):
        decision = decision_rows.get(question)
        group = decision_groups.get(question)
        if decision is None or group is None:
            continue
        if (season, source_farm_label) not in _question_keys(group):
            continue
        answer = _text(decision.get(f"decision_{season.replace('-', '_')}"))
        if not answer:
            continue
        if answer == "YES_ALL":
            saw_yes_all = True
            continue
        if answer == "YES_CANDIDATE":
            candidates = _base_ids(group.get("candidate_base_ids"))
            if len(candidates) == 1:
                targets.append((question, candidates[0], "BUSINESS_CONFIRMED_UNIQUE_CANDIDATE"))
            continue
        if answer.startswith("CORRECT_BASE:"):
            canonical_name = answer.removeprefix("CORRECT_BASE:").strip()
            target_id = base_name_to_id.get(canonical_name, "")
            if target_id:
                targets.append((question, target_id, "BUSINESS_CONFIRMED_EXPLICIT_BASE"))
            continue
    if targets:
        unique_targets = {target_id for _question, target_id, _basis in targets}
        if len(unique_targets) > 1:
            return [], "CONFLICTING_BUSINESS_DECISION_TARGETS"
        return targets, ""
    if saw_yes_all:
        return [], "BUSINESS_DECISION_YES_ALL_HAS_NO_EXPLICIT_TARGET"
    return [], ""


def resolve_source_identity(
    *,
    season: str,
    source_farm_label: str,
    candidate_base_ids: Sequence[str] | str,
    current_identity: Mapping[str, Any] | None = None,
    historical_identity: Mapping[str, Any] | None = None,
    source_subfarm_label: str = "",
    parent_relation: Mapping[str, Any] | None = None,
    decision_rows: Mapping[str, Mapping[str, Any]] | None = None,
    decision_groups: Mapping[str, Mapping[str, Any]] | None = None,
    base_name_to_id: Mapping[str, str] | None = None,
) -> IdentityResolution:
    """Resolve one exact season/farm identity only from existing authority.

    A single candidate is not authority. Historical mappings are reused only
    when the exact current key is absent; an explicit current unresolved row
    takes precedence and is not silently overwritten.
    """

    candidates = _base_ids(candidate_base_ids)
    if current_identity is not None and not _same_identity_key(
        current_identity, season=season, source_farm_label=source_farm_label
    ):
        current_identity = None
    if historical_identity is not None and not _same_identity_key(
        historical_identity, season=season, source_farm_label=source_farm_label
    ):
        historical_identity = None

    current_status = _text((current_identity or {}).get("mapping_status"))
    current_base = _text((current_identity or {}).get("canonical_base_id"))
    if current_status in ACCEPTED_RESOLUTION_BY_MAPPING_STATUS:
        if not current_base:
            return IdentityResolution(
                "CONFLICTING_EVIDENCE",
                basis="CURRENT_ACCEPTED_MAPPING_WITHOUT_BASE_ID",
                evidence_ids=(_text((current_identity or {}).get("identity_revision_id")),),
                conflict_status="ACCEPTED_MAPPING_MISSING_BASE_ID",
            )
        return IdentityResolution(
            ACCEPTED_RESOLUTION_BY_MAPPING_STATUS[current_status],
            base_id=current_base,
            basis="EXACT_SEASON_AND_SOURCE_FARM_LABEL_ONLY",
            evidence_ids=(_text((current_identity or {}).get("identity_revision_id")),),
        )
    if current_status == "CONFLICTING":
        return IdentityResolution(
            "CONFLICTING_EVIDENCE",
            basis="CURRENT_IDENTITY_AUTHORITY_CONFLICT",
            evidence_ids=(_text((current_identity or {}).get("identity_revision_id")),),
            conflict_status="CURRENT_IDENTITY_AUTHORITY_CONFLICT",
        )

    hist_status = _text((historical_identity or {}).get("mapping_status"))
    hist_match = _text((historical_identity or {}).get("match_type"))
    hist_base_values = _base_ids((historical_identity or {}).get("candidate_base_id"))
    hist_accepted = (
        hist_status == "ACCEPTED_FROZEN_IDENTITY_MAPPING"
        and _text((historical_identity or {}).get("decision")) == "ACCEPTED"
        and hist_match in HISTORICAL_ACCEPTED_MATCH_TYPES
        and len(hist_base_values) == 1
    )
    if hist_accepted and current_identity is not None:
        return IdentityResolution(
            "CONFLICTING_EVIDENCE",
            basis="CURRENT_AND_HISTORICAL_IDENTITY_AUTHORITY_DISAGREE_ON_ACCEPTANCE",
            evidence_ids=tuple(
                item
                for item in (
                    _text((current_identity or {}).get("identity_revision_id")),
                    _text((historical_identity or {}).get("evidence")),
                )
                if item
            ),
            conflict_status="CURRENT_UNRESOLVED_VS_HISTORICAL_ACCEPTED",
        )
    if hist_accepted:
        return IdentityResolution(
            HISTORICAL_ACCEPTED_MATCH_TYPES[hist_match],
            base_id=hist_base_values[0],
            basis="EXACT_SEASON_AND_SOURCE_FARM_LABEL_HISTORICAL_AUTHORITY",
            evidence_ids=(_text((historical_identity or {}).get("evidence")),),
        )

    decisions = decision_rows or {}
    groups = decision_groups or {}
    names = base_name_to_id or {}
    decision_questions = _text((current_identity or {}).get("decision_questions"))
    business_targets, business_error = _explicit_business_targets(
        season=season,
        source_farm_label=source_farm_label,
        decision_questions=decision_questions,
        decision_rows=decisions,
        decision_groups=groups,
        base_name_to_id=names,
    )
    if business_error == "CONFLICTING_BUSINESS_DECISION_TARGETS":
        return IdentityResolution(
            "CONFLICTING_EVIDENCE",
            basis=business_error,
            conflict_status=business_error,
        )
    if business_targets:
        _question, target_id, basis = business_targets[0]
        return IdentityResolution(
            "ACCEPTED_BUSINESS_CONFIRMED_MAPPING",
            base_id=target_id,
            basis=basis,
            evidence_ids=tuple(sorted({item[0] for item in business_targets})),
        )

    if (
        parent_relation is not None
        and _text(parent_relation.get("season")) == season
        and _text(parent_relation.get("source_farm_label")) == source_farm_label
        and _text(parent_relation.get("source_subfarm_label")) == source_subfarm_label
        and _text(parent_relation.get("parent_relation_status"))
        in EXPLICIT_PARENT_RELATION_STATUSES
    ):
        parent_base = _text(parent_relation.get("canonical_base_id_from_farm_identity"))
        quantity_base = _text(parent_relation.get("quantity_assignment_base_id"))
        if parent_base and parent_base == quantity_base:
            return IdentityResolution(
                "ACCEPTED_MEMBER_TO_BASE_MAPPING",
                base_id=parent_base,
                basis="EXPLICIT_PARENT_BASE_MAPPING",
                evidence_ids=(_text(parent_relation.get("relation_revision_id")),),
            )

    if business_error == "BUSINESS_DECISION_YES_ALL_HAS_NO_EXPLICIT_TARGET":
        basis = business_error
    elif (
        parent_relation is not None
        and _text(parent_relation.get("season")) == season
        and _text(parent_relation.get("source_farm_label")) == source_farm_label
        and _text(parent_relation.get("source_subfarm_label")) == source_subfarm_label
        and _text(parent_relation.get("parent_relation_status")) == "SOURCE_REPORTED_PARENT"
    ):
        basis = "SOURCE_REPORTED_PARENT_WITHOUT_CANONICAL_BASE_ASSIGNMENT"
    else:
        basis = "NO_AUTHORIZED_EXACT_SEASON_IDENTITY_EVIDENCE"

    return IdentityResolution(
        "UNRESOLVED_MULTIPLE_BASES" if len(candidates) > 1 else "UNRESOLVED_NO_EVIDENCE",
        basis=basis,
        conflict_status="NO_AUTHORITY_CONFLICT"
        if len(candidates) <= 1
        else "MULTIPLE_CANDIDATE_BASES",
    )


def build_target_base_seasons(
    *,
    s6_eligibility_rows: Sequence[Mapping[str, Any]],
    quality_rows: Sequence[Mapping[str, Any]],
    completeness_rows: Sequence[Mapping[str, Any]],
    unresolved_rows: Sequence[Mapping[str, Any]],
    training_seasons: frozenset[str] = TRAINING_SEASONS,
    expected_target_count: int = 41,
) -> list[dict[str, str]]:
    """Select only S6-ineligible training Base-seasons with identity blockers."""

    quality_by_key = {
        (_text(row.get("base_id")), _text(row.get("season"))): row for row in quality_rows
    }
    completeness_by_key = {
        (_text(row.get("base_id")), _text(row.get("season"))): row for row in completeness_rows
    }
    eligibility_by_key: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in s6_eligibility_rows:
        key = (_text(row.get("base_id")), _text(row.get("season")))
        if not all(key) or key in eligibility_by_key:
            raise TrainingSourceIdentityClosureError("DUPLICATE_OR_MISSING_ELIGIBILITY_KEY")
        eligibility_by_key[key] = row

    unresolved_by_key: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in unresolved_rows:
        season = _text(row.get("season"))
        for candidate_id in _base_ids(row.get("candidate_base_ids")):
            key = (candidate_id, season)
            if key in eligibility_by_key and season in training_seasons:
                unresolved_by_key[key].append(row)

    result: list[dict[str, str]] = []
    for key in sorted(eligibility_by_key):
        base_id, season = key
        eligibility = eligibility_by_key[key]
        if (
            season not in training_seasons
            or _text(eligibility.get("strict_training_eligible")).lower() != "false"
        ):
            continue
        quality = quality_by_key.get(key)
        completeness = completeness_by_key.get(key)
        if quality is None or completeness is None:
            raise TrainingSourceIdentityClosureError("TARGET_QUALITY_OR_COMPLETENESS_MISSING")
        identity_status = _text(quality.get("source_identity_status"))
        if identity_status not in {
            "NO_ACCEPTED_SOURCE_ROWS",
            "IDENTITY_CONFIRMED_WITH_UNRESOLVED_CANDIDATES",
            "IDENTITY_UNRESOLVED",
        }:
            raise TrainingSourceIdentityClosureError("NON_IDENTITY_TRAINING_BLOCKER_IN_TARGET")
        labels = {
            _text(row.get("source_farm_label"))
            for row in unresolved_by_key.get(key, [])
            if _text(row.get("source_farm_label"))
        }
        candidate_quantity = sum(
            (
                _decimal(
                    row.get("business_window_quantity_kg"), field="business_window_quantity_kg"
                )
                for row in unresolved_by_key.get(key, [])
            ),
            Decimal(0),
        )
        blockers = _text(completeness.get("blocker_codes"))
        result.append(
            {
                "base_id": base_id,
                "base_name": _text(eligibility.get("base_name")),
                "season": season,
                "s6_strict_training_eligible": "false",
                "s6_blocker_codes": blockers,
                "no_accepted_source_identity": str(
                    identity_status == "NO_ACCEPTED_SOURCE_ROWS"
                ).lower(),
                "unresolved_source_identity_conflict": str(
                    identity_status
                    in {
                        "IDENTITY_CONFIRMED_WITH_UNRESOLVED_CANDIDATES",
                        "IDENTITY_UNRESOLVED",
                    }
                ).lower(),
                "partial_days_present": str(
                    int(_text(completeness.get("partial_known_subtotal_day_count")) or "0") > 0
                ).lower(),
                "unresolved_source_label_count": str(len(labels)),
                "unresolved_quantity_kg": _decimal_text(candidate_quantity),
                "target_for_s7": "true",
            }
        )
    if len(result) != expected_target_count:
        raise TrainingSourceIdentityClosureError("TARGET_BASE_SEASON_COUNT_MISMATCH")
    return result


def validate_eligibility_preservation(
    *,
    before_rows: Sequence[Mapping[str, Any]],
    after_rows: Sequence[Mapping[str, Any]],
    training_seasons: frozenset[str] = TRAINING_SEASONS,
    oot_season: str = "2025-2026",
) -> dict[str, int]:
    """Verify unchanged cohorts do not lose any already-eligible identity."""

    def eligible_keys(
        rows: Sequence[Mapping[str, Any]], season_scope: set[str], field: str
    ) -> set[tuple[str, str]]:
        return {
            (_text(row.get("base_id")), _text(row.get("season")))
            for row in rows
            if _text(row.get("season")) in season_scope and _text(row.get(field)).lower() == "true"
        }

    before_train = eligible_keys(before_rows, set(training_seasons), "strict_training_eligible")
    after_train = eligible_keys(after_rows, set(training_seasons), "strict_training_eligible")
    before_oot = eligible_keys(before_rows, {oot_season}, "strict_oot_eligible")
    after_oot = eligible_keys(after_rows, {oot_season}, "strict_oot_eligible")
    return {
        "previously_eligible_regression_count": len(before_train - after_train),
        "oot_eligibility_regression_count": len(before_oot - after_oot),
        "strict_training_eligible_before": len(before_train),
        "strict_training_eligible_after": len(after_train),
        "strict_oot_eligible_before": len(before_oot),
        "strict_oot_eligible_after": len(after_oot),
    }
