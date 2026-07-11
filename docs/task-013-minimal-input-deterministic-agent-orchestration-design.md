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

- ❌ **The claim that `Issue #35` is the TASK-012 tracking issue** — **WRONG**.
  - ✅ `Issue #35` title = `[TASK-011][Phase 4a] Design amendment: evaluation materialization and mask foundation`. `Issue #35` belongs to **TASK-011 Phase 4a**, not TASK-012.
  - ✅ TASK-012 had no standalone tracking Issue. Its work was driven by PRs #82–#90 plus Issue #35's downstream evaluation-mask amendment.
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
7. **Deterministic recommendation** — apply deterministic rules + scenario outputs to produce the recommendation payload (6 categories per `docs/10` §5.5).

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
- deterministic recommendations (6 categories).

---

## §5 Scope and explicit exclusions

### §5.1 In scope (this design)

- Logical orchestration of the 8 logical tools listed in `CODEX_TASKS.md` 任务 13.
- Versioned deterministic authority resolution for location, parameters, model selection, replay-trained result.
- Structured explanation payload (machine-readable) that the future LLM adapter (Slice E) may rephrase without changing authoritative values.
- Deterministic recommendation rules (6 categories per `docs/10` §5.5).
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
- `prediction_run_id` / `model_run_id` / `scenario_id` / `forecast_cutoff_at` / `task8_run_id` / `task9_run_id` / `task10_run_id` / `task11_run_id`
- explicit algorithm selection
- explicit model version selection
- explicit replay-trained selection
- explicit backtest selection

These may be supplied as **advanced overrides**(§8) only.

---

## §6 Domain terminology

| Term | Definition |
|---|---|
| **Ordinary user** | A user who supplies only location + per-variety planting area |
| **Advanced user** | A user who supplies additional overrides |
| **Resolved location** | The output of `resolve_location`: standard address, coordinates, agro-climate zone, similar-farm set, all versioned |
| **Parameter prior** | A versioned probability distribution for an inferred parameter (per-mu yield, commodity-fruit rate, etc.) |
| **Authority** | A resolvable identity (e.g. `task8_run_id`, `scenario_id`, `prediction_run_id`) that names a specific persisted artifact |
| **Authority resolution** | The deterministic process of selecting authorities given a versioned prior, an explicit `as_of`, and a stable tie-break order |
| **Identity** | A typed identifier (string/UUID) that uniquely names a persisted artifact and is stable across reload |
| **Hash** | A deterministic fingerprint of an artifact's canonical JSON content; used to detect tampering / substitution |
| **Manifest** | A versioned catalog of (artifact identity, content hash, lineage) for a run |
| **Provenance** | The chain of evidence that ties a numerical output to its source task, run identity, manifest hash, and forecast cutoff |
| **Confidence ladder** | 高 / 中 / 低 + required evidence (sample count, historical MAPE, date MAE, P90 coverage, key missing items) per `docs/10` §7 |
| **Blocker** | A structured error code that names the reason the Agent cannot proceed (input invalid, authority not found, etc.) |
| **Confirmation token** | An explicit human-issued token that authorizes a write-class action (NOT introduced in this design round; reserved for future advanced-execution amendment) |
| **Citation block** | A JSON sub-payload attached to every authoritative numerical value, listing source task / run id / hash / cutoff / parameter source / confidence evidence |

---

## §7 Minimal-input request contract

### §7.1 Request schema (Pydantic / JSON Schema, both acceptable)

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
  as_of: date | null              # forecast cutoff; defaults to "today" in UTC
  forecast_season: integer | null # e.g. 2026; defaults to current planning season
  advanced_overrides: AdvancedOverrides | null  # see §8
  presentation_locale: string | null  # e.g. "zh-CN"; default "zh-CN"
```

### §7.2 Validation rules

- `location` must have **at least one** of `raw_text`, `coordinates`, `map_pick_token`. Else → `INPUT_INVALID_LOCATION`.
- `varieties` must be a non-empty list. Else → `INPUT_INVALID_VARIETIES`.
- Each `planting_area_mu > 0`. Else → `INPUT_INVALID_PLANTING_AREA`.
- `variety_id` must be a known catalog variety. Unknown variety → `UNKNOWN_VARIETY` (still proceeds with explicit `LOW_CONFIDENCE` for that variety, never silently drops).
- `as_of` if supplied must be a valid date in UTC; if `as_of > today + 1 day` → `INPUT_INVALID_AS_OF`.
- `forecast_season` if supplied must be a known season; else → `INPUT_INVALID_SEASON`.

### §7.3 What MUST NOT be in the minimal input

- explicit run IDs (`task8_run_id` etc.)
- explicit algorithm / model / replay selection
- explicit backtest request
- arbitrary free-form prompt that the LLM (when introduced) would interpret to fill authority

If any of these appear in the input, they MUST be moved into `advanced_overrides` (§8) and re-validated under stricter rules.

---

## §8 Advanced override contract

### §8.1 Override schema

```yaml
AdvancedOverrides:
  parameter_overrides:
    - variety_id: string
      parameter: enum [
        "expected_per_mu_yield",
        "commodity_fruit_rate",
        "first_harvest_date",
        "maturity_curve",
        "spring_festival_harvest_rate",
        "weather_adjustment",
      ]
      value: number | distribution_ref | null
      source_attestation: string  # free-text justification; NOT machine-validated in this slice
  scenario_overrides:
    staffing_override: number | null
    spring_festival_intensity: enum [NONE, LOW, MEDIUM, HIGH] | null
    processor_capacity_t_per_day: number | null
  execution_overrides:
    request_backtest: bool | null  # MUST default to false; backtest is advanced execution
    request_replay_trained_run: bool | null  # MUST default to false; creation is advanced execution
    request_simulation_id: string | null  # re-run an existing simulation
  authority_overrides:
    task8_run_id: string | null
    task9_run_id: string | null
    task10_run_id: string | null
    task11_run_id: string | null
    task12_prediction_run_id: string | null
  as_of: date | null  # overrides §7.1 as_of
```

### §8.2 Override authority rules

- Every override **MUST** carry `source_attestation` (free text, but required).
- Every override **MUST** be reflected in the output's citation block with `OVERRIDE_APPLIED` tag.
- Algorithm / model / replay selection overrides are **not** accepted as `algorithm_override`. They MUST go through `authority_overrides.*_run_id`, and if no matching persisted run exists → `AUTHORITY_NOT_FOUND` blocker.
- `request_backtest = true` and `request_replay_trained_run = true` are **advanced execution** flags. In the first implementation Slice they MUST be rejected with `EXECUTION_DEFERRED` blocker; a future amendment may unlock them with explicit confirmation token.

### §8.3 Override MUST NOT

- inject raw SQL / shell / Python
- inject arbitrary URLs
- inject credentials
- request any side-effect outside the allowlist (§11)
- request access to `.hermes` / shell history / secrets

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
| `default model` | must be replaced by `explicit task8 / task10 / task12 run_id` |
| `silent fallback` | must be replaced by `versioned prior + confidence widening + missing-items report` |
| `unrecorded authority substitution` | must be replaced by `recorded authority identity in output citation` |
| `cross-run substitution` | forbidden unconditionally — see §22 |

### §9.3 Output must disclose resolved identities

Even for the minimal-input MVP, the Agent MUST disclose, in the output citation block, the actual resolved authorities it consumed:

| Field | Source |
|---|---|
| `task8_authority` | resolved natural-maturity run id + manifest hash |
| `task9_authority` | resolved harvest-state run id + result hash |
| `task10_authority` | resolved residual-model run id + manifest hash |
| `task11_authority` | resolved backtest run id + manifest hash (if any was consumed) |
| `task12_authority` | resolved replay-trained `prediction_run_id` + result hash (if any was consumed) |
| `manifest_hashes` | full list of manifests consulted |
| `result_hashes` | full list of results consumed |
| `parameter_version_identities` | versioned prior identities used per parameter |
| `location_catalog_version` | version of the location-mapping catalog consumed |

These MUST be machine-readable in the output's `provenance` block.

### §9.4 Authority conflict

If two persisted artifacts both satisfy the selector (e.g. same `task10_run_id` and same `forecast_cutoff` but different `result_hash`):
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

### §10.3 Confidence widening

If the matching-priority step is ≤ step 4, P80/P90 intervals MUST be widened by a documented factor (per parameter), and the confidence MUST be downgraded. The widening factor table is part of the implementation; this design freezes the principle.

### §10.4 Required evidence per confidence level

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
| 4 | `forecast_peak` | Peak metrics derived deterministically from the daily curve | `EXISTING_COMPOSITE` |
| 5 | `simulate_scenario` | Re-run with a modified scenario (staffing, Spring-Festival intensity, etc.) | `NEW_DETERMINISTIC_ADAPTER` (no full existing service) |
| 6 | `run_backtest` | TASK-011 backtest execution | `DEFERRED_ADVANCED_TOOL` |
| 7 | `explain_forecast` | Structured explanation payload | `NEW_DETERMINISTIC_RULE_TOOL` |
| 8 | `generate_recommendations` | Deterministic 6-category recommendations | `NEW_DETERMINISTIC_RULE_TOOL` |

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
| `generate_recommendations` | Deterministic 6-category recommendations | consumes output of tools 3–5; applies documented rules | none | deterministic rule engine | `NEW_DETERMINISTIC_RULE_TOOL` | ✅ |

The classification deliberately rejects the implicit assumption "if no Python function named X exists, then tool X is not implemented". The logical tool is a **contract**; the implementation is whatever deterministic service / adapter / rule that satisfies the contract.

---

## §13 `resolve_location` contract

### §13.1 Purpose

Convert the user's raw location input into a `ResolvedLocation` carrying standard coordinates, agro-climate zone, similar-farm set, and a location-catalog version identity.

### §13.2 Input

```yaml
resolve_location_input:
  raw_text: string | null
  coordinates: {lat: number, lon: number} | null
  map_pick_token: string | null
  as_of: date | null  # visibility cutoff for the location catalog
```

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
- `LOCATION_CATALOG_STALE` — `as_of` is before the catalog's effective date.
- `LOCATION_AM BIGUOUS` — multiple zone candidates with same score → return top-N candidates; do NOT auto-pick.

### §13.6 Read/Write / Idempotency

- Read-only. Idempotent on `(raw_text, coordinates, as_of, catalog_version)`.

### §13.7 Citation identity

- `location_catalog_version`, `agro_climate_zone.zone_id`, `agro_climate_zone.zone_version`.

---

## §14 `infer_parameters` contract

### §14.1 Purpose

For each `(location × variety)` pair, infer the 9 parameter categories from `docs/10` §3, with versioned priors, confidence ladder, and per-parameter source attestation.

### §14.2 Input

```yaml
infer_parameters_input:
  resolved_location: ResolvedLocation  # output of resolve_location
  varieties: [{variety_id, planting_area_mu}]
  as_of: date
  advanced_overrides: AdvancedOverrides | null
```

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
- `VARIETY_PRIOR_STALE` — the prior's effective date is before `as_of`.

### §14.6 Read/Write / Idempotency

- Read-only. Idempotent on `(resolved_location_id, varieties, as_of, prior_version)`.

### §14.7 Citation identity

- `prior_version`, `catalog_version`, `sample_count`, `covered_seasons`, `historical_mape`.

---

## §15 `forecast_daily_curve` contract

### §15.1 Purpose

Produce per-day (from season start to April 30) values for natural maturity, harvest implementation, backlog, weather / Spring-Festival tags, and final per-day commodity-fruit arrival volume.

### §15.2 Input

```yaml
forecast_daily_curve_input:
  parameters: [...]  # output of infer_parameters
  resolved_location: ResolvedLocation
  as_of: date
  forecast_season: integer
  scenario: ScenarioConfig  # default planning scenario
  advanced_overrides: AdvancedOverrides | null
```

### §15.3 Output

```yaml
forecast_daily_curve_output:
  per_day:
    - date: date
      natural_maturity_volume_p50: number
      natural_maturity_volume_p80: number
      natural_maturity_volume_p90: number
      harvest_implementation_volume: number
      estimated_backlog_volume: number
      final_arrival_volume_p50: number
      final_arrival_volume_p80: number
      final_arrival_volume_p90: number
      weather_tags: [string]
      spring_festival_phase: enum [PRE, DURING, POST, NONE]
      per_variety_contribution:
        - variety_id: string
          volume_p50: number
          volume_p80: number
          volume_p90: number
  authorities_consumed:
    task8_authority: {run_id, manifest_hash, result_hash}
    task9_authority: {run_id, manifest_hash, result_hash}
    task10_authority: {run_id, manifest_hash, result_hash}
    task12_authority: {run_id, manifest_hash, result_hash} | null
```

### §15.4 Authority contract

- Composes TASK-008 natural maturity + TASK-009 harvest state + TASK-010 residual adjustment.
- Composition MUST be deterministic: given the same inputs + same authorities + same `as_of`, the output MUST be byte-identical.

### §15.5 Blockers

- `TASK8_AUTHORITY_NOT_FOUND` — no task8 run matches `(location, varieties, as_of)`.
- `TASK9_AUTHORITY_NOT_FOUND` — analogous.
- `TASK10_AUTHORITY_NOT_FOUND` — analogous.
- `TASK12_AUTHORITY_NOT_FOUND` — only when an explicit `task12_prediction_run_id` is supplied and not found.
- `FORECAST_CUTOFF_IN_FUTURE` — `as_of > today + grace_days`.

### §15.6 Read/Write / Idempotency

- Read-only (composes existing reads). Idempotent on `(input, as_of, authorities)`.

### §15.7 Citation identity

- All consumed `*_authority` identities + hashes + `forecast_cutoff`.

### §15.8 MVP scope

For MVP, this tool consumes existing TASK-008/009/010 services; TASK-012 is consulted only when an explicit `task12_prediction_run_id` is supplied (advanced override). Default path does NOT call TASK-012.

---

## §16 `forecast_peak` contract

### §16.1 Purpose

Derive peak metrics deterministically from `forecast_daily_curve_output`.

### §16.2 Input

`forecast_daily_curve_output.per_day`.

### §16.3 Output

```yaml
forecast_peak_output:
  single_day_peak:
    p50: {date, volume}
    p80: {date, volume}
    p90: {date, volume}
  sustained_3day_peak:
    p50: {start_date, end_date, volume}
    p80: {start_date, end_date, volume}
    p90: {start_date, end_date, volume}
  peak_duration_days: integer
  peak_window_cumulative_volume: number  # ±7-day cumulative
  dominant_variety: {variety_id, contribution_rate}
  peak_formation_explanation_ref: string  # pointer into explain_forecast output
```

### §16.4 Authority contract

- Pure deterministic derivation. **LLM MUST NOT compute peak values.**
- Authoritative numbers in the output carry the same citation identity as the underlying `forecast_daily_curve_output`.

### §16.5 Blockers

- `EMPTY_CURVE` — `per_day` is empty (season start > April 30 or all days had zero data).
- `PEAK_TIE_BREAK_FAILED` — multiple equal-volume peak candidates and tie-break order produced no unique answer → return top-N with stable ordering, do not auto-pick.

### §16.6 Read/Write / Idempotency

- Read-only. Idempotent on input.

### §16.7 Citation identity

- Inherits from `forecast_daily_curve_output`.

---

## §17 `simulate_scenario` contract

### §17.1 Purpose

Re-run `forecast_daily_curve` and `forecast_peak` with a modified scenario (staffing, Spring-Festival intensity, processor capacity). Default scenario is the planning scenario.

### §17.2 Input

```yaml
simulate_scenario_input:
  base_request: MinimalInputRequest
  scenario_overrides:
    staffing_override: number | null
    spring_festival_intensity: enum [NONE, LOW, MEDIUM, HIGH] | null
    processor_capacity_t_per_day: number | null
  as_of: date | null
```

### §17.3 Output

```yaml
simulate_scenario_output:
  scenario_id: string  # deterministic hash of the scenario config
  forecast_daily_curve: forecast_daily_curve_output
  forecast_peak: forecast_peak_output
  delta_vs_baseline:
    peak_volume_delta_p50: number
    peak_volume_delta_p80: number
    peak_volume_delta_p90: number
    sustained_3day_delta: number
  scenario_config_hash: string
```

### §17.4 Authority contract

- Wraps `forecast_daily_curve` + `forecast_peak` with a deterministic scenario config.
- The `scenario_id` MUST be a content hash of the scenario config (canonical JSON).
- `simulation_id` from existing TASK-009 simulation service MAY be reused; if absent, the new adapter supplies its own hash.

### §17.5 Blockers

- `SCENARIO_INVALID` — staffing < 0, capacity < 0, etc.
- `SCENARIO_INCOMPATIBLE_WITH_BASE` — scenario requires a parameter that the base request did not provide.

### §17.6 Read/Write / Idempotency

- Read-only. Idempotent on `(base_request, scenario_overrides, as_of)`.

### §17.7 Citation identity

- `scenario_config_hash` + inherited from underlying daily curve / peak.

### §17.8 MVP scope

Allowed in MVP. The adapter is new, but it wraps existing services; no new numerical algorithm is created in this design.

---

## §18 `run_backtest` advanced / deferred boundary

### §18.1 Why deferred

`run_backtest` maps to TASK-011's `backend/app/rolling_backtest/` (service.py + orchestration.py + cli.py). Calling it inside the Agent's default MVP path would:
- be expensive (historical visibility + evaluation materialization);
- require explicit `task11_run_id` + scenario config;
- require the Agent to interpret backtest metrics into natural language (a Step where an LLM could be tempted to fabricate summary text).

Therefore `run_backtest` is classified as **`DEFERRED_ADVANCED_TOOL`**:
- NOT in the default minimal-input MVP path.
- Allowed only via `advanced_overrides.execution_overrides.request_backtest = true`.
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
          citation:
            source_task: string  # e.g. "TASK-008"
            run_id: string | null
            result_hash: string | null
            manifest_hash: string | null
            forecast_cutoff: date | null
            field_path: string  # e.g. "forecast_daily_curve_output.per_day[7].final_arrival_volume_p50"
```

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

### §20.1 Purpose

Produce deterministic recommendations for the 6 categories listed in `docs/10` §5.5:

1. Recommended sustained processing capacity (推荐持续处理能力)
2. Recommended receiving / temporary-storage / pre-cooling peak capacity (推荐收货/暂存/预冷瞬时能力)
3. Peak-period shift recommendation (高峰期班次建议)
4. Spring-Festival staffing preparation (春节人员准备)
5. Variety stagger / pruning batch recommendation (品种错峰或修剪批次建议)
6. Cross-plant dispatch necessity (是否需要跨厂分流)
7. (extra) Which additional data would most improve accuracy (哪些额外数据最能提升准确性)

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
    - category: enum [SUSTAINED_PROCESSING_CAPACITY, RECEIVING_PEAK_CAPACITY, SHIFT_STAFFING, SPRING_FESTIVAL_STAFFING, VARIETY_STAGGER, CROSS_PLANT_DISPATCH, MISSING_DATA_IMPACT]
      text: string  # deterministic template output
      rule_id: string  # identifies the exact rule used
      evidence:
        - citation:
            source_task: string
            run_id: string | null
            field_path: string
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

| Task | What TASK-013 consumes | Authority identity used | Notes |
|---|---|---|---|
| TASK-008 natural maturity curve | `backend/app/maturity/service.py` outputs (per-day natural maturity distribution) | `task8_run_id`, `maturity_manifest_hash`, `maturity_result_hash` | Carried into `forecast_daily_curve_output.per_day.natural_maturity_volume_*` |
| TASK-009 / TASK-009A harvest state | `backend/app/harvest_state/service.py` outputs (backlog, release, arrival, harvest-implementation rate) | `task9_run_id`, `harvest_state_manifest_hash` | Carried into `forecast_daily_curve_output.per_day.harvest_implementation_volume` + `estimated_backlog_volume` |
| TASK-010 residual model | `backend/app/residual_model/` + `backend/app/baseline/` outputs (residual adjustment, fallback semantics) | `task10_run_id`, `residual_model_manifest_hash`, `residual_model_result_hash` | Carried into `forecast_daily_curve_output.per_day.final_arrival_volume_*` (combined with TASK-008 + TASK-009) |
| TASK-011 rolling backtest | `backend/app/rolling_backtest/` outputs (when explicitly requested via advanced override) | `task11_run_id`, `backtest_manifest_hash` | NOT in MVP path; deferred per §18 |
| TASK-012 replay-trained model | `backend/app/rolling_backtest/replay_trained_*.py` outputs (only when explicit `task12_prediction_run_id` override) | `task12_prediction_run_id`, `prediction_result_hash`, `prediction_manifest_hash` | NOT in MVP path; see §22 |

### §21.1 Composition order (deterministic)

The composition order in `forecast_daily_curve` MUST be:
1. TASK-008 produces natural maturity per-day.
2. TASK-009 produces harvest-implementation / backlog per-day from TASK-008.
3. TASK-010 produces residual adjustment per-day and combines with TASK-008 + TASK-009.
4. TASK-012 (only if explicitly requested) provides a replay-trained overlay; the overlay MUST NOT replace steps 1–3; it MAY add a residual signal that is itself cited.

### §21.2 Anti-leakage rule

The composition MUST NOT:
- apply TASK-012 residual as a hidden override of TASK-008 natural maturity;
- substitute TASK-011 backtest metric as a TASK-008 maturity value;
- rewrite TASK-009 backlog based on TASK-010 residual.

---

## §22 TASK-012 replay-trained model boundary

### §22.1 Read path (always allowed, identity-bearing)

TASK-013 MAY read TASK-012's persisted artifacts (`prediction_run_id` + `result_hash` + `manifest_hash`) when:
- an explicit `task12_prediction_run_id` is supplied in `advanced_overrides.authority_overrides`; OR
- the deterministic authority resolver (§9) returns a TASK-012 authority for the requested `as_of` (this is an advanced path, not MVP).

In both cases the Agent MUST carry the `prediction_run_id` + `result_hash` + `manifest_hash` into the output's citation block.

### §22.2 Forbidden actions

The Agent MUST NOT:
- forge a `prediction_run_id`, `result_hash`, or `manifest_hash` for TASK-012;
- substitute one TASK-012 run's result for another (cross-run substitution);
- call TASK-012 POST (`POST /rolling_backtest/replay-trained`) in the default MVP path;
- treat a TASK-012 result as "latest historical observation";
- replace TASK-008 / TASK-010 outputs with a TASK-012 overlay without explicit caller opt-in.

### §22.3 Write path (always deferred)

Creating a new replay-trained run is **advanced execution**. It:
- MUST NOT be triggered by the default MVP path;
- MUST require an explicit `advanced_overrides.execution_overrides.request_replay_trained_run = true`;
- MUST be guarded by a future confirmation-token mechanism (out of scope here);
- MUST be authorized by a separate TASK-013 amendment.

### §22.4 Slice gating

| Slice | TASK-012 role |
|---|---|
| A (logical tool schemas + adapters) | Read path only; no POST |
| B (minimal-input orchestration) | Read path only via advanced override |
| C (explanation + recommendations) | Read path only |
| D (HTTP API + optional CLI) | Read path exposed; write path exposed under confirmation gate (separate amendment) |
| E (LLM adapter) | Read path only |

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
  resolved_location: ResolvedLocation
  parameters: [ParameterEstimate]  # from infer_parameters
  daily_curve: forecast_daily_curve_output
  peak: forecast_peak_output
  recommendations: generate_recommendations_output
  explanation: explain_forecast_output
  confidence: {level, evidence}
  provenance:
    task8_authority: {run_id, manifest_hash, result_hash, forecast_cutoff}
    task9_authority: {run_id, manifest_hash, result_hash, forecast_cutoff}
    task10_authority: {run_id, manifest_hash, result_hash, forecast_cutoff}
    task11_authority: {run_id | null, manifest_hash | null}
    task12_authority: {prediction_run_id | null, result_hash | null, manifest_hash | null}
    manifest_hashes: [string]
    result_hashes: [string]
    parameter_version_identities: [string]
    location_catalog_version: string
    prior_versions_used: [string]
    scenario_config_hash: string | null
    as_of: date
  blockers: [Blocker]
  warnings: [string]
```

### §24.2 Citation discipline

Every authoritative numerical value in the output MUST carry:
- `field_name`
- `value`
- `unit`
- `source_task` / `source_tool`
- resolved `authority` / `run_id` identity
- `result_hash` / `manifest_hash` when applicable
- `forecast_cutoff` / `as_of`
- `parameter_source`
- `confidence_evidence` (sample count, covered seasons, historical MAPE, P90 coverage, key missing)

Natural-language sections MUST be classified as one of the four kinds in §19.1.

### §24.3 What the Agent MAY rephrase

Only paragraphs tagged `DETERMINISTIC_EXPLANATION` and `NON_AUTHORITATIVE_PRESENTATION`. The rephrase MUST NOT:
- change a number, hash, date, or volume;
- introduce a new recommendation category;
- drop a citation block.

---

## §25 Confidence and uncertainty contract

### §25.1 Per-parameter confidence

Each parameter estimate carries its own confidence level + evidence (`docs/10` §7). Aggregate confidence is the worst confidence of all parameters, **unless** the parameter set is overdetermined (e.g. one `LOW_CONFIDENCE` parameter is dominated by a `HIGH_CONFIDENCE` parameter) — in which case a documented rule may upgrade the aggregate. The rule table is part of the implementation.

### §25.2 Required evidence disclosure

For each confidence level, the output MUST disclose:
- sample count (number of historical observations used)
- covered seasons (e.g. 2024, 2025)
- historical MAPE
- historical date MAE
- P90 coverage rate
- key missing items (e.g. "no same-farm history", "no same-variety in same climate zone")

### §25.3 Uncertainty widening

When the inference priority (§10.1) is at step ≤ 4, P80/P90 intervals MUST be widened by a documented factor per parameter. The widening factor table is part of the implementation; this design freezes the principle.

### §25.4 Forbidden short-cut

The Agent MUST NOT:
- emit a single high-level confidence label without the required evidence fields;
- silently absorb a low-confidence parameter into a high-confidence aggregate;
- substitute "average historical yield" for an explicit prior version.

---

## §26 Error and blocker contract

### §26.1 Blocker taxonomy (canonical codes)

| Code | Meaning |
|---|---|
| `INPUT_INVALID_LOCATION` | `location` field missing all three of raw_text / coordinates / map_pick_token |
| `INPUT_INVALID_VARIETIES` | empty varieties list |
| `INPUT_INVALID_PLANTING_AREA` | planting_area_mu ≤ 0 |
| `INPUT_INVALID_AS_OF` | `as_of` malformed or in distant future |
| `INPUT_INVALID_SEASON` | `forecast_season` not in known seasons |
| `UNKNOWN_VARIETY` | variety_id not in catalog → still proceeds with `LOW_CONFIDENCE` for that variety |
| `LOCATION_UNRESOLVED` | location could not be resolved to any zone |
| `LOCATION_AM BIGUOUS` | multiple zone candidates with same score → return top-N |
| `LOCATION_CATALOG_STALE` | as_of is before catalog effective date |
| `INSUFFICIENT_HISTORY` | no historical data at any priority step |
| `PARAMETER_OVERRIDE_INVALID` | advanced override references unknown parameter |
| `VARIETY_PRIOR_STALE` | prior effective date before as_of |
| `TASK8_AUTHORITY_NOT_FOUND` | no task8 run matches selector |
| `TASK9_AUTHORITY_NOT_FOUND` | analogous |
| `TASK10_AUTHORITY_NOT_FOUND` | analogous |
| `TASK11_AUTHORITY_NOT_FOUND` | only when advanced override requests backtest |
| `TASK12_AUTHORITY_NOT_FOUND` | only when advanced override supplies prediction_run_id |
| `AUTHORITY_CONFLICT` | two persisted artifacts both satisfy the selector → do NOT auto-pick |
| `EXECUTION_DEFERRED` | caller requested backtest or replay-trained run creation (not allowed in this slice) |
| `CITATION_MISSING_FIELD_PATH` | AUTHORITATIVE_VALUE paragraph missing field_path |
| `CITATION_HASH_MISMATCH` | cited hash does not match the artifact actually consumed |
| `SCENARIO_INVALID` | scenario_overrides invalid (negative staffing, negative capacity, etc.) |
| `SCENARIO_INCOMPATIBLE_WITH_BASE` | scenario requires absent parameter |
| `RULE_NOT_APPLICABLE` | no recommendation rule matched |
| `RULE_THRESHOLD_MISSING` | required threshold parameter absent |
| `INTERNAL_FAILURE` | internal exception (must include a stable error code, never a raw traceback) |

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

- Existing business run identities (`*_run_id`, `prediction_run_id`, etc.).
- Existing model / result / manifest hashes.
- Request-scoped structured provenance in the response body.
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
4. **Deterministic repeatability** — same inputs + same `as_of` + same authorities → byte-identical output.
5. **Stable tool ordering** — tool-call order is deterministic for the same request.
6. **No implicit latest** — for any authority selection, the resolved identity is recorded and disclosed.
7. **Source and model identity disclosure** — output's `provenance` block lists every consumed authority.
8. **No LLM numerical generation** — no number / hash / date / capacity appears in `NON_AUTHORITATIVE_PRESENTATION` paragraphs.
9. **No fabricated recommendation** — every recommendation has at least one evidence block.
10. **Missing location** — `INPUT_INVALID_LOCATION` blocker.
11. **Unknown variety** — `UNKNOWN_VARIETY` blocker + `LOW_CONFIDENCE` for that variety.
12. **Insufficient historical samples** — `INSUFFICIENT_HISTORY` blocker + widened intervals.
13. **Authority conflict** — `AUTHORITY_CONFLICT` blocker + top-N candidates disclosed.
14. **Result-hash preservation** — output's `result_hash` matches the actual artifact consumed (no tampering).
15. **Cross-run substitution rejection** — supplying one `task12_prediction_run_id` and consuming a different one is detected.

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
- ✅ Issue-tracker misclassification for the TASK-011/TASK-012 boundary is explicitly corrected (§2.2).
- ✅ Minimal-input planning is the core MVP (§4 + §7).
- ✅ Option A read-only-only positioning is rejected (§1).
- ✅ 8 logical tools are mapped to current services (§12) — no same-name-function assumption.
- ✅ Deterministic authority resolution is frozen (§9).
- ✅ No implicit `latest` / `current` (§9.2 + §18 + §22).
- ✅ Versioned prior fallback is frozen (§10).
- ✅ All authoritative values are provenance-linked (§24).
- ✅ Recommendations are deterministic (§20).
- ✅ TASK-012 POST is excluded from default MVP path (§22).
- ✅ No migration (§28).
- ✅ No Agent persistence tables (§28).
- ✅ No frontend (§29).
- ✅ No LLM dependency required (§23 + §29).
- ✅ Implementation slices are frozen (§29.3 + §32).
- ✅ Implementation is NOT authorized (this PR is design-only).
- ✅ Ready / Merge are NOT authorized (this PR is Draft).

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