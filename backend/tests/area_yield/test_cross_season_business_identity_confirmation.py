from decimal import Decimal

from scripts.package_cross_season_business_identity_confirmation import (
    _aggregate_selected,
    attach_model_impact,
    build_business_relation_groups,
    select_confirmation_groups,
)


def _farm(
    season: str,
    label: str,
    status: str,
    base_id: str,
    quantity: str,
    business_quantity: str | None = None,
) -> dict[str, str]:
    return {
        "season": season,
        "source_farm_label": label,
        "raw_row_count": "2",
        "observed_day_count": "2",
        "first_date": f"{season[:4]}-08-01",
        "last_date": f"{season[:4]}-08-02",
        "quantity_kg": quantity,
        "business_window_quantity_kg": business_quantity or quantity,
        "business_window_observed_day_count": "2",
        "current_mapping_status": status,
        "current_match_type": status,
        "current_candidate_base_id": base_id,
        "current_canonical_base_name": "Base One" if base_id == "base-1" else "",
        "mapping_authority": "FROZEN_TEST_AUTHORITY",
        "mapping_evidence": "fixture evidence",
    }


def _issue(
    issue_id: str,
    season: str,
    label: str = "",
    subfarm: str = "",
    problem: str = "Accepted or unresolved source-member evidence changed.",
    priority: str = "P1_HIGH",
) -> dict[str, str]:
    return {
        "issue_id": issue_id,
        "priority": priority,
        "season": season,
        "source_label": label,
        "source_subfarm": subfarm,
        "quantity_kg": "0",
        "current_base": "Base One",
        "current_mapping_type": "EXACT",
        "problem": problem,
        "evidence": "fixture",
        "recommended_question": "",
        "business_decision": "",
    }


def _fixture() -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    farms = [
        _farm("2023-2024", "Alias Farm", "AUTHORIZED_ALIAS", "base-1", "100", "90"),
        _farm("2024-2025", "Alias Farm", "AUTHORIZED_ALIAS", "base-1", "200", "180"),
        _farm("2023-2024", "Ambiguous Farm", "UNRESOLVED", "base-1;base-2", "300"),
        _farm("2025-2026", "No Candidate Farm", "UNRESOLVED", "", "400"),
        _farm("2023-2024", "建水南庄基地", "AUTHORIZED_ALIAS", "base-1", "50"),
        _farm("2024-2025", "建水岔科基地", "UNRESOLVED", "base-1", "60"),
        _farm("2023-2024", "Parent A", "EXACT", "base-1", "700"),
        _farm("2023-2024", "Parent B", "EXACT", "base-2", "800"),
        _farm("2024-2025", "元江甘庄农场", "EXACT", "base-1", "900"),
        _farm("2024-2025", "新平扬武农场", "EXACT", "base-1", "901"),
        _farm("2025-2026", "盈江联农带农", "EXACT", "base-2", "902"),
        _farm("2025-2026", "砚山回龙农场", "EXACT", "base-1", "903"),
        _farm("2025-2026", "回龙中心实验站", "EXACT", "base-1", "904"),
    ]
    identity = [
        {"season": "2023-2024", "source_farm_label": "Parent A", "source_subfarm_label": "Shared"},
        {"season": "2023-2024", "source_farm_label": "Parent B", "source_subfarm_label": "Shared"},
    ]
    issues = [
        _issue("i-1", "2023-2024", "Alias Farm"),
        _issue("i-2", "2023-2024", "Alias Farm", problem="Reference-area yield ratio flagged."),
        _issue("i-3", "2024-2025", "Alias Farm"),
        _issue("i-4", "2023-2024", "Ambiguous Farm", problem="No accepted season-scoped mapping."),
        _issue(
            "i-5", "2025-2026", "No Candidate Farm", problem="No accepted season-scoped mapping."
        ),
        _issue("i-6", "2023-2024", "建水南庄基地"),
        _issue("i-7", "2024-2025", "建水岔科基地", problem="No accepted season-scoped mapping."),
        _issue(
            "i-8",
            "2023-2024",
            subfarm="Shared",
            problem="Same subfarm text appears under multiple source farm parents.",
        ),
        _issue(
            "i-12",
            "2023-2024",
            "Parent A",
            problem=(
                "Only 2 distinct in-window observed days; season-total coverage is not established."
            ),
        ),
        _issue(
            "i-9",
            "2024-2025",
            "元江甘庄农场",
            problem="Task-mandated high-risk review YUANJIANG_GANZHUANG_YANGWU.",
        ),
        _issue(
            "i-10",
            "2025-2026",
            "盈江联农带农",
            problem="Task-mandated high-risk review TENGCHONG_DEHONG_YINGJIANG.",
        ),
        _issue(
            "i-11",
            "2025-2026",
            "砚山回龙农场",
            problem="Task-mandated high-risk review YANSHAN_HUILONG_CENTER_STATION.",
        ),
    ]
    return issues, farms, identity


def test_exact_label_and_base_grouping_is_deterministic_and_issue_complete() -> None:
    issues, farms, identity = _fixture()
    first = build_business_relation_groups(issues, farms, identity, [])
    second = build_business_relation_groups(issues, farms, identity, [])

    assert [row["group_id"] for row in first] == [row["group_id"] for row in second]
    attached = [issue_id for group in first for issue_id in group["covered_issue_ids"]]
    assert sorted(attached) == sorted(issue["issue_id"] for issue in issues)
    assert len(attached) == len(set(attached))

    alias = next(group for group in first if group["source_labels"] == {"Alias Farm"})
    assert alias["seasons"] == {"2023-2024", "2024-2025"}
    assert alias["mapped_kg_at_risk"] == Decimal("300")
    assert alias["business_window_mapped_kg_at_risk"] == Decimal("270")
    assert alias["priority_band"] == "BAND_A_CURRENT_MAPPING_RISK"


def test_mandatory_composite_group_preserves_exact_label_lineage() -> None:
    issues, farms, identity = _fixture()
    groups = build_business_relation_groups(issues, farms, identity, [])

    group = next(row for row in groups if row["mandatory_group_id"] == "JIANSHUI_CHAKE_NANZHUANG")
    assert {"建水南庄基地", "建水岔科基地"}.issubset(group["source_labels"])
    assert {"i-6", "i-7"}.issubset(group["covered_issue_ids"])
    assert group["mapped_kg_at_risk"] == Decimal("50")
    assert group["unresolved_kg_potentially_recoverable"] == Decimal("60")


def test_reused_subfarm_relation_is_secondary_and_has_no_additive_kg_ownership() -> None:
    issues, farms, identity = _fixture()
    groups = build_business_relation_groups(issues, farms, identity, [])

    group = next(row for row in groups if row["relation_type"] == "REUSED_SUBFARM_PARENT_REVIEW")
    assert group["source_labels"] == {"Parent A", "Parent B"}
    assert group["related_parent_group_ids"]
    assert group["quantity_ownership"] == "SUPPORTING_REFERENCE_NON_ADDITIVE"
    assert group["owned_label_keys"] == set()
    assert group["reference_raw_kg"] == Decimal("1500")
    assert group["mapped_kg_at_risk"] == Decimal("0")
    assert group["priority_band"] == "BAND_C_CROSS_SEASON_STRUCTURE"


def test_model_impact_uses_exact_base_season_scope() -> None:
    issues, farms, identity = _fixture()
    groups = build_business_relation_groups(issues, farms, identity, [])
    group = next(row for row in groups if row["source_labels"] == {"Alias Farm"})
    attach_model_impact(
        group,
        prior_history_keys={("base-1", "2023-2024")},
        validation_label_keys={("base-1", "2024-2025")},
        ab_comparison_keys={("base-1", "2023-2024"), ("base-1", "2024-2025")},
    )

    assert group["used_in_frozen_prior_history"] is True
    assert group["used_in_v07_validation_labels"] is True
    assert group["used_in_v07_ab_comparison"] is True
    assert (
        group["model_impact_evidence_status"]
        == "S1_R2_AUTHORITY_MATCH;S3_BASE_SEASON_SCOPE_ONLY_SOURCE_LABEL_MEMBERSHIP_NOT_PROVEN"
    )


def test_selection_includes_mandatory_groups_and_caps_without_merging_relations() -> None:
    issues, farms, identity = _fixture()
    groups = build_business_relation_groups(issues, farms, identity, [])
    # Synthetic distinct unresolved relationships exercise selection ordering.
    for index in range(50):
        row = _farm(
            "2023-2024",
            f"Unresolved {index:02}",
            "UNRESOLVED",
            "base-1",
            str(1000 - index),
        )
        groups.extend(
            build_business_relation_groups(
                [
                    _issue(
                        f"extra-{index}",
                        "2023-2024",
                        row["source_farm_label"],
                        problem="No accepted season-scoped mapping.",
                    )
                ],
                [row],
                [],
                [],
            )
        )

    selected = select_confirmation_groups(groups, minimum=20, maximum=40)
    assert 20 <= len(selected) <= 40
    mandatory = {group["mandatory_group_id"] for group in selected if group["mandatory_group_id"]}
    assert "JIANSHUI_CHAKE_NANZHUANG" in mandatory
    assert all(group["business_decision_prefilled"] is False for group in selected)
    assert len({group["group_id"] for group in selected}) == len(selected)


def test_shortlist_rollup_deduplicates_related_parent_label_kg() -> None:
    issues, farms, identity = _fixture()
    groups = build_business_relation_groups(issues, farms, identity, [])
    parent_group = next(group for group in groups if group["source_labels"] == {"Parent A"})
    reused = next(
        group for group in groups if group["relation_type"] == "REUSED_SUBFARM_PARENT_REVIEW"
    )

    owned = set(parent_group["owned_label_keys"])
    secondary = set(reused["reference_label_keys"])
    union = owned | secondary
    quantity_by_key = {
        (row["season"], row["source_farm_label"]): Decimal(row["quantity_kg"]) for row in farms
    }
    assert sum((quantity_by_key[key] for key in union), Decimal(0)) == Decimal("1500")
    assert len(union) == 2


def test_multi_season_issue_is_an_exact_reference_relation_not_a_positional_pairing() -> None:
    issues, farms, identity = _fixture()
    issues.append(
        _issue(
            "i-13",
            "2023-2024;2024-2025",
            "Alias Farm;Other Exact Name",
            problem="Accepted or unresolved source-member evidence changed.",
        )
    )
    farms.append(_farm("2024-2025", "Other Exact Name", "EXACT", "base-2", "250"))

    groups = build_business_relation_groups(issues, farms, identity, [])
    relation = next(group for group in groups if "i-13" in group["covered_issue_ids"])

    assert relation["explicit_relation_flag"] is True
    assert relation["quantity_ownership"] == "SUPPORTING_REFERENCE_NON_ADDITIVE"
    assert relation["owned_label_keys"] == set()
    assert relation["reference_label_keys"] == {
        ("2023-2024", "Alias Farm"),
        ("2024-2025", "Alias Farm"),
        ("2024-2025", "Other Exact Name"),
    }
    assert relation["mapped_kg_at_risk"] == Decimal("550")
    assert relation["member_change_flag"] is True


def test_selected_reference_groups_roll_up_kg_by_unique_identity_key() -> None:
    farms = [
        _farm("2023-2024", "Mapped A", "EXACT", "base-1", "10"),
        _farm("2023-2024", "Unresolved B", "UNRESOLVED", "", "28634123.590"),
        _farm("2023-2024", "Unresolved C", "UNRESOLVED", "", "0"),
    ]
    issues = [
        _issue(
            "overlap-1",
            "2023-2024",
            "Mapped A;Unresolved B",
            problem="Accepted or unresolved source-member evidence changed.",
        ),
        _issue(
            "overlap-2",
            "2023-2024",
            "Mapped A;Unresolved C",
            problem="Accepted or unresolved source-member evidence changed.",
        ),
    ]
    groups = build_business_relation_groups(issues, farms, [], [])
    farm_by_key = {(row["season"], row["source_farm_label"]): row for row in farms}

    totals = _aggregate_selected(groups, groups, farm_by_key)

    assert totals["selected_mapped_kg_at_risk"] == Decimal("10")
    assert totals["selected_unresolved_kg"] == Decimal("28634123.590")
