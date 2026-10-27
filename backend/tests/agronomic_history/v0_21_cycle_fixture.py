"""Explicit SYNTHETIC normalized V020 fixtures, not an Excel parser or authority.

python -m backend.tests.agronomic_history.v0_21_cycle_fixture --output NEW_DIRECTORY
"""

import argparse
import calendar
import copy
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BASE = "0fe06ca320724d4067f573535f2b6be25ffafbc1"


def canonical(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def span(raw=""):
    precision, lower, upper = "UNKNOWN", None, None
    if len(raw) == 10:
        precision, lower, upper = "DAY", raw, raw
    elif len(raw) == 7:
        y, m = map(int, raw.split("-"))
        precision, lower, upper = "MONTH", raw + "-01", f"{raw}-{calendar.monthrange(y, m)[1]}"
    elif len(raw) == 4:
        precision, lower, upper = "YEAR", raw + "-01-01", raw + "-12-31"
    return dict(raw=raw, precision=precision, lower_date=lower, upper_date=upper, instant=None)


def clock(day, planned=False):
    return dict(
        provenance="SYNTHETIC_EXPLICIT_CLOCKS",
        observed_at=None if planned else day + "T17:00:00+08:00",
        recorded_at=day + "T18:00:00+08:00",
        known_at=day + "T19:00:00+08:00",
        evidence_reference="SYNTHETIC-clock-proof-not-real-authority",
    )


def seal(package):
    data = {
        k: v
        for k, v in package.items()
        if k not in {"package_id", "preparation_sha256", "artifact_sha256"}
    }
    package["preparation_sha256"] = digest(data)
    package["package_id"] = "V0_20-" + digest(data)


def reseal(package, declarations):
    """Fault/variation fixtures remain explicitly synthetic; preserve lineage of changes."""
    package["source_rows"] = [
        dict(
            id=r["source_row_id"],
            sheet=r["source_sheet"],
            sheet_index=0,
            row_number=i + 1,
            headers=["SYNTHETIC-fact"],
            cells=[dict(text=canonical(r), kind="text")],
        )
        for i, r in enumerate(package["records"])
    ]
    package["source_file_sha256"] = digest(package["source_rows"])
    package["summary"]["record_count"] = len(package["records"])
    package["summary"]["source_row_count"] = len(package["source_rows"])
    from collections import Counter

    package["summary"].update(
        kind_counts={
            k: sum(r["kind"] == k for r in package["records"])
            for k in ("AREA", "EVENT", "PHENOLOGY")
        },
        state_counts={
            state: sum(state in r["states"] for r in package["records"])
            for state in (
                "VALID_STRUCTURE",
                "PARTIAL",
                "CONFLICT",
                "UNMAPPED",
                "SOURCE_AUTHORITY_NOT_PROVEN",
                "PIT_NOT_PROVEN",
            )
        },
        season_counts=dict(Counter(r["scope"]["season"] for r in package["records"])),
        issue_counts=dict(Counter(i["code"] for r in package["records"] for i in r["issues"])),
        base_count=len({r["scope"]["base"] for r in package["records"]}),
        variety_count=len({r["scope"]["variety"] for r in package["records"]}),
        structurally_complete_count=0,
    )
    seal(package)
    declarations["package_sha256"] = package["preparation_sha256"]
    for r in package["records"]:
        if r["record_id"] in declarations["record_clocks"]:
            declarations["record_clocks"][r["record_id"]]["record_sha256"] = digest(r)


def fixture():
    vocab = json.loads(
        subprocess.check_output(
            ["git", "show", f"{BASE}:frontend/src/dashboard/agronomic/v0_20_vocabulary.json"],
            cwd=ROOT,
        )
    )
    package = dict(
        schema_version="V0_20_AGRONOMIC_PREPARATION_R1",
        version="0.20.0",
        data_class="SYNTHETIC_TEST_FIXTURE",
        source_file_sha256="",
        mapping_sha256=digest([]),
        vocabulary_sha256=digest(vocab),
        upstream=vocab,
        plans=[],
        source_rows=[],
        records=[],
        summary=dict(record_count=0, source_row_count=0, research_admitted_count=0),
        restrictions={
            k: False
            for k in [
                "source_authority_proven",
                "strict_pit_validated",
                "model_use_authorized",
                "prediction_adjustment_authorized",
                "production_database_writes",
                "real_data_verified",
                "formal_version_complete",
            ]
        },
    )
    declarations = dict(
        schema_version="V0_21_S1_DECLARATIONS_R1",
        data_class="SYNTHETIC_TEST_FIXTURE",
        package_sha256="",
        members=[],
        cycles=[],
        origins=[],
        record_clocks={},
    )
    systems = ["DECIDUOUS_NATURAL", "DECIDUOUS_FORCING", "EVERGREEN"]
    for year in (2023, 2024):
        season = f"{year}-{year + 1}"
        for i, system in enumerate(systems):
            cid = f"SYN-CYCLE-{i}-{year}"
            start = f"{year}-08-20" if year == 2023 else f"{year}-09-10"
            declarations["cycles"].append(
                dict(
                    cycle_id=cid,
                    base=f"SYN-BASE-{i}",
                    season=season,
                    start=span(start),
                    clocks=clock(start),
                )
            )
            declarations["origins"].append(
                dict(
                    origin_id=f"SYN-ORIGIN-{i}-{year}",
                    base=f"SYN-BASE-{i}",
                    season=season,
                    origin_date=f"{year + 1}-03-01",
                    timezone="Asia/Shanghai",
                    cutoff=f"{year + 1}-03-01T08:00:00+08:00",
                )
            )
            for plot in range(2 if i == 0 else 1):
                member = dict(
                    member_id=f"SYN-MEMBER-{i}-{plot}-{year}",
                    cycle_id=cid,
                    scope=dict(
                        base=f"SYN-BASE-{i}",
                        farm=f"SYN-FARM-{i}",
                        subfarm=f"SYN-SUB-{plot}",
                        plot=f"SYN-PLOT-{plot}",
                        variety=f"SYN-VARIETY-{plot}",
                        season=season,
                        production_system=system,
                    ),
                    provenance="SYNTHETIC_EXPLICIT_RELATIONSHIP",
                    known_at=f"{year}-07-01T10:00:00+08:00",
                    evidence_reference="SYNTHETIC-member-relation-not-master-data",
                    primary_pruning=[],
                    intervals=[],
                )
                declarations["members"].append(member)
                for label, kind, raw, canonical_type, day, state in [
                    (
                        "prune",
                        "EVENT",
                        "PRUNING",
                        "PRUNING",
                        f"{year}-09-{15 + plot:02}",
                        "OBSERVED",
                    ),
                    ("prune2", "EVENT", "PRUNING", "PRUNING", f"{year}-10-03", "OBSERVED"),
                    (
                        "bloom",
                        "PHENOLOGY",
                        "盛花",
                        "flowering_peak_date",
                        f"{year + 1}-02-28",
                        "OBSERVED",
                    ),
                    ("b50", "PHENOLOGY", "BLOOM_50", "BLOOM_50", f"{year + 1}-02-28", "OBSERVED"),
                    ("forcing", "EVENT", "促早日期", None, f"{year}-10-02", "OBSERVED"),
                    ("planned", "EVENT", "PRUNING", "PRUNING", f"{year + 1}-04-01", "PLANNED"),
                ]:
                    rid = member["member_id"] + "-" + label
                    event = (
                        dict(
                            raw_type=raw,
                            canonical_type=canonical_type,
                            method="UNKNOWN" if label == "forcing" else "SYNTHETIC-method",
                            pruning_type="SYNTHETIC",
                            operation_count="1",
                            intensity_mode="PRESENCE_ONLY",
                            intensity_value=None,
                            intensity_unit=None,
                            intensity_denominator=None,
                            end_date=span(),
                        )
                        if kind == "EVENT"
                        else None
                    )
                    pheno = (
                        dict(
                            raw_stage=raw,
                            canonical_stage="BLOOM_50" if label == "b50" else None,
                            production_plan_field="flowering_peak_date"
                            if label == "bloom"
                            else None,
                            method="SYNTHETIC-method",
                            sample_scope="SYNTHETIC-10-plants",
                            quality_status="SYNTHETIC_DECLARED",
                        )
                        if kind == "PHENOLOGY"
                        else None
                    )
                    r = dict(
                        record_id=rid,
                        kind=kind,
                        source_row_id=rid + "-row",
                        source_sheet="SYNTHETIC",
                        source_row=len(package["records"]) + 1,
                        source_columns={},
                        slot=None,
                        scope={
                            **copy.deepcopy(member["scope"]),
                            "resolved": None,
                            "plot_authority_id": None,
                        },
                        logical_id=rid,
                        revision_id="r1",
                        supersedes_revision=None,
                        observed_or_planned=state,
                        source_reference="SYNTHETIC-normalized-facts",
                        source_version="SYN-R1",
                        business_date=span(day),
                        recorded_at=span(),
                        known_at=span(),
                        observed_at=span(),
                        area=None,
                        event=event,
                        phenology=pheno,
                        issues=[],
                        states=["UNMAPPED", "SOURCE_AUTHORITY_NOT_PROVEN", "PIT_NOT_PROVEN"],
                    )
                    package["records"].append(r)
                    declarations["record_clocks"][rid] = dict(
                        record_sha256="",
                        **clock(
                            f"{year}-11-01" if state == "PLANNED" else day,
                            planned=state == "PLANNED",
                        ),
                    )
                    if label == "prune":
                        member["primary_pruning"] = [rid]
                    if label == "bloom":
                        member["intervals"].append(
                            dict(
                                interval_id="pruning_to_generic_peak",
                                start_record_id=member["primary_pruning"][0],
                                end_record_id=rid,
                            )
                        )
    reseal(package, declarations)
    return package, declarations


def producer_fixture():
    """Untouched output of the existing V020 parser/preparer, plus explicit S1 links."""
    package = json.loads(
        (
            ROOT / "backend/tests/agronomic_history/fixtures/v0_21_original_v020_package.json"
        ).read_bytes()
    )
    declarations = dict(
        schema_version="V0_21_S1_DECLARATIONS_R1",
        data_class="SYNTHETIC_TEST_FIXTURE",
        package_sha256=package["preparation_sha256"],
        members=[],
        cycles=[],
        origins=[],
        record_clocks={},
    )
    keys = ("base", "farm", "subfarm", "plot", "variety", "season", "production_system")
    scopes = {tuple(r["scope"][k] for k in keys) for r in package["records"]}
    cycle_keys = sorted({(s[0], s[5]) for s in scopes})
    for base, season in cycle_keys:
        year = int(season[:4])
        start = f"{year}-08-20" if year == 2023 else f"{year}-09-01"
        cid = f"SYN-PRODUCER-CYCLE-{base}-{season}"
        declarations["cycles"].append(
            dict(cycle_id=cid, base=base, season=season, start=span(start), clocks=clock(start))
        )
        declarations["origins"].append(
            dict(
                origin_id=f"SYN-PRODUCER-ORIGIN-{base}-{season}",
                base=base,
                season=season,
                origin_date=f"{year + 1}-03-01",
                timezone="Asia/Shanghai",
                cutoff=f"{year + 1}-03-01T08:00:00+08:00",
            )
        )
    for i, scope in enumerate(sorted(scopes)):
        rows = [r for r in package["records"] if tuple(r["scope"][k] for k in keys) == scope]
        primary = next(r for r in rows if (r["slot"] or {}).get("id") == "prune1")
        declarations["members"].append(
            dict(
                member_id=f"SYN-PRODUCER-MEMBER-{i}",
                cycle_id=f"SYN-PRODUCER-CYCLE-{scope[0]}-{scope[5]}",
                scope=dict(zip(keys, scope, strict=True)),
                provenance="SYNTHETIC_EXPLICIT_RELATIONSHIP",
                known_at=f"{scope[5][:4]}-08-01T10:00:00+08:00",
                evidence_reference="SYNTHETIC-existing-raw-keys-not-plot-authority",
                primary_pruning=[primary["record_id"]],
                intervals=[],
            )
        )
    for r in package["records"]:
        if r["kind"] == "AREA":
            continue
        day = r["business_date"]["upper_date"]
        declarations["record_clocks"][r["record_id"]] = dict(
            record_sha256=digest(r),
            provenance="SYNTHETIC_EXPLICIT_CLOCKS",
            observed_at=day + "T17:00:00+08:00",
            recorded_at=r["recorded_at"]["lower_date"] + "T18:00:00+08:00",
            known_at=r["known_at"]["lower_date"] + "T19:00:00+08:00",
            evidence_reference="SYNTHETIC-independent-clock-witness-not-real-authority",
        )
    return package, declarations


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    args.output.mkdir(mode=0o700)
    for name, data in zip(
        ("synthetic-v020-package.json", "synthetic-declarations.json"), fixture(), strict=True
    ):
        p = args.output / name
        with p.open("x") as f:
            f.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        p.chmod(0o600)
