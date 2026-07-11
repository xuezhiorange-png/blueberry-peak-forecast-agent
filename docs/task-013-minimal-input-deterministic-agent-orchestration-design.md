# TASK-013 — Minimal-Input Deterministic Forecast Agent Orchestration

> 中文名:**极简输入确定性预测 Agent 编排层**
>
> **Status:** DRAFT — design-only. **Not** implementation. **Not** migration. **Not** tests. **Not** production code. **Not** Ready. **Not** merged.
>
> **Repository:** `xuezhiorange-png/blueberry-peak-forecast-agent`
>
> **Base:** `origin/main` HEAD = `d57d382299725f349c19e3b957fa88e3591ab45d`(TASK-012 Slice E3 merge SHA)
>
> **Tracking Issue:** see "Tracking Issue" section at the end of this document.

---

## §1 Purpose

This document freezes the design of **TASK-013 — Minimal-Input Deterministic Forecast Agent Orchestration**. The product goal is to let ordinary users — who only know a farm location and a per-variety planting area — obtain a deterministic, reproducible 1–4 月 production-peak forecast, with full source citations, parameter provenance, confidence evidence, and deterministic recommendations.

The Agent is an **orchestration contract** over the deterministic services already delivered by TASK-008 through TASK-012. The Agent does not compute. The Agent does not invent. The Agent composes, cites, and explains.

This design explicitly:
- **rejects** the "read-only result explanation Agent" reduction(Option A from the source-definition round). The product is not "user supplies a `prediction_run_id`, Agent explains it". A `prediction_run_id` may be supplied as an **advanced override**, but it is not the MVP entry point.
- **rejects** the "autonomous business-control Agent" expansion(Option C from the source-definition round). The Agent must never modify farm master data, planting area, harvest plan, or processor capacity; it must never execute arbitrary SQL / shell / Python / URL; it must never reach the internet; it must never auto-publish external reports.

The Agent is bounded by three load-bearing distinctions:

| Layer | Authority | Role |
|---|---|---|
| **Deterministic services**(TASK-008–012) | Numerical authority | Compute P50/P80/P90, peaks, dates, hashes |
| **Agent orchestration contract**(TASK-013) | Routing authority | Compose services, carry identities, structure output |
| **LLM**(optional, deferred to Slice E) | Presentation only | Rephrase structured payload to natural language |

LLM is not introduced in this design round. The first implementation Slice (A/B/C) must be deliverable with a deterministic planner and a structured response only.

---

## §2 Roadmap numbering drift and source reconciliation

`CODEX_TASKS.md` is the original product roadmap. Two pieces of drift must be made explicit before any reader assumes that the "old task numbers" still describe the **current** product scope.

### §2.1 What `CODEX_TASKS.md` actually says

- `CODEX_TASKS.md` **任务 11** = "滚动预测与回测" — implemented in current `main` as TASK-011 (rolling forecast + leakage-safe backtest orchestration).
- `CODEX_TASKS.md` **任务 12** = "预测 API 与 frontend" — implemented in current `main` as TASK-012 (replay-trained model + Slice E API/CLI). The roadmap's "任务 12" sentence (which talks about minimal-input forms and frontend) **describes the product intent that TASK-013 must now own**, not TASK-012's current code.
- `CODEX_TASKS.md` **任务 13** = "Agent 编排层" — **not yet implemented**; this document freezes its design.
- `CODEX_TASKS.md` **任务 14** = "生产化" — not yet implemented; will absorb permissions, audit log persistence, monitoring, drift detection.

### §2.2 Misclassification corrections

The following incorrect inferences must be removed from any reader's mental model:

- ❌ **The claim that `PR #35` is the TASK-012 tracking issue/PR** — **WRONG**.
  - ✅ `PR #35` is a TASK-011 Phase 4a design PR (`[TASK-011][Phase 4a] Design amendment: evaluation materialization and mask foundation`). It is **not** a TASK-012 tracking Issue or PR.
  - ✅ TASK-012 had no standalone tracking Issue.
- ❌ **"TASK-012 = frontend + API" (per `CODEX_TASKS.md` 任务 12)** — **WRONG for current code**.
  - ✅ Current `main` TASK-012 = **replay-trained model** (`backend/app/rolling_backtest/replay_trained_*.py` + `backend/app/api/rolling_backtest_replay_trained.py`). It is a numerical service, not a frontend.
- ❌ **"8 个工具名 = 8 个同名 Python function"** — **WRONG**.
  - ✅ The 8 logical tool names in `CODEX_TASKS.md` 任务 13 are a **logical tool contract**, not an implementation claim. The mapping table in §11–§20 is what authorizes their existence. Only `resolve_location` has a directly-named service today; the rest are composed from existing TASK-008–012 modules.
- ❌ **"TASK-013 is read-only result explanation"** — **WRONG (rejected by §1)**.

### §2.3 Reconciliation rule

For any reader of this design:
1. The two **authoritative sources** for TASK-013 are `CODEX_TASKS.md` (high-level product intent, 8-tool list) and `docs/10_minimal_input_agent_spec.md` (212-line detailed product spec). These are the **primary contracts**.
2. TASK-013 is designed **on top of current `main` TASK-008 through TASK-012** — not on top of the "old" roadmap product boxes.
3. The "old" TASK-012 sentence in `CODEX_TASKS.md` is **redirected to TASK-013** as the future minimal-input / frontend / chat-UI surface.
4. `README.md`, `docs/13_natural_maturity_curve.md`, `docs/task-009a-design-ratification.md`, TASK-010/011/012 frozen design docs are **supporting evidence** only and may not override the two primary sources.

---

## §3 Authoritative source

### §3.1 Primary sources(frozen as the contract for TASK-013)

| Source | Path | Authority weight |
|---|---|---|
| Product roadmap — TASK-013 段 | `CODEX_TASKS.md` line 88–90 | Defines 8 logical tools + product-level boundary |
| Detailed minimal-input spec | `docs/10_minimal_input_agent_spec.md` (212 lines) | Defines user input, system inference, output contract, two modes (规划 / 动态), confidence ladder |

### §3.2 Supporting evidence(used only where non-conflicting with §3.1)

| Source | Path | What it contributes |
|---|---|---|
| Product README | `README.md` | Confirms "可选 OpenAI Agent 层:仅负责任务编排、解释和情景问答,数值计算必须调用确定性工具" |
| TASK-008 spec | `docs/13_natural_maturity_curve.md` | Natural maturity contract + downstream-consumer label "Task 13 Agent" |
| TASK-009A design | `docs/task-009a-design-ratification.md` | Authority resolution patterns + reserved `backend/app/agent/**` path |
| TASK-010 frozen designs | `docs/task-010-report-api-contract.md`, `docs/task-010-api-slice2-execution-endpoints-design.md` | Residual model API/CLI contract + explicit "this PR does NOT authorize agent workflow" guard |
| TASK-011 frozen designs | `docs/task-11-phase3-*.md`, `docs/task-11-phase4a/b/c-*.md` | Rolling backtest + evaluation materialization + reload integrity |
| TASK-012 frozen designs | `docs/task-012-replay-trained-model-design.md`, `docs/task-012-slice-e-api-cli-amendment.md` | Replay-trained model + Slice E HTTP API + idempotency + hash contract |
| Repo rules | `AGENTS.md`, `CODEX_MASTER_PROMPT.md` | Hard rules 1–14 (no fabricated tons, append-only raw, NUMERIC, etc.) |

### §3.3 Source priority rule

In any conflict between §3.1 and §3.2, §3.1 wins. In any conflict between two §3.1 sources, `docs/10_minimal_input_agent_spec.md` wins on output/input detail; `CODEX_TASKS.md` wins on tool-list boundary.

---

## §4 Product user and minimal-input journey

### §4.1 Primary user

The primary user is an **ordinary farm operator** who knows:
- the farm **location** (province / prefecture / county / township / address, or coordinates, or map pick); and
- a **per-variety planting area** (e.g. `Dx = 700 mu`, `D12 = 300 mu`).

This user **must not** be required to supply: expected per-mu yield, commodity-fruit rate, maturity curve, weather inputs, Spring-Festival staffing, harvest efficiency, or any other "advanced" parameter. These are auto-inferred.

### §4.2 Secondary user(advanced)

A power user may override any auto-inferred parameter through the **advanced override contract**(§8). Such overrides must be explicit, version-tracked, and reported back in the output's provenance block.

### §4.3 The minimal-input journey(ordinary user)

The Agent MUST execute the following deterministic steps, in this order:

1. **Location resolution** — convert textual / coordinate location input into a standard `ResolvedLocation` + `AgroClimateZone`, using a versioned location-mapping catalog.
2. **Parameter inference** — for each `(location × variety)` pair, infer:
   - 1–4 月 expected per-mu yield distribution
   - effective commodity-fruit rate distribution
   - effective total commodity-fruit volume
   - first-harvest date distribution
   - maturity-curve shape and width
   - temperature / GDD / radiation / rainfall adjustments
   - Spring-Festival harvest-implementation rate
   - post-Spring-Festival backlog-release intensity
   - historical anomaly-peak probability
3. **Daily forecast generation** — produce a per-day natural maturity curve, apply harvest-state + residual adjustment, simulate Spring-Festival + weather effects.
4. **Peak analysis** — from the daily curve, deterministically compute:
   - single-day peak (P50 / P80 / P90) + date
   - sustained 3-day peak (P50 / P80 / P90) + start date
   - peak duration
   - peak ± 7-day cumulative volume
   - per-variety contribution
5. **Scenario calculation** — default scenario is the planning scenario (no actual arrivals, no live staffing). Optional scenarios (e.g. add staffing, change Spring-Festival intensity) are exposed as advanced overrides.
6. **Forecast explanation** — assemble a structured explanation payload containing every numerical value with its source task, run identity, and hash.
- 7. **Deterministic recommendation** — apply deterministic rules + scenario outputs to produce the recommendation payload (7 categories total = 6 operational + 1 data-quality per §20).

The output **must include**:
- per-day P50/P80/P90 from season start to April 30;
- per-variety contribution;
- natural maturity volume, harvest-implementation volume, estimated backlog;
- weather / Spring-Festival tags;
- single-day peak + sustained 3-day peak + P80/P90 peak + peak duration + peak ± 7-day cumulative;
- dominant variety + contribution rate;
- per-parameter source + sample count + covered seasons + historical error;
- model + backtest performance summary;
- confidence ladder (高 / 中 / 低) with evidence;
- primary uncertainties + missing-data list;
- deterministic recommendations (7 categories total = 6 operational + 1 data-quality per §20).

---

## §5 Scope and explicit exclusions

### §5.1 In scope (this design)

- Logical orchestration of the 8 logical tools listed in `CODEX_TASKS.md` 任务 13.
- Versioned deterministic authority resolution for location, parameters, model selection, replay-trained result.
- Structured explanation payload (machine-readable) that the future LLM adapter (Slice E) may rephrase without changing authoritative values.
- Deterministic recommendation rules (7 categories total = 6 operational + 1 data-quality per §20).
- Minimal-input MVP request contract (location + variety-area rows).
- Advanced override contract for power users.
- Provenance / hash / confidence / uncertainty output contract.
- Error / blocker taxonomy.
- Anti-fabrication guardrails.
- Implementation Slice plan (Slice A–E + TASK-014 hand-off).

### §5.2 Explicit exclusions (NOT in scope)

| Excluded | Reason |
|---|---|
| Frontend / chat UI / form UI | Belongs to a separate frontend task; explicitly listed in §12 |
| Conversation persistence (跨 turn / 跨 session memory) | `CODEX_TASKS.md` 把对话审计归入 TASK-014 生产化 |
| `agent_run` / `agent_query_audit` / `agent_confirmation_log` / `agent_conversation` tables | Persistence belongs to TASK-014 or a separate TASK-013 amendment |
| Database migration (Alembic) | Persistence not authorized in this round |
| TASK-012 POST trigger in default MVP path | Replay-trained run creation is **advanced execution**, deferred |
| TASK-011 backtest trigger in default MVP path | Backtest execution is **advanced execution**, deferred |
| `run_backtest` execution in MVP | Advanced / expensive; deferred to Slice D+ with separate authorization |
| Internet retrieval / external knowledge source | Would break determinism + open prompt-injection surface |
| Cross-farm / cross-tenant / cross-subfarm comparison | Authority boundary not authorized; would risk data exfiltration |
| Auto-publish external report (email / IM / file delivery) | Side-effect not authorized |
| Auto-modification of farm / variety / planting area / staffing / processor capacity | Forbidden — Agent is non-control |
| Arbitrary SQL / shell / Python / URL tools | Forbidden — strict allowlist only |
| Reading credentials / `.hermes` / shell history | Forbidden — security boundary |
| Recreating TASK-008 through TASK-012 algorithms | Forbidden — orchestration only |
| LLM dependency in Slice A–D | Optional; deferred to Slice E |
| TASK-014 production controls (permissions, monitoring, drift detection) | Belongs to TASK-014 |
| Self-assigning new task numbers (TASK-014+, etc.) | `CODEX_TASKS.md` reserves TASK-014+; this design does not invent numbers |

### §5.3 The "minimal-input" non-negotiable

The ordinary user MVP **must not** require any of the following as input:
- explicit authority-overrides that bypass `AdvancedOverrides.authority_overrides[].target` typed envelope (raw row-id strings are not accepted)
- explicit algorithm selection
- explicit model version selection
- explicit replay-trained selection
- explicit backtest selection

These may be supplied as **advanced overrides** — specifically through `AdvancedOverrides.authority_overrides[].target = TASK8_FORECAST_RUN | TASK9_HARVEST_STATE_RUN | TASK10_PREDICTION_RUN | TASK11_BACKTEST_RUN | TASK12_PREDICTION_RUN` (typed, integer-valued row ids; see §8.1). `TASK10_TRAINING_RUN` is a separate optional override for surfacing the upstream training artifact and **MUST NOT** be used as a substitute for the prediction-run selector (§8.1 / §9.3.3). The ordinary user MVP does not require these.

---

## §6 Domain terminology

| Term | Definition |
|---|---|
| **Ordinary user** | A user who supplies only location + per-variety planting area |
| **Advanced user** | A user who supplies additional overrides |
| **Resolved location** | The output of `resolve_location`: standard address, coordinates, agro-climate zone, similar-farm set, all versioned |
| **Parameter prior** | A versioned probability distribution for an inferred parameter (per-mu yield, commodity-fruit rate, etc.) |
| **Authority** | A resolvable identity delivered through one of the typed envelopes (`Task8Authority` / `Task9Authority` / `Task10Authority` / `Task11Authority` / `Task12Authority`) that names a specific persisted artifact |
| **Authority resolution** | The deterministic process of selecting authorities given a versioned prior, an explicit `as_of`, and a stable tie-break order |
| **Identity** | A typed identifier (string/UUID) that uniquely names a persisted artifact and is stable across reload |
| **Hash** | A deterministic fingerprint of an artifact's canonical JSON content; used to detect tampering / substitution |
| **Manifest** | A versioned catalog of (artifact identity, content hash, lineage) for a run |
| **Provenance** | The chain of evidence that ties a numerical output to its source task, run identity, manifest hash, and forecast cutoff |
| **Confidence ladder** | 高 / 中 / 低 + required evidence (sample count, historical MAPE, date MAE, P90 coverage, key missing items) per `docs/10` §7 |
| **Blocker** | A structured error code that names the reason the Agent cannot proceed (input invalid, authority not found, etc.) |
| **Confirmation token** | An explicit human-issued token that authorizes a write-class action (NOT introduced in this design round; reserved for future advanced-execution amendment) |
| **NormalizedAgentRequest** | The deterministic, server-resolved request produced by applying the season-calendar policy to `MinimalInputRequest`; consumed by all tools |
| **`effective_as_of_date`** | The date used for authority resolution; resolved from `requested_as_of_date` via the versioned season-calendar policy, never silently defaulted to a wall-clock value |
| **`effective_forecast_season`** | The season used for authority resolution; resolved from `requested_forecast_season` via the versioned season-calendar policy |
| **`season_resolution_policy_version`** | Version identifier of the season-calendar policy used to resolve `effective_*` fields |
| **`season_calendar_config_hash`** | sha256 of the season-calendar policy config consulted; included in canonical request hash and provenance |
| **`PeakMetricPolicy`** | Versioned rule object defining `sustained_window_days`, `sustained_metric`, `tie_break`, `peak_window_days_before/after`, `high_load_threshold_ratio` |
| **`UncertaintyWideningPolicy`** | Versioned rule object defining widening factors per inference priority step (steps 2–5 widen; step 1 does not when HIGH evidence requirements are met; step 5 max widening, always LOW confidence) |
| **`DailyQuantiles`** | `{p50: decimal_string, p80: decimal_string, p90: decimal_string}`; the canonical shape for any TASK-009-derived per-day scalar in the daily curve |
| **Typed authority envelope** | A schema (`Task8Authority` / `Task9Authority` / `Task10Authority` / `Task11Authority` / `Task12Authority`) carrying only fields the underlying real main contract exposes, each cited to its source path/class |
| **`PARTIAL` request status** | Overall request status when at least one variety (or other per-variety / per-tool outcome) was blocked but the rest of the request could proceed; per-blocked-item carries its own blocker code |
| **`agent_*` hash** | Adapter-introduced canonical-output hash with explicit `agent_` prefix; never aliases an existing task hash |
| **Citation block** | A JSON sub-payload attached to every authoritative numerical value, listing source task / run id / hash / cutoff / parameter source / confidence evidence |

---

## §7 Minimal-input request contract

### §7.1 Request schema — Stage 1: caller-supplied `MinimalInputRequest`

`MinimalInputRequest` is the **caller-supplied** request as received from the transport. It carries exactly the fields the caller may set; it MUST NOT silently inject wall-clock or current-season defaults.

```yaml
MinimalInputRequest:
  request_id: string  # caller-supplied correlation id; not persisted in this slice
  location:
    raw_text: string | null       # e.g. "云南省红河州建水县..."
    coordinates: {lat: number, lon: number} | null
    map_pick_token: string | null # future
  varieties:
    - variety_id: string          # e.g. "Dx", "D12"
      planting_area_mu: number    # > 0, NUMERIC precision
  requested_as_of_date: date | null         # caller-supplied; null means "no caller preference"
  requested_forecast_season: integer | null # caller-supplied; null means "no caller preference"
  advanced_overrides: AdvancedOverrides | null  # see §8
  presentation_locale: string | null  # e.g. "zh-CN"; default "zh-CN"
```

The fields `requested_as_of_date` and `requested_forecast_season` are the **only** date / season inputs the caller controls. They are explicit `null` when the caller has no preference — they MUST NOT be silently rewritten to a wall-clock value inside `MinimalInputRequest`.

`request_received_at` is **not** part of `MinimalInputRequest`. It is injected by the transport / runtime as an aware UTC `datetime` at the moment the orchestrator begins processing, and is recorded in `NormalizedAgentRequest` (§7.2).

### §7.2 Request schema — Stage 2: server-normalized `NormalizedAgentRequest`

`NormalizedAgentRequest` is the **deterministic, fully-resolved** request that the orchestrator's tools consume. It is produced by a single explicit normalization step from `MinimalInputRequest` and `request_received_at`.

```yaml
NormalizedAgentRequest:
  request_id: string
  request_received_at: aware_datetime  # injected by transport; UTC; not caller-supplied
  effective_as_of_date: date           # resolved from requested_as_of_date via §7.3
  effective_forecast_season: integer   # resolved from requested_forecast_season via §7.3
  season_resolution_policy_version: string  # exact policy used to resolve season (e.g. "season-calendar/v1")
  season_calendar_config_hash: sha256      # sha256 of the season-calendar policy config consulted
  requested_as_of_date_provenance: RequestedAsOfDateProvenance  # per §8.2; included in canonical_request_hash
  normalized_location: ResolvedLocation  # produced by resolve_location
  varieties:
    - variety_id: string
      planting_area_mu: number
  advanced_overrides: AdvancedOverrides | null
  canonical_request_hash: sha256  # hash of canonical JSON of this entire structure, including requested_as_of_date_provenance
```

```yaml
RequestedAsOfDateProvenance:            # frozen schema; both NormalizedAgentRequest and AgentForecastOutput.provenance carry this object
  caller_requested_as_of_date: date      # original value from MinimalInputRequest.requested_as_of_date (or null-equivalent canonical)
  effective_as_of_date: date             # post-normalization effective date
  override_applied: boolean              # true iff an AdvancedOverrides.as_of_overrides[AS_OF_OVERRIDE] was supplied for this request
  override_kind: AS_OF_OVERRIDE | null   # discriminator for the override kind (only AS_OF_OVERRIDE is recognized on the as-of axis)
  source_attestation: string | null      # copied verbatim from the AsOfOverride envelope; null when override_applied=false
  source_ref: object | null              # copied verbatim from the AsOfOverride envelope; null when override_applied=false
```

**Provenance-preservation rule.** `RequestedAsOfDateProvenance` preserves BOTH the original caller preference (`caller_requested_as_of_date`) AND the post-normalization effective value (`effective_as_of_date`). The `override_applied` flag and the `override_kind` / `source_attestation` / `source_ref` triple record whether the precedence rule in §8.2 fired. The object participates in the canonical request hash (§24) and is also surfaced in `AgentForecastOutput.provenance` (§24.1) so a downstream reader can answer, for any effective-as-of, what the caller originally asked for and whether an override shifted the value.

### §7.3 Two-stage normalization — season-calendar policy

When the caller leaves `requested_as_of_date` or `requested_forecast_season` as `null`, the orchestrator resolves the effective values via a **versioned season-calendar policy**:

1. The orchestrator consults a registered `season_calendar` policy object carrying:
   - `policy_version` (e.g. `"season-calendar/v1"`),
   - `config_hash` (sha256 of the policy's canonical JSON config),
   - the policy's deterministic `as_of → season` and `received_at → as_of` rules.
2. The resolved `effective_as_of_date` and `effective_forecast_season` are recorded.
3. `season_resolution_policy_version` and `season_calendar_config_hash` are recorded.
4. Both effective values are included in the **canonical request hash** (§24) and the output's `provenance` block.
5. The orchestrator MUST NOT use any undocumented wall-clock / current-season fallback. If the policy cannot resolve (e.g. no policy registered for the runtime), the request fails with `SEASON_CALENDAR_POLICY_MISSING` (§26).

The season-calendar policy itself is a deterministic, versioned rule object. It is **not** a hidden `today()` call; its source must be inspectable from `season_calendar_config_hash`.

### §7.4 Validation rules (on `MinimalInputRequest`)

- `location` must have **at least one** of `raw_text`, `coordinates`, `map_pick_token`. Else → `INPUT_INVALID_LOCATION`.
- `varieties` must be a non-empty list. Else → `INPUT_INVALID_VARIETIES`.
- Each `planting_area_mu > 0`. Else → `INPUT_INVALID_PLANTING_AREA`.
- `variety_id` known-unknown behavior is governed by §26 — `UNKNOWN_VARIETY` is a per-variety blocked outcome, not an overall request blocker; known varieties continue; overall request status becomes `PARTIAL`; no numerical prediction for the unknown variety.
- `requested_as_of_date`, if supplied, MUST be a valid `date`. Out-of-policy values → `INPUT_INVALID_AS_OF`.
- `requested_forecast_season`, if supplied, MUST be a value the season-calendar policy recognizes. Unknown season → `INPUT_INVALID_SEASON`.
- After normalization, `effective_as_of_date` and `effective_forecast_season` are recorded in `NormalizedAgentRequest.effective_*` and appear in the output's provenance.

### §7.5 What MUST NOT be in the minimal input

- explicit authority overrides that bypass `AdvancedOverrides.authority_overrides[].target` typed envelope (e.g. raw `prediction_run_id` strings, raw run-id aliases for any task)
- explicit algorithm / model / replay selection that bypasses `AdvancedOverrides.authority_overrides`
- explicit backtest request that bypasses `AdvancedOverrides.execution_overrides[target = REQUEST_BACKTEST]`
- arbitrary free-form prompt that the LLM (when introduced) would interpret to fill authority
- any standalone `as_of` / `forecast_season` field that is not part of `MinimalInputRequest` (which carries `requested_as_of_date` / `requested_forecast_season`) or `AdvancedOverrides` (which carries typed overrides)

If any of these appear in the input, they MUST be moved into `advanced_overrides` (§8) or the typed stage-1 fields (`requested_as_of_date`, `requested_forecast_season`) and re-validated under stricter rules.

---

## §8 Advanced override contract

### §8.1 Override schema — discriminated typed overrides

Overrides are **discriminated typed objects**, not a single `value: number | distribution_ref` blob. Each override carries `override_kind`, a typed `value`, an explicit `unit`, a `source_attestation`, and an optional `source_ref`. Date / ratio / kg-per-mu / capacity / distribution overrides each have their own concrete type.

```yaml
AdvancedOverrides:
  parameter_overrides:
    - override_kind: PARAMETER_OVERRIDE_KIND
      variety_id: string
      target_parameter: enum [
        "expected_per_mu_yield",            # YieldPerMuOverride
        "commodity_fruit_rate",             # RateOverride
        "first_harvest_date",               # DateOverride
        "maturity_curve",                   # DistributionOverride
        "spring_festival_harvest_rate",     # RateOverride
        "weather_adjustment",               # WeatherAdjustmentOverride
      ]
      value: <typed per target_parameter, see §8.1.1>
      unit: string | null
      source_attestation: string           # required; free text, not machine-validated in this slice
      source_ref: object | null            # optional structured pointer (e.g. {kind: "internal_doc", path: "..."})
  scenario_overrides:
    - override_kind: SCENARIO_OVERRIDE_KIND
      target: enum [STAFFING, SPRING_FESTIVAL_INTENSITY, PROCESSOR_CAPACITY]
      value: <typed per target, see §8.1.2>
      unit: string | null
      source_attestation: string
      source_ref: object | null
  execution_overrides:
    - override_kind: EXECUTION_OVERRIDE_KIND
      target: enum [REQUEST_BACKTEST, REQUEST_REPLAY_TRAINED_RUN, REQUEST_SIMULATION]
      value: bool | string                 # bool for toggles; string for simulation id
      unit: null
      source_attestation: string
      source_ref: object | null
  authority_overrides:
    - override_kind: AUTHORITY_OVERRIDE_KIND
      target: enum [
        "TASK8_FORECAST_RUN",
        "TASK9_HARVEST_STATE_RUN",
        "TASK10_PREDICTION_RUN",
        "TASK10_TRAINING_RUN",
        "TASK11_BACKTEST_RUN",
        "TASK12_PREDICTION_RUN",
      ]
      value: integer                       # real persisted row id; never a synthetic alias
      unit: null
      source_attestation: string
      source_ref: object | null
  as_of_overrides:
    - override_kind: AS_OF_OVERRIDE       # at most one entry may be supplied (see §8.4)
      value: date                         # ISO-8601 date
      unit: "date"
      source_attestation: string          # required; participates in universal attestation rule (§8.1)
      source_ref: object | null
```

**Universal attestation rule.** Every override — parameter, scenario, execution, authority, **or `as_of_overrides[AS_OF_OVERRIDE]`** — MUST carry `source_attestation`. The schema above applies the same envelope to all override kinds. Bare scalars (`as_of: date | null` or any other un-typed scalar) MUST NOT appear inside `AdvancedOverrides`. A bare `as_of` is rejected as bypass of the universal attestation envelope.

#### §8.1.1 Per-parameter override value types

```yaml
YieldPerMuOverride:        # kg / mu
  value: number
  unit: "kg_per_mu"

RateOverride:              # dimensionless ratio in [0, 1]
  value: decimal_string    # canonical decimal string
  unit: "ratio"

DateOverride:
  value: date              # ISO-8601 date
  unit: "date"

DistributionOverride:
  value: { type: enum [NORMAL, BETA, HISTORICAL_EMPIRICAL], parameters: object }
  unit: "distribution"

WeatherAdjustmentOverride:
  value: { temperature_delta_c: decimal_string | null, rainfall_scale: decimal_string | null, gdd_scale: decimal_string | null }
  unit: "weather_adjustment"
```

#### §8.1.2 Per-scenario override value types

```yaml
StaffingOverride:
  value: number
  unit: "person_per_day"

SpringFestivalIntensityOverride:
  value: enum [NONE, LOW, MEDIUM, HIGH]
  unit: null

ProcessorCapacityOverride:
  value: number
  unit: "t_per_day"
```

### §8.2 `AsOfOverride` — typed override for the as-of date

A bare `as_of: date | null` scalar in `AdvancedOverrides` is **forbidden**; the only typed override path for the as-of date is `as_of_overrides[].override_kind = AS_OF_OVERRIDE` (schema above). The `AsOfOverride` envelope is consumed by the normalization step and replaces `requested_as_of_date` before the season-calendar policy resolves `effective_as_of_date`. The resulting `effective_as_of_date` and `season_resolution_policy_version` + `season_calendar_config_hash` are recorded as for any other request.

**Path A — caller uses `requested_as_of_date` in `MinimalInputRequest`** (the **preferred ordinary-user path**): the caller puts the value on the typed stage-1 schema and lets the season-calendar policy produce `effective_as_of_date` on `NormalizedAgentRequest`. No `as_of_overrides` entry is needed.

**Path B — caller supplies an `AsOfOverride`** (typed envelope above): used when the caller wants to override `requested_as_of_date` after the stage-1 schema was already assembled (e.g. re-running with a different as-of). The envelope carries `source_attestation` per the universal attestation rule (§8.1).

**At-most-one and conflict rules.**

1. `AdvancedOverrides.as_of_overrides` MUST contain **at most one** entry whose `override_kind = AS_OF_OVERRIDE`. If more than one `AS_OF_OVERRIDE` is supplied → request fails with `OVERRIDE_CONFLICT` (§26.1).
2. If the caller supplies BOTH `MinimalInputRequest.requested_as_of_date` AND one `AdvancedOverrides.as_of_overrides[AS_OF_OVERRIDE]`:
   - the **typed `AsOfOverride` wins**, and the caller-supplied `requested_as_of_date` is recorded only as `requested_as_of_date_provenance` (the original caller preference is preserved for audit, not used for season-calendar resolution).
   - This precedence rule is deterministic and frozen. Any future request to invert precedence requires a separate amendment and a re-frozen §8.2.
3. `AsOfOverride` is NOT an `authority_overrides` entry and does NOT consume the `AUTHORITY_CONFLICT` resolution path.

**Authority-effect semantics (corrected).** `AsOfOverride` **cannot directly nominate, substitute, or pin an authority**. It may change the deterministic authority candidate set **only through** the resulting `effective_as_of_date`. Specifically:

- The typed `AsOfOverride` carries **no** `run_id`, `prediction_run_id`, `training_run_id`, `forecast_run_id`, `harvest_state_run_id`, `backtest_run_id`, or any other authority-pointer field. If such a field appears inside the override envelope, the request fails with `OVERRIDE_CONFLICT`.
- After normalization, the resulting `effective_as_of_date` is fed into the existing authority resolver (§9) under the same selectors, visibility rules, versioned policies, and stable tie-breaks as any other request. No selector, visibility rule, or tie-break in §9 is altered by the override.
- Because `effective_as_of_date` IS an input to authority selection, two requests that differ ONLY by their `AsOfOverride` MAY resolve different historically visible authorities (e.g. a TASK-008 forecast run whose `as_of_date ≤ effective_as_of_date` and which was previously below the visibility horizon becomes a candidate). This is a *derived effect* of the as-of shift, not a direct override of authority selection. The resolved authority identities are disclosed in `AgentForecastOutput.provenance` and every authority-bearing citation carries `RequestedAsOfDateProvenance` + `OVERRIDE_APPLIED` per the citation schema (§19.3).
- Cross-run substitution, cross-run aliasing, and any other bypass of the authority override targets (`TASK8_FORECAST_RUN` / `TASK9_HARVEST_STATE_RUN` / `TASK10_PREDICTION_RUN` / `TASK11_BACKTEST_RUN` / `TASK12_PREDICTION_RUN`) remain forbidden when triggered via an as-of shift.

#### §8.2.1 Design-only test matrix for future implementation

This round is design-only; no test code is written. The following matrix is frozen for the implementation round to assert against:

| # | Property | Frozen expectation |
|---|---|---|
| 1 | Same `MinimalInputRequest` + different `AsOfOverride` MAY resolve different historically visible authorities | True iff the candidate set under the new `effective_as_of_date` differs from the candidate set under the original; the difference is fully recorded in `provenance` + citation `OVERRIDE_APPLIED`. |
| 2 | The authority candidate-set change is deterministic and fully provenance-linked | The new resolved authorities are stable under repeated calls with the same `MinimalInputRequest` + same `AsOfOverride` + same versioned policies + same `request_received_at`; every resolved identity is disclosed in `provenance` and `RequestedAsOfDateProvenance`. |
| 3 | `AsOfOverride` envelope cannot contain a `run_id` or any field that bypasses `authority_overrides.*` targets | Any such field is rejected with `OVERRIDE_CONFLICT` (§26.1) and the request fails before normalization. |
| 4 | Cross-run substitution via an as-of shift remains forbidden | The resolved authorities are produced by the §9 selector under the new `effective_as_of_date`; the orchestrator MUST NOT pick a `prediction_run_id` / `training_run_id` / etc. that the selector would not otherwise have produced under the same as-of. |

### §8.3 Override authority rules

- Every override (parameter, scenario, execution, authority, `as_of_overrides[AS_OF_OVERRIDE]`) MUST carry `source_attestation`.
- Every override MUST be reflected in the output's citation block by setting `citation.tags = [OVERRIDE_APPLIED]` and enumerating the override under `citation.override_refs[]` (per §19.3 / §24.2). No other citation shape is permitted for the `OVERRIDE_APPLIED` tag.
- Algorithm / model / replay selection overrides are **not** accepted as `algorithm_override`. They MUST go through `authority_overrides.*`, and if no matching persisted run exists → `AUTHORITY_NOT_FOUND` blocker.
- `execution_overrides` where `target = REQUEST_BACKTEST` or `target = REQUEST_REPLAY_TRAINED_RUN` are **advanced execution** flags. In the first implementation Slice they MUST be rejected with `EXECUTION_DEFERRED` blocker; a future amendment may unlock them with explicit confirmation token. Slice D does NOT include any confirmation-token mechanism; that requires a separate amendment (§18, §22.4).
- `as_of_overrides[AS_OF_OVERRIDE]` does NOT carry any authority-pointer field (no `run_id` / `prediction_run_id` / `training_run_id` / `forecast_run_id` / `harvest_state_run_id` / `backtest_run_id`); its effect on authority candidates is mediated exclusively by the resulting `effective_as_of_date` per §8.2 (Authority-effect semantics).

### §8.4 Override MUST NOT

- inject raw SQL / shell / Python
- inject arbitrary URLs
- inject credentials
- request any side-effect outside the allowlist (§11)
- request access to `.hermes` / shell history / secrets
- bypass the universal attestation rule (§8.1)

---

## §9 Deterministic authority-resolution contract

### §9.1 Allowed deterministic inference

The Agent MAY:
1. resolve a textual / coordinate location to a `ResolvedLocation` using a **versioned location-mapping catalog**.
2. apply a **versioned parameter prior** for each `(location × variety)` parameter.
3. select authorities using an explicit `as_of` / forecast cutoff against a historical-visibility index.
4. apply a **stable tie-break order** when multiple candidates satisfy the same selection criteria.
5. widen P80/P90 intervals when evidence is sparse (§10).
6. return `LOW_CONFIDENCE` and an explicit missing-items list when evidence is insufficient.
7. compose multiple TASK-008–012 service outputs into a unified result (e.g. combine natural maturity + harvest-state + residual).

### §9.2 Forbidden implicit selection

The Agent MUST NOT use any of the following as a default selector:

| Forbidden | Replacement (when/if needed) |
|---|---|
| `latest` | must be replaced by `versioned deterministic selector` |
| `current` | must be replaced by `explicit as_of cutoff` |
| `most recent` | must be replaced by `versioned deterministic selector` |
| `best available` | must be replaced by `stable tie-break order + resolved identity in output` |
| `default model` | must be replaced by `versioned deterministic selector` + `effective_as_of_date` + typed resolved authority envelope (`Task8Authority` / `Task10Authority` / `Task12Authority`) |
| `silent fallback` | must be replaced by `versioned prior + confidence widening + missing-items report` |
| `unrecorded authority substitution` | must be replaced by `recorded authority identity in output citation` |
| `cross-run substitution` | forbidden unconditionally — see §22 |

### §9.3 Output must disclose resolved identities — typed authority envelopes

The Agent MUST disclose, in the output's `provenance` block, the actual resolved authorities it consumed. Authority identities are **typed envelopes** aligned to the real main contracts; generic `taskX_run_id` aliases are NOT frozen as current persisted fields. Every field below cites its source path/class.

#### §9.3.1 `Task8Authority` (TASK-008 natural maturity curve)

Source contract: `backend/app/models/maturity.py` — `MaturityModelRun` (L26), `MaturityModelArtifact` (L71), `MaturityForecastRun` (L99). `MaturityForecastRun.as_of_date` is the source field; the TASK-013 envelope key `maturity_forecast_as_of_date` is an explicit mapping from this source field, recorded here to avoid confusion. The source ORM field is **not** named `forecast_as_of_date`.

```yaml
Task8Authority:
  maturity_model_run_id: integer                # MaturityModelRun.id
  maturity_model_version: string                # MaturityModelRun.model_version
  maturity_model_config_hash: sha256            # MaturityModelRun.config_hash
  maturity_model_source_signature: string       # MaturityModelRun.source_signature
  maturity_model_artifact_id: integer           # MaturityModelArtifact.id
  maturity_model_artifact_hash: sha256          # MaturityModelArtifact.artifact_hash
  maturity_forecast_run_id: integer             # MaturityForecastRun.id
  maturity_forecast_source_signature: string    # MaturityForecastRun.source_signature
  maturity_forecast_as_of_date: date            # mapped from MaturityForecastRun.as_of_date
```

**Source-field vs envelope-key note.** `MaturityForecastRun.as_of_date` is the actual ORM column. The TASK-013 envelope uses `maturity_forecast_as_of_date` to keep the prefix consistent with the rest of the envelope; the documentation above makes the mapping explicit. If a future amendment prefers, the envelope key may be renamed to plain `as_of_date` and the prefix dropped — that rename is a separate, additive amendment.

#### §9.3.2 `Task9Authority` (TASK-009 / TASK-009A harvest state)

Source contract: `backend/app/models/harvest_state.py` — `HarvestStateRun` (L109). Real `HarvestStateRun` columns are: `id`, `status`, `output_schema_version`, `result_hash_schema_version`, `resolved_parameter_snapshot_schema_version`, `source_ref_schema_version`, `stable_cohort_key_schema_version`, `config_hash`, `result_hash`, `canonical_payload_hash`, `forecast_start_date`, `forecast_end_date`, `as_of_date`, `destination_factory_id`, `pool_row_count`, `member_row_count`, `cohort_row_count`, `future_arrival_row_count`, plus the embedded `maturity_*` mirror columns (which mirror TASK-008 fields and are not the canonical TASK-013 envelope source for `maturity_*`).

```yaml
Task9Authority:
  harvest_state_run_id: integer                 # HarvestStateRun.id
  harvest_state_run_config_hash: sha256         # HarvestStateRun.config_hash
  harvest_state_run_result_hash: sha256         # HarvestStateRun.result_hash
  harvest_state_run_canonical_payload_hash: sha256  # HarvestStateRun.canonical_payload_hash
  harvest_state_output_schema_version: string   # HarvestStateRun.output_schema_version
  harvest_state_as_of_date: date                # HarvestStateRun.as_of_date
  harvest_state_forecast_start_date: date       # HarvestStateRun.forecast_start_date
  harvest_state_forecast_end_date: date         # HarvestStateRun.forecast_end_date
  destination_factory_id: integer               # HarvestStateRun.destination_factory_id
  pool_row_count: integer                       # HarvestStateRun.pool_row_count
  member_row_count: integer                     # HarvestStateRun.member_row_count
  cohort_row_count: integer                     # HarvestStateRun.cohort_row_count
  future_arrival_row_count: integer             # HarvestStateRun.future_arrival_row_count
  source_ref_schema_version: string             # HarvestStateRun.source_ref_schema_version (NOT a RollingBacktestRun field)
  result_hash_schema_version: string            # HarvestStateRun.result_hash_schema_version
  stable_cohort_key_schema_version: string      # HarvestStateRun.stable_cohort_key_schema_version
  resolved_parameter_snapshot_schema_version: string  # HarvestStateRun.resolved_parameter_snapshot_schema_version
```

The `source_ref_schema_version` field belongs to `HarvestStateRun`, NOT to `RollingBacktestRun`. The previous draft incorrectly carried it on `Task11Authority`; the audit confirms the correct provenance is `HarvestStateRun.source_ref_schema_version`. The TASK-008 prediction source ref that this version governs is exposed via `task8_prediction_source_ref` (`Task8PredictionSourceRef` from `backend/app/harvest_state/schemas.py` L114) — included in the output citation block, not as a `Task9Authority` column.

#### §9.3.3 `Task10Authority` (TASK-010 residual model)

Source contract: `backend/app/models/residual_model.py` — `ResidualModelTrainingRun` (L41) carries `id` + `manifest_hash` + `config_hash` + `feature_schema_hash` + `canonical_payload_hash`; `ResidualModelPredictionRun` (L416) carries `id` + `training_run_id` (FK to `ResidualModelTrainingRun.id`) + `task9_run_id` (FK to `HarvestStateRun.id`) + `task9_result_hash` + `config_hash` + `prediction_input_signature` + `prediction_hash` + `artifact_hashes` + `feature_schema_hash` + `canonical_payload_hash`. The training-side manifest hash source is `ResidualModelTrainingRun.manifest_hash`. The training-side manifest row table (`ResidualModelManifestRow`) is not the source of any field surfaced in `Task10Authority`.

```yaml
Task10Authority:
  training_run_id: integer | null               # ResidualModelPredictionRun.training_run_id (FK to ResidualModelTrainingRun.id); null when the prediction row was not produced by a persisted training run
  training_manifest_hash: sha256 | null        # ResidualModelTrainingRun.manifest_hash (null when training_run_id is null)
  prediction_run_id: integer                    # ResidualModelPredictionRun.id (PRIMARY FK surfaced)
  task9_run_id: integer                         # ResidualModelPredictionRun.task9_run_id (FK to HarvestStateRun.id)
  task9_result_hash: sha256                     # ResidualModelPredictionRun.task9_result_hash
  prediction_hash: sha256                       # ResidualModelPredictionRun.prediction_hash
  prediction_config_hash: sha256                # ResidualModelPredictionRun.config_hash
  prediction_input_signature: sha256            # ResidualModelPredictionRun.prediction_input_signature
  artifact_hashes: [sha256]                     # ResidualModelPredictionRun.artifact_hashes (JSON list)
  feature_schema_hash: sha256                   # ResidualModelPredictionRun.feature_schema_hash
  prediction_canonical_payload_hash: sha256     # ResidualModelPredictionRun.canonical_payload_hash
```

`model_run_id` is NOT frozen as the persisted prediction FK — the persisted FK is `prediction_run_id`. The earlier draft's `model_run_id` was a generic alias; the audit confirms it is not a real field on `ResidualModelPredictionRun`.

#### §9.3.4 `Task11Authority` (TASK-011 rolling backtest)

Source contract: `backend/app/models/rolling_backtest.py` — `RollingBacktestRun` (L49). Real `RollingBacktestRun` columns are: `id`, `run_signature`, `config_hash`, `execution_mode`, `rolling_schema_version`, `canonical_serialization_version`, `availability_registry_version`, `node_calendar_version`, `forecast_horizon_policy_version`, `upstream_selection_policy_version`, `metric_policy_version`, `calendar_phase_policy_version`, `cutoff_policy_version`, `cutoff_timezone`, `cutoff_local_time`, `status`, `expected_node_count`, `canonical_payload`, `canonical_payload_hash`, `created_at`, `updated_at`.

```yaml
Task11Authority:
  rolling_backtest_run_id: integer               # RollingBacktestRun.id
  run_signature: sha256                          # RollingBacktestRun.run_signature
  config_hash: sha256                            # RollingBacktestRun.config_hash
  canonical_payload_hash: sha256                 # RollingBacktestRun.canonical_payload_hash
  rolling_schema_version: string                 # RollingBacktestRun.rolling_schema_version
  canonical_serialization_version: string        # RollingBacktestRun.canonical_serialization_version
  availability_registry_version: string          # RollingBacktestRun.availability_registry_version
  node_calendar_version: string                  # RollingBacktestRun.node_calendar_version
  forecast_horizon_policy_version: string        # RollingBacktestRun.forecast_horizon_policy_version
  upstream_selection_policy_version: string      # RollingBacktestRun.upstream_selection_policy_version
  metric_policy_version: string                  # RollingBacktestRun.metric_policy_version
  cutoff_policy_version: string                  # RollingBacktestRun.cutoff_policy_version
  execution_mode: string                         # RollingBacktestRun.execution_mode ('historical_observed' | 'retrospective_replay')
  status: string                                 # RollingBacktestRun.status
  expected_node_count: integer                   # RollingBacktestRun.expected_node_count
```

**Consumption metadata (TASK-013 owned, NOT `RollingBacktestRun` columns).** The Agent may also report related-row counts and identities that are derived by TASK-013 from query of related tables. These are explicitly labelled as consumption metadata, not `RollingBacktestRun` fields:

```yaml
Task11ConsumptionMetadata:                       # TASK-013 owned; not on RollingBacktestRun
  node_count: integer                            # count of RollingBacktestNode rows for rolling_backtest_run_id
  attempt_count: integer                         # count of RollingBacktestAttempt rows for rolling_backtest_run_id
  orchestration_snapshot_id: integer | null      # RollingBacktestOrchestrationSnapshot.id when present
  resolved_input_id: integer | null              # RollingBacktestResolvedInput.id when present
```

#### §9.3.5 `Task12Authority` (TASK-012 replay-trained model)

Source contract: `backend/app/rolling_backtest/schemas.py` `ReplayTrainedModelIdentity` (L137) carries `policy`, `training_cutoff_at`, `allowed_training_season_ids`, `validation_policy_version`, `label_visibility_policy_version`, `feature_visibility_policy_version`, `artifact_visibility_policy_version`, `training_manifest_semantic_hash`, `model_config_hash`, `model_artifact_hash`, `model_code_version`, `task12_policy_version`. `ReplayTrainedPredictionBinding` (`backend/app/rolling_backtest/replay_trained_prediction.py` L275–L316) carries `prediction_run_id`, `task9_run_id`, `task9_result_hash`, `prediction_hash`, `training_manifest_hash`, `model_artifact_hash`, `forecast_cutoff_at`, `training_cutoff_at`, `replay_attempt_id`, `replay_node_id`, `replay_code_version`, `task9_replay_binding_identity`. The HTTP request/response in `backend/app/api/rolling_backtest_replay_trained.py` (L117–L118, L244–L325, L685–L705) carries `task9_result_hash`, `task10_manifest_hash`, `task10_config_hash`. The TASK-013 envelope exposes the union of identity fields.

```yaml
Task12Authority:
  prediction_run_id: integer                     # ReplayTrainedPredictionBinding.prediction_run_id
  scenario_id: string                            # ReplayTrainedModelIdentity-derivable scenario reference; surfaced via GET response field, not as a free string
  training_manifest_hash: sha256                 # ReplayTrainedModelIdentity.training_manifest_semantic_hash (== ReplayTrainedPredictionBinding.training_manifest_hash)
  model_config_hash: sha256                      # ReplayTrainedModelIdentity.model_config_hash
  task9_run_id: integer                          # ReplayTrainedPredictionBinding.task9_run_id
  task9_result_hash: sha256                      # ReplayTrainedPredictionBinding.task9_result_hash
  prediction_hash: sha256                        # ReplayTrainedPredictionBinding.prediction_hash
  forecast_cutoff_at: aware_datetime             # ReplayTrainedPredictionBinding.forecast_cutoff_at
  training_cutoff_at: aware_datetime             # ReplayTrainedPredictionBinding.training_cutoff_at
  model_code_version: string                     # ReplayTrainedModelIdentity.model_code_version
  task12_policy_version: string                  # ReplayTrainedModelIdentity.task12_policy_version
  validation_policy_version: string              # ReplayTrainedModelIdentity.validation_policy_version
  label_visibility_policy_version: string        # ReplayTrainedModelIdentity.label_visibility_policy_version
  feature_visibility_policy_version: string      # ReplayTrainedModelIdentity.feature_visibility_policy_version
  artifact_visibility_policy_version: string     # ReplayTrainedModelIdentity.artifact_visibility_policy_version
  model_artifact_hash: sha256 | null             # ReplayTrainedPredictionBinding.model_artifact_hash (null when not present)
  task9_replay_binding_identity: sha256          # ReplayTrainedPredictionBinding.task9_replay_binding_identity
  task10_manifest_hash: sha256 | null            # request-side task10_manifest_hash; surfaced from the prediction request payload (not a persisted column on ReplayTrainedPredictionBinding)
  task10_config_hash: sha256 | null              # request-side task10_config_hash; surfaced from the prediction request payload (not a persisted column on ReplayTrainedPredictionBinding)
```

The TASK-013 envelope does not include a `result_hash` field — TASK-012 does not persist a separate `result_hash` on its prediction row; the binding identity is represented by `prediction_hash` + `task9_replay_binding_identity`.

#### §9.3.6 Provenance-block composition rule

The output `provenance` block MUST include **exactly one** of each typed envelope above when its source service was actually consumed, and `null` (typed) otherwise. Adapter-supplied canonical-output hashes (introduced by the TASK-013 orchestrator) MUST be named with an explicit `agent_*` prefix (e.g. `agent_daily_curve_hash`, `agent_peak_hash`, `agent_normalized_request_hash`) so they cannot impersonate an existing task's hash.

Rules:
- No generic `taskX_run_id` alias is frozen as an existing persisted field. The `*_run_id` keys in the typed envelopes above are adapter references to real main-contract row ids, each cited to its source class/path.
- No manifest / result hash appears in a typed envelope where the source task does not expose one; "when applicable" is encoded in the type (`sha256 | null`), not in prose.
- Every field in a typed envelope cites its source path/class in §21 and §22.
- Adapter-introduced hashes are prefixed `agent_*` and never alias a real task hash.

### §9.4 Authority conflict

If two persisted artifacts both satisfy the selector (e.g. two `Task10Authority` envelopes with different `prediction_run_id` / `prediction_hash` but matching `effective_as_of_date` / `effective_forecast_season` / `normalized_location` / `varieties`):
1. Do NOT silently pick either.
2. Return `AUTHORITY_CONFLICT` blocker.
3. Output both candidates with their hashes + tie-break order used.
4. Wait for caller to re-submit with `authority_overrides` to disambiguate.

### §9.5 Anti chat-fill rule

The Agent MUST NOT use natural-language cues from the request body to silently fill `*_run_id` fields. Natural language MAY be used to populate free-text fields (`source_attestation`, `notes`), but NEVER to pick a persisted authority.

---

## §10 Versioned prior and confidence widening contract

### §10.1 Inference priority (per `docs/10` §3)

When inferring a parameter for `(location × variety)`, the Agent MUST apply this priority:

1. Same-farm + same-variety history (≥ 1 产季).
2. Same-township / similar-altitude + same-variety history.
3. Same-county / same-agro-climate-zone + same-variety history.
4. Yunnan province-level + same-variety aggregate prior.
5. Variety-document prior (only when no historical data; always `LOW_CONFIDENCE`).

### §10.2 Versioning

Every prior MUST carry a **version identifier** (catalog version + season version). The output MUST include the exact prior version used.

### §10.3 Confidence widening — corrected rule

Widening is governed by a versioned **`UncertaintyWideningPolicy`** (§10.4). The corrected rule:

| Step | Behavior |
|---|---|
| **Step 1** — same-farm + same-variety | No mandatory widening **when HIGH evidence requirements are met** (per `docs/10` §7). If HIGH requirements are not all met, treat as step 2 for widening purposes. |
| **Step 2** — same-township / similar-altitude | Widening required. Factor monotonically > 1 (greater than step 1's no-widening case). |
| **Step 3** — same-county / same-agro-climate-zone | Widening required. Factor strictly greater than step 2's factor. |
| **Step 4** — Yunnan province-level same-variety | Widening required. Factor strictly greater than step 3's factor. |
| **Step 5** — variety-document prior only | **Maximum widening.** Confidence is **always LOW**. Factor strictly greater than step 4's factor. |

The factor must **monotonically increase with fallback depth** — this is a hard monotonicity property, not a hint. The exact factor values live in `UncertaintyWideningPolicy.factors_by_source_level` (§10.4).

The historical rule "widen whenever the priority fallback depth is at or above step 4" is **deleted**. The new rule says: step 1 widens only when HIGH evidence is missing; steps 2–5 always widen with monotonically increasing factors; step 5 has maximum widening and always LOW confidence.

### §10.4 `UncertaintyWideningPolicy` (versioned)

```yaml
UncertaintyWideningPolicy:
  policy_version: string                          # e.g. "uncertainty-widening/v1"
  config_hash: sha256                             # sha256 of canonical JSON of this policy
  factors_by_source_level:
    step_1_same_farm_same_variety_high_evidence: decimal_string  # 1.000 (no widening)
    step_2_same_township_similar_altitude: decimal_string        # > 1.000
    step_3_same_county_same_climate_zone: decimal_string         # > step_2
    step_4_province_level_same_variety: decimal_string           # > step_3
    step_5_variety_document_prior_only: decimal_string           # > step_4 (maximum)
  monotonicity_invariant: true                    # frozen property, asserted at policy registration
```

The exact factor per `(variety_id, parameter_name, source_level)` is resolved from this policy and is included in the output's provenance block. The factors are not exposed as runtime-configurable knobs in this slice.

### §10.5 Required evidence per confidence level

| Level | Required evidence (per `docs/10` §7) |
|---|---|
| 高 | Same-farm + same-variety ≥ 2 产季, location + weather complete, rolling backtest达标 |
| 中 | Same-climate-zone + same-variety samples sufficient, but missing same-farm history |
| 低 | Same-variety history sparse, location resolution coarse, per-mu yield / commodity-fruit rate mainly provincial prior |

The output MUST also report: sample count, historical MAPE, date MAE, P90 coverage rate, key missing items.

---

## §11 Logical tool registry

The 8 logical tools defined by `CODEX_TASKS.md` 任务 13 are listed below. Each is mapped to existing services in §12–§20.

| # | Logical tool | Product purpose | MVP classification |
|---|---|---|---|
| 1 | `resolve_location` | Convert raw location to standard `ResolvedLocation` | `EXISTING_DIRECT` |
| 2 | `infer_parameters` | Per-(location×variety) parameter prior with confidence + source | `EXISTING_COMPOSITE` |
| 3 | `forecast_daily_curve` | Per-day natural maturity + harvest-state + residual composition | `EXISTING_COMPOSITE` |
| 4 | `forecast_peak` | Peak metrics derived deterministically from the daily curve (governed by `PeakMetricPolicy`) | `NEW_DETERMINISTIC_RULE_TOOL` | ✅ |
| 5 | `simulate_scenario` | Re-run with a modified scenario (staffing, Spring-Festival intensity, etc.) | `NEW_DETERMINISTIC_ADAPTER` (no full existing service) |
| 6 | `run_backtest` | TASK-011 backtest execution | `DEFERRED_ADVANCED_TOOL` |
| 7 | `explain_forecast` | Structured explanation payload | `NEW_DETERMINISTIC_RULE_TOOL` |
| 8 | `generate_recommendations` | Deterministic 7-category recommendations (6 operational + 1 data-quality) | `NEW_DETERMINISTIC_RULE_TOOL` |

Classification meanings:
- `EXISTING_DIRECT` — directly call an existing service module / endpoint.
- `EXISTING_COMPOSITE` — compose multiple existing services in a deterministic adapter.
- `NEW_DETERMINISTIC_ADAPTER` — new adapter wraps existing services but exposes a tool contract; no new numerical algorithm.
- `NEW_DETERMINISTIC_RULE_TOOL` — new deterministic rule tool (no LLM, no learned model).
- `DEFERRED_ADVANCED_TOOL` — not in MVP; future slice with separate authorization.

---

## §12 Tool-to-existing-service mapping

This is the consolidated mapping table. Detail per tool in §13–§20.

| Logical tool | Product purpose | Existing source service/module | Existing API/CLI | Required adapter | Classification | MVP |
|---|---|---|---|---|---|---|
| `resolve_location` | Convert raw location to standard `ResolvedLocation` | `backend/app/planning/location.py` (661 lines) + `backend/app/planning/service.py` | TASK-005/006/007 planning endpoints (to be re-confirmed in implementation slice) | none additional | `EXISTING_DIRECT` | ✅ |
| `infer_parameters` | Per-(location×variety) parameter prior with confidence + source | TASK-005/006/007 location mapping + versioned parameter prior + current parameter resolution | TASK-005/006/007 endpoints | thin orchestrator over existing parameter resolution | `EXISTING_COMPOSITE` | ✅ |
| `forecast_daily_curve` | Per-day natural maturity + harvest-state + residual composition | TASK-008 `backend/app/maturity/service.py` + TASK-009 `backend/app/harvest_state/service.py` + TASK-010 `backend/app/residual_model/` | `backend/app/api/maturity.py` + `harvest_state.py` + `residual_model.py` | deterministic composition adapter; **no new numerical algorithm** | `EXISTING_COMPOSITE` | ✅ |
| `forecast_peak` | Single-day / 3-day sustained / P80-P90 / duration / ±7-day cumulative | derived deterministically from `forecast_daily_curve` output | none direct | deterministic peak-derivation adapter | `NEW_DETERMINISTIC_RULE_TOOL` (rule-only, no new model) | ✅ |
| `simulate_scenario` | Re-run with scenario override (staffing, Spring-Festival, capacity) | TASK-009 harvest-state + scenario inputs; TASK-008 / TASK-010 parameters | partial coverage today | new adapter wraps existing services with a scenario-input contract | `NEW_DETERMINISTIC_ADAPTER` | ✅ |
| `run_backtest` | TASK-011 backtest execution | `backend/app/rolling_backtest/service.py` + `orchestration.py` + `cli.py` | `backend/app/api/rolling_backtest_*.py` (no dedicated run-backtest HTTP endpoint in MVP) | none required for deferred status | `DEFERRED_ADVANCED_TOOL` | ⏸ deferred |
| `explain_forecast` | Structured explanation payload | consumes output of tools 1–5; produces structured payload | none | deterministic structured-payload builder | `NEW_DETERMINISTIC_RULE_TOOL` | ✅ |
| `generate_recommendations` | Deterministic 7-category recommendations (6 operational + 1 data-quality) | consumes output of tools 3–5; applies documented rules | none | deterministic rule engine | `NEW_DETERMINISTIC_RULE_TOOL` | ✅ |

The classification deliberately rejects the implicit assumption "if no Python function named X exists, then tool X is not implemented". The logical tool is a **contract**; the implementation is whatever deterministic service / adapter / rule that satisfies the contract.

---

## §13 `resolve_location` contract

### §13.1 Purpose

Convert the user's raw location input into a `ResolvedLocation` carrying standard coordinates, agro-climate zone, similar-farm set, and a location-catalog version identity.

### §13.2 Input

```yaml
resolve_location_input:
  normalized_request: NormalizedAgentRequest   # carries effective_as_of_date / effective_forecast_season / season_resolution_policy_version / season_calendar_config_hash / canonical_request_hash
  raw_text: string | null
  coordinates: {lat: number, lon: number} | null
  map_pick_token: string | null
```

### §13.2.1 Idempotency

Idempotent on `(normalized_request.canonical_request_hash, raw_text, coordinates, map_pick_token, location_catalog_version)`.

### §13.3 Output

```yaml
resolve_location_output:
  resolved: ResolvedLocation  # schema in backend/app/planning/schemas.py
  agro_climate_zone: ClimateZoneResolution
  similar_farm_set: [LocationReference]
  location_catalog_version: string
  matched_method: enum [TEXT_MATCH, COORDINATE_MATCH, FUZZY_MATCH, UNRESOLVED]
  confidence: enum [HIGH, MEDIUM, LOW]
  warning_codes: [string]
```

### §13.4 Authority contract

- Reads from `backend/app/planning/location.py` (existing direct service).
- Carries `location_catalog_version` identity forward into §9.3 disclosure.

### §13.5 Blockers

- `LOCATION_UNRESOLVED` — input too ambiguous.
- `LOCATION_CATALOG_STALE` — `effective_as_of_date` is before the catalog's effective date.
- `LOCATION_AMBIGUOUS` — multiple zone candidates with same score → return top-N candidates; do NOT auto-pick.

### §13.6 Read/Write / Idempotency

- Read-only. Idempotent on `(normalized_request.canonical_request_hash, raw_text, coordinates, map_pick_token, location_catalog_version)`.

### §13.7 Citation identity

- `location_catalog_version`, `agro_climate_zone.zone_id`, `agro_climate_zone.zone_version`.

---

## §14 `infer_parameters` contract

### §14.1 Purpose

For each `(location × variety)` pair, infer the 9 parameter categories from `docs/10` §3, with versioned priors, confidence ladder, and per-parameter source attestation.

### §14.2 Input

```yaml
infer_parameters_input:
  normalized_request: NormalizedAgentRequest   # carries effective_as_of_date / effective_forecast_season / season_resolution_policy_version / season_calendar_config_hash / canonical_request_hash
  resolved_location: ResolvedLocation          # output of resolve_location
  varieties: [{variety_id, planting_area_mu}]
  advanced_overrides: AdvancedOverrides | null
```

### §14.2.1 Idempotency

Idempotent on `(normalized_request.canonical_request_hash, resolved_location_id, varieties, advanced_overrides_hash, prior_version)`.

### §14.3 Output

```yaml
infer_parameters_output:
  parameters:
    - variety_id: string
      parameter_name: enum [...]
      distribution: {type, parameters, version}
      point_estimate: number | null
      confidence: enum [HIGH, MEDIUM, LOW]
      source: {priority_step: int, sample_count: int, covered_seasons: int, historical_mape: number | null, key_missing: [string]}
  aggregate: {total_volume_distribution, total_volume_confidence}
```

### §14.4 Authority contract

- Composes existing TASK-005/006/007 location mapping + versioned parameter prior + current parameter resolution service.
- **LLM MUST NOT infer numeric parameter values.** This is enforced by deterministic-only composition.

### §14.5 Blockers

- `INSUFFICIENT_HISTORY` — even priority step 5 has no data.
- `PARAMETER_OVERRIDE_INVALID` — an advanced override references a parameter that does not exist.
- `VARIETY_PRIOR_NOT_VISIBLE_AT_AS_OF` — no prior version satisfies `effective_from <= effective_as_of_date AND (effective_to IS NULL OR effective_as_of_date <= effective_to) AND available_at <= effective_as_of_date`. The full semantics are recorded in §26.1 below; the bare-scalar `as_of` reference is removed.

### §14.6 Read/Write / Idempotency

- Read-only. Idempotent on `(normalized_request.canonical_request_hash, resolved_location_id, varieties, prior_version)`.

### §14.7 Citation identity

- `prior_version`, `catalog_version`, `sample_count`, `covered_seasons`, `historical_mape`.

---

## §15 `forecast_daily_curve` contract

### §15.1 Purpose

Produce per-day (from season start to April 30) values for natural maturity, harvest implementation, backlog, weather / Spring-Festival tags, and final per-day commodity-fruit arrival volume.

### §15.2 Input

```yaml
forecast_daily_curve_input:
  normalized_request: NormalizedAgentRequest   # carries effective_as_of_date / effective_forecast_season / season_resolution_policy_version / season_calendar_config_hash / canonical_request_hash
  parameters: [...]                            # output of infer_parameters
  resolved_location: ResolvedLocation
  scenario: ScenarioConfig                      # default planning scenario
  advanced_overrides: AdvancedOverrides | null
```

### §15.2.1 Idempotency

Idempotent on `(normalized_request.canonical_request_hash, parameters_hash, resolved_location_id, scenario_config_hash, advanced_overrides_hash, authorities)`.

### §15.3 Output — quantile-preserving per-day row

```yaml
ForecastDailyRow:
  date: date
  natural_maturity_quantity_kg: DailyQuantiles           # P50/P80/P90 kg, canonical decimal strings
  harvested_quantity_kg: DailyQuantiles                  # TASK-009 derived; quantile-preserving
  closing_mature_inventory_kg: DailyQuantiles            # TASK-009 derived end-of-day inventory
  unharvested_backlog_kg: DailyQuantiles                 # TASK-009 derived backlog
  arrival_quantity_kg: DailyQuantiles                    # TASK-009 derived daily arrival (kg)
  final_corrected_arrival_quantity_kg: DailyQuantiles    # TASK-008/010 corrected
  per_variety_contribution:
    - variety_id: string
      volume_kg_p50: decimal_string
      volume_kg_p80: decimal_string
      volume_kg_p90: decimal_string
  weather_tags: [string]
  spring_festival_phase: enum [PRE, DURING, POST, NONE]
```

Where `DailyQuantiles` is the canonical shape:

```yaml
DailyQuantiles:
  p50: decimal_string    # canonical decimal string, e.g. "1234.567"
  p80: decimal_string
  p90: decimal_string
```

Rules:
- All per-day scalar fields derived from TASK-009 MUST preserve the P50/P80/P90 triplet. Collapsing any of `harvested_quantity_kg`, `closing_mature_inventory_kg`, `unharvested_backlog_kg`, `arrival_quantity_kg`, `final_corrected_arrival_quantity_kg` into a single unqualified number is rejected.
- Quantile values are emitted as canonical decimal strings (NUMERIC precision; never Python `float`).
- The unit for all per-day quantity fields is **kilograms (kg)**. `per_variety_contribution[*].volume_kg_*` are also kg.
- A per-day row carries an `agent_daily_row_hash: sha256` (prefixed `agent_*` per §9.3.6) so the orchestrator can prove byte-equality on reload.

### §15.4 Authority contract

- Composes TASK-008 natural maturity + TASK-009 harvest state + TASK-010 residual adjustment.
- Composition MUST be deterministic: given the same inputs + same authorities + same `effective_as_of_date`, the output MUST be byte-identical.
- Consumed authorities are reported as **typed envelopes** per §9.3 — not as `task8_authority: {run_id, manifest_hash, result_hash}` shorthand.

```yaml
authorities_consumed:
  task8_authority: Task8Authority | null            # typed envelope, §9.3.1
  task9_authority: Task9Authority | null            # typed envelope, §9.3.2
  task10_authority: Task10Authority | null          # typed envelope, §9.3.3
  task12_authority: Task12Authority | null          # typed envelope, §9.3.5; null when not consulted
  agent_daily_curve_hash: sha256                    # adapter-introduced hash, never aliases a real task hash
```

### §15.5 Blockers

- `TASK8_AUTHORITY_NOT_FOUND` — no TASK-008 run matches `(effective_as_of_date, effective_forecast_season, normalized_location, varieties)`.
- `TASK9_AUTHORITY_NOT_FOUND` — analogous; typed per §9.3.2.
- `TASK10_AUTHORITY_NOT_FOUND` — analogous; typed per §9.3.3.
- `TASK12_AUTHORITY_NOT_FOUND` — only when an explicit `TASK12_PREDICTION_RUN` authority override is supplied and not found.
- `EFFECTIVE_AS_OF_OUT_OF_POLICY` — `effective_as_of_date` falls outside the season-calendar policy window.
- `SEASON_CALENDAR_POLICY_MISSING` — no season-calendar policy registered at runtime.

### §15.6 Read/Write / Idempotency

- Read-only (composes existing reads). Idempotent on `(normalized_request.canonical_request_hash, effective_as_of_date, authorities)`.

### §15.7 Citation identity

- All consumed typed authority envelopes (§9.3) + `effective_as_of_date` + `effective_forecast_season` + `season_resolution_policy_version` + `season_calendar_config_hash`.

### §15.8 MVP scope

TASK-012 is **NOT consulted** in any default or advanced MVP path. The TASK-012 read path is reachable **only** when an explicit `AdvancedOverrides.authority_overrides[target = TASK12_PREDICTION_RUN].value` is supplied, per §22.1. There is no TASK-012 default branch in this design.

---

## §16 `forecast_peak` contract

### §16.1 Purpose

Derive peak metrics deterministically from `ForecastDailyRow[]` produced by `forecast_daily_curve`. All rules live in a versioned **`PeakMetricPolicy`** object (§16.4) — no rule is implicit.

### §16.2 Input

`forecast_daily_curve_output.per_day: ForecastDailyRow[]`.

### §16.3 Output

```yaml
forecast_peak_output:
  peak_metric_policy_version: string       # exact PeakMetricPolicy version used
  peak_metric_policy_config_hash: sha256   # sha256 of the policy config
  agent_peak_hash: sha256                  # adapter-introduced; never aliases a real task hash
  single_day_peak:
    p50: { date: date, volume_kg: decimal_string }
    p80: { date: date, volume_kg: decimal_string }
    p90: { date: date, volume_kg: decimal_string }
  sustained_window_days: 3                # from PeakMetricPolicy
  sustained_3day_peak:
    p50:
      start_date: date
      end_date: date                       # inclusive; 3 consecutive calendar dates
      rolling_daily_average_kg_per_day: decimal_string
      cumulative_quantity_kg: decimal_string  # also output (formula §16.5.4)
    p80: { ... }
    p90: { ... }
  peak_window_days_before: 7               # from PeakMetricPolicy
  peak_window_days_after: 7                # from PeakMetricPolicy
  peak_window_cumulative_quantity_kg:      # ±7-day inclusive 15-day window, clipped to forecast boundaries (§16.5.6)
    p50: decimal_string
    p80: decimal_string
    p90: decimal_string
  peak_duration_days:                      # per §16.5.8 (high_load_reference + high_load_threshold_ratio from policy)
    p50: integer
    p80: integer
    p90: integer
  high_load_threshold:                     # decimal-string threshold per quantile, per §16.5.8
    p50: decimal_string
    p80: decimal_string
    p90: decimal_string
  dominant_variety:
    p50: { variety_id: string, contribution_rate: decimal_string, numerator_kg: decimal_string, denominator_kg: decimal_string }
    p80: { ... }
    p90: { ... }
  peak_formation_explanation_ref: string   # pointer into explain_forecast output
```

Every peak / window / sustained value is output separately for P50, P80, and P90 (§16.5.7).

### §16.4 `PeakMetricPolicy` (versioned)

```yaml
PeakMetricPolicy:
  policy_version: string                              # e.g. "peak-metric/v1"
  policy_config_hash: sha256                          # sha256 of canonical JSON of this policy
  sustained_window_days: 3
  sustained_metric: ROLLING_DAILY_AVERAGE             # mean over the window
  tie_break: EARLIEST_START_DATE                      # stable tie-break that always resolves a winner
  peak_window_days_before: 7
  peak_window_days_after: 7
  high_load_reference: SINGLE_DAY_PEAK                # defines the reference statistic used to compute high_load_threshold[q] below
  high_load_threshold_ratio: decimal_string           # dimensionless; high_load_threshold[q] = ratio × reference_volume[q]
```

The peak policy is **deterministic and versioned**. It is NOT a hidden "3-day" prose rule; its `policy_version` and `policy_config_hash` are recorded in the output.

**`high_load_reference` is a frozen policy field.** `SINGLE_DAY_PEAK` is the frozen default and means `high_load_threshold[q] = high_load_threshold_ratio × single_day_peak[q].volume_kg`. If a future amendment chooses another reference statistic (e.g. `SUSTAINED_3DAY_PEAK`), that amendment MUST also freeze its exact formula, ordering, rounding rule, and tie-break in this section; until such an amendment is merged, `high_load_reference = SINGLE_DAY_PEAK` is the only allowed value.

### §16.5 Frozen formulas

1. **`single_day_peak[q]`** = maximum `final_corrected_arrival_quantity_kg.q` over all rows of `per_day`. Equal maxima resolve to the **earliest date** (the `tie_break` from `PeakMetricPolicy` always resolves a winner).
2. **Tie-break** = earliest date. Stable. Always resolves a winner. The tie-break is part of the policy; no extra blocker code is raised on equal maxima.
3. **`sustained_3day_peak[q]`** = maximum rolling three-day arithmetic mean of `final_corrected_arrival_quantity_kg.q`, in **kg/day**. The rolling window is computed over `per_day` ordered by `date`.
4. **Sustained cumulative quantity.** For the same three-day window that produced `sustained_3day_peak[q]`, the cumulative sum of `final_corrected_arrival_quantity_kg.q` over the three days is also output as `sustained_3day_peak[q].cumulative_quantity_kg`.
5. **Window continuity rule.** A sustained window MUST contain three **actual consecutive calendar dates** present in `per_day`. If the daily row sequence has gaps, the window is not eligible.
6. **±7-day window cumulative.** An inclusive 15-day window (`peak_window_days_before=7` calendar dates before the single-day-peak date plus `peak_window_days_after=7` calendar dates after) is taken around `single_day_peak[q].date`. The window is clipped to the forecast boundaries (season start and April 30, or the explicit `forecast_window` if one is supplied). The cumulative quantity of `final_corrected_arrival_quantity_kg.q` over that window is output as `peak_window_cumulative_quantity_kg[q]`.
7. **Per-quantile separation.** Every peak / window / sustained value is output separately for P50, P80, P90. Mixing quantiles inside a single field is rejected.
8. **`peak_duration_days[q]`** uses `high_load_threshold_ratio` and `high_load_reference` from `PeakMetricPolicy`. With the frozen default `high_load_reference = SINGLE_DAY_PEAK`, `high_load_threshold[q] = high_load_threshold_ratio × single_day_peak[q].volume_kg` (decimal-string arithmetic, canonical round-half-to-even at 18 fractional digits, no float). A day is in the peak duration window if its `final_corrected_arrival_quantity_kg.q ≥ high_load_threshold[q]`. `peak_duration_days[q]` is the length of the **maximum consecutive run** of such days **containing** `single_day_peak[q].date`, with `tie_break = EARLIEST_START_DATE`. The `high_load_threshold[q]` value itself is output as a decimal string in `forecast_peak_output.high_load_threshold[q]` for auditability.
9. **Dominant variety** is computed for the **selected peak window and quantile** (`single_day_peak[q]` or `sustained_3day_peak[q]` per the call site). The dominant variety is the variety with the largest sum of `per_variety_contribution[*].volume_kg_q` over the window. The output discloses both `numerator_kg` (that variety's sum) and `denominator_kg` (the window total) so the contribution rate is independently verifiable.
10. **Stable tie-break, no extra blocker.** The stable tie-break in the policy always resolves a winner; no extra blocker is raised on equal maxima. The historical equal-maxima blocker code (a separate code raised when equal maxima could not be resolved) is removed.

### §16.6 Authority contract

- Pure deterministic derivation from `ForecastDailyRow[]`. **LLM MUST NOT compute peak values.**
- Authoritative numbers in the output carry the same citation identity as the underlying daily curve (§15.7) + `peak_metric_policy_version` + `peak_metric_policy_config_hash`.

### §16.7 Blockers

- `EMPTY_CURVE` — `per_day` is empty (season start > April 30 or all days had zero data) → `forecast_peak` cannot run; downstream `explain_forecast` emits a no-peak explanation.
- `PEAK_POLICY_MISSING` — no `PeakMetricPolicy` registered at runtime → request fails before any peak computation. This is a different error from the historical equal-maxima blocker that has been removed.

### §16.8 Read/Write / Idempotency

- Read-only. Idempotent on `(per_day, peak_metric_policy_version, peak_metric_policy_config_hash)`.

### §16.9 Citation identity

- `peak_metric_policy_version` + `peak_metric_policy_config_hash` + `agent_peak_hash` + inherited from `forecast_daily_curve_output`.

---

## §17 `simulate_scenario` contract

### §17.1 Purpose

Re-run `forecast_daily_curve` and `forecast_peak` with a modified scenario (staffing, Spring-Festival intensity, processor capacity). Default scenario is the planning scenario.

### §17.2 Input

```yaml
simulate_scenario_input:
  normalized_request: NormalizedAgentRequest   # carries effective_as_of_date / effective_forecast_season / season_resolution_policy_version / season_calendar_config_hash / canonical_request_hash
  scenario_overrides: [AdvancedOverrides.scenario_overrides]   # typed override list per §8.1 (StaffingOverride / SpringFestivalIntensityOverride / ProcessorCapacityOverride)
```

### §17.3 Output

```yaml
simulate_scenario_output:
  scenario_id: sha256                      # sha256 of canonical JSON of scenario_overrides (frozen to sha256, not "string")
  scenario_config_hash: sha256             # sha256 of canonical JSON of simulate_scenario_input.scenario_overrides
  forecast_daily_curve: forecast_daily_curve_output
  forecast_peak: forecast_peak_output
  delta_vs_baseline:
    single_day_peak_volume_delta_kg:       # per-day peak volume difference vs baseline, decimal_string, per quantile
      p50: decimal_string
      p80: decimal_string
      p90: decimal_string
    sustained_3day_daily_average_delta_kg_per_day:  # rolling 3-day mean delta vs baseline, decimal_string, per quantile
      p50: decimal_string
      p80: decimal_string
      p90: decimal_string
    sustained_3day_cumulative_delta_kg:    # 3-day cumulative delta vs baseline, decimal_string, per quantile
      p50: decimal_string
      p80: decimal_string
      p90: decimal_string
```

All authoritative quantities in `delta_vs_baseline` are **decimal strings** (no Python `float`, no generic JSON number); arithmetic uses canonical decimal-string arithmetic per §16.5.8 conventions. `scenario_id` and `scenario_config_hash` are sha256 strings over the canonical JSON.

### §17.4 Authority contract

- Wraps `forecast_daily_curve` + `forecast_peak` with a deterministic scenario config.
- The `scenario_id` MUST be a content hash of the scenario config (canonical JSON).
- `simulation_id` from existing TASK-009 simulation service MAY be reused; if absent, the new adapter supplies its own hash.

### §17.5 Blockers

- `SCENARIO_INVALID` — staffing < 0, capacity < 0, etc.
- `SCENARIO_INCOMPATIBLE_WITH_BASE` — scenario requires a parameter that the base request did not provide.

### §17.6 Read/Write / Idempotency

- Read-only. Idempotent on `(normalized_request.canonical_request_hash, scenario_overrides_hash)`.

### §17.7 Citation identity

- `scenario_config_hash` (sha256 of canonical JSON of `simulate_scenario_input.scenario_overrides`) + inherited from underlying daily curve / peak + `normalized_request.canonical_request_hash`.

### §17.8 MVP scope

Allowed in MVP. The adapter is new, but it wraps existing services; no new numerical algorithm is created in this design.

---

## §18 `run_backtest` advanced / deferred boundary

### §18.1 Why deferred

`run_backtest` maps to TASK-011's `backend/app/rolling_backtest/` (service.py + orchestration.py + cli.py). Calling it inside the Agent's default MVP path would:
- be expensive (historical visibility + evaluation materialization);
- would require explicit `AdvancedOverrides.authority_overrides[target = TASK11_BACKTEST_RUN].value` (typed integer row id) + scenario config;
- require the Agent to interpret backtest metrics into natural language (a Step where an LLM could be tempted to fabricate summary text).

Therefore `run_backtest` is classified as **`DEFERRED_ADVANCED_TOOL`**:
- NOT in the default minimal-input MVP path.
- Allowed only via `AdvancedOverrides.execution_overrides[target = REQUEST_BACKTEST]` (typed override envelope; boolean value).
- When requested, MUST be guarded by a future confirmation-token mechanism (out of scope for this design round).

### §18.2 Future amendment gate

A future design amendment MUST separately authorize:
1. The exact backtest request contract.
2. The confirmation-token mechanism.
3. The post-backtest explanation contract (TASK-011 evaluation materialization already exists, but the Agent-side consumption pattern is not yet frozen).
4. The cost / latency budget for a single Agent-side backtest invocation.

This design round does NOT authorize any of the above.

---

## §19 `explain_forecast` contract

### §19.1 Purpose

Produce a **structured explanation payload** that:
- lists every authoritative numerical value with its citation block;
- provides a deterministic, pre-defined natural-language template per metric category;
- marks every natural-language sentence with one of:
  - `AUTHORITATIVE_VALUE` — quote an exact value from a deterministic service;
  - `DETERMINISTIC_EXPLANATION` — deterministic narrative derived from a documented rule;
  - `DETERMINISTIC_RECOMMENDATION` — output of `generate_recommendations`;
  - `NON_AUTHORITATIVE_PRESENTATION` — rephrasing (reserved for future LLM Slice E).

### §19.2 Input

Outputs of tools 1–5 (or subset).

### §19.3 Output

```yaml
explain_forecast_output:
  structured_payload:
    - section: string  # e.g. "Daily curve summary", "Peak analysis", "Variety contribution"
      paragraphs:
        - kind: enum [AUTHORITATIVE_VALUE, DETERMINISTIC_EXPLANATION, DETERMINISTIC_RECOMMENDATION, NON_AUTHORITATIVE_PRESENTATION]
          text: string  # for AUTHORITATIVE_VALUE, the exact value reference must be a structured cite, not a number string
          citation:                                     # canonical Citation schema; the single source of truth for all citations in this design
            source_tasks:                                # list (composite fields may depend on multiple source tasks simultaneously)
              - enum [TASK_008, TASK_009, TASK_010, TASK_011, TASK_012, TASK_013]
            source_tool: enum [
              RESOLVE_LOCATION,
              INFER_PARAMETERS,
              FORECAST_DAILY_CURVE,
              FORECAST_PEAK,
              SIMULATE_SCENARIO,
              EXPLAIN_FORECAST,
              GENERATE_RECOMMENDATIONS
            ]
            authorities:                                  # list (one per source task actually consumed)
              - authority_type: enum [
                  TASK_8_AUTHORITY,
                  TASK_9_AUTHORITY,
                  TASK_10_AUTHORITY,
                  TASK_11_AUTHORITY,
                  TASK_12_AUTHORITY
                ]
                authority: Task8Authority | Task9Authority | Task10Authority | Task11Authority | Task12Authority
            agent_artifact_hash: sha256 | null           # adapter-introduced canonical hash (e.g. agent_daily_curve_hash); never aliases a real task hash
            field_path: string                           # e.g. "daily_curve.per_day[7].final_corrected_arrival_quantity_kg.p50"
            effective_as_of_date: date
            confidence_evidence: object | null           # structured object, not free text
            tags:                                        # empty list when no override affected the cited value
              - enum [OVERRIDE_APPLIED]                  # MUST contain OVERRIDE_APPLIED iff any override materially affected the value
            override_refs:                               # identifies every override that materially affected the value; empty list when none
              - override_kind: enum [
                  PARAMETER_OVERRIDE_KIND,
                  SCENARIO_OVERRIDE_KIND,
                  EXECUTION_OVERRIDE_KIND,
                  AUTHORITY_OVERRIDE_KIND,
                  AS_OF_OVERRIDE
                ]
                target: string | null                    # typed override target (e.g. "TASK12_PREDICTION_RUN"); null for parameter_overrides without a target
                source_attestation: string               # copied verbatim from the override envelope
                source_ref: object | null                # copied verbatim from the override envelope
```

**Single source of truth.** The `Citation` schema above is the canonical citation contract; it is the only citation shape allowed in §19 / §20 / §24.2. Universal shorthands `run_id` / `result_hash` / `manifest_hash` / `forecast_cutoff` / `as_of` MUST NOT appear as top-level citation fields; if any such value is needed, it MUST appear only inside the typed authority envelope (`Task8Authority` / `Task9Authority` / `Task10Authority` / `Task11Authority` / `Task12Authority` per §9.3).

**`OVERRIDE_APPLIED` discipline.** The `tags` list MUST contain `OVERRIDE_APPLIED` whenever any override (parameter, scenario, execution, authority, or as-of) materially affected the cited value; `override_refs` MUST enumerate every such override with its `override_kind`, `target`, `source_attestation`, and `source_ref`. When no override affected the value, `tags = []` and `override_refs = []`. This contract is identical in §19.3, §20.3, and §24.2 (no second citation schema).

### §19.4 Authority contract

- The Agent (this slice) outputs only `AUTHORITATIVE_VALUE`, `DETERMINISTIC_EXPLANATION`, `DETERMINISTIC_RECOMMENDATION` kinds.
- `NON_AUTHORITATIVE_PRESENTATION` is reserved for Slice E (future LLM adapter).
- An LLM (when introduced in Slice E) MAY only rephrase `DETERMINISTIC_EXPLANATION` and `NON_AUTHORITATIVE_PRESENTATION`; it MUST NOT alter the number, hash, date, or recommendation content of an `AUTHORITATIVE_VALUE` / `DETERMINISTIC_RECOMMENDATION` sentence.

### §19.5 Blockers

- `CITATION_MISSING_FIELD_PATH` — an `AUTHORITATIVE_VALUE` paragraph lacks a `field_path`.
- `CITATION_HASH_MISMATCH` — the cited hash does not match the artifact actually consumed.

### §19.6 Read/Write / Idempotency

- Read-only. Idempotent on inputs.

### §19.7 Citation identity

- Every paragraph carries its own citation block.

---

## §20 `generate_recommendations` contract

### §20.1 Purpose — 7 categories total (6 operational + 1 data-quality)

Produce deterministic recommendations for **7 categories total = 6 operational recommendation categories + 1 MISSING_DATA_IMPACT category (data-quality)**:

| # | Category | Kind |
|---|---|---|
| 1 | Recommended sustained processing capacity (推荐持续处理能力) | operational |
| 2 | Recommended receiving / temporary-storage / pre-cooling peak capacity (推荐收货/暂存/预冷瞬时能力) | operational |
| 3 | Peak-period shift recommendation (高峰期班次建议) | operational |
| 4 | Spring-Festival staffing preparation (春节人员准备) | operational |
| 5 | Variety stagger / pruning batch recommendation (品种错峰或修剪批次建议) | operational |
| 6 | Cross-plant dispatch necessity (是否需要跨厂分流) | operational |
| 7 | Which additional data would most improve accuracy (哪些额外数据最能提升准确性) | **data-quality** — `MISSING_DATA_IMPACT` |

Every recommendation is tagged with its `kind` (`OPERATIONAL` or `DATA_QUALITY`) so downstream consumers can filter or rank them.

### §20.2 Authority contract

- All recommendations MUST be derivable from:
  - documented deterministic rules;
  - scenario outputs (when `simulate_scenario` was called);
  - capacity thresholds (documented per rule);
  - confidence thresholds (documented per rule);
  - explicit evidence references (citation block).
- LLM MUST NOT generate recommendation numbers, dates, capacities, or staffing counts from intuition.

### §20.3 Output

```yaml
generate_recommendations_output:
  recommendations:
    - category: enum [
        SUSTAINED_PROCESSING_CAPACITY,
        RECEIVING_PEAK_CAPACITY,
        SHIFT_STAFFING,
        SPRING_FESTIVAL_STAFFING,
        VARIETY_STAGGER,
        CROSS_PLANT_DISPATCH,
        MISSING_DATA_IMPACT,
      ]
      kind: enum [OPERATIONAL, DATA_QUALITY]   # OPERATIONAL for #1–#6, DATA_QUALITY for #7
      text: string                            # deterministic template output
      rule_id: string                         # identifies the exact rule used
      evidence:
        - citation:                                     # canonical Citation schema per §19.3 (single source of truth)
            source_tasks:
              - enum [TASK_008, TASK_009, TASK_010, TASK_011, TASK_012, TASK_013]
            source_tool: enum [
              RESOLVE_LOCATION,
              INFER_PARAMETERS,
              FORECAST_DAILY_CURVE,
              FORECAST_PEAK,
              SIMULATE_SCENARIO,
              EXPLAIN_FORECAST,
              GENERATE_RECOMMENDATIONS
            ]
            authorities:
              - authority_type: enum [
                  TASK_8_AUTHORITY,
                  TASK_9_AUTHORITY,
                  TASK_10_AUTHORITY,
                  TASK_11_AUTHORITY,
                  TASK_12_AUTHORITY
                ]
                authority: Task8Authority | Task9Authority | Task10Authority | Task11Authority | Task12Authority
            agent_artifact_hash: sha256 | null
            field_path: string                           # e.g. "peak.sustained_3day_peak.p90.rolling_daily_average_kg_per_day"
            effective_as_of_date: date
            confidence_evidence: object | null
            tags:                                        # empty list when no override affected the recommendation value
              - enum [OVERRIDE_APPLIED]
            override_refs:
              - override_kind: enum [
                  PARAMETER_OVERRIDE_KIND,
                  SCENARIO_OVERRIDE_KIND,
                  EXECUTION_OVERRIDE_KIND,
                  AUTHORITY_OVERRIDE_KIND,
                  AS_OF_OVERRIDE
                ]
                target: string | null
                source_attestation: string
                source_ref: object | null
        - threshold: {parameter, value, unit}
      confidence: enum [HIGH, MEDIUM, LOW]
```

### §20.4 Blockers

- `RULE_NOT_APPLICABLE` — input parameters do not meet any rule's preconditions → emit "no recommendation" with citation.
- `RULE_THRESHOLD_MISSING` — required threshold parameter absent → `LOW_CONFIDENCE` recommendation.

### §20.5 Read/Write / Idempotency

- Read-only. Idempotent on inputs.

### §20.6 Citation identity

- `rule_id`, `evidence[].citation`, `evidence[].threshold`.

### §20.7 Anti-fabrication guard

Any recommendation text MUST contain at least one `evidence` block; else the recommendation MUST be suppressed.

---

## §21 TASK-008 through TASK-012 integration

TASK-013 consumes TASK-008–012 services through the typed authority envelopes in §9.3. The integration table below cites, for each task, the real field names that surface in the orchestrator's provenance and citation blocks. Generic `taskX_run_id` aliases are NOT used; each entry is the real field.

| Task | What TASK-013 consumes | Authority envelope used (§9.3) | Real fields that surface in citation |
|---|---|---|---|
| TASK-008 natural maturity curve | `backend/app/maturity/service.py` outputs (per-day natural maturity distribution) | `Task8Authority` (§9.3.1) | `maturity_model_run_id`, `maturity_model_version`, `maturity_model_config_hash`, `maturity_model_source_signature`, `maturity_model_artifact_id`, `maturity_model_artifact_hash`, `maturity_forecast_run_id`, `maturity_forecast_source_signature`, `maturity_forecast_as_of_date` |
| TASK-009 / TASK-009A harvest state | `backend/app/harvest_state/service.py` outputs (backlog, release, arrival, harvest-implementation rate, end-of-day inventory) | `Task9Authority` (§9.3.2) | `harvest_state_run_id`, `harvest_state_run_config_hash`, `harvest_state_run_result_hash`, `harvest_state_run_canonical_payload_hash`, `harvest_state_output_schema_version`, `harvest_state_as_of_date`, `harvest_state_forecast_start_date`, `harvest_state_forecast_end_date`, `destination_factory_id`, `pool_row_count`, `member_row_count`, `cohort_row_count`, `future_arrival_row_count`, `source_ref_schema_version`, `result_hash_schema_version`, `stable_cohort_key_schema_version`, `resolved_parameter_snapshot_schema_version` |
| TASK-010 residual model | `backend/app/residual_model/` + `backend/app/baseline/` outputs (residual adjustment, fallback semantics) | `Task10Authority` (§9.3.3) | `training_run_id`, `training_manifest_hash`, `prediction_run_id`, `task9_run_id`, `task9_result_hash`, `prediction_hash`, `prediction_config_hash`, `prediction_input_signature`, `artifact_hashes`, `feature_schema_hash`, `prediction_canonical_payload_hash` |
| TASK-011 rolling backtest | `backend/app/rolling_backtest/` outputs (when explicitly requested via advanced override) | `Task11Authority` (§9.3.4) | `rolling_backtest_run_id`, `run_signature`, `config_hash`, `canonical_payload_hash`, `rolling_schema_version`, `canonical_serialization_version`, `availability_registry_version`, `node_calendar_version`, `forecast_horizon_policy_version`, `upstream_selection_policy_version`, `metric_policy_version`, `cutoff_policy_version`, `execution_mode`, `status`, `expected_node_count` (+ TASK-013 consumption metadata: `node_count`, `attempt_count`, `orchestration_snapshot_id`, `resolved_input_id`) |
| TASK-012 replay-trained model | `backend/app/rolling_backtest/replay_trained_*.py` outputs (only when explicit `TASK12_PREDICTION_RUN` authority override is supplied) | `Task12Authority` (§9.3.5) | `prediction_run_id`, `training_manifest_hash`, `model_config_hash`, `task9_run_id`, `task9_result_hash`, `prediction_hash`, `forecast_cutoff_at`, `training_cutoff_at`, `model_code_version`, `task12_policy_version`, `validation_policy_version`, `label_visibility_policy_version`, `feature_visibility_policy_version`, `artifact_visibility_policy_version`, `model_artifact_hash`, `task9_replay_binding_identity`, `task10_manifest_hash`, `task10_config_hash` |

### §21.1 Composition order (deterministic)

The composition order in `forecast_daily_curve` MUST be:
1. TASK-008 produces natural maturity per-day.
2. TASK-009 produces harvest-implementation / backlog / end-of-day inventory / arrival per-day from TASK-008.
3. TASK-010 produces residual adjustment per-day and combines with TASK-008 + TASK-009.
4. TASK-012 (only if explicitly requested) provides a replay-trained overlay; the overlay MUST NOT replace steps 1–3; it MAY add a residual signal that is itself cited.

### §21.2 Anti-leakage rule

The composition MUST NOT:
- apply TASK-012 residual as a hidden override of TASK-008 natural maturity;
- substitute TASK-011 backtest metric as a TASK-008 maturity value;
- rewrite TASK-009 backlog based on TASK-010 residual.

---

## §22 TASK-012 replay-trained model boundary

### §22.1 Read path (explicit override only)

**Frozen rule.** TASK-013 MAY read TASK-012's persisted artifacts through `GET /api/v1/rolling-backtest/replay-trained-predictions/{prediction_run_id}` **only** when an explicit `TASK12_PREDICTION_RUN` authority override is supplied (`AdvancedOverrides.authority_overrides[target = TASK12_PREDICTION_RUN].value` = integer `prediction_run_id`).

No other TASK-013 path is permitted to consume TASK-012:

- The deterministic authority resolver (§9) MUST NOT auto-select a TASK-012 authority for any `effective_as_of_date`. There is no automatic TASK-012 resolution path.
- The MVP default path MUST NOT call TASK-012. §15.8, §21, §22.1, §22.4, and §34.1 are synchronized to this rule.

When the explicit `TASK12_PREDICTION_RUN` authority override is supplied, the Agent MUST carry the `Task12Authority` envelope (§9.3.5) — including `prediction_run_id`, `scenario_id`, `training_manifest_hash`, `model_config_hash`, `task9_result_hash`, `task10_manifest_hash`, `task10_config_hash`, `model_code_version`, and `model_artifact_hash` when present — into the output's provenance block. No field is fabricated; the Agent reads them from the persisted row and the request payload. If the supplied `prediction_run_id` is not found in the persisted TASK-012 prediction rows → `TASK12_AUTHORITY_NOT_FOUND` blocker (§26.1); the Agent MUST NOT silently substitute a different `prediction_run_id`.

### §22.2 Forbidden actions

The Agent MUST NOT:
- call `POST /api/v1/rolling-backtest/replay-trained-predictions` in the default MVP path or any other frozen slice (§22.4);
- forge any field of the `Task12Authority` envelope (`prediction_run_id`, `scenario_id`, `training_manifest_hash`, `model_config_hash`, `task9_result_hash`, `task10_manifest_hash`, `task10_config_hash`, `model_code_version`, `model_artifact_hash`);
- substitute one TASK-012 run's result for another (cross-run substitution);
- treat a TASK-012 result as "latest historical observation";
- replace TASK-008 / TASK-010 outputs with a TASK-012 overlay without explicit caller opt-in.

### §22.3 Write path (always deferred)

Creating a new replay-trained run is **advanced execution**. It:
- MUST NOT be triggered by the default MVP path or any frozen slice (§22.4);
- MUST NOT be triggered by `POST /api/v1/rolling-backtest/replay-trained-predictions` from TASK-013 in any frozen slice;
- MUST require an explicit `AdvancedOverrides.execution_overrides[target = REQUEST_REPLAY_TRAINED_RUN]` flag;
- MUST be guarded by a future confirmation-token mechanism (out of scope here);
- MUST be authorized by a separate TASK-013 amendment that also re-opens §22.4.

### §22.4 Slice gating — TASK-012 POST is outside all currently frozen slices

The TASK-012 read path is allowed under §22.1. The TASK-012 POST (creation) path is **outside every currently frozen implementation slice**:

| Slice | TASK-012 role |
|---|---|
| A (logical tool schemas + adapters) | Read path only; no POST |
| B (minimal-input orchestration) | Read path only via advanced override |
| C (explanation + recommendations) | Read path only |
| D (HTTP API + optional CLI) | Read path only — TASK-012 POST creation remains **NOT** part of Slice D |
| E (LLM adapter) | Read path only |

`POST /api/v1/rolling-backtest/replay-trained-predictions` and the corresponding `GET /api/v1/rolling-backtest/replay-trained-predictions/{prediction_run_id}` are real TASK-012 endpoints, but **TASK-013 does not invoke the POST in any frozen slice** and **TASK-013 does not invoke the GET automatically**. TASK-013 only consumes existing `prediction_run_id` results via GET when an explicit `AdvancedOverrides.authority_overrides[target = TASK12_PREDICTION_RUN].value` is supplied. The deterministic resolver (§9) MUST NOT auto-discover or auto-select a TASK-012 authority for any `effective_as_of_date`; TASK-012 reads are gated by explicit override only (frozen in §22.1).

TASK-012 POST may enter TASK-013 only after a **separately merged amendment** — which will introduce the confirmation-token mechanism, the per-tenant rate-limit / cost / latency budget, and a re-frozen §22.4. **This design does NOT include confirmation-token support.** Slice D does NOT ship with confirmation-token gating, and this PR must not imply otherwise.

---

## §23 Agent-versus-LLM authority boundary

### §23.1 Hard rules

| Capability | Agent (this design) | LLM (when introduced, Slice E) |
|---|---|---|
| Compute P50/P80/P90 | ❌ never | ❌ never |
| Compute peak (volume / date) | ❌ never | ❌ never |
| Compute inventory / backlog | ❌ never | ❌ never |
| Compute confidence interval | ❌ never | ❌ never |
| Generate model / result hash | ❌ never | ❌ never |
| Pick `*_run_id` autonomously | ❌ never | ❌ never |
| Generate parameter numbers | ❌ never | ❌ never |
| Generate recommendation numbers / dates / capacities | ❌ never | ❌ never |
| Bypass tool schema | ❌ never | ❌ never |
| Access non-allowlist tool | ❌ never | ❌ never |
| Read `.hermes` / shell history / secrets | ❌ never | ❌ never |
| Rephrase a `DETERMINISTIC_EXPLANATION` paragraph | ✅ (deterministic templates only) | ✅ (Slice E only; cannot alter underlying numbers) |
| Compose tool calls into a deterministic plan | ✅ (deterministic planner) | ✅ (Slice E only; cannot bypass allowlist) |
| Inject raw prompt content into a tool input beyond the documented schema | ❌ never | ❌ never |

### §23.2 LLM is optional

This design explicitly permits the first implementation Slice to ship without any LLM dependency. The structured explanation payload (§19) is the canonical output; a future Slice E LLM adapter may rephrase `DETERMINISTIC_EXPLANATION` paragraphs into natural language but cannot alter authoritative values.

### §23.3 No OpenAI / Anthropic dependency in Slice A–D

`pyproject.toml` MUST NOT introduce `openai`, `anthropic`, or any LLM client dependency in Slice A–D. Slice E may introduce it under a separate authorization round.

---

## §24 Output and provenance contract

### §24.1 Top-level output envelope

```yaml
AgentForecastOutput:
  request_id: string
  request_status: enum [OK, PARTIAL, BLOCKED]   # PARTIAL when UNKNOWN_VARIETY or per-tool partial outcomes (§26.1.1)
  normalized_request:
    request_id: string
    request_received_at: aware_datetime
    effective_as_of_date: date
    effective_forecast_season: integer
    season_resolution_policy_version: string
    season_calendar_config_hash: sha256
    canonical_request_hash: sha256
  resolved_location: ResolvedLocation
  parameters: [ParameterEstimate]  # from infer_parameters
  daily_curve: forecast_daily_curve_output
  peak: forecast_peak_output
  recommendations: generate_recommendations_output
  explanation: explain_forecast_output
  confidence: {level: enum [HIGH, MEDIUM, LOW], evidence: object}  # aggregate per §25.1
  uncertainty_widening_policy_version: string
  uncertainty_widening_policy_config_hash: sha256
  peak_metric_policy_version: string
  peak_metric_policy_config_hash: sha256
  provenance:
    requested_as_of_date_provenance: RequestedAsOfDateProvenance  # mirror of NormalizedAgentRequest.requested_as_of_date_provenance (§7.2 / §8.2)
    task8_authority: Task8Authority | null            # typed envelope, §9.3.1
    task9_authority: Task9Authority | null            # typed envelope, §9.3.2
    task10_authority: Task10Authority | null          # typed envelope, §9.3.3
    task11_authority: Task11Authority | null          # typed envelope, §9.3.4
    task12_authority: Task12Authority | null          # typed envelope, §9.3.5
    parameter_version_identities: [string]
    location_catalog_version: string
    prior_versions_used: [string]
    scenario_config_hash: string | null
    effective_as_of_date: date
    effective_forecast_season: integer
    season_resolution_policy_version: string
    season_calendar_config_hash: sha256
    uncertainty_widening_policy_version: string
    uncertainty_widening_policy_config_hash: sha256
    peak_metric_policy_version: string
    peak_metric_policy_config_hash: sha256
    agent_daily_curve_hash: sha256                    # adapter-introduced
    agent_peak_hash: sha256                           # adapter-introduced
  blockers: [Blocker]
  warnings: [string]
```

### §24.2 Citation discipline

The **canonical Citation schema** is defined in §19.3 and is the **single source of truth** for all citations in this design (used by §19 `explain_forecast`, §20 `generate_recommendations`, and §24 itself). Every authoritative numerical value in the output MUST carry a `Citation` block in the §19.3 shape, which means:

- `source_tasks` (list, not scalar) — the source tasks that produced the value (composite fields MAY depend on multiple tasks simultaneously).
- `source_tool` — the logical tool that produced the value.
- `authorities` (list, not scalar) — one typed envelope per source task actually consumed; each entry pairs an `authority_type` enum with its `authority` typed object from §9.3.
- `agent_artifact_hash` (sha256 | null) — adapter-introduced canonical hash (e.g. `agent_daily_curve_hash`), never aliases a real task hash.
- `field_path` — the precise JSON pointer to the field being cited (e.g. `daily_curve.per_day[7].final_corrected_arrival_quantity_kg.p50`).
- `effective_as_of_date` (date).
- `confidence_evidence` (object | null) — structured object (not free text).
- `tags` — list. MUST contain `OVERRIDE_APPLIED` iff any override (parameter, scenario, execution, authority, or as-of) materially affected the cited value. Empty list otherwise.
- `override_refs` — list. MUST enumerate every override that materially affected the cited value, with `override_kind` + `target` + `source_attestation` + `source_ref`. Empty list otherwise.

**Universal shorthands forbidden.** The strings `run_id`, `result_hash`, `manifest_hash`, `forecast_cutoff`, and `as_of` MUST NOT appear as top-level fields of a citation. When such a value is required by a downstream consumer, it MUST appear **only** inside the applicable typed authority envelope (`Task8Authority` / `Task9Authority` / `Task10Authority` / `Task11Authority` / `Task12Authority`) as defined in §9.3.

Natural-language sections MUST be classified as one of the four kinds in §19.1.

### §24.3 What the Agent MAY rephrase

Only paragraphs tagged `DETERMINISTIC_EXPLANATION` and `NON_AUTHORITATIVE_PRESENTATION`. The rephrase MUST NOT:
- change a number, hash, date, or volume;
- introduce a new recommendation category;
- drop a citation block.

---

## §25 Confidence and uncertainty contract

### §25.1 Aggregate confidence — frozen rule

Aggregate confidence = **worst confidence among all required parameters**.

This is a frozen rule. The earlier prose allowing aggregate confidence to be upgraded because a parameter set is "overdetermined" is **removed**. Until an exact upgrade rule is separately frozen (and only via a future amendment), no upgrade may be applied. Any implementation that would otherwise be tempted to upgrade aggregate confidence MUST NOT.

The aggregate is computed once per request and reported in the output envelope.

### §25.2 Required evidence disclosure

For each confidence level, the output MUST disclose:
- sample count (number of historical observations used)
- covered seasons (e.g. 2024, 2025)
- historical MAPE
- historical date MAE
- P90 coverage rate
- key missing items (e.g. "no same-farm history", "no same-variety in same climate zone")

### §25.3 Uncertainty widening — single source of truth

Uncertainty widening is governed **exclusively** by `UncertaintyWideningPolicy` in §10.3–§10.4. No second widening rule exists in §25.

- **Step 1**: no mandatory widening when HIGH evidence requirements are met.
- **Steps 2–5**: mandatory monotonically increasing widening.
- **Step 5**: maximum widening and LOW confidence.

All other text in this document that previously restated the widening rule is removed; any new restatement is rejected as drift.

### §25.4 Forbidden short-cut

The Agent MUST NOT:
- emit a single high-level confidence label without the required evidence fields;
- silently absorb a low-confidence parameter into a high-confidence aggregate (no overdetermined upgrade; §25.1);
- substitute "average historical yield" for an explicit prior version.

---

## §26 Error and blocker contract

### §26.1 Blocker taxonomy (canonical codes)

| Code | Meaning |
|---|---|
| `INPUT_INVALID_LOCATION` | `location` field missing all three of raw_text / coordinates / map_pick_token |
| `INPUT_INVALID_VARIETIES` | empty varieties list |
| `INPUT_INVALID_PLANTING_AREA` | planting_area_mu ≤ 0 |
| `INPUT_INVALID_AS_OF` | `requested_as_of_date` malformed or out of season-calendar policy window |
| `INPUT_INVALID_SEASON` | `requested_forecast_season` not recognized by the season-calendar policy |
| `SEASON_CALENDAR_POLICY_MISSING` | no season-calendar policy registered at runtime — `effective_as_of_date` / `effective_forecast_season` cannot be resolved |
| `EFFECTIVE_AS_OF_OUT_OF_POLICY` | `effective_as_of_date` falls outside the season-calendar policy window |
| `UNKNOWN_VARIETY` | **Per-variety blocked outcome.** The unknown variety produces no numerical prediction; known varieties in the same request continue; overall request status becomes `PARTIAL`. |
| `LOCATION_UNRESOLVED` | location could not be resolved to any zone |
| `LOCATION_AMBIGUOUS` | multiple zone candidates with same score → return top-N candidates; do NOT auto-pick |
| `LOCATION_CATALOG_STALE` | `effective_as_of_date` is before the catalog's effective date |
| `INSUFFICIENT_HISTORY` | no historical data at any priority step |
| `PARAMETER_OVERRIDE_INVALID` | advanced override references unknown parameter |
| `VARIETY_PRIOR_NOT_VISIBLE_AT_AS_OF` | **No prior version satisfies all three visibility constraints at `effective_as_of_date`** for the requested variety+parameter: `effective_from <= effective_as_of_date` AND `(effective_to IS NULL OR effective_as_of_date <= effective_to)` AND `available_at <= effective_as_of_date`. A prior whose `effective_from` is on/after `effective_as_of_date` is NOT considered visible (it has not yet started), and a prior whose `effective_to` is before `effective_as_of_date` is NOT considered visible (it has ended). This code is reserved for the case where the requested `(variety_id, parameter)` has **no** valid+visible prior at the effective as-of. |
| `TASK8_AUTHORITY_NOT_FOUND` | no TASK-008 run matches the typed selector (§9.3.1) |
| `TASK9_AUTHORITY_NOT_FOUND` | analogous; typed per §9.3.2 |
| `TASK10_AUTHORITY_NOT_FOUND` | analogous; typed per §9.3.3 |
| `TASK11_AUTHORITY_NOT_FOUND` | only when advanced override requests backtest |
| `TASK12_AUTHORITY_NOT_FOUND` | only when advanced `TASK12_PREDICTION_RUN` authority override is supplied and not found |
| `AUTHORITY_CONFLICT` | two persisted artifacts both satisfy the selector → do NOT auto-pick |
| `OVERRIDE_CONFLICT` | `AdvancedOverrides.as_of_overrides` contains more than one `AS_OF_OVERRIDE` entry, OR the precedence between `MinimalInputRequest.requested_as_of_date` and `AsOfOverride` is broken in a way not covered by §8.2 |
| `EXECUTION_DEFERRED` | caller requested backtest or replay-trained run creation (not allowed in this slice; no confirmation-token mechanism in any frozen slice) |
| `CITATION_MISSING_FIELD_PATH` | AUTHORITATIVE_VALUE paragraph missing field_path |
| `CITATION_HASH_MISMATCH` | cited hash does not match the artifact actually consumed |
| `PEAK_POLICY_MISSING` | no `PeakMetricPolicy` registered at runtime |
| `UNCERTAINTY_WIDENING_POLICY_MISSING` | no `UncertaintyWideningPolicy` registered at runtime |
| `SCENARIO_INVALID` | scenario_overrides invalid (negative staffing, negative capacity, etc.) |
| `SCENARIO_INCOMPATIBLE_WITH_BASE` | scenario requires absent parameter |
| `RULE_NOT_APPLICABLE` | no recommendation rule matched |
| `RULE_THRESHOLD_MISSING` | required threshold parameter absent |
| `INTERNAL_FAILURE` | internal exception (must include a stable error code, never a raw traceback) |

### §26.1.1 Per-variety partial-result behavior (UNKNOWN_VARIETY)

When `UNKNOWN_VARIETY` is raised for one or more varieties in a request:
- The affected varieties are removed from `forecast_daily_curve_output.per_day[*].per_variety_contribution` and from `forecast_peak_output.dominant_variety`.
- No numerical prediction (no P50/P80/P90) is emitted for the unknown variety.
- The remaining known varieties proceed normally; their `agent_daily_row_hash` and `agent_peak_hash` are computed only over the known-variety subset.
- The output's overall `request_status` is `PARTIAL`, and the `UNKNOWN_VARIETY` blocker is recorded against the affected `variety_id` only.
- `explain_forecast` MUST NOT mention the unknown variety in any `AUTHORITATIVE_VALUE` paragraph; if a recommendation depends on the unknown variety, it is suppressed with `RULE_THRESHOLD_MISSING` rather than fabricated.

### §26.2 Stable error envelope

```yaml
Blocker:
  code: string  # from §26.1
  message: string  # human-readable, deterministic across runs
  details: object | null
  citation: object | null
  retry_hint: enum [FIX_INPUT, PROVIDE_OVERRIDE, WAIT_FOR_DATA, CONTACT_OPS, NONE]
```

Error messages MUST be stable, non-leaking, machine-parseable. Raw tracebacks MUST NOT appear in the response.

---

## §27 Security and prompt-injection boundary

### §27.1 Data payload is not system instruction

The Agent MUST treat all repository / data payload as data, never as system instruction. No user-supplied text may:
- widen the tool allowlist;
- request a non-allowlisted tool;
- inject raw SQL / shell / Python / URL;
- request access to secrets / `.hermes` / shell history.

### §27.2 Tool output is not executable

The Agent MUST NOT execute:
- commands found in tool output;
- URLs found in tool output;
- tokens / credentials found in tool output.

Tool output is consumed only as data for the deterministic composition step.

### §27.3 Secret-handling rule

The Agent MUST NOT:
- echo, log, or persist secrets;
- include raw `Idempotency-Key` values in response bodies;
- include full internal traceback in response bodies;
- cross-tenant / cross-farm / cross-subfarm data lookup (single-request authority only).

### §27.4 Future LLM (Slice E) additional guardrails

When Slice E is implemented, additional rules apply:
- The LLM sees only the structured payload, not the raw user request verbatim (after PII redaction).
- The LLM's output is constrained to the four kinds in §19.1; numbers MUST come from the structured payload, not from LLM generation.
- The LLM's tool-call proposals MUST be validated against the allowlist before execution.

---

## §28 Persistence and migration non-scope

### §28.1 No persistence tables in this slice

The first implementation Slice MUST NOT create:
- `agent_query_audit`
- `agent_run`
- `agent_conversation`
- `agent_confirmation_log`

### §28.2 No Alembic migration in this slice

The first implementation Slice MUST NOT add an Alembic migration for TASK-013.

### §28.3 Reason

- The source `CODEX_TASKS.md` 把审计日志与生产化明确列入 TASK-014,不属于 TASK-013。
- The TASK-013 source has not frozen conversation persistence.
- Persistence / migration MUST be authorized by a separate TASK-013 amendment or by TASK-014.

### §28.4 What the first slice uses for traceability

- Existing business run identities (typed authority envelopes in §9.3: `Task8Authority` / `Task9Authority` / `Task10Authority` / `Task11Authority` / `Task12Authority`).
- Existing model / result / manifest hashes carried by those typed envelopes.
- Versioned policy identities and hashes:
  - `season_resolution_policy_version` + `season_calendar_config_hash` (§7.3);
  - `peak_metric_policy_version` + `peak_metric_policy_config_hash` (§16.4);
  - `uncertainty_widening_policy_version` + `uncertainty_widening_policy_config_hash` (§10.4).
- Request-scoped structured provenance in the response body: `agent_normalized_request_hash` (= `canonical_request_hash`), `agent_daily_curve_hash`, `agent_peak_hash`.
- Standard application logs with a stable `correlation_id` per request (NOT persisted to a TASK-013-owned table).

### §28.5 What MUST NOT be logged

- Raw prompt text.
- Full caller identity (only the request-supplied `request_id` is logged).
- Secrets.
- Raw `Idempotency-Key` values.
- Full internal tracebacks.

---

## §29 API / CLI / frontend boundary

### §29.1 API / CLI deferred to Slice D

This design freezes the **logical tool contracts** (§11–§20) and the **output envelope** (§24). The HTTP API and CLI surfaces are deferred to Slice D and require a separate authorization round.

### §29.2 Frontend explicitly excluded

Frontend (chat UI, form UI, any user-facing web component) is explicitly excluded from TASK-013. A separate frontend task will consume the Slice D HTTP API.

### §29.3 Implementation slices (proposed)

| Slice | Scope | Authorization gate |
|---|---|---|
| **Slice A** — Logical tool schemas + deterministic adapters | Define Pydantic / JSON Schema for tools 1–8; implement `resolve_location`, `infer_parameters`, `forecast_daily_curve`, `forecast_peak`, `simulate_scenario` adapters wrapping existing services. SQLite unit tests. | Requires Charles authorization for implementation round; this design round only freezes the contracts. |
| **Slice B** — Minimal-input deterministic orchestration service | Implement the orchestrator that takes `MinimalInputRequest` and produces `AgentForecastOutput`. SQLite + PostgreSQL integration tests. Golden JSON output. No HTTP API yet. | Requires Charles authorization. |
| **Slice C** — Structured explanation + deterministic recommendations | Implement `explain_forecast` + `generate_recommendations`. Rule engine + rule_id registry + threshold tables. Tests for rule coverage + anti-fabrication. | Requires Charles authorization. |
| **Slice D** — HTTP API + optional CLI | Expose the orchestrator behind a documented HTTP contract (POST request, GET retrieval, idempotency, hashes, error envelope). Optional CLI. NO frontend. | Requires Charles authorization. |
| **Slice E** — Optional LLM tool-routing / presentation adapter | Introduce an LLM client behind the allowlist; LLM MAY only rephrase `DETERMINISTIC_EXPLANATION` and `NON_AUTHORITATIVE_PRESENTATION`; never numbers / hashes / dates / recommendations. | Requires Charles authorization + LLM dependency approval. |
| **TASK-014 or separate TASK-013 amendment** | Audit persistence, permissions, monitoring, drift detection, model registry. | Belongs to TASK-014 or a separate amendment. |
| **Separate frontend task** | User-facing web UI consuming Slice D HTTP API. | Belongs to a separate frontend task. |

### §29.4 Currently excluded from all slices

- frontend
- chat UI
- conversation persistence
- external knowledge retrieval
- internet search
- cross-tenant comparison
- automatic report sending
- TASK-014 production controls

---

## §30 Testing strategy (design-only; no tests in this round)

The first implementation Slice MUST include the following test categories. This section freezes the test surface; no test code is written in this design round.

### §30.1 Functional tests

1. **Minimal location + variety-area input** — ordinary user path produces an `AgentForecastOutput` with all required sections.
2. **Versioned prior fallback** — when no same-farm history exists, falls back to lower-priority steps and widens confidence.
3. **Uncertainty widening** — low-priority inference step widens P80/P90 by the documented factor.
4. **Deterministic repeatability** — same `MinimalInputRequest` + same `request_received_at` + same versioned policies (`PeakMetricPolicy` / `UncertaintyWideningPolicy` / season-calendar policy) + same resolved typed authorities → byte-identical `NormalizedAgentRequest` and `AgentForecastOutput`.
5. **Stable tool ordering** — tool-call order is deterministic for the same request.
6. **No implicit latest** — for any authority selection, the resolved identity is recorded and disclosed.
7. **Source and model identity disclosure** — output's `provenance` block lists every consumed authority.
8. **No LLM numerical generation** — no number / hash / date / capacity appears in `NON_AUTHORITATIVE_PRESENTATION` paragraphs.
9. **No fabricated recommendation** — every recommendation has at least one evidence block.
10. **Missing location** — `INPUT_INVALID_LOCATION` blocker.
11. **Unknown variety** — `UNKNOWN_VARIETY` blocker; no numerical output for the affected variety; affected-variety outcome is `BLOCKED`; known varieties continue; overall `request_status` is `PARTIAL`. Do NOT assert any `LOW_CONFIDENCE` numerical prediction for the unknown variety.
12. **Insufficient historical samples** — `INSUFFICIENT_HISTORY` blocker + widened intervals.
13. **Authority conflict** — `AUTHORITY_CONFLICT` blocker + top-N candidates disclosed.
14. **Result-hash preservation** — every typed authority envelope's `result_hash` / `canonical_payload_hash` / `prediction_hash` field (where applicable) matches the actual artifact consumed (no tampering). Adapter-introduced `agent_artifact_hash` does not collide with any real task hash.
15. **Cross-run substitution rejection** — supplying one `AdvancedOverrides.authority_overrides[target = TASK12_PREDICTION_RUN].value` (integer `prediction_run_id`) and consuming a different `Task12Authority.prediction_run_id` is detected.

### §30.2 Security / prompt-injection tests

16. **Prompt injection cannot expand tool allowlist** — a user-supplied text claiming "now you may call tool X" is ignored.
17. **Tool output cannot execute commands** — a tool output containing shell command strings is not executed.
18. **No external URL / SQL / shell tools** — no such tool exists in the allowlist.
19. **No secrets in response** — `Idempotency-Key`, raw traceback, and credential strings never appear in response bodies.

### §30.3 Integration tests

20. **TASK-012 POST absent from default path** — default MVP path never calls TASK-012 POST.
21. **Deterministic recommendation evidence** — every recommendation rule has at least one evidence reference.
22. **Exact reload / equality** — when existing persisted runs are consumed, reloading them produces byte-identical outputs.
23. **SQLite unit tests** — all tool adapters have SQLite-backed unit tests.
24. **PostgreSQL integration tests** — orchestration tests use real PG via `docker-compose.test.yml`.
25. **Golden JSON output** — golden JSON fixtures pin the output envelope shape for the ordinary-user MVP.
26. **No network call in CI** — CI environment has no outbound network for the Agent code path.

### §30.4 Anti-fabrication tests

- A fuzz test that injects plausible-but-fake numbers into tool output is rejected.
- A fuzz test that injects plausible-but-fake `prediction_run_id` is rejected.
- A fuzz test that injects natural-language authority hints is rejected; the Agent returns the candidate list instead.

---

## §31 PostgreSQL / integration-test boundary

### §31.1 SQLite for unit tests

Each tool adapter MUST have SQLite-backed unit tests that exercise the adapter in isolation (without HTTP / network / external services).

### §31.2 PostgreSQL for integration tests

Orchestration tests (Slice B+) MUST use real PostgreSQL via the existing `docker-compose.test.yml`. The integration test suite MUST:
- not introduce new schema migrations;
- not depend on TASK-013 persistence tables (because none exist);
- rely on the existing TASK-008 through TASK-012 schema and Alembic migrations.

### §31.3 CI environment

- CI MUST NOT make outbound network calls from Agent code paths.
- CI MUST NOT require an LLM API key for Slice A–D tests.
- CI MUST NOT require an external knowledge source.

---

## §32 Implementation slices

See §29.3 for the proposed slice plan. This section adds the explicit sequencing rules:

### §32.1 Slice ordering rule

A later slice MUST NOT silently introduce functionality reserved for an earlier slice. Specifically:
- Slice B MUST NOT introduce HTTP API (reserved for Slice D).
- Slice C MUST NOT introduce LLM (reserved for Slice E).
- Slice D MUST NOT introduce persistence (reserved for TASK-014 or separate amendment).
- Slice E MUST NOT introduce frontend (separate task).

### §32.2 Per-slice gate

Each Slice MUST be authorized by Charles in its own round. No slice auto-starts.

### §32.3 Anti-scope-creep

If a slice's implementation discovers that it needs capability outside its frozen scope, the slice MUST stop and surface a new amendment request. It MUST NOT silently widen scope.

---

## §33 Acceptance criteria

This design PR is acceptable when:

- ✅ Exactly one repository file changed (this document).
- ✅ Source reconciliation (§2) is explicit.
- ✅ Issue-tracker misclassification for the TASK-011/TASK-012 boundary is explicitly corrected (§2.2); references use `PR #35` correctly.
- ✅ Minimal-input planning is the core MVP (§4 + §7).
- ✅ Option A read-only-only positioning is rejected (§1).
- ✅ 8 logical tools are mapped to current services (§12) — no same-name-function assumption.
- ✅ Two-stage request normalization (`MinimalInputRequest` + `NormalizedAgentRequest`) is frozen (§7.1–§7.3); `requested_as_of_date` / `requested_forecast_season` carry the caller preference; `effective_as_of_date` / `effective_forecast_season` are produced by a versioned season-calendar policy with `season_resolution_policy_version` + `season_calendar_config_hash` recorded in provenance.
- ✅ No hidden wall-clock defaults; no `as_of > today + N` rules.
- ✅ Typed authority envelopes (`Task8Authority` / `Task9Authority` / `Task10Authority` / `Task11Authority` / `Task12Authority`) are defined in §9.3 and cited to real main-contract paths; no generic `taskX_run_id` alias is frozen as an existing persisted field.
- ✅ `PeakMetricPolicy` (versioned, frozen formulas) governs all peak computations (§16); the historical equal-maxima blocker is removed (replaced by the stable tie-break in the policy).
- ✅ `UncertaintyWideningPolicy` (versioned, monotonically increasing factors) governs widening (§10.4); step 1 widens only when HIGH evidence requirements are not met; step 5 has maximum widening and always LOW confidence.
- ✅ Per-day `ForecastDailyRow` preserves TASK-009 P50/P80/P90 quantiles in `DailyQuantiles` shape (§15.3); `harvested_quantity_kg`, `closing_mature_inventory_kg`, `unharvested_backlog_kg`, `arrival_quantity_kg`, `final_corrected_arrival_quantity_kg` are NOT collapsed.
- ✅ Discriminated typed overrides (`AdvancedOverrides` + per-target types) carry `source_attestation` universally across parameter / scenario / execution / authority / `as_of_overrides` overrides (§8.1).
- ✅ Bare `as_of: date | null` scalar is **forbidden** inside `AdvancedOverrides`; the only typed as-of path is `as_of_overrides[].override_kind = AS_OF_OVERRIDE` (§8.1 / §8.2). At-most-one rule and `OVERRIDE_CONFLICT` blocker enforced.
- ✅ `Citation` is the canonical citation contract — single source of truth in §19.3; `source_tasks` (list) + `authorities` (list of typed envelopes) replaces generic `run_id` / `result_hash` / `manifest_hash` / `forecast_cutoff` / `as_of` top-level fields (§19 / §20 / §24.2).
- ✅ TASK-012 read path is gated by explicit `TASK12_PREDICTION_RUN` authority override only (§15.8 / §22.1 / §22.4). No automatic TASK-012 authority resolution exists in any frozen slice.
- ✅ Authority override registry covers all five `AUTHORITY_CONFLICT` candidate types: `TASK8_FORECAST_RUN`, `TASK9_HARVEST_STATE_RUN`, `TASK10_PREDICTION_RUN`, `TASK11_BACKTEST_RUN`, `TASK12_PREDICTION_RUN`. `TASK10_TRAINING_RUN` is a separate optional override that MUST NOT substitute for `TASK10_PREDICTION_RUN` (§8.1 / §9.3.3).
- ✅ `simulate_scenario_output` deltas are structured per quantile and typed as `decimal_string` (no Python `float`, no generic JSON number); `scenario_id` / `scenario_config_hash` are `sha256` (§17.3).
- ✅ `peak_duration_days[q]` uses frozen `PeakMetricPolicy.high_load_reference = SINGLE_DAY_PEAK` + `high_load_threshold_ratio`; `high_load_threshold[q] = ratio × single_day_peak[q].volume_kg` is output for auditability (§16.3 / §16.4 / §16.5.8).
- ✅ `RequestedAsOfDateProvenance` is a frozen schema surfaced both on `NormalizedAgentRequest.requested_as_of_date_provenance` (§7.2) and on `AgentForecastOutput.provenance.requested_as_of_date_provenance` (§24.1); preserves `caller_requested_as_of_date` + `effective_as_of_date` + `override_applied` + override attestation triple; participates in `canonical_request_hash` (§24).
- ✅ `Citation.tags` + `Citation.override_refs` are part of the canonical Citation schema (§19.3); `OVERRIDE_APPLIED` is the single tag value; `override_refs` enumerates every override that materially affected the cited value (§8.3 / §19.3 / §20.3 / §24.2).
- ✅ `AsOfOverride` authority-effect semantics are corrected: cannot directly nominate / substitute / pin an authority; effect is mediated exclusively through the resulting `effective_as_of_date`; no authority-pointer fields allowed in the envelope (§8.2 / §8.3); design-only test matrix frozen in §8.2.1.
- ✅ Aggregate confidence = worst confidence among all required parameters (§25.1); the "overdetermined upgrade" rule is removed.
- ✅ All authoritative values are provenance-linked (§24).
- ✅ Recommendations are deterministic with 7 categories total = 6 operational + 1 data-quality (MISSING_DATA_IMPACT) (§20).
- ✅ `UNKNOWN_VARIETY` is a per-variety blocked outcome; known varieties continue; overall request status becomes `PARTIAL` (§26.1.1).
- ✅ `LOCATION_AMBIGUOUS` (correct spelling) is the blocker; the old mis-spelled code (with a stray space) is removed.
- ✅ `VARIETY_PRIOR_NOT_VISIBLE_AT_AS_OF` is the correct stale-prior semantics (§26.1).
- ✅ TASK-012 endpoint path is `POST /api/v1/rolling-backtest/replay-trained-predictions` / `GET /api/v1/rolling-backtest/replay-trained-predictions/{prediction_run_id}`; the old wrong path is removed (§22).
- ✅ TASK-012 POST is **outside** every currently frozen slice; confirmation-token support is NOT included (§22.4).
- ✅ No migration (§28).
- ✅ No Agent persistence tables (§28).
- ✅ No frontend (§29).
- ✅ No LLM dependency required (§23 + §29).
- ✅ Implementation slices are frozen (§29.3 + §32).
- ✅ Implementation is NOT authorized.
- ✅ Ready / Merge are NOT authorized.

---

## §34 Non-actions and anti-fabrication guard

### §34.1 What this PR does NOT do

- Does NOT create `agent_run` / `agent_query_audit` / `agent_conversation` / `agent_confirmation_log` tables.
- Does NOT add an Alembic migration.
- Does NOT add an HTTP API endpoint for TASK-013.
- Does NOT add a CLI command for TASK-013.
- Does NOT add frontend code.
- Does NOT add `openai` / `anthropic` / any LLM dependency.
- Does NOT call TASK-012 POST in the design's described default path.
- Does NOT call TASK-011 backtest in the design's described default path.
- Does NOT silently pick `latest` / `current` / `most recent` / `best available` / `default model` as authority selectors.
- Does NOT substitute one run's result for another (cross-run substitution).
- Does NOT modify any existing TASK-008–012 file.
- Does NOT modify any test file.
- Does NOT modify any CI / workflow / docker / pyproject / lockfile file.
- Does NOT mark the PR Ready.
- Does NOT merge.
- Does NOT publish to Feishu.

### §34.2 Anti-fabrication guard (frozen rules)

1. **Every authoritative numerical value carries a citation block (§24.2).** If the citation block is missing, the value MUST NOT appear in the output.
2. **Every recommendation carries evidence + rule_id (§20.7).** If evidence is missing, the recommendation MUST be suppressed.
3. **LLM (when introduced in Slice E) MUST NOT generate numbers, hashes, dates, capacities, staffing counts (§23.1).**
4. **No "implicit latest" selector (§9.2).** If a selector is genuinely needed, it MUST be replaced by `versioned deterministic selector` + `explicit as_of cutoff` + `stable tie-break order` + `resolved identity in output`.
5. **TASK-012 result is never the source of "latest historical observation" (§22.2).**
6. **Replayed or trained results are clearly distinguished from real historical observations in the output** via the `task12_authority` provenance block.
7. **Natural maturity proxy is never described as physiological maturity observation** — the original AGENTS.md / `docs/13` rule is preserved verbatim.
8. **Spring-Festival window is never silently dropped** — the original AGENTS.md rule 6 is preserved.

### §34.3 Audit trail

The Agent's response MUST allow a downstream reader to answer, for any number in the output:
- Which deterministic service produced it?
- Which persisted artifact / run identity was consumed?
- What is the result_hash / manifest_hash?
- What was the forecast cutoff?
- What prior version was used?
- What is the confidence level and what evidence supports it?

If any of these questions cannot be answered from the response, the Agent has violated §34.2.

---

## Tracking Issue (this design round)

The tracking Issue is created in this round and is referenced here for traceability. The Issue body contains:
- authoritative source (§3);
- roadmap numbering drift (§2);
- design-only boundary (§34);
- no implementation / frontend / migration / dependency;
- no Ready / merge;
- proposed document path = `docs/task-013-minimal-input-deterministic-agent-orchestration-design.md`;
- acceptance checklist mapped to §33.

The Issue remains OPEN at the end of this round.

---

## Change log

| Date | Author | Change |
|---|---|---|
| 2026-07-11 | codex (TASK-013 design round) | Initial draft of design contract — 34 sections, frozen per §33 acceptance criteria. |