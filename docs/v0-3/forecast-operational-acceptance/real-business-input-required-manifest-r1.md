# V0.3 real business input required manifest R1

```text
TASK_ID=V0_3_REAL_BUSINESS_INPUT_MATERIALIZATION_AND_FIRST_FORECAST_R1
MANIFEST_VERSION=v0.3-real-business-input-required-manifest-v1
RESULT=REAL_BUSINESS_INPUT_REQUIRED
CURRENT_REAL_BUSINESS_SOURCE_FOUND=false
CURRENT_REAL_BUSINESS_SOURCE_CLASS=NOT_LOCATED_IN_AUTHORIZED_ENVIRONMENT
CURRENT_REAL_FORECAST_CAPABILITY=BLOCKED_REAL_BUSINESS_INPUT_NOT_PROVIDED
```

## Purpose and authority boundary

This manifest is the minimum input contract for a future normal V0.3 business
Forecast. It is not a fixture, a reconstructed historical package, a model
experiment, or an instruction to create authority rows. The package must be
provided by an authorized business/data owner and must be loaded through the
repository-owned ingestion and application paths.

The following are explicitly not acceptable substitutes:

- `data/raw` historical receipt workbooks;
- files under `data/templates`, including `production_plans.csv`;
- SOURCE-002 TRAIN, VALIDATION, or TEST materializations;
- test fixtures, CI databases, task-isolated databases, or old demo runtimes;
- manually authored values, synthetic forecasts, backfilled captures, or data
  assembled from known outcomes.

## Required package

Every field below is required unless marked optional. Each supplied object must
also carry source provenance (`source_system`, `source_record_key`, `source_version`,
`available_at`, `source_owner`, and an authorized content identity). Secrets,
tokens, and passwords must remain outside Git and evidence.

### 1. Source and runtime provenance

| Field | Requirement |
| --- | --- |
| `source_system` | Authorized current business source identifier. |
| `source_record_key` | Stable source-side record or package key. |
| `source_version` | Source version or extraction revision. |
| `source_as_of` | Source observation/effective timestamp. |
| `source_owner` | Business/data owner accountable for the source. |
| `authorization_record` | Reference proving the source may be used by the pilot runtime. |
| `content_sha256` | SHA-256 of the supplied object or canonical record set. |
| `byte_count` | Required for a file/object source. |
| `available_at` | Time at which the input became available to the forecast authority. |

### 2. Master and operational scope

The scope must resolve without ambiguity to the current business entities:

- `farm_id`, `farm_code`, `farm_name`;
- `subfarm_id`, `subfarm_code`, `subfarm_name`;
- `season_id`, `season_code`;
- `variety_id`, `variety_code`;
- `factory_id`, `factory_code`, `factory_name`, and active status;
- required farm/location timezone and climate/weather mapping identities;
- active/effective status and source hashes for each relationship.

Concrete Trial Forecast scope requires a subfarm and an active destination
factory. A farm-total or variety-collapsed substitute is not sufficient.

### 3. Production plan authority

The current plan must be supplied through
`backend.app.planning.plan_importer.import_production_plans_csv` or its
equivalent server-owned API path. At minimum, the resolved
`FarmSeasonVarietyPlan` must bind:

- `farm_name`, `subfarm_name` when applicable, `season_code`, `variety_code`;
- `planted_area_mu`;
- `expected_yield_kg_per_mu`;
- planting/phenology dates used by the current model;
- `expected_total_marketable_kg` when required by the forecast request;
- `marketable_rate` only as a source plan field, never as a substitute for the
  separate active marketable retention policy;
- `version`, `effective_from`, `effective_to`, `available_at`;
- `source_type`, `source_name`, `source_version`, and the resulting plan hash.

The importer alone does not establish complete Forecast authority. Master data,
scope relationships, active factory, and the policy below must resolve too.

### 4. Active marketable retention policy

The runtime must load an existing active policy, not infer one from the plan
row. The policy header and every scoped entry must provide:

- `public_policy_hash`, `policy_version`, `source_system`,
  `source_record_key`, `available_at`, `effective_from`, `effective_to`,
  `status=ACTIVE`, and `row_set_hash`;
- one entry for each `farm_id × subfarm_id × variety_id` scope;
- `sorting_retention_rate`, `postharvest_retention_rate`, `source_version`,
  and `row_hash` for every entry.

No policy row may be inserted by this manifest task.

### 5. Task8 maturity authority

The normal maturity path must have a completed current authority bound to the
same cutoff and scope:

- `maturity_model_run_id` and model/artifact identity;
- `maturity_forecast_run_id`;
- completed status, result hash, artifact hash, and code authority identity;
- complete daily P50/P80/P90 prediction rows;
- resolved model inputs and lineage, including the required analytics/receipt,
  base-temperature, location/weather mapping, and effective weather authority;
- forecast cutoff and availability timestamps proving point-in-time visibility.

The existing maturity service is a consumer of these authorities; this
manifest does not authorize synthetic Task8 output.

### 6. Task9 harvest-state authority

The normal harvest-state path must have a completed run whose request is bound
to the same season, scope, cutoff, and Task8 result. The input package must
make available, as applicable:

- season identity, `as_of_date`, forecast start/end, destination factory and
  timezones;
- canonical `[P50, P80, P90]` quantiles;
- holiday calendar version/hash/dates;
- weather rule configuration;
- parameter source references;
- capacity pools, daily capacity inputs, and daily weather features;
- persisted Task8 daily predictions with verification snapshots;
- initial inventory cohorts/opening inventory and mature-inventory loss inputs;
- completed Task9 status, result hash, and source lineage.

No Task9 run may be fabricated from a plan or from known actual outcomes.

### 7. Forecast execution actor and runtime binding

Before a normal Forecast request, the runtime owner must provide a non-default
database binding at current Alembic head, externalized credentials, and a
server-owned actor configuration loaded by
`backend.app.actual_harvest_import.api_auth.get_actual_harvest_actor`.
The actor must have the minimum permitted operations for reading input
authority, creating/reading/exporting a Forecast, and must be explicitly
non-production if this is an acceptance runtime.

## Acceptance gate

The package is complete only when the canonical input-authority resolver returns
at least one fully resolved item and a normal
`POST /api/v1/trial/forecasts` can be executed without direct retention calls,
fixture overrides, or TEST access. Completion then requires persisted Forecast
output, natural production-authority capture, and fresh-session
`load_pit_visible_forecast_authority` readback.

Until that package is provided, the required next action is:

```text
NEXT_REQUIRED_ACTION=COORDINATOR_PROVIDE_CURRENT_BUSINESS_INPUT_PACKAGE
```
