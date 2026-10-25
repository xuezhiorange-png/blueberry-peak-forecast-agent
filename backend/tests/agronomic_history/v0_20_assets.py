"""V0_20 public vocabulary projection and bounded SYNTHETIC spreadsheets.

Reads repository contracts only. Never discovers business files or a database.
python -m backend.tests.agronomic_history.v0_20_assets
"""

import base64
import csv
import hashlib
import io
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[3]
BASE = "d30e40b7a71f258f223c73c5fdb2b273d35ef1fa"
TARGET = ROOT / "frontend/src/dashboard/agronomic"
SOURCES = (
    "docs/v0-9/s1/management-event-registry-r1.json",
    "docs/v0-9/s1/biological-state-registry-r1.json",
    "backend/app/pit/schemas.py",
    "backend/app/pit/visibility.py",
    "backend/app/models/master_data.py",
    "backend/app/planning/plan_schemas.py",
)


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def vocabulary():
    historical = {
        p: subprocess.check_output(["git", "show", f"{BASE}:{p}"], cwd=ROOT) for p in SOURCES
    }
    events = json.loads(historical[SOURCES[0]])
    biology = json.loads(historical[SOURCES[1]])
    return dict(
        schema_version="V0_20_AGRONOMIC_VOCABULARY_R1",
        base_main_sha=BASE,
        upstream_versions={
            "management_events": events["contract_version"],
            "phenology": biology["contract_version"],
            "pit": "V0_6_S1",
        },
        sources={p: hashlib.sha256(historical[p]).hexdigest() for p in SOURCES},
        event_types=[
            dict(
                code=e["event_type"], family=e["family"], applicable_systems=e["applicable_systems"]
            )
            for e in events["event_types"]
        ],
        phenology_stages=biology["phenology_state_machine"]["state_ids"],
        production_systems=[s["system_id"] for s in biology["production_systems"]],
        intensity_modes=events["intensity_contract"]["allowed_modes"],
        intensity_requirements=events["intensity_contract"]["numeric_intensity_requires"],
        production_plan_fields=[
            "planted_area_mu",
            "tree_age_years",
            "pruning_date",
            "flowering_start_date",
            "flowering_peak_date",
            "flowering_end_date",
            "version",
            "effective_from",
            "effective_to",
            "available_at",
            "source_type",
            "source_name",
            "source_version",
        ],
        interpretation="PREPARATION_ONLY_NO_BIOLOGICAL_MODEL_OR_AUTHORITY",
    )


COMMON = [
    "base",
    "farm",
    "subfarm",
    "plot",
    "variety",
    "season",
    "production_system",
    "status",
    "source_reference",
    "source_version",
    "recorded_at",
    "known_at",
    "logical_id",
    "revision_id",
]
AREAS = [
    "planted_area",
    "productive_area",
    "effective_area",
    "area_unit",
    "effective_from",
    "effective_to",
    "tree_age_years",
    "planting_year",
]
EXTRA = [
    "method",
    "sample_scope",
    "quality_status",
    "observed_at",
    "event_type",
    "date",
    "end_date",
    "area_basis",
    "area_value",
    "stage",
    "intensity_mode",
    "intensity_value",
    "intensity_unit",
    "intensity_denominator",
    "pruning_type",
    "operation_count",
    "supersedes_revision",
]
LABELS = dict(
    base="基地编码",
    farm="农场代码",
    subfarm="分场代码",
    plot="原始地块",
    variety="品种代码",
    season="产季",
    production_system="栽培制度",
    status="计划或实际",
    source_reference="来源证明",
    source_version="来源版本",
    recorded_at="记录日期",
    known_at="可见日期",
    logical_id="记录编号",
    revision_id="修订号",
    planted_area="种植面积",
    productive_area="投产面积",
    effective_area="有效面积",
    area_unit="面积单位",
    effective_from="生效开始",
    effective_to="生效结束",
    tree_age_years="声明树龄",
    planting_year="种植年份",
    method="观测或操作方法",
    sample_scope="样本范围",
    quality_status="质量状态",
    observed_at="实际观测日期",
    event_type="事件类型",
    date="业务日期",
    end_date="结束日期",
    area_basis="面积口径",
    area_value="面积数值",
    stage="物候阶段",
    intensity_mode="强度表达",
    intensity_value="强度数值",
    intensity_unit="强度单位",
    intensity_denominator="强度分母",
    pruning_type="剪枝类型",
    operation_count="声明次数",
    supersedes_revision="前版修订号",
)
EVENT_SLOTS = [
    ("prune1", "PRUNING", "剪枝第一次"),
    ("prune2", "PRUNING", "剪枝第二次"),
    ("close", "GREENHOUSE_CLOSE", "关棚"),
    ("open", "GREENHOUSE_OPEN", "开棚"),
    ("heat", "HEATING_START", "加温开始"),
    ("stop", "HEATING_STOP", "加温结束"),
]
PHENO_SLOTS = [
    ("flowering_start_date", "flowering_start_date", "开花开始"),
    ("flowering_peak_date", "flowering_peak_date", "盛花"),
    ("flowering_end_date", "flowering_end_date", "开花结束"),
    ("b10", "BLOOM_10", "BLOOM_10"),
    ("b50", "BLOOM_50", "BLOOM_50"),
    ("b90", "BLOOM_90", "BLOOM_90"),
]


def fixed_xlsx(sheets):
    book = Workbook()
    book.remove(book.active)
    for name, rows in sheets:
        sheet = book.create_sheet(name)
        for row in rows:
            sheet.append(row)
    book.properties.creator = "V0_20_SYNTHETIC_TEST_FIXTURE"
    book.properties.created = book.properties.modified = datetime(2000, 1, 1)
    buffer = io.BytesIO()
    book.save(buffer)
    output = io.BytesIO()
    with ZipFile(buffer) as src, ZipFile(output, "w") as dst:
        for name in sorted(src.namelist()):
            raw = src.read(name)
            if name == "docProps/core.xml":
                raw = re.sub(rb"(<dcterms:modified[^>]*>)[^<]*", rb"\g<1>2000-01-01T00:00:00Z", raw)
            info = ZipInfo(name, (2000, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            dst.writestr(info, raw)
    return output.getvalue()


def synthetic(scenario):
    negative = scenario == "negative"
    long = scenario == "long"
    sheets = [("说明", [["V0_20 SYNTHETIC_TEST_FIXTURE，合成历史，不代表真实业务"]])]
    plans = []
    reference = []
    for i in range(3):
        reference.append(
            dict(
                base=f"SYN-BASE-{1 if i < 2 else 2}",
                farm=f"SYN-FARM-{1 if i < 2 else 2}",
                subfarm=f"SYN-SUB-{i + 1}",
                plot=f"SYN-PLOT-{i + 1}",
                variety=f"SYN-VAR-{1 if i != 1 else 2}",
                base_id="V0_20_SYNTHETIC_BASE_A" if i < 2 else "V0_20_SYNTHETIC_BASE_B",
                farm_id=101 if i < 2 else 102,
                subfarm_id=201 + i,
                variety_id=301 if i != 1 else 302,
            )
        )
    common_rows = []
    for year in (2023, 2024):
        for i, scope in enumerate(reference):
            c = {k: scope[k] for k in ("base", "farm", "subfarm", "plot", "variety")}
            c.update(
                season=f"{year}-{year + 1}",
                production_system=("EVERGREEN", "DECIDUOUS_FORCING", "EVERGREEN")[i],
                status="OBSERVED",
                source_reference="SYNTHETIC-FIELD-LOG",
                source_version="SYN-R1",
                recorded_at=f"{year}-12-31",
                known_at=f"{year + 1}-01-01",
                logical_id=f"SYN-{year}-{i}",
                revision_id="r1",
                method="SYNTHETIC人工样方记录",
                sample_scope="SYNTHETIC固定10株样方",
                quality_status="SYNTHETIC_DECLARED",
                observed_at="",
                effective_from=f"{year}-07-01",
                effective_to=f"{year + 1}-06-30",
                tree_age_years="3",
                planting_year=str(year - 3),
                area_unit="mu",
                planted_area="100",
                productive_area="80",
                effective_area="70",
                intensity_mode="PRESENCE_ONLY",
                intensity_value="",
                intensity_unit="",
                intensity_denominator="",
                pruning_type="枝条修剪",
                operation_count="1",
                supersedes_revision="",
            )
            common_rows.append(c)
    for kind, title in [("AREA", "种植面积"), ("EVENT", "农事操作"), ("PHENOLOGY", "开花物候")]:
        fields = COMMON + (
            ["area_basis", "area_value", *AREAS[3:]]
            if long and kind == "AREA"
            else AREAS
            if kind == "AREA"
            else EXTRA
        )
        slots = EVENT_SLOTS if kind == "EVENT" else PHENO_SLOTS if kind == "PHENOLOGY" else []
        if not long:
            fields = [k for k in fields if k not in ("date", "stage", "event_type")] + [
                s[0] for s in slots
            ]
        header = 0 if long else 2
        rows = []
        for n, c in enumerate(common_rows):
            year = int(c["season"][:4])
            v = dict(c)
            if kind == "AREA":
                if negative and n == 0:
                    v["productive_area"] = "140"
                if long:
                    for basis, key in [
                        ("PLANTED", "planted_area"),
                        ("PRODUCTIVE", "productive_area"),
                        ("EFFECTIVE", "effective_area"),
                    ]:
                        rows.append({**v, "area_basis": basis, "area_value": v[key]})
                else:
                    rows.append(v)
            else:
                for j, (key, _code, _label) in enumerate(slots):
                    v[key] = f"{year}-{'09' if kind == 'EVENT' else '11'}-{5 + j * 3:02}"
                    if negative and n == 0 and key == "b50":
                        v[key] = f"{year}-11"
                if long:
                    for key, code, _label in slots:
                        rows.append(
                            {
                                **v,
                                "logical_id": v["logical_id"] + "-" + key,
                                "date": v[key],
                                "event_type": code if kind == "EVENT" else "",
                                "stage": code if kind == "PHENOLOGY" else "",
                            }
                        )
                else:
                    rows.append(v)
        if negative and kind == "AREA":
            rows.append({**rows[0], "logical_id": "SYN-CONFLICT", "planted_area": "120"})
        if negative and kind == "EVENT":
            # A separate long sheet preserves ambiguous forcing and duplicate/revision facts.
            extras = [
                {
                    **common_rows[0],
                    "logical_id": "SYN-UNKNOWN-FORCING",
                    "event_type": "促早",
                    "date": "2023-10-01",
                    "method": "",
                },
                {
                    **common_rows[0],
                    "logical_id": "SYN-DUP",
                    "event_type": "PRUNING",
                    "date": "2023-09-01",
                },
                {
                    **common_rows[0],
                    "logical_id": "SYN-DUP",
                    "event_type": "PRUNING",
                    "date": "2023-09-01",
                    "status": "PLANNED",
                    "observed_at": "2023-09-01",
                },
                {
                    **common_rows[0],
                    "logical_id": "SYN-UNMAPPED",
                    "plot": "UNKNOWN-PLOT",
                    "event_type": "PRUNING",
                    "date": "2023-09-02",
                },
            ]
            ef = COMMON + EXTRA
            sheets.append(
                ("负面长表", [[k for k in ef], *[[r.get(k, "") for k in ef] for r in extras]])
            )
            plans.append(
                dict(
                    sheet=len(sheets) - 1,
                    header=0,
                    kind="EVENT",
                    layout="LONG",
                    columns={k: i for i, k in enumerate(ef)},
                    slots=[],
                )
            )
        labels = (
            fields
            if long
            else [LABELS.get(k, dict((s[0], s[2]) for s in slots).get(k, k)) for k in fields]
        )
        prefix = [] if long else [["V0_20 合成历史 / 不用于模型"], ["请人工核对第三行表头"]]
        sheets.append((title, [*prefix, labels, *[[r.get(k, "") for k in fields] for r in rows]]))
        plans.append(
            dict(
                sheet=len(sheets) - 1,
                header=header,
                kind=kind,
                layout="LONG" if long else "WIDE",
                columns={k: i for i, k in enumerate(fields) if k not in {s[0] for s in slots}},
                slots=[
                    dict(
                        id=key,
                        column=fields.index(key),
                        declared_type=code,
                        label=label,
                        state="UNKNOWN",
                    )
                    for key, code, label in slots
                ]
                if not long
                else [],
            )
        )
    sheets.append(
        (
            "Excel时间精度",
            [
                ["原始 Excel 时钟（无时区证明）"],
                [datetime(2024, 9, 1, 12, 0)],
                [datetime(2024, 9, 2)],
            ],
        )
    )

    def view_hash(data):
        def cell(v):
            if isinstance(v, datetime):
                return (
                    v.isoformat(timespec="milliseconds")
                    if v.time() != datetime.min.time()
                    else v.date().isoformat()
                )
            return "" if v is None else str(v)

        def trim(row):
            values = [cell(v) for v in row]
            while values and values[-1] == "":
                values.pop()
            return values

        grid = [dict(name=n, rows=[trim(r) for r in rows]) for n, rows in data]
        return hashlib.sha256(
            json.dumps(grid, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest()

    raw = fixed_xlsx(sheets)
    assets = dict(
        xlsx=dict(
            filename=f"V0_20-SYNTHETIC-{scenario}.xlsx",
            sha256=hashlib.sha256(raw).hexdigest(),
            view_sha256=view_hash(sheets),
            base64=base64.b64encode(raw).decode(),
            plans=plans,
        )
    )
    # CSV exercises the same area facts in a single-sheet long representation.
    csv_fields = COMMON + ["area_basis", "area_value", *AREAS[3:]]
    out = io.StringIO(newline="")
    w = csv.writer(out)
    w.writerow(csv_fields)
    csv_rows = [csv_fields]
    for c in common_rows:
        for basis, key in [
            ("PLANTED", "planted_area"),
            ("PRODUCTIVE", "productive_area"),
            ("EFFECTIVE", "effective_area"),
        ]:
            row = [{**c, "area_basis": basis, "area_value": c[key]}.get(k, "") for k in csv_fields]
            w.writerow(row)
            csv_rows.append(row)
    raw = ("\ufeff" + out.getvalue()).encode()
    assets["csv"] = dict(
        filename="V0_20-SYNTHETIC-area.csv",
        sha256=hashlib.sha256(raw).hexdigest(),
        view_sha256=view_hash([("CSV", csv_rows)]),
        base64=base64.b64encode(raw).decode(),
        plans=[
            dict(
                sheet=0,
                header=0,
                kind="AREA",
                layout="LONG",
                columns={k: i for i, k in enumerate(csv_fields)},
                slots=[],
            )
        ],
    )
    return dict(data_class="SYNTHETIC_TEST_FIXTURE", scope_reference=reference, assets=assets)


def main():
    TARGET.mkdir(parents=True, exist_ok=True)
    (TARGET / "v0_20_vocabulary.json").write_bytes(canonical(vocabulary()))
    (TARGET / "v0_20_synthetic.json").write_bytes(
        canonical({s: synthetic(s) for s in ("wide", "long", "negative")})
    )
    evidence = dict(
        task_id="V0_20_AGRONOMIC_HISTORY_DATA_FOUNDATION_R1",
        version="0.20.0",
        version_name="AGRONOMIC_HISTORY_DATA_FOUNDATION",
        base_main_sha=BASE,
        release_class="DATA_READINESS_ENGINEERING",
        schema="V0_20_AGRONOMIC_PREPARATION_R1",
        upstream=vocabulary(),
        synthetic_assets={
            s: {
                f: {k: a[k] for k in ("filename", "sha256", "view_sha256")}
                for f, a in synthetic(s)["assets"].items()
            }
            for s in ("wide", "long", "negative")
        },
        expected_synthetic=dict(
            seasons=["2023-2024", "2024-2025"],
            base_count=2,
            variety_count=2,
            source_plots=3,
            area=18,
            event=36,
            phenology=36,
            total=90,
            research_admitted_count=0,
        ),
        preparation_states=[
            "VALID_STRUCTURE",
            "PARTIAL",
            "CONFLICT",
            "UNMAPPED",
            "SOURCE_AUTHORITY_NOT_PROVEN",
            "PIT_NOT_PROVEN",
        ],
        outputs=[
            "agronomic-preparation.json",
            "agronomic-area.csv",
            "agronomic-events.csv",
            "agronomic-phenology.csv",
            "agronomic-quality-report.html",
        ],
        restrictions={
            k: False
            for k in (
                "real_data_read",
                "real_data_imported",
                "production_database_writes",
                "source_authority_proven",
                "strict_pit_validated",
                "model_trained",
                "agronomic_effect_validated",
                "prospective_accuracy_validated",
                "s6_s7_s8_s9_algorithms_changed",
                "model_promotion",
                "deployed",
                "ready_authorized",
                "merge_authorized",
                "release_authorized",
                "formal_version_complete",
            )
        },
        acceptance_status="REQUIRES_LOCAL_CHECKS_EXACT_HEAD_CI_INDEPENDENT_REVIEW_AND_POSTMERGE_MAIN_CI",
    )
    dest = ROOT / "docs/v0-20/evidence/v0.20.0-foundation-contract-r1.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(canonical(evidence))


if __name__ == "__main__":
    main()
