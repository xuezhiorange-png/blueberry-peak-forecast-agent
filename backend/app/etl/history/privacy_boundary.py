"""Deterministic privacy review roles, not publication or deletion authority."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import yaml

BASELINE = "e2d0ffa233483821e4fed3d429e317510dfcfcc1"
_DOC = "docs/tech-debt/"
INPUT_PINS = {
    _DOC + "td01c-public-derived-risk-register.csv": "c2c7dd1b3fef990d9795792fc82a9fc87066cfac",
    _DOC + "td01c-public-derived-audit-summary.json": "a7befde6f8a5e11f7993d864d0b7969786ee05a0",
    _DOC + "td01b-public-ref-exposure-r1.csv": "b1c04917bbbedd56a09d522ccba51b329c36ebaa",
    _DOC
    + "td01c-historical-contract-migration-plan-r1.md": "b5113114db95a89ce9dad7a6d0d0c0052037664e",
}
INPUT_PATHS = tuple(INPUT_PINS)
EXPECTED_COUNTS = {
    "CODE_SCHEMA_OR_POSSIBLE_LITERAL": 418,
    "FROZEN_REPORT_OR_EVIDENCE": 1121,
    "CONFIGURATION_OR_PUBLIC_TEXT": 107,
    "LARGE_PUBLIC_REPORT_TEXT_STREAMED": 7,
    "COMPRESSED_FIXTURE_METADATA_ONLY": 5,
}
CLASSES = {
    "PUBLIC_CODE",
    "PUBLIC_SYNTHETIC",
    "POSSIBLE_REAL_BUSINESS_INFORMATION",
    "FROZEN_HISTORICAL_EVIDENCE",
    "COMPRESSED_CONTENT_NOT_INSPECTED",
    "NEEDS_OWNER_DECISION",
}
PRIORITY_CONFIGS = (
    "configs/factory_aliases.yaml",
    "configs/base_registry_s1.json",
    "configs/v0_5_base_reference_registry_v1.json",
    "configs/production_plan.yaml",
    "configs/v0_8_s4_three_season_area_authority_r1.json",
    "configs/v0_8_s6_no_record_zero_semantics_r1.json",
    "configs/v0_8_cross_season_identity_authority_r1.json",
)
DECISIONS = (
    ("D01", "原始 Legacy XLS", "PRIVATE_REAL", "另行批准私有保管与真实历史移除；本轮不执行"),
    ("D02", "精确基地与工厂关联", "OWNER_REVIEW", "复核当前公开结构；不复制关系或据此批准公开"),
    (
        "D03",
        "真实精确产量、面积与统计",
        "OWNER_REVIEW",
        "确认真实性与公开边界；不改原训练数据和经营事实",
    ),
    ("D04", "算法、Schema与程序代码", "PUBLIC_CODE", "保留正常代码；精确经营字面量仍需单独复核"),
    ("D05", "独立合成样本", "PUBLIC_SYNTHETIC", "仅放行可信生成器可复算的完整产物；标签不是许可"),
    (
        "D06",
        "冻结历史研究证据",
        "PRESERVE_AND_REVIEW",
        "保留原事实与Hash；不推定全部敏感或全部可公开",
    ),
    ("D07", "五个压缩测试资产", "UNVERIFIED", "只核对Git元数据；来源与公开许可单独确认"),
    (
        "D08",
        "真实Git历史及Tag/Release处置",
        "SEPARATE_APPROVAL_REQUIRED",
        "先验证定位兼容迁移，再单独批准不可逆远端操作",
    ),
    (
        "D09",
        "私有真实源保管、读取与审计",
        "SEPARATE_APPROVAL_REQUIRED",
        "分别确定保管人、访问范围、审计与回滚；不转为公开源",
    ),
)


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _pinned_inputs(root: Path) -> dict[str, bytes]:
    result = {}
    for path, oid in INPUT_PINS.items():
        data = (root / path).read_bytes()
        if git_blob(data) != oid:
            raise ValueError("PINNED_INPUT_CHANGED: " + path)
        result[path] = data
    return result


def classify_row(row: dict[str, str], structural: bool = False) -> dict[str, str]:
    kind = row["ASSET_CLASS"]
    if kind == "CODE_SCHEMA_OR_POSSIBLE_LITERAL":
        tier, strength, reason, group = (
            "PUBLIC_CODE",
            "CODE_ROLE_ONLY",
            "FIELD_NAMES_DO_NOT_CONFIRM_BUSINESS_RECORDS",
            "D04",
        )
    elif kind in {"FROZEN_REPORT_OR_EVIDENCE", "LARGE_PUBLIC_REPORT_TEXT_STREAMED"}:
        tier, strength, reason, group = (
            "FROZEN_HISTORICAL_EVIDENCE",
            "HISTORICAL_ROLE_ONLY",
            "PRESERVE_FACTS_REVIEW_CONFIDENTIALITY_SEPARATELY",
            "D06",
        )
    elif kind == "COMPRESSED_FIXTURE_METADATA_ONLY":
        tier, strength, reason, group = (
            "COMPRESSED_CONTENT_NOT_INSPECTED",
            "GIT_METADATA_ONLY",
            "NO_CONTENT_INSPECTION_OR_PUBLICATION_PROOF",
            "D07",
        )
    else:
        tier = "POSSIBLE_REAL_BUSINESS_INFORMATION" if structural else "NEEDS_OWNER_DECISION"
        strength = "CURRENT_PUBLIC_STRUCTURE_ONLY" if structural else "ORIGINAL_TEXT_INDICATOR_ONLY"
        reason = "STRUCTURE_IS_NOT_PROOF_OF_REALNESS_OR_PERMISSION"
        group = "D02" if row["PATH"] in PRIORITY_CONFIGS[:3] else "D03"
    identity = hashlib.sha256(
        json.dumps(row, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    return {
        **row,
        "ORIGINAL_ROW_SHA256": identity,
        "CLASSIFICATION": tier,
        "EVIDENCE_STRENGTH": strength,
        "REVIEW_STATE": "UNVERIFIED",
        "PUBLICATION_PERMISSION": "NOT_ESTABLISHED",
        "REASON": reason,
        "DECISION_GROUP": group,
    }


def _public_shape(value: object) -> set[str]:
    markers: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                continue
            if re.search(
                r"base_name|farm_name|factory|subfarm|variety|基地|农场|加工厂", key, re.I
            ) and isinstance(item, str):
                markers.add("IDENTITY_SCALAR_FIELDS_PRESENT")
            if re.search(r"area|weight|quantity|harvest|kg|产量|面积|亩", key, re.I) and (
                type(item) in {int, float}
                or isinstance(item, str)
                and re.fullmatch(r"-?\d+(?:\.\d+)?", item)
            ):
                markers.add("PRECISE_QUANTITY_OR_AREA_VALUES_PRESENT")
            if re.search(r"latitude|longitude|经度|纬度", key, re.I):
                markers.add("GEOLOCATION_FIELDS_PRESENT")
            if key in {"aliases", "farm_to_base", "base_members", "members"} and isinstance(
                item, (dict, list)
            ):
                markers.add("MAPPING_STRUCTURE_PRESENT")
            if re.search(r"source.*hash|source.*sha|source.*path|file_sha256", key, re.I):
                markers.add("SOURCE_IDENTITY_FIELDS_PRESENT")
            markers.update(_public_shape(item))
    elif isinstance(value, list):
        for item in value:
            markers.update(_public_shape(item))
    return markers


def structural_review(root: Path, representatives: list[str]) -> dict[str, dict[str, str]]:
    # Only explicitly named CURRENT PUBLIC text. Never source partitions or XLS.
    result = {}
    for path in dict.fromkeys([*PRIORITY_CONFIGS, *representatives]):
        target = root / path
        if not target.is_file():
            result[path] = {"status": "NOT_PRESENT", "evidence": "NO_INFERENCE"}
            continue
        if target.stat().st_size > 2_000_000:
            result[path] = {
                "status": "METADATA_ONLY_LARGE_TEXT",
                "evidence": "NO_NEW_CONTENT_INSPECTION",
            }
            continue
        text = target.read_text()
        value: object = json.loads(text) if path.endswith(".json") else yaml.safe_load(text)
        structured = isinstance(value, (dict, list))
        result[path] = {
            "status": "STRUCTURE_PRESENT" if structured else "TEXT_ONLY",
            "evidence": "CURRENT_PUBLIC_FIELDS_ONLY_VALUES_NOT_REPRODUCED",
            "shape_markers": ";".join(sorted(_public_shape(value))) or "SCHEMA_OR_METADATA_ONLY",
        }
    return result


@dataclass(frozen=True)
class Classification:
    rows: list[dict[str, str]]
    priority: list[dict[str, str]]
    decisions: list[tuple[str, str, str, str]]
    ref_rows: list[dict[str, str]]
    structures: dict[str, dict[str, str]]
    compressed_metadata: list[dict[str, str]]

    def csv_text(self) -> str:
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=list(self.rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(self.rows)
        return stream.getvalue()

    def summary(self) -> dict[str, object]:
        return {
            "task_id": "BLUEBERRY_TECH_DEBT_TD01D_PRIVACY_BOUNDARY_AND_HISTORY_DISPOSITION_GATE_R1",
            "baseline": BASELINE,
            "candidate_count": len(self.rows),
            "original_counts": dict(Counter(row["ASSET_CLASS"] for row in self.rows)),
            "classification_counts": {
                tier: sum(r["CLASSIFICATION"] == tier for r in self.rows)
                for tier in sorted(CLASSES)
            },
            "owner_decision_items": len(self.decisions),
            "priority": self.priority,
            "structural_review": self.structures,
            "compressed_metadata": self.compressed_metadata,
            "source_ref_rows": len(self.ref_rows),
            "source_tag_count": sum(r["ref"].startswith("refs/tags/") for r in self.ref_rows),
            "all_business_review_states": "UNVERIFIED",
            "publication_granted": False,
            "historical_removal_authorized": False,
            "registry_sha256": hashlib.sha256(self.csv_text().encode()).hexdigest(),
        }


def classify(root: Path) -> Classification:
    inputs = _pinned_inputs(root)
    original = list(csv.DictReader(io.StringIO(inputs[INPUT_PATHS[0]].decode())))
    if len(original) != 1658 or Counter(r["ASSET_CLASS"] for r in original) != EXPECTED_COUNTS:
        raise ValueError("ORIGINAL_CANDIDATE_IDENTITY_MISMATCH")
    summary = json.loads(inputs[INPUT_PATHS[1]])
    if hashlib.sha256(inputs[INPUT_PATHS[0]]).hexdigest() != summary["register_sha256"]:
        raise ValueError("ORIGINAL_REGISTER_HASH_MISMATCH")
    representatives = []
    for version in ("v0-8", "v0-15", "v0-19"):
        selected = sorted(
            r["PATH"]
            for r in original
            if r["PATH"].startswith(f"docs/{version}/evidence/")
            and r["PATH"].endswith(".json")
            and any(c in r["DISCLOSURE_CATEGORY"] for c in ("QUANTITY_AREA", "DAILY_CURVE"))
        )[:2]
        representatives.extend(selected)
    structures = structural_review(root, representatives)
    rows = [
        classify_row(r, structures.get(r["PATH"], {}).get("status") == "STRUCTURE_PRESENT")
        for r in original
    ]
    priority = []
    seen: set[str] = set()

    def add(selected: list[dict[str, str]], limit: int) -> None:
        for row in sorted(selected, key=lambda r: r["PATH"])[:limit]:
            if row["PATH"] not in seen:
                priority.append(row)
                seen.add(row["PATH"])

    add([r for r in rows if r["PATH"] in PRIORITY_CONFIGS], 7)
    add([r for r in rows if r["ASSET_CLASS"] == "COMPRESSED_FIXTURE_METADATA_ONLY"], 5)
    add([r for r in rows if r["PATH"] in representatives], 6)
    refs = list(csv.DictReader(io.StringIO(inputs[INPUT_PATHS[2]].decode())))
    if len(refs) != 742:
        raise ValueError("REF_INVENTORY_IDENTITY_MISMATCH")
    expected = {
        row["path"]: row["git_blob_id"] for row in summary["compressed_assets_metadata_only"]
    }
    raw = subprocess.check_output(
        ["git", "ls-tree", "-r", "-z", "HEAD", "--", *sorted(expected)],
        cwd=root,
        env={**os.environ, "GIT_NO_LAZY_FETCH": "1"},
    )
    observed = {}
    for entry in raw.split(b"\0"):
        if entry:
            meta, path = entry.split(b"\t", 1)
            observed[path.decode()] = meta.decode().split()[2]
    if expected != observed:
        raise ValueError("COMPRESSED_METADATA_IDENTITY_CHANGED")
    compressed = [
        {"path": path, "git_blob_id": oid, "evidence": "GIT_TREE_METADATA_ONLY_CONTENT_NOT_OPENED"}
        for path, oid in sorted(observed.items())
    ]
    return Classification(rows, priority, list(DECISIONS), refs, structures, compressed)


def outputs(root: Path) -> dict[str, bytes]:
    report = classify(root)
    table = [
        "# TD-01D Owner 决策总表",
        "",
        "以下全部是建议默认值，不是公开、删除、脱敏或历史改写许可。",
        "未知项继续 UNVERIFIED；字段/路径命中不等于泄露。机器清单保持全部1658条原身份。",
        "",
        "| 编号 | 决策类别 | 建议状态 | 审核边界 |",
        "| --- | --- | --- | --- |",
    ]
    table.extend("| " + " | ".join(row) + " |" for row in report.decisions)
    table.extend(
        [
            "",
            "优先对象由固定配置路径、全部压缩资产及各版本证据目录的稳定路径排序选出；",
            "完整优先路径及证据强度见同目录 summary JSON，数量受上限约束，不向 Owner 平铺1658行。",
            "生产计划属于当前公开文本的补充结构核对，不擅自添加到原1658条候选。",
            "PUBLIC_CODE 是文件角色，PUBLIC_SYNTHETIC 须独立复算；都不是任意业务字面量的公开许可。",
            "原候选没有仅凭 SYNTHETIC 标签升级；PUBLIC_SYNTHETIC 的原候选数可以为0。",
            "真实模型、原始日期/重量/空间关系/PIT不变；公开演示只允许独立合成。",
            "",
        ]
    )
    return {
        "td01d-classified-register.csv": report.csv_text().encode(),
        "td01d-classification-summary.json": (
            json.dumps(report.summary(), ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        ).encode(),
        "td01d-owner-decisions-r1.md": "\n".join(table).encode(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    generated = outputs(args.repo)
    args.output_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    for name, content in generated.items():
        with (args.output_dir / name).open("xb") as stream:
            stream.write(content)
    print(json.dumps({"classified": 1658, "decisions": 9, "public_authorization_granted": False}))


if __name__ == "__main__":
    main()
