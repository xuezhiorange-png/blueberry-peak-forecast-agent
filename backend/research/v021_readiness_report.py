"""V0_21 S4: execute existing synthetic preparers and report their separate states.

Pure calculation and rendering: no files, network, database, fitting or prediction
generation. Label inputs are accepted only after the existing S3 prediction seal.
"""

from __future__ import annotations

import copy
import html
import json
import re
from collections import Counter
from dataclasses import dataclass, replace
from typing import Any, Literal

from pydantic import ValidationError

from backend.research import v021_cycle_features as cycle
from backend.research import v021_evaluation_readiness as evaluation
from backend.research import v021_structure_scenarios as structure

Record = dict[str, Any]
S2_SCENARIOS = (
    "UNCHANGED",
    "AREA_INCREASE",
    "AREA_DECREASE",
    "ASYNCHRONOUS_AREA_CHANGE",
    "VARIETY_REPLACEMENT",
    "REPLANT",
    "DENSITY_CHANGE",
    "MIXED_PRODUCTION_SYSTEMS",
    "UNPROVEN_CONTINUITY",
    "CONFLICTING_EFFECTIVE_INTERVALS",
    "ZERO_PREVIOUS_AREA",
    "MISSING_AREA",
    "UNIT_MISMATCH",
    "SAME_NAME_DIFFERENT_ENTITY",
    "BUSINESS_EXAMPLE",
)
S3_SCENARIOS = (
    "COMPLETE",
    "INVALID_REMAINING",
    "PEAK_TIE",
    "SHORT_5",
    "SHORT_10",
    "MISSING_DAY",
    "DUPLICATE_DAY",
    "NEGATIVE_KG",
    "INVALID_KG",
    "ZERO_ACTUAL",
    "LATE_SOURCE",
    "LATE_ISSUANCE",
    "IMMATURE_LABELS",
    "DAILY_TOTAL_CANCELLATION",
    "COMMON_COHORT_FAILURES",
    "IMPROVED",
    "WORSENED",
    "BASIS_MISMATCH",
    "MEMBER_MISMATCH",
    "LABEL_CONFLICT",
    "UNKNOWN_CALENDAR_END",
    "PREFIX_MISMATCH",
)
GAPS = (
    (
        "MEMBER_IDENTITY",
        "真实地块与完整成员身份权威",
        "Base/Farm/Subfarm/Plot/Variety/Season/制度的精确业务键与责任人证明",
    ),
    ("CONTINUITY", "跨季连续性证明", "跨季实体、成员、株群关系；同名不能证明连续"),
    ("AREA", "面积口径及生效期权威", "种植/投产/有效面积分别提供亩、版本、有效期和来源"),
    ("CYCLE_EVENTS", "周期起点和农事事件来源", "每季显式起点、主剪枝、计划/实际事件与观测方法"),
    ("COHORT_DENSITY", "换苗、株数与密度测量", "旧新株群、测量日期、株数、对应面积与测量方法"),
    (
        "CLOCKS",
        "独立来源时钟证明",
        "observed/recorded/known/ingested 时间独立证明，日精度不冒充严格 PIT",
    ),
    (
        "ISSUANCE",
        "Origin、cutoff 和预测版本",
        "预注册业务时区、范围、模型/fit、发行版本和可信发行时刻",
    ),
    (
        "PHYSICAL_BASIS",
        "入库重量口径与单位",
        "RECORDED_INBOUND_WEIGHT 的事件定义、kg、净毛重及来源关系",
    ),
    ("LABELS", "独立成熟逐日标签", "完整日期、成员覆盖、成熟时间、修订 winner、冲突与缺日账本"),
    ("MODEL_IDENTITY", "模型及训练范围身份", "固定模型、训练截止、参数配置和训练/评价成员分离"),
    ("AUTHORIZATION", "真实读取与独立实验授权", "后续真实读取、模型实验和独立标签评分分别授权"),
)
FAIR_CONDITIONS = (
    "事前冻结 comparison_family、C0、成员、日历、origin/cutoff 和预测发行版本。",
    "比较双方使用同一目标、同一物理量、同日期以及每指标完全相同的共同样本 Cm。",
    "时间顺序训练、跨季验证，数据支持时实施基地留出；不随机拆分相邻日。",
    "先封存预测，再通过独立接口打开完整且合法成熟的标签。",
    "完整产季、声明剩余产季和 H7/H15 分开；结构性零不能证明峰时能力。",
    "保留失败、退化、无稳定收益和 MIXED；重叠 origin 不视为独立统计样本。",
    "这些是后续研究条件，本版不训练、不开展真实实验，不宣称农艺因果效果。",
)


class Case(cycle.Contract):
    dataset_id: str
    stage: Literal["S1", "S2", "S3"]
    scenario_id: str


@dataclass(frozen=True)
class Prepared:
    spec: Case
    inputs: Record
    s1: Record | None = None
    s2: Record | None = None
    registration: Record | None = None
    seal: Record | None = None
    rejection: str | None = None


def _synthetic(value: Record | None) -> None:
    if value is not None and value.get("data_class") != "SYNTHETIC_TEST_FIXTURE":
        raise ValueError("SYNTHETIC_ONLY")


def _reason(error: ValueError) -> str:
    if isinstance(error, ValidationError):
        return "INVALID_INPUT_SCHEMA"
    text = str(error)
    return text if re.fullmatch(r"[A-Z][A-Z0-9_:]{0,159}", text) else "UPSTREAM_INPUT_REJECTED"


def prepare_case(
    spec: Record,
    package: Record,
    declarations: Record,
    structure_declarations: Record | None = None,
    protocol: Record | None = None,
) -> Prepared:
    """Recompute S1/S2 and register S3 without accepting any labels or predictions."""
    request = Case.model_validate(spec)
    for value in (package, declarations, structure_declarations, protocol):
        _synthetic(value)
    p = Prepared(request, dict(package=copy.deepcopy(package), cycles=copy.deepcopy(declarations)))
    try:
        p = replace(p, s1=cycle.prepare(package, declarations))
        if request.stage == "S1":
            return p
        if structure_declarations is None:
            return replace(p, rejection="MISSING_STRUCTURE_INPUT")
        p.inputs["structure"] = copy.deepcopy(structure_declarations)
        assert p.s1 is not None
        p = replace(p, s2=structure.prepare(p.s1, structure_declarations))
        assert p.s2 is not None
        if request.stage == "S2":
            if request.scenario_id not in {s["scenario_id"] for s in p.s2["scenario_results"]}:
                raise ValueError("SCENARIO_IDENTITY_MISMATCH")
            return p
        if protocol is None:
            return replace(p, rejection="MISSING_EVALUATION_PROTOCOL")
        p.inputs["protocol"] = copy.deepcopy(protocol)
        assert p.s1 is not None
        return replace(p, registration=evaluation.register(p.s1, p.s2, protocol))
    except ValueError as exc:
        return replace(p, rejection=_reason(exc))


def seal_case(prepared: Prepared, predictions: Record | None) -> Prepared:
    """Thin S3 A wrapper; labels are not in this interface."""
    _synthetic(predictions)
    if prepared.rejection:
        return prepared
    if prepared.registration is None or predictions is None:
        return replace(prepared, rejection="MISSING_PREDICTION_INPUT")
    inputs = dict(prepared.inputs, predictions=copy.deepcopy(predictions))
    try:
        sealed = evaluation.seal_predictions(prepared.registration, predictions)
        return replace(prepared, inputs=inputs, seal=sealed)
    except ValueError as exc:
        return replace(prepared, inputs=inputs, rejection=_reason(exc))


def _counts(values: list[Any]) -> Record:
    return dict(sorted(Counter(str(v) for v in values if v is not None).items()))


def _feature_reasons(value: Any) -> list[str]:
    if isinstance(value, dict):
        return ([str(value["reason"])] if value.get("reason") else []) + [
            r for k, v in value.items() if k != "reason" for r in _feature_reasons(v)
        ]
    if isinstance(value, list):
        return [r for v in value for r in _feature_reasons(v)]
    return []


def _s1(value: Record) -> Record:
    declarations = value["original_declarations"]
    features = []
    for snapshot in value["origin_snapshots"]:
        features.append(
            {
                k: copy.deepcopy(snapshot[k])
                for k in (
                    "member_id",
                    "origin_id",
                    "scope",
                    "origin_date",
                    "cutoff",
                    "features",
                    "feature_sha256",
                    "status",
                )
            }
        )
    return dict(
        base_count=len({m["scope"]["base"] for m in declarations["members"]}),
        seasons=sorted({m["scope"]["season"] for m in declarations["members"]}),
        cycle_count=len(declarations["cycles"]),
        cycle_definitions=[
            {k: copy.deepcopy(c[k]) for k in ("cycle_id", "base", "season", "start")}
            for c in declarations["cycles"]
        ],
        primary_pruning_references=[
            dict(member_id=m["member_id"], record_ids=m["primary_pruning"])
            for m in declarations["members"]
        ],
        member_count=len(declarations["members"]),
        snapshot_count=len(features),
        record_count=len(value["record_ledger"]),
        associated_members=sum(r["reason"] is None for r in value["association_ledger"]),
        unassociated_members=copy.deepcopy([r for r in value["association_ledger"] if r["reason"]]),
        record_association_reasons=_counts([r["reason"] for r in value["record_ledger"]]),
        origin_decision_reasons=_counts([r["reason"] for r in value["origin_decisions"]]),
        feature_reasons=_counts([r for s in features for r in _feature_reasons(s["features"])]),
        source_quality_states=_counts(
            [state for r in value["record_ledger"] for state in r["raw_record"].get("states", [])]
        ),
        feature_states={
            name: _counts([s["features"][name]["status"] for s in features])
            for name in ("days_since_cycle_start", "days_since_primary_pruning")
        },
        features=features,
        planned_events_count=sum(
            len(s.get("planned_events", [])) for s in value["origin_snapshots"]
        ),
        temporal_scope="ONLY_ELIGIBLE_ORIGIN_SNAPSHOTS_NOT_ENTIRE_RAW_LEDGER",
    )


def _comparison(row: Record) -> Record:
    result = {
        k: copy.deepcopy(row[k])
        for k in (
            "link_id",
            "kind",
            "previous_member_id",
            "next_member_id",
            "previous_scope",
            "next_scope",
            "previous_as_of",
            "next_as_of",
            "status",
            "reasons",
            "area_changes",
            "density_change",
            "variety_changes",
        )
    }
    result["replant"] = dict(
        status=row["replant"]["status"],
        reasons=row["replant"]["reasons"],
        events=[
            {
                k: copy.deepcopy(e[k])
                for k in (
                    "record_id",
                    "old_cohort_id",
                    "new_cohort_id",
                    "business_date",
                    "observed_or_planned",
                )
            }
            for e in row["replant"]["events"]
        ],
        planned_or_unknown_count=len(row["replant"]["planned_or_unknown"]),
    )
    return result


def _s2(value: Record) -> Record:
    rows = value["comparisons"]
    return dict(
        comparisons=[_comparison(r) for r in rows],
        area_axes={
            basis: dict(
                status_counts=_counts([r["area_changes"][basis]["status"] for r in rows]),
                reasons=_counts(
                    [reason for r in rows for reason in r["area_changes"][basis]["reasons"]]
                ),
            )
            for basis in ("PLANTED", "PRODUCTIVE", "EFFECTIVE")
        },
        component_counts=structure._component_counts(rows),
        continuity_reasons=_counts([reason for r in rows for reason in r["reasons"]]),
        unlinked_members=copy.deepcopy(value["unlinked_members"]),
        origin_snapshots=[
            dict(
                origin_id=s["origin_id"],
                comparison=_comparison(s["comparison"]),
                feature_sha256=s["feature_sha256"],
            )
            for s in value["origin_snapshots"]
        ],
        visibility_reasons=_counts([r["reason"] for r in value["visibility_ledger"]]),
        temporal_scope="RETROSPECTIVE_DESCRIPTION_AND_SEPARATE_ORIGIN_SNAPSHOTS",
        population_totals_not_aggregated=True,
    )


def finish_case(prepared: Prepared, labels: Record | None = None, *, as_of: str) -> Record:
    """Score only after an existing S3 seal; return actual coverage and failures."""
    _synthetic(labels)
    p = prepared
    inputs = copy.deepcopy(p.inputs)
    output: Record | None = None
    rejection = p.rejection
    labels_read = labels is not None and p.seal is not None and not rejection
    if p.spec.stage == "S3" and not rejection:
        if p.seal is None or labels is None:
            rejection = "MISSING_SEAL_OR_LABEL_INPUT"
        else:
            inputs["labels"] = copy.deepcopy(labels)
            try:
                output = evaluation.score(p.seal, labels, as_of=as_of)
            except ValueError as exc:
                rejection = _reason(exc)
    blockers: Record = {}

    def record(scope: str, reasons: list[Any]) -> None:
        blockers.update({scope + ":" + key: count for key, count in _counts(reasons).items()})

    if rejection:
        record("PIPELINE", [rejection])
    if p.s1:
        record("S1_ORIGIN_RECORD", [r["reason"] for r in p.s1["origin_decisions"]])
        record("S1_MEMBER", [r["reason"] for r in p.s1["association_ledger"]])
        record(
            "S1_FEATURE",
            [
                reason
                for s in p.s1["origin_snapshots"]
                for reason in _feature_reasons(s["features"])
            ],
        )
    if p.s2:
        record("S2_CONTINUITY", [reason for r in p.s2["comparisons"] for reason in r["reasons"]])
        record(
            "S2_DENSITY",
            [reason for r in p.s2["comparisons"] for reason in r["density_change"]["reasons"]],
        )
        record(
            "S2_REPLANT",
            [reason for r in p.s2["comparisons"] for reason in r["replant"]["reasons"]],
        )
    if output:
        record("S3_MEMBER", [r["principal_reason"] for r in output["member_ledger"]])
    source = dict(
        input_sha256=cycle.digest(inputs),
        s1_result_sha256=p.s1["result_sha256"] if p.s1 else None,
        s2_result_sha256=p.s2["result_sha256"] if p.s2 else None,
        registration_sha256=p.registration["registration_sha256"] if p.registration else None,
        prediction_seal_sha256=p.seal["seal_sha256"] if p.seal else None,
        evaluation_result_sha256=output["result_sha256"] if output else None,
        labels_read=labels_read,
        protocol_identity=(
            {
                k: copy.deepcopy(p.registration["protocol"][k])
                for k in (
                    "models",
                    "quantity_basis",
                    "unit",
                    "source_population_sha256",
                    "training_scope_sha256",
                    "label_authority_sha256",
                    "label_source_version",
                )
            }
            if p.registration
            else None
        ),
    )
    body = dict(
        schema_version="V0_21_S4_DATASET_EXECUTION_R1",
        data_class="SYNTHETIC_TEST_FIXTURE",
        **p.spec.model_dump(),
        implementation_status="EXISTING_PREPARERS_EXECUTED",
        synthetic_validation_status="REJECTED_INPUT"
        if rejection
        else "EXECUTED_WITH_BLOCKERS"
        if blockers
        else "EXECUTED",
        real_evidence_status="NOT_PROVEN",
        source_identity=source,
        evidence_refs=[v for k, v in source.items() if k.endswith("sha256") and v],
        blockers=dict(sorted(blockers.items())),
        rejection=rejection,
        s1=_s1(p.s1) if p.s1 else None,
        s2=_s2(p.s2) if p.s2 else None,
        s3=dict(
            interpretation="SYNTHETIC_ARITHMETIC_DEMONSTRATION",
            groups=copy.deepcopy(output["groups"]),
            member_ledger=copy.deepcopy(output["member_ledger"]),
            quantity_basis=output["quantity_basis"],
            unit=output["unit"],
            candidate_count=output["candidate_count"],
        )
        if output
        else None,
    )
    return dict(body, execution_sha256=cycle.digest(body))


def _check(value: Record, key: str) -> None:
    _synthetic(value)
    if value.get(key) != cycle.digest({k: v for k, v in value.items() if k != key}):
        raise ValueError("REPORT_EXECUTION_HASH_MISMATCH")
    if key == "result_sha256" and (
        value.get("closeout", {}).get("formal_complete") is not False
        or value.get("closeout", {}).get("owner_merge_authorized") is not False
        or value.get("closeout", {}).get("release_authorized") is not False
        or value.get("closeout", {}).get("deploy_authorized") is not False
        or value.get("closeout", {}).get("independent_review_status") != "NOT_PROVEN"
        or value.get("closeout", {}).get("post_merge_main_ci") != "NOT_EXECUTED_FOR_S4"
        or any(v is not False for v in value.get("restrictions", {}).values())
    ):
        raise ValueError("S4_FORMAL_COMPLETION_NOT_AUTHORIZED")


def build_report(
    cases: list[Record], evidence: Record | None, *, title: str = "V0.21 合成研究就绪报告"
) -> Record:
    if not cases or len(cases) > 64 or len(title) > 1000:
        raise ValueError("REPORT_INPUT_LIMIT")
    for value in cases:
        _check(value, "execution_sha256")
    ids = [r["dataset_id"] for r in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("DUPLICATE_DATASET_ID")
    if evidence is not None and (
        evidence.get("schema_version") != "V0_21_S4_EVIDENCE_R1"
        or evidence.get("source_class") != "PUBLIC_REPOSITORY_METADATA"
    ):
        raise ValueError("PUBLIC_EVIDENCE_SCHEMA_REQUIRED")
    stages = copy.deepcopy(evidence.get("predecessors", [])) if evidence else []
    scenario_hashes = evidence.get("scenario_input_sha256", {}) if evidence else {}
    coverage = {}
    for stage, required in (("S2", S2_SCENARIOS), ("S3", S3_SCENARIOS)):
        relevant = [r for r in cases if r["stage"] == stage]
        seen = {r["scenario_id"] for r in relevant}
        if len(seen) != len(relevant):
            raise ValueError("DUPLICATE_SCENARIO_EXECUTION")
        matching = [
            r["scenario_id"]
            for r in relevant
            if scenario_hashes.get(stage + ":" + r["scenario_id"])
            == r["source_identity"]["input_sha256"]
        ]
        coverage[stage] = dict(
            required_count=len(required),
            executed_count=len(seen & set(required)),
            executed_scenario_ids=sorted(seen & set(required)),
            missing_scenario_ids=sorted(set(required) - seen),
            extra_scenario_ids=sorted(seen - set(required)),
            input_identity_verified_ids=sorted(matching),
            reference_status="INPUT_IDENTITIES_MATCH_PINNED_RECIPES"
            if set(required) <= set(matching)
            else "NOT_PROVEN",
            scope="SYNTHETIC_SCENARIOS_NOT_BUSINESS_POPULATION",
        )
    goal_executions = {
        goal: [
            dict(
                dataset_id=r["dataset_id"],
                groups=[g for g in r["s3"]["groups"] if g.split(":", 1)[-1] in families],
            )
            for r in cases
            if r["s3"] and any(g.split(":", 1)[-1] in families for g in r["s3"]["groups"])
        ]
        for goal, families in (
            ("season_peak", evaluation.FAMILIES[:2]),
            ("origin_h7_h15", evaluation.FAMILIES[2:]),
        )
    }
    body = dict(
        schema_version="V0_21_S4_RESEARCH_READINESS_R1",
        data_class="SYNTHETIC_TEST_FIXTURE",
        task_id="V0_21_S4_RESEARCH_READINESS_REPORT_AND_CLOSEOUT_R1",
        version="0.21.0",
        version_name="AGRONOMIC_CYCLE_AND_FORECAST_RESEARCH_READINESS",
        title=title,
        implementation_status="S4_REPORT_GENERATOR_EXECUTED",
        synthetic_validation_status="EXECUTED_PER_DATASET_WITH_SEPARATE_BLOCKERS",
        real_evidence_status="NOT_PROVEN",
        coverage_policy="PER_DATASET_NO_BUSINESS_POPULATION_SUM",
        source_identity=dict(
            upstream="REEXECUTED_S1_S2_REGISTER_SEAL_SCORE_S3",
            evidence_sha256=cycle.digest(evidence) if evidence else None,
            execution_sha256={
                r["dataset_id"]: r["execution_sha256"]
                for r in sorted(cases, key=lambda r: r["dataset_id"])
            },
            s4_execution_manifest="manifest.json",
        ),
        historical_deliveries=dict(
            status="MERGES_RECORDED_IN_PINNED_PUBLIC_EVIDENCE"
            if {r.get("stage") for r in stages} == {"S0", "S1", "S2", "S3"}
            else "NOT_PROVEN",
            stages=stages,
        ),
        goals={
            "season_peak": dict(
                priority="EQUAL",
                families=list(evaluation.FAMILIES[:2]),
                implementation_status="IMPLEMENTED_SEPARATE_FULL_AND_DECLARED_REMAINING_SCOPES",
                synthetic_validation_status="EXECUTED_SEE_PER_METRIC_COVERAGE"
                if goal_executions["season_peak"]
                else "NOT_PROVEN_NO_SCOPE_EXECUTION",
                execution_refs=goal_executions["season_peak"],
                real_evidence_status="NOT_PROVEN",
            ),
            "origin_h7_h15": dict(
                priority="EQUAL",
                families=list(evaluation.FAMILIES[2:]),
                implementation_status="IMPLEMENTED_SAME_H15_VECTOR_PREFIX_WITH_R2_VALIDATION",
                synthetic_validation_status="EXECUTED_SEE_PER_METRIC_COVERAGE"
                if goal_executions["origin_h7_h15"]
                else "NOT_PROVEN_NO_SCOPE_EXECUTION",
                execution_refs=goal_executions["origin_h7_h15"],
                real_evidence_status="NOT_PROVEN",
            ),
        },
        datasets=copy.deepcopy(cases),
        scenario_coverage=coverage,
        real_data_gaps=[
            dict(
                id=key,
                requirement=label,
                needed_evidence=needed,
                status="NOT_PROVEN",
                evidence_refs=[],
            )
            for key, label, needed in GAPS
        ],
        fair_research_conditions=list(FAIR_CONDITIONS),
        closeout=dict(
            implementation_status="S4_IMPLEMENTED",
            independent_review_status="NOT_PROVEN",
            owner_merge_authorized=False,
            post_merge_main_ci="NOT_EXECUTED_FOR_S4",
            formal_complete=False,
            release_authorized=False,
            deploy_authorized=False,
            status="DRAFT_AWAITING_INDEPENDENT_REVIEW_OWNER_MERGE_AND_MAIN_CI",
        ),
        restrictions=dict(
            real_data_read=False,
            model_training=False,
            real_accuracy_validated=False,
            strict_pit_validated=False,
            production_forecast_change=False,
            model_promotion=False,
            agronomic_effect_validated=False,
            ready_authorized=False,
            merge_authorized=False,
            release_authorized=False,
            deployed=False,
            v0_21_formal_complete=False,
        ),
    )
    return dict(body, result_sha256=cycle.digest(body))


def _text(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def _md(value: Any) -> str:
    # Escape raw HTML as well as Markdown links, table separators and delimiters.
    return (
        re.sub(r"([\\`*{}\[\]()#_|])", r"\\\1", html.escape(_text(value), quote=True))
        .replace("\r", " ")
        .replace("\n", " ")
    )


def _sections(value: Record) -> list[Record]:
    # Saved canonical JSON and in-memory execution must render identical bytes.
    value = json.loads(cycle.canonical(value))
    sections = []

    def add(title: str, note: str, headers: list[str], rows: list[list[Any]]) -> None:
        sections.append(dict(title=title, note=note, headers=headers, rows=rows))

    add(
        "1. 版本与范围",
        "显式合成输入。源码、Hash、执行时间见manifest.json；不证明真实来源或历史签名。",
        ["项目", "状态/身份"],
        [
            ["版本", value["version"]],
            ["版本名称", value["version_name"]],
            ["当前任务", value["task_id"]],
            ["结果Hash", value["result_sha256"]],
            ["实现", value["implementation_status"]],
            ["合成执行", value["synthetic_validation_status"]],
            ["真实证据", value["real_evidence_status"]],
        ]
        + [
            [r.get("stage"), {k: v for k, v in r.items() if k != "stage"}]
            for r in value["historical_deliveries"]["stages"]
        ],
    )
    add(
        "2. 两个同优先级的业务目标",
        "RECORDED_INBOUND_WEIGHT / kg。H7/H15局部峰不能替代产季峰；不是田间量。",
        ["目标", "优先级", "评价族", "实现", "合成验证", "真实缺口"],
        [
            [
                key,
                g["priority"],
                g["families"],
                g["implementation_status"],
                g["synthetic_validation_status"],
                "真实成员、周期、面积、来源时间、模型和成熟标签待证明；授权另行申请",
            ]
            for key, g in value["goals"].items()
        ],
    )
    add(
        "3. S1–S3 功能与覆盖情况",
        "数据集分别统计，不能相加冒充真实业务覆盖。模拟时钟不证明严格PIT。",
        ["数据集", "阶段/场景", "合成状态", "真实证据", "阻断/缺口"],
        [
            [
                r["dataset_id"],
                r["stage"] + " / " + r["scenario_id"],
                r["synthetic_validation_status"],
                r["real_evidence_status"],
                {"reason_types": len(r["blockers"]), "details": "展开该数据集查看"},
            ]
            for r in value["datasets"]
        ],
    )
    add(
        "合成场景引用与执行身份",
        "场景数量仅表示执行覆盖；被拒绝的输入仍保留，不因有Hash而自证权威。",
        ["阶段", "应有", "已执行", "未执行", "额外回归", "输入身份核对"],
        [
            [
                s,
                v["required_count"],
                v["executed_count"],
                v["missing_scenario_ids"],
                v["extra_scenario_ids"],
                v["reference_status"],
            ]
            for s, v in value["scenario_coverage"].items()
        ],
    )
    # A readable entry point into the full per-metric ledgers, without recomputing math.
    for data in value["datasets"]:
        if data["scenario_id"] == "COMPLETE" and data["s3"]:
            add(
                "合成数值示例 / " + data["dataset_id"],
                "SYNTHETIC_ARITHMETIC_DEMONSTRATION；以下直接投影已计算的S3结果，不代表农艺效果。完整分母与失败原因见数据集详情。",
                ["评价族", "指标", "C0 / Cm", "基线值", "候选值", "合成诊断"],
                [
                    [
                        family,
                        metric,
                        [m["candidate_count"], m["common_count"]],
                        m["baseline"]["metric_value"],
                        m["candidate"]["metric_value"],
                        group["diagnosis"],
                    ]
                    for family, group in data["s3"]["groups"].items()
                    for metric, m in group["metrics"].items()
                    if metric in {"DAILY_MAE", "V0_21_ORIGIN_WINDOW_TOTAL_MAE"}
                    and m["common_count"]
                ],
            )
    for data in value["datasets"]:
        prefix = data["dataset_id"]
        add(
            prefix + " / 执行来源",
            "独立输入、特征、预测封存、标签和评价身份分别记录。只读as-of特征，不将原始事实账本整体当作输入。",
            ["身份", "Hash/状态"],
            [[k, v] for k, v in data["source_identity"].items()],
        )
        add(
            prefix + " / 独立阻断账本",
            "数量单位按原因命名空间区分，不合并为真实业务总体。",
            ["原因 / 计数单位", "数量"],
            [[k, v] for k, v in data["blockers"].items()],
        )
        if data["s1"]:
            s = data["s1"]
            add(
                prefix + " / S1 周期与时点",
                "数量仅属于此数据集；PLANNED与OBSERVED分开，未知不填0。",
                ["基地数", "产季", "主周期", "成员", "已关联", "快照", "时间/关联原因"],
                [
                    [
                        s["base_count"],
                        s["seasons"],
                        s["cycle_count"],
                        s["member_count"],
                        s["associated_members"],
                        s["snapshot_count"],
                        s["origin_decision_reasons"],
                    ]
                ],
            )
            add(
                prefix + " / S1 特征可用情况",
                "仅列合法origin快照内的特征。EXACT、区间与NOT_COMPUTABLE不混同；计划事件不冒充实际。",
                ["成员", "Origin", "状态", "周期经过日", "主剪枝经过日", "已观测事件/阶段间隔"],
                [
                    [
                        s["member_id"],
                        s["origin_date"],
                        s["status"],
                        s["features"]["days_since_cycle_start"],
                        s["features"]["days_since_primary_pruning"],
                        {
                            k: v
                            for k, v in s["features"].items()
                            if k not in {"days_since_cycle_start", "days_since_primary_pruning"}
                        },
                    ]
                    for s in data["s1"]["features"]
                ],
            )
        if data["s2"]:
            s = data["s2"]
            add(
                prefix + " / S2 生产结构",
                "PLANTED/PRODUCTIVE/EFFECTIVE按口径、成员、评估日独立。以下是事后描述，不自动成为origin可用结构信息。",
                [
                    "连续关系",
                    "前后成员",
                    "面积口径",
                    "前亩",
                    "后亩",
                    "差亩",
                    "变化ratio",
                    "状态/原因",
                ],
                [
                    [
                        r["link_id"],
                        [r["previous_member_id"], r["next_member_id"]],
                        basis,
                        a["previous_mu"],
                        a["next_mu"],
                        a["delta_mu"],
                        a["relative_change_ratio"],
                        dict(
                            status=a["status"],
                            reasons=a["reasons"],
                            relative_change_reason=a["relative_change_reason"],
                        ),
                    ]
                    for r in s["comparisons"]
                    for basis, a in r["area_changes"].items()
                ],
            )
            add(
                prefix + " / S2 连续性、品种、密度与换苗",
                "可比性按轴独立。换苗、密度不产生系数，origin结构另列Hash。",
                ["关系", "连续性状态/原因", "品种进出", "密度", "换苗", "Origin结构快照"],
                [
                    [
                        r["link_id"],
                        dict(status=r["status"], reasons=r["reasons"]),
                        r["variety_changes"],
                        r["density_change"],
                        r["replant"],
                        [
                            dict(
                                origin_id=o["origin_id"],
                                status=o["comparison"]["status"],
                                feature_sha256=o["feature_sha256"],
                            )
                            for o in s["origin_snapshots"]
                            if o["comparison"]["link_id"] == r["link_id"]
                        ],
                    ]
                    for r in s["comparisons"]
                ],
            )
        if data["s3"]:
            s = data["s3"]
            for group_id, g in s["groups"].items():
                rows = []
                for name, m in g["metrics"].items():
                    if "common_count" in m:
                        rows.append(
                            [
                                name,
                                m["candidate_count"],
                                m["common_count"],
                                m["not_computable_count"],
                                {
                                    k: m["baseline"][k]
                                    for k in ("numerator", "denominator", "ratio")
                                },
                                {
                                    k: m["candidate"][k]
                                    for k in ("numerator", "denominator", "ratio")
                                },
                                m.get("candidate_minus_baseline"),
                                m["reasons"],
                                m.get("timing_skill_interpretable", "—"),
                            ]
                        )
                    else:
                        rows.append(
                            [
                                name,
                                g["candidate_count"],
                                "见逐指标",
                                "见逐指标",
                                m,
                                "—",
                                "—",
                                "—",
                                "—",
                            ]
                        )
                add(
                    prefix + " / " + group_id,
                    "SYNTHETIC_ARITHMETIC_DEMONSTRATION；诊断="
                    + g["diagnosis"]
                    + "。C0/Cm与分母保留；重叠origin非独立样本，结构性0无峰时含义。",
                    [
                        "指标",
                        "C0",
                        "Cm",
                        "不可算",
                        "基线 分子/分母/值",
                        "候选 分子/分母/值",
                        "候选−基线",
                        "原因",
                        "峰时可解释",
                    ],
                    rows,
                )
            add(
                prefix + " / 单日及连续7/15日峰",
                "预测与实际各自独立选峰，并列最早；窗口范围以评价族为准。全零实际不产生虚假峰时命中。",
                ["成员/范围", "Origin", "峰类型", "基线", "候选", "实际", "不可算原因"],
                [
                    [
                        r["case_id"],
                        r["origin"]["origin_date"],
                        peak,
                        r["baseline_peaks"].get(peak) if r["baseline_peaks"] else None,
                        r["candidate_peaks"].get(peak) if r["candidate_peaks"] else None,
                        r["actual_peaks"].get(peak) if r["actual_peaks"] else None,
                        r["principal_reason"],
                    ]
                    for r in s["member_ledger"]
                    for peak in ("single_day", "rolling7", "rolling15")
                ],
            )
            add(
                prefix + " / 每日与累计误差",
                "每日误差和累计误差分别报告，不能用正负抵消掩盖日偏差。完整向量来自S3实际执行，不从展示值复算。",
                [
                    "成员/范围",
                    "日期",
                    "基线kg",
                    "候选kg",
                    "实际kg",
                    "基线signed/abs",
                    "候选signed/abs",
                ],
                [
                    [
                        r["case_id"],
                        d["date"],
                        d["baseline_kg"],
                        d["candidate_kg"],
                        d["actual_kg"],
                        [d["baseline_signed_error_kg"], d["baseline_absolute_error_kg"]],
                        [d["candidate_signed_error_kg"], d["candidate_absolute_error_kg"]],
                    ]
                    for r in s["member_ledger"]
                    for d in r["daily"]
                ],
            )
            add(
                prefix + " / 累计与失败账本",
                "失败成员不从C0删除；不足15日、未成熟、缺预测、缺日等按原原因保留。SEASON_TOTAL_WAPE仅完整产季适用。",
                ["成员/范围", "累计与累计误差", "失败/不可计算"],
                [[r["case_id"], r["totals"], r["failures"]] for r in s["member_ledger"]],
            )
    add(
        "4. 真实数据与研究准入缺口",
        "本版只使用合成记录。Hash存在、字段填写、模拟时钟或结构通过均不构成真实来源权威。",
        ["要求", "状态", "仍需材料"],
        [[g["requirement"], g["status"], g["needed_evidence"]] for g in value["real_data_gaps"]],
    )
    add(
        "5. 后续公平研究条件",
        "下列条件不是执行授权；本次不开展真实研究或模型训练。",
        ["序号", "条件"],
        [[i + 1, v] for i, v in enumerate(value["fair_research_conditions"])],
    )
    add(
        "6. 工程版本收口状态",
        "实现、合成、真实证据、评审、合并、main CI和发布分别设门禁。正式完成=false。",
        ["门禁", "状态"],
        [[k, v] for k, v in value["closeout"].items()]
        + [[k, v] for k, v in value["restrictions"].items()],
    )
    return sections


def render_markdown(value: Record) -> str:
    _check(value, "result_sha256")
    lines = [
        "# " + _md(value["title"]),
        "",
        "SYNTHETIC_TEST_FIXTURE · 仅研究准备 · 非真实预测精度/农艺效果验证",
        "",
    ]
    for section in _sections(value):
        lines += [
            "## " + _md(section["title"]),
            "",
            _md(section["note"]),
            "",
            "| " + " | ".join(_md(v) for v in section["headers"]) + " |",
            "| " + " | ".join("---" for _ in section["headers"]) + " |",
        ]
        lines += ["| " + " | ".join(_md(v) for v in row) + " |" for row in section["rows"]]
        lines.append("")
    return "\n".join(lines)


def render_html(value: Record) -> str:
    _check(value, "result_sha256")

    def escape(text: Any) -> str:
        return html.escape(_text(text), quote=True)

    parts = [
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta http-equiv="Content-Security-Policy" content="default-src '
        "'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action "
        "'none'\">",
        "<title>" + escape(value["title"]) + "</title>",
        "<style>body{margin:0;background:#f3f5f7;color:#172332;font:14px/"
        "1.65 system-ui,sans-serif;overflow-wrap:anywhere}*{box-sizing:border-box}"
        "main{max-width:1250px;margin:auto;padd"
        "ing:24px}h1{font-size:26px}h2{font-size:19px;margin:0}header,sec"
        "tion{background:white;border:1px solid #d8dee6;border-radius:8px"
        ";padding:18px;margin-bottom:16px}nav{display:flex;flex-wrap:wrap;gap:12px;"
        "margin:16px 0}nav a{color:#234e70}"
        ".dataset{border:1px solid #d8dee6;border-radius:8px;padding:14px;"
        "margin:12px 0;background:#fff}"
        ".dataset>summary{padding:4px}.dataset section{margin-top:12px;margin-bottom:0}"
        ".notice{color:#755000;backgroun"
        "d:#fff7dc;padding:10px;border-left:4px solid #c48b14}.table-scro"
        "ll{overflow:auto;margin-top:12px}table{border-collapse:collapse;"
        "width:100%;font-size:12px}th,td{text-align:left;vertical-align:t"
        "op;border:1px solid #dce2e9;padding:7px;max-width:520px;overflow"
        "-wrap:anywhere}th{background:#edf2f6;white-space:nowrap}p{margin"
        ":8px 0;color:#455467}details summary{cursor:pointer;font-weight:"
        "600}table:has(th:nth-child(8)){min-width:1900px}"
        "@media(max-width:600px){main{padding:10px}header,section{pad"
        "ding:12px}h1{font-size:21px}h2{font-size:17px}th,td{min-width:95"
        "px;max-width:240px}table{font-size:12px}}</style></head><body><m"
        "ain><header><h1>",
        escape(value["title"]),
        "</h1><p>V0.21.0 · AGRONOMIC_CYCLE_AND_FORECAST_RESEARCH_READINES"
        'S</p><div class="notice">SYNTHETIC_TEST_FIXTURE · 合成研究准备，不代表真实农艺'
        "增强预测、生产精度或正式版本完成。</div></header>",
        '<nav aria-label="报告章节">'
        + "".join(
            f'<a href="#chapter-{i}">{label}</a>'
            for i, label in enumerate(
                ("版本范围", "业务目标", "合成覆盖", "真实缺口", "公平研究", "收口门禁"), 1
            )
        )
        + "</nav>",
    ]
    datasets = {d["dataset_id"]: d for d in value["datasets"]}
    active_dataset = None
    for section in _sections(value):
        dataset_id = next(
            (name for name in datasets if section["title"].startswith(name + " / ")), None
        )
        if dataset_id != active_dataset:
            if active_dataset is not None:
                parts.append("</details>")
            if dataset_id is not None:
                data = datasets[dataset_id]
                parts += [
                    '<details class="dataset"><summary>',
                    escape(dataset_id),
                    " · ",
                    escape(data["synthetic_validation_status"]),
                    "</summary>",
                ]
            active_dataset = dataset_id
        chapter = re.match(r"^([1-6])\.", section["title"])
        anchor = f' id="chapter-{chapter[1]}"' if chapter else ""
        parts += [
            "<section"
            + anchor
            + "><details"
            + (
                " open"
                if section["title"][0].isdigit() or section["title"].startswith("合成")
                else ""
            )
            + "><summary><h2>",
            escape(section["title"]),
            "</h2></summary><p>",
            escape(section["note"]),
            '</p><div class="table-scroll"><table><thead><tr>',
        ]
        parts += ["<th>" + escape(v) + "</th>" for v in section["headers"]]
        parts.append("</tr></thead><tbody>")
        for row in section["rows"]:
            parts.append("<tr>" + "".join("<td>" + escape(v) + "</td>" for v in row) + "</tr>")
        parts.append("</tbody></table></div></details></section>")
    if active_dataset is not None:
        parts.append("</details>")
    return "".join(parts) + "</main></body></html>\n"
