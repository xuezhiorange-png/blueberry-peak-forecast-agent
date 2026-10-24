"""Create explicit public SYNTHETIC S8-contract packages; no real source discovery.

python -m backend.tests.rolling_forecast.source_readiness_package --scenario complete
    --output-dir /tmp/SYNTHETIC-s9-package
The isolated catalog has NO capabilities and is never installed into settings.
"""

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from backend.app.rolling_forecast.inbound import Index
from backend.app.rolling_forecast.model_artifacts import ModelReference
from backend.app.rolling_forecast.policy import Catalog
from backend.app.rolling_forecast.source_readiness_report import new_directory
from backend.app.rolling_forecast.source_requirements import template
from backend.research.v019_synthetic_validation import digest
from backend.tests.rolling_forecast.inbound_fixture import fixture, write

MODEL_FILE_SHA256 = "204bd74e90a9cc64a298c975f572e2c2388a44cca398455250e2e53713ab3c3a"
SCENARIOS = (
    "complete",
    "missing-day",
    "partial-member",
    "confirmed-zero",
    "late-record",
    "duplicate-revision",
    "basis-conflict",
    "fit-mismatch",
    "metadata-only",
)


def frozen_reference(directory: Path) -> ModelReference:
    path = Path(__file__).parent / "fixtures/SYNTHETIC-s8-frozen-models.json"
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != MODEL_FILE_SHA256:
        raise ValueError("SYNTHETIC_FROZEN_FIXTURE_MISMATCH")
    target = directory / "SYNTHETIC-models.json"
    with target.open("xb") as file:
        target.chmod(0o600)
        file.write(raw)
    return ModelReference(
        reference="SYNTHETIC",
        path=str(target.resolve()),
        file_sha256=MODEL_FILE_SHA256,
        fit_sha256="8686a68cff4679ceea09572faa91cc1793d22fbe84b065122573413ba2aa58a7",
        source_code_identity="a" * 64,
        source_code_sha="0" * 40,
        provenance="SYNTHETIC_TEST_FIXTURE",
        model_training_target_quantity_basis="RECORDED_INBOUND_WEIGHT",
    )


def create_package(
    output_dir: Path, scenario: str = "complete", *, principal_id: str | None = None
) -> tuple[Catalog, Path]:
    if scenario not in SCENARIOS:
        raise ValueError("UNKNOWN_SYNTHETIC_SCENARIO")
    root = new_directory(output_dir)
    model = frozen_reference(root)

    def mutate(i: int, day: dict[str, Any]) -> None:
        if i != 34:
            return
        if scenario in ("missing-day", "confirmed-zero"):
            day["records"] = []
        elif scenario == "late-record":
            day["records"][0]["server_ingested_at"] = "2026-11-06T10:00:00Z"
        elif scenario == "duplicate-revision":
            day["records"] *= 2

    original = fixture(
        root / "source",
        principal_id=principal_id or "SYNTHETIC-user",
        mutate=mutate,
        frozen_model_reference=model,
    )
    value = original.model_dump(mode="json")
    context = value["contexts"][0]
    source = context["snapshots"][0]
    index = json.loads(Path(source["manifest_path"]).read_bytes())
    if scenario == "partial-member":
        index["days"][34]["member_coverage"] = []
    elif scenario == "basis-conflict":
        index["physical_definition"]["measure"] = "NET_WEIGHT"
        source["physical_definition_hash"] = digest(index["physical_definition"])
    elif scenario == "fit-mismatch":
        source["target_binding"]["fit_sha256"] = "9" * 64
    elif scenario == "metadata-only":
        for item in index["days"]:
            item["known_at"] = None
            item["completeness_status"] = "UNKNOWN"
    if scenario == "confirmed-zero":
        source["confirmed_zero_dates"] = ["2026-11-04"]
    index = Index.model_validate(index).model_dump(mode="json")
    if scenario == "missing-day":
        index["days"] = [d for d in index["days"] if d["business_date"] != "2026-11-04"]
    # Day files remain under source/; this index is also located there.
    manifest = root / "source/scenario-manifest.json"
    source.update(
        manifest_path=str(manifest.resolve()),
        manifest_sha256=write(manifest, index),
        snapshot_hash=digest(index),
    )
    # No labels are required for readiness and no test package enrolls evaluation resources.
    context["review_snapshots"] = []
    value["revision"] = "SYNTHETIC-S9-" + scenario
    if principal_id is None:
        value["capabilities"] = []
    catalog = Catalog.model_validate(value)
    path = root / "SYNTHETIC-catalog.json"
    write(path, catalog.model_dump(mode="json"))
    write(root / "source-requirements-v1.json", template().model_dump(mode="json"))
    write(
        root / "SYNTHETIC-package.json",
        dict(
            data_class="SYNTHETIC_TEST_FIXTURE",
            scenario=scenario,
            auto_enrolled=False,
            source_authority_created=False,
            model_refit=False,
            source_snapshot_hash=source["snapshot_hash"],
            frozen_model_file_sha256=MODEL_FILE_SHA256,
        ),
    )
    return catalog, path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=SCENARIOS, default="complete")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    _, path = create_package(args.output_dir, args.scenario)
    print(
        json.dumps(
            dict(data_class="SYNTHETIC_TEST_FIXTURE", catalog=str(path), auto_enrolled=False)
        )
    )


if __name__ == "__main__":
    main()
