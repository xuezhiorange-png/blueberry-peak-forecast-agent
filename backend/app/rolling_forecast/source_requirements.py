"""A fillable evidence checklist, never a source authorization or verification."""

from typing import Literal

from pydantic import Field, model_validator

from backend.app.rolling_forecast.schemas import Contract, Hash, Name

CATEGORIES = {
    "SOURCE_IDENTITY": ("来源身份", "source_system, accountable_owner, source_version, season"),
    "PHYSICAL_BASIS": (
        "业务口径",
        "event, weight_field, raw/gross/net, unit, equivalence_evidence",
    ),
    "BUSINESS_DATE": ("日期口径", "business_date, timezone, cross_day_rule"),
    "BASE_MEMBERSHIP": ("基地映射", "base_id, season/farm/subfarm/variety_keys, mapping_version"),
    "GRADE_POLICY": ("品级规则", "accepted_grades, excluded_grades, rule_version, evidence"),
    "REVISION_WINNERS": ("修订规则", "logical_id, revision_id, winner, void/conflict_rule"),
    "TIME_AUTHORITY": ("时间证明", "source_recorded_at, server_ingested_at, visible_at, proof"),
    "COMPLETENESS": ("完整性", "daily_member_coverage, confirmed_zero, missing/partial, known_at"),
    "MODEL_TARGET": ("模型关联", "frozen_fit_sha256, training_target_basis, equivalence_evidence"),
    "LABEL_AUTHORITY": ("独立标签", "label_source_identity, dates, maturity, separate_permission"),
}


class EvidenceRequirement(Contract):
    category: Name
    title: Name
    required_fields: str = Field(min_length=1, max_length=2000)
    accountable_owner: str | None = None
    declared_details: str | None = Field(default=None, max_length=4000)
    evidence_reference: str | None = None
    evidence_sha256: Hash | None = None
    claim_status: Literal["NOT_PROVIDED", "SUPPLIED_NOT_VERIFIED", "SYNTHETIC_ONLY"] = (
        "NOT_PROVIDED"
    )


class SourceRequirements(Contract):
    schema_version: Literal["INBOUND_SOURCE_REQUIREMENTS_V1"] = "INBOUND_SOURCE_REQUIREMENTS_V1"
    purpose: Literal["PREPARATION_NOT_AUTHORIZATION"] = "PREPARATION_NOT_AUTHORIZATION"
    real_source_read_authorized: Literal[False] = False
    real_source_enrolled: Literal[False] = False
    items: tuple[EvidenceRequirement, ...]

    @model_validator(mode="after")
    def exact_requirements(self) -> "SourceRequirements":
        if len(self.items) != len(CATEGORIES) or {v.category for v in self.items} != set(
            CATEGORIES
        ):
            raise ValueError("SOURCE_REQUIREMENTS_CATEGORY_MISMATCH")
        return self


def template() -> SourceRequirements:
    return SourceRequirements(
        items=tuple(
            EvidenceRequirement(category=k, title=v[0], required_fields=v[1])
            for k, v in CATEGORIES.items()
        )
    )


def public_checklist(value: SourceRequirements) -> list[dict[str, str | bool]]:
    # Do not publish private evidence paths, names or user-entered details.
    return [
        {
            "category": i.category,
            "title": CATEGORIES[i.category][0],
            "required_fields": CATEGORIES[i.category][1],
            "materials_supplied": bool(i.evidence_sha256 and i.evidence_reference),
            "status": "PENDING_SOURCE_AUTHORITY",
        }
        for i in value.items
    ]
