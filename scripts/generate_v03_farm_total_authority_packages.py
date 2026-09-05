#!/usr/bin/env python3
"""Generate V0.3 Farm-total authority packages from reviewed R2/R3 reconciliation output.

Reads a reviewed mapping table JSON (from R2 output) and emits:
- mapping package JSON
- area authority package JSON (31 eligible PREVIOUS_SEASON_PROXY rows)

Does NOT read raw Excel at runtime. Intended for controlled local generation only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.app.forecast_quality.farm_total_area_authority import (  # noqa: E402
    area_authority_package_to_payload,
    build_area_authority_package,
    build_area_authority_row,
)
from backend.app.forecast_quality.farm_total_group_mapping import (  # noqa: E402
    build_mapping_package,
    build_mapping_row,
    mapping_package_to_payload,
)
from backend.app.forecast_quality.farm_total_policy import (  # noqa: E402
    AREA_AUTHORITY_CLASS_PREVIOUS_SEASON_PROXY,
    CONFLICT_EXCLUDED_BASELINE_FARM_GROUPS,
    EXCLUSION_REASON_TEMPORAL_CONFLICT,
    FARM_TOTAL_MAPPING_POLICY_VERSION,
    FARM_TOTAL_PRIOR_AREA_SOURCE_SEASON,
    REVIEWED_ELIGIBLE_PROXY_AREA_MU,
    REVIEWED_ELIGIBLE_PROXY_GROUP_COUNT,
)


def _extract_mapping_table(text: str) -> list[dict]:
    match = re.search(r"BASELINE_FARM_GROUP_MAPPING_TABLE=(\[.*\])\n", text)
    if not match:
        raise RuntimeError("BASELINE_FARM_GROUP_MAPPING_TABLE not found in review output")
    return json.loads(match.group(1))


PRIOR_AREA_EVIDENCE_HASH_KEY = "prior_area_evidence_file"


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_prior_area_evidence_hash(
    *,
    prior_area_evidence_path: Path | None,
    allow_synthetic: bool,
) -> str | None:
    if prior_area_evidence_path is None or not prior_area_evidence_path.exists():
        if allow_synthetic:
            return None
        raise SystemExit(
            "real package generation requires --prior-area-evidence-path "
            "pointing to the prior-area evidence workbook"
        )


def _build_reviewed_area_source_row_ref(
    *,
    review_evidence_hash: str,
    prior_area_evidence_hash: str | None,
    group_key: str,
    area_member_names: list[str] | None,
) -> str:
    members = ",".join(sorted(area_member_names or []))
    evidence_part = prior_area_evidence_hash or "synthetic"
    return (
        f"reviewed-r2-area-membership:{review_evidence_hash}:{evidence_part}:{group_key}:{members}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--review-output",
        type=Path,
        required=True,
        help="Path to baseline_farm_group_reconciliation_r2_output.txt",
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--prior-area-source-identity",
        default="25产季产量预测汇总表",
        help="Semantic identity for prior-season area evidence",
    )
    parser.add_argument(
        "--prior-area-evidence-path",
        type=Path,
        default=None,
        help="Path to prior-area evidence workbook (required for real generation)",
    )
    parser.add_argument(
        "--allow-synthetic-source-hashes",
        action="store_true",
        help="Allow generation without prior-area evidence workbook (tests only)",
    )
    args = parser.parse_args()

    review_text = args.review_output.read_text(encoding="utf-8")
    review_evidence_hash = hashlib.sha256(review_text.encode()).hexdigest()
    prior_area_evidence_hash = _require_prior_area_evidence_hash(
        prior_area_evidence_path=args.prior_area_evidence_path,
        allow_synthetic=args.allow_synthetic_source_hashes,
    )
    mapping_table = _extract_mapping_table(review_text)

    mapping_rows = []
    area_rows = []
    eligible_area_total = Decimal("0")

    for entry in mapping_table:
        group_key = entry["baseline_farm_group"]
        source_keys = tuple(sorted(entry["source_farm_business_keys"]))
        rel_type = entry["mapping_relationship_type"]
        if group_key in CONFLICT_EXCLUDED_BASELINE_FARM_GROUPS:
            mapping_rows.append(
                build_mapping_row(
                    baseline_farm_group_key=group_key,
                    source_farm_business_keys=source_keys,
                    mapping_relationship_type=rel_type,
                    exclusion_status="EXCLUDED_CONFLICT",
                    exclusion_reason=EXCLUSION_REASON_TEMPORAL_CONFLICT,
                )
            )
            continue

        mapping_rows.append(
            build_mapping_row(
                baseline_farm_group_key=group_key,
                source_farm_business_keys=source_keys,
                mapping_relationship_type=rel_type,
                exclusion_status="ELIGIBLE",
                exclusion_reason=None,
            )
        )
        area_mu = Decimal(str(entry["farm_total_area_mu"]))
        area_source_hash = hashlib.sha256(
            f"{group_key}|{area_mu}|{args.prior_area_source_identity}".encode()
        ).hexdigest()
        source_row_ref = _build_reviewed_area_source_row_ref(
            review_evidence_hash=review_evidence_hash,
            prior_area_evidence_hash=prior_area_evidence_hash,
            group_key=group_key,
            area_member_names=entry.get("area_member_names"),
        )
        area_rows.append(
            build_area_authority_row(
                baseline_farm_group_key=group_key,
                source_farm_business_keys=source_keys,
                area_mu=area_mu,
                area_authority_class=AREA_AUTHORITY_CLASS_PREVIOUS_SEASON_PROXY,
                area_source_season=FARM_TOTAL_PRIOR_AREA_SOURCE_SEASON,
                area_source_identity=args.prior_area_source_identity,
                area_source_hash=area_source_hash,
                mapping_policy_version=FARM_TOTAL_MAPPING_POLICY_VERSION,
                mapping_identity_hash="",
                source_row_refs=(source_row_ref,),
            )
        )
        eligible_area_total += area_mu

    mapping_package = build_mapping_package(rows=tuple(mapping_rows))
    area_rows_with_mapping_hash = []
    for row in area_rows:
        area_rows_with_mapping_hash.append(
            build_area_authority_row(
                baseline_farm_group_key=row.baseline_farm_group_key,
                source_farm_business_keys=row.source_farm_business_keys,
                area_mu=row.area_mu,
                area_authority_class=row.area_authority_class,
                area_source_season=row.area_source_season,
                area_source_identity=row.area_source_identity,
                area_source_hash=row.area_source_hash,
                mapping_policy_version=row.mapping_policy_version,
                mapping_identity_hash=mapping_package.mapping_set_sha256,
                source_row_refs=row.source_row_refs,
            )
        )

    source_hashes: list[tuple[str, str]] = [("reviewed_r2_mapping_table", review_evidence_hash)]
    if prior_area_evidence_hash is not None:
        source_hashes.append((PRIOR_AREA_EVIDENCE_HASH_KEY, prior_area_evidence_hash))

    area_package = build_area_authority_package(
        rows=tuple(area_rows_with_mapping_hash),
        source_file_hashes=tuple(source_hashes),
        mapping_policy_version=FARM_TOTAL_MAPPING_POLICY_VERSION,
        mapping_identity_hash=mapping_package.mapping_set_sha256,
    )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    mapping_path = args.out_dir / "farm_total_group_mapping_package.json"
    area_path = args.out_dir / "farm_total_area_authority_package.json"
    mapping_path.write_text(
        json.dumps(mapping_package_to_payload(mapping_package), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    area_path.write_text(
        json.dumps(area_authority_package_to_payload(area_package), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    eligible_count = len(area_rows_with_mapping_hash)
    if eligible_count != REVIEWED_ELIGIBLE_PROXY_GROUP_COUNT:
        raise SystemExit(
            f"eligible group count mismatch: "
            f"{eligible_count} != {REVIEWED_ELIGIBLE_PROXY_GROUP_COUNT}"
        )
    reviewed_area = Decimal(REVIEWED_ELIGIBLE_PROXY_AREA_MU)
    if eligible_area_total.quantize(Decimal("0.000001")) != reviewed_area.quantize(
        Decimal("0.000001")
    ):
        raise SystemExit(f"eligible area mismatch: {eligible_area_total} != {reviewed_area}")

    print(f"FARM_GROUP_MAPPING_SET_SHA256={mapping_package.mapping_set_sha256}")
    print(f"FARM_AREA_AUTHORITY_SET_SHA256={area_package.area_authority_set_sha256}")
    print(f"ELIGIBLE_FARM_GROUP_COUNT={eligible_count}")
    print(f"AUTHORIZED_AREA_MU={eligible_area_total}")
    print(f"MAPPING_PACKAGE_PATH={mapping_path}")
    print(f"AREA_AUTHORITY_PACKAGE_PATH={area_path}")


if __name__ == "__main__":
    main()
