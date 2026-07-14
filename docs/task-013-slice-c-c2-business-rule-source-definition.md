# TASK-013 Slice C Phase C2 — Business Rule Source Definition and Design Freeze

| Field | Value |
|---|---|
| Document ID | `task-013-slice-c-c2-business-rule-source-definition` |
| Document version | v1 |
| Document status | `DRAFT — awaiting Charles confirmation` |
| Tracking Issue | `#99` (OPEN) |
| Source Issue body SHA-256 | `b157ffa0fcbe3c270c9501bd348d41406a08ab781f1d9e9259237de09b139669` |
| C1 baseline merge commit | `2e860511dd9279d0aa3c64dd760bea8531fad458` |
| C1 baseline branch | `codex/task-013-slice-c-c1-deterministic-foundation` (PR #100) |
| Working base for C2 design | `origin/main` at `2e860511dd9279d0aa3c64dd760bea8531fad458` |
| C2 implementation | NOT AUTHORIZED in this document |
| C2 branch | NOT AUTHORIZED in this document |
| Ready | NOT AUTHORIZED in this document |
| Merge | NOT AUTHORIZED in this document |
| TASK-014+ | NOT AUTHORIZED in this document |

---

## §1 Scope and non-scope

### §1.1 In scope

This document freezes the **business-rule source definition** for TASK-013 Slice C Phase C2. It explicitly defines, for each of the six C2 operational categories, the source authority, required upstream fields, RFC 6901 JSON Pointer, source identity, formula skeleton, threshold contract, decision table, and Charles confirmation items. C2 activation (i.e. transitioning a category from `BUSINESS_SOURCE_REQUIRED` to a real `APPLICABLE` or `NOT_APPLICABLE` decision) is **not** authorized in this document. C2 activation requires a future implementation round with separate Charles authorization.

This document is the **only** design artifact that may be merged to satisfy the C2 design-freeze gate. It does not embed production code, fixtures, golden payloads, or test scaffolding.

### §1.2 Out of scope (explicit exclusions)

C2 source-definition does not authorize and does not produce:

1. Any modification of `backend/app/**` production code.
2. Any modification of `backend/tests/agent/**` or `backend/tests/integration/agent/**` to embed operational formulas.
3. Any modification of `backend/app/agent/slice_c/**` to activate operational rules.
4. Any new persistence table, Alembic migration, or `Alembic` revision.
5. Any HTTP API endpoint, CLI command, or frontend widget.
6. Any Slice D, Slice E, or TASK-014+ design or implementation.
7. Any LLM call, prompt, or free-form natural-language generation.
8. Any automatic operational execution, TASK-012 POST, or external side effect.
9. Any change to TASK-008 through TASK-012 numerical semantics.
10. Any authority reselection, cross-run substitution, or implicit latest/current/best/default authority.
11. Any business formula, threshold, coefficient, productivity, turnover, shift duration, capacity conversion, or business rounding value **without** an approved source ID in the Charles confirmation matrix (§7).
12. Any C2 implementation, branch, worktree, Draft PR, Ready transition, or merge.
13. Any closure of Issue #99.

### §1.3 What this document does produce

1. A C2 category-by-category source authority contract with required upstream fields, JSON Pointer paths, and source identity fields.
2. A six-category `BUSINESS_SOURCE_REQUIRED` matrix enumerating which parameters must come from Charles before C2 activation.
3. A formula skeleton and decision table for each category that software must implement exactly when sources become available.
4. A Charles confirmation matrix of closed, directly-answerable questions.
5. A proposed six-slice implementation plan (C2-A through C2-F) for future rounds.

### §1.4 Authority of the prototype UI

The TASK-013 C2 Concept UI Prototype v1 (branch `prototype/task-013-c2-concept-ui-v1`, HEAD `15d2e53076ec30ba56f5a2f6657de50a5bd5abdf`, Issue #99 amendment comment `4967834240`) is a **visual business-workflow validation prototype only**. It is not a source authority. The prototype:

- MUST NOT be cited as a source ID, source version, source effective date, source hash, formula, threshold, coefficient, or rounding mode.
- MUST NOT be quoted to justify any `APPLICABLE` decision in C2.
- MAY be cited only as `prototype_visual_reference: <branch>@<sha>` in the `audit_log` of a Charles confirmation item when Charles confirms a parameter.
- The prototype's six capability blocks (CAPACITY-001/002, STAFF-001/002, VARIETY-001, DISPATCH-001) are exploratory labels and do not map one-to-one to the seven `RecommendationCategory` enum values in `backend/app/agent/enums.py::RecommendationCategory`. Mapping from prototype labels to production categories is a separate Charles confirmation item (CONF-EX-001 in §7).

---

## §2 Source authority hierarchy

All business-rule values in C2 must resolve to a source from the following five-level hierarchy. Lower-priority sources MAY NOT be silently promoted to higher-priority authority.

### §2.1 Hierarchy (highest to lowest)

| Rank | Authority | Description | Allowed as source for | Frozen status |
|---:|---|---|---|---|
| 1 | `CHARLES_CONFIRMED_SOURCE` | Charles has explicitly confirmed a specific business rule, source identity, formula, threshold, rounding, or non-action. Captured in the Charles confirmation matrix (§7) with a confirmation ID `CONF-*`. | Any C2 category field. | PENDING this round |
| 2 | `APPROVED_AUDITABLE_SOURCE` | A frozen, audit-traceable corporate rule, production standard, planning parameter, or equipment specification that has been approved through Charles's normal governance process and can be cited by source ID, version, effective date, and content hash. | Any C2 category field. | NOT YET PROVIDED for any C2 parameter — all C2-B01..B06 remain `BUSINESS_SOURCE_REQUIRED` |
| 3 | `PERSISTED_UPSTREAM_MODEL_OUTPUT` | A value already persisted and integrity-validated by TASK-008 through TASK-012 in the Slice B `AgentForecastOutput`. This includes `parameters`, `daily_curve`, and `peak` payloads. | C2 category fields whose RFC 6901 JSON Pointer resolves to a Slice B value. Examples: `/peak/peak_window_cumulative_quantity_kg/P80`, `/daily_curve/7/final_corrected_arrival_quantity_kg/p50`. | RESOLVED — Slice B persistence chain Task 8 → Task 9 v2 → Task 10 → Slice B is `RESOLVED_BY_MERGED_AUTHORITY` (PR #100). |
| 4 | `PROTOTYPE_VISUAL_REFERENCE` | The TASK-013 C2 Concept UI Prototype v1 visual labels, placeholder text, and interaction flow. NOT a source of values, formulas, or thresholds. | Audit-log annotation only, never as a primary source. | NOT A PRIMARY AUTHORITY |
| 5 | `INDUSTRY_HEURISTIC_OR_DEFAULT` | Industry average, rule of thumb, "common practice", web-sourced default, or LLM-inferred default. | FORBIDDEN — MUST NOT be used as authority. C2 activation requires promotion of every such candidate to rank 1 or 2 via Charles confirmation. | EXPLICITLY FORBIDDEN |

### §2.2 Promotion rule

- A value at rank 5 MUST NOT be silently promoted to rank 3 or above.
- A value at rank 4 MUST NOT be silently promoted to rank 3 or above.
- A value at rank 3 MAY be cited only with a valid Slice B Citation whose JSON Pointer resolves to the value, whose artifact hash matches, and whose source level is in `{1, 2, 3, 4, 5}` (i.e. the five-step priority chain defined in `UncertaintyWideningPolicy`).
- A value at rank 2 MAY be cited only with a Charles-provided `source_id`, `source_version`, `source_effective_date`, and `source_hash`.
- A value at rank 1 (Charles confirmation) is binding until explicitly revised by Charles; revision requires a new CONF-* row with `supersedes` linkage.

### §2.3 Conflict resolution

If two sources disagree:

1. The higher-rank source wins.
2. If sources are at the same rank, the more recent `source_effective_date` wins.
3. If `source_effective_date` is identical, the higher `source_hash` (lexicographic) wins.
4. If still tied, the conflict is `SOURCE_CONFLICT` and the decision is `BLOCKED` with `reason_code = REQUIRED_EVIDENCE_MISSING` until Charles resolves.
5. The conflict itself is logged in §10.3 of the implementation plan (`C2-E — production wiring`) and is a Test C2-E-008 acceptance gate.

---

## §3 Six operational category source-definition

### §3.0 Common contract applied to all six categories

The following items are identical for all six operational categories. Any category-specific deviation is explicitly stated in §3.1–§3.6.

#### §3.0.1 Output envelope (all categories)

| Field | Value | Source | Status |
|---|---|---|---|
| Output shape | Single `RecommendationDecision` (Issue #99 §"RecommendationDecision and reason contract"). Implementation requires schema upgrade of `backend/app/agent/schemas.py::Recommendation` to add `status`, `reason_code`, `reason_details`, `priority_rank`, `template_id`, `advisory_text`, `applicability_conditions`, `risk_codes`, `confidence_boundary`, `blocker_dependencies`, `non_action`. | Issue #99 §"GenerateRecommendations contract" + "RecommendationDecision and reason contract" | `CONFIRMED` (design) / `NOT YET IMPLEMENTED` (code) |
| Output count | Exactly seven `RecommendationDecision` objects per `GenerateRecommendationsOutput`, in canonical category order (§3.0.2). | Issue #99 §"Recommendation canonical order" | `CONFIRMED` |
| C1 state for the six operational categories | `status = BLOCKED`, `reason_code = REQUIRED_THRESHOLD_MISSING`, `advisory_text = null`. | Issue #99 §"Phase C1 and C2 authorization gates" + amendment `4964903322` | `RESOLVED_BY_MERGED_AUTHORITY` (PR #100) |
| Non-action code | One of the seven category-specific non-action codes plus the universal `ADVISORY_ONLY_NO_AUTOMATIC_EXECUTION` text. | Issue #99 §"Unified non-action contract" | `CONFIRMED_BY_CHARLES` |
| Citation reuse | `RecommendationEvidence` reuses the canonical `Citation` schema (`backend/app/agent/schemas.py::Citation`). No shorthand citation is permitted. | Issue #99 §"Output form and Citation" | `CONFIRMED` |
| Field-path policy | RFC 6901 JSON Pointer, version `slice-c-json-pointer-policy-v1`. | Issue #99 §"RFC 6901 evidence field-path contract" | `CONFIRMED` |
| Forbidden action language | `execute`, `dispatch now`, `schedule automatically`, `assign staff`, `modify pruning plan`, `change capacity`, `submit order`, `trigger POST` are forbidden unless they appear in an explicit non-action or prohibition statement. | Issue #99 §"Unified non-action contract" | `CONFIRMED_BY_CHARLES` |

#### §3.0.2 Canonical category order

| Rank | Category | Kind | C1 priority_rank | C2 priority_rank (proposed) | Frozen status |
|---:|---|---|---:|---:|---|
| 1 | `SUSTAINED_PROCESSING_CAPACITY` | `OPERATIONAL` | 1 | 1 (proposed) | `BUSINESS_SOURCE_REQUIRED` |
| 2 | `RECEIVING_PEAK_CAPACITY` | `OPERATIONAL` | 2 | 2 (proposed) | `BUSINESS_SOURCE_REQUIRED` |
| 3 | `SHIFT_STAFFING` | `OPERATIONAL` | 3 | 3 (proposed) | `BUSINESS_SOURCE_REQUIRED` |
| 4 | `SPRING_FESTIVAL_STAFFING` | `OPERATIONAL` | 4 | 4 (proposed) | `BUSINESS_SOURCE_REQUIRED` |
| 5 | `VARIETY_STAGGER` | `OPERATIONAL` | 5 | 5 (proposed) | `BUSINESS_SOURCE_REQUIRED` |
| 6 | `CROSS_PLANT_DISPATCH` | `OPERATIONAL` | 6 | 6 (proposed) | `BUSINESS_SOURCE_REQUIRED` |
| 7 | `MISSING_DATA_IMPACT` | `DATA_QUALITY` | 7 | 7 (C1 frozen, not part of C2 activation) | `CONFIRMED` |

Source: `backend/app/agent/enums.py::RecommendationCategory` (`RESOLVED_BY_MERGED_AUTHORITY`).

The seven C2 priority_ranks are confirmed by `RESOLVED_BY_MERGED_AUTHORITY` (PR #100 C1 implementation, `backend/app/agent/slice_c/engine.py`).

#### §3.0.3 Common blocker / reason mapping (all categories)

| Status | Allowed reason codes |
|---|---|
| `APPLICABLE` | `RULE_APPLICABLE` |
| `NOT_APPLICABLE` | `CONDITIONS_NOT_MET`, `OUTSIDE_AUTHORIZED_SCOPE` |
| `BLOCKED` | `REQUIRED_THRESHOLD_MISSING`, `REQUIRED_EVIDENCE_MISSING`, `UPSTREAM_BLOCKED`, `POLICY_UNAVAILABLE` |

Source: Issue #99 §"RecommendationDecision and reason contract" + §"Reason mapping" — `CONFIRMED_BY_CHARLES`.

#### §3.0.4 Common decision rules (all categories)

- Exactly seven decisions are emitted in merged category order; no category is omitted.
- Rules are ordered by category canonical rank, then `priority_rank`, then `rule_id` lexical ascending.
- The first rule whose `applicability_conditions` are all `TRUE` wins.
- Any `UNKNOWN` caused by missing required evidence produces `BLOCKED`.
- If every evaluated condition is `FALSE`, the decision is `NOT_APPLICABLE`.
- Only `APPLICABLE` permits non-null `advisory_text`.
- `NOT_APPLICABLE` has `advisory_text = null` and uses an allowed stable reason.
- `BLOCKED` has `advisory_text = null` and emits no action number.
- No new severity taxonomy; only `priority_rank` is used.

#### §3.0.5 Common slice-C blocker codes

| Code | Meaning | Categories |
|---|---|---|
| `EXPLANATION_POLICY_MISSING` | Explanation policy/catalog identity missing. | All (explanation side, not C2) |
| `EXPLANATION_TEMPLATE_MISSING` | Explanation template missing. | All (explanation side, not C2) |
| `RECOMMENDATION_POLICY_MISSING` | Recommendation policy/catalog identity missing. | All 7 |
| `RECOMMENDATION_RULE_MISSING` | Specific rule row missing from the rule catalog. | All 7 |
| `RECOMMENDATION_THRESHOLD_MISSING` | Required threshold value missing or `BUSINESS_SOURCE_REQUIRED`. | 6 operational |
| `REQUIRED_CITATION_MISSING` | Canonical Citation missing for a required evidence field. | All 7 |
| `REQUIRED_AUTHORITY_MISSING` | Authority envelope missing or invalid. | All 7 |
| `REQUIRED_PROVENANCE_MISSING` | Provenance (source ID / version / date / hash) missing. | 6 operational |
| `EVIDENCE_FIELD_PATH_INVALID` | RFC 6901 JSON Pointer did not resolve. | All 7 |
| `EVIDENCE_HASH_MISMATCH` | Resolved value's hash did not match citation's artifact hash. | All 7 |

Source: Issue #99 §"Blocker and propagation contract" — `CONFIRMED_BY_CHARLES`.

#### §3.0.6 Common replay / hash surface

- `agent_recommendations_hash = sha256(canonical JSON of the complete GenerateRecommendationsOutput excluding agent_recommendations_hash)`. Source: Issue #99 §"GenerateRecommendations contract".
- The rule catalog is itself hashed: `rule_catalog_hash = sha256(canonical JSON of the complete ordered rule catalog excluding rule_catalog_hash itself)`. Source: Issue #99 §"Policy schemas, identifiers, and canonical hashes".
- The hash surface excludes runtime timestamps, database-generated IDs, hosts, paths, environment-specific values, unordered sets, and nondeterministically ordered mappings. Source: same.
- Hashes are computed from final canonical payloads and are never manually assigned. Source: same.

---

### §3.1 SUSTAINED_PROCESSING_CAPACITY

#### §3.1.1 Business purpose

Recommend a sustained (multi-day) processing capacity that the receiving plant can rely on across the peak window, based on a forecast daily curve and a Charles-confirmed safety factor. The category emits a single capacity value (or `BLOCKED`) and does not embed per-day processing instructions.

#### §3.1.2 Allowed upstream fields

- `/peak/peak_window_cumulative_quantity_kg/{P50,P80,P90}` — three-day rolling peak total (kg).
- `/peak/peak_window_days_before`, `/peak/peak_window_days_after` — window configuration.
- `/peak/peak_metric_policy_version`, `/peak/peak_metric_policy_config_hash` — policy identity.
- `/peak/peak_window_cumulative_quantity_kg` policy-resolved quantile selection (C2 source `CONF-001`, see §7).
- `/daily_curve/{day_index}/final_corrected_arrival_quantity_kg/{p50,p80,p90}` — daily corrected arrivals.
- `/daily_curve/{day_index}/spring_festival_phase` — per-day Spring Festival phase (relevant for sustained-window identification across the festival boundary).
- `/peak/high_load_threshold_ratio` — high-load reference ratio, but the choice of which quantile to use is `BUSINESS_SOURCE_REQUIRED` (CONF-001).

#### §3.1.3 RFC 6901 JSON Pointer examples

```text
/peak/peak_window_cumulative_quantity_kg/P50
/peak/peak_window_cumulative_quantity_kg/P80
/peak/peak_window_cumulative_quantity_kg/P90
/peak/peak_window_days_before
/peak/peak_window_days_after
/daily_curve/0/final_corrected_arrival_quantity_kg/p80
/daily_curve/7/final_corrected_arrival_quantity_kg/p50
/daily_curve/14/spring_festival_phase
```

#### §3.1.4 Field-level source authority

| Field | Authority type | Source ID | Source version | Source effective date | Source hash | Status |
|---|---|---|---|---|---|---|
| `/peak/peak_window_cumulative_quantity_kg/P50` | `PERSISTED_UPSTREAM_MODEL_OUTPUT` (Slice B) | `forecast_peak.run_id` | Slice B `peak_metric_policy_version` | Slice B `as_of` | Slice B `peak_metric_policy_config_hash` | `RESOLVED_BY_MERGED_AUTHORITY` |
| Same for `/P80` and `/P90` | same | same | same | same | same | `RESOLVED_BY_MERGED_AUTHORITY` |
| Selected quantile (`P50` / `P80` / `P90`) for capacity basis | `CHARLES_CONFIRMED_SOURCE` | `CONF-001` | TBD on confirmation | TBD | TBD on confirmation | `BUSINESS_SOURCE_REQUIRED` |
| `sustained_window_days` (currently hard-coded `3` by `PeakMetricPolicy.strict_three_day_window`) | `APPROVED_AUDITABLE_SOURCE` (production standard) or `CHARLES_CONFIRMED_SOURCE` | `CONF-002` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Single-day vs sustained-three-day basis choice | `CHARLES_CONFIRMED_SOURCE` | `CONF-003` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Safety factor (capacity margin reduction) | `APPROVED_AUDITABLE_SOURCE` | `CONF-004` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Unit (kg/day) and display unit (t/day) | `CHARLES_CONFIRMED_SOURCE` | `CONF-005` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Decimal precision (display digits after decimal) | `CHARLES_CONFIRMED_SOURCE` | `CONF-006` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Business rounding mode (e.g. `ROUND_HALF_UP`, `ROUND_FLOOR`, `ROUND_CEIL`) | `CHARLES_CONFIRMED_SOURCE` | `CONF-007` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Confidence downgrade rule (e.g. if `confidence_score` below threshold, set `confidence = MEDIUM`) | `CHARLES_CONFIRMED_SOURCE` | `CONF-008` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Risk codes (e.g. `SUSTAINED_PEAK_BREACH_RISK`, `SAFETY_FACTOR_INSUFFICIENT`) | `CHARLES_CONFIRMED_SOURCE` | `CONF-009` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Advisory template (deterministic, versioned text) | `CHARLES_CONFIRMED_SOURCE` | `CONF-010` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |

#### §3.1.5 Applicability and granularity

- **Applicable grain (time)**: per requested season × resolved location × resolved varieties.
- **Applicable grain (space)**: per plant (TBD: cross-plant? CONF-011).
- **Unit (output)**: kg/day, optionally display in t/day (rounded). Source: CONF-005.
- **Quantile (output)**: a single quantile selected by CONF-001.

#### §3.1.6 Formula skeleton (machine-executable form)

Inputs (canonical scalar strings; resolved via JSON Pointer):

```
Q_in        := value at /peak/peak_window_cumulative_quantity_kg/<QUANTILE_CHOSEN>  (Decimal, kg over 3-day window)
WINDOW_DAYS := value at /peak/peak_window_days_before + /peak/peak_window_days_after + 1  (Int, days; for sustained=3 window: 3)
SAFETY      := SAFETY_FACTOR  (Decimal in (0, 1]; 1.0 = no margin, 0.85 = 15% margin)        [BUSINESS_SOURCE_REQUIRED — CONF-004]
UNIT_OUT    := "kg/day" or "t/day"                                                       [BUSINESS_SOURCE_REQUIRED — CONF-005]
PRECISION   := int >= 0                                                                  [BUSINESS_SOURCE_REQUIRED — CONF-006]
ROUND_MODE  := "ROUND_HALF_UP" | "ROUND_HALF_EVEN" | "ROUND_FLOOR" | "ROUND_CEIL"        [BUSINESS_SOURCE_REQUIRED — CONF-007]
```

Computation (pseudocode; canonical implementation language = Python `decimal` module with explicit context):

```python
from decimal import Decimal, ROUND_HALF_UP, ROUND_HALF_EVEN, ROUND_FLOOR, ROUND_CEIL

def sustained_processing_capacity(
    Q_in: Decimal,        # kg over 3-day window
    WINDOW_DAYS: int,     # must equal 3 under strict_three_day_window=True
    SAFETY: Decimal,      # in (0, 1]
    UNIT_OUT: str,        # "kg/day" | "t/day"
    PRECISION: int,       # >= 0
    ROUND_MODE: str,
) -> Decimal:
    # dimension check
    assert WINDOW_DAYS == 3, "WINDOW_DAYS must equal 3 under strict_three_day_window=True"
    assert 0 < SAFETY <= 1, "SAFETY must be in (0, 1]"
    # missing input → BLOCKED upstream
    if Q_in is None:
        raise ValueError("REQUIRED_EVIDENCE_MISSING")
    # zero handling
    if Q_in == 0:
        # per spec: zero daily arrival → capacity recommendation = 0 kg/day (no rounding)
        return Decimal("0")
    # negative value forbidden
    if Q_in < 0:
        raise ValueError("EVIDENCE_HASH_MISMATCH or upstream inconsistency")
    # raw daily capacity
    raw_daily_kg = (Q_in / Decimal(WINDOW_DAYS)) * SAFETY
    # unit conversion
    if UNIT_OUT == "t/day":
        out = raw_daily_kg / Decimal("1000")
    elif UNIT_OUT == "kg/day":
        out = raw_daily_kg
    else:
        raise ValueError("OUTSIDE_AUTHORIZED_SCOPE")
    # rounding
    rm = {"ROUND_HALF_UP": ROUND_HALF_UP, "ROUND_HALF_EVEN": ROUND_HALF_EVEN,
          "ROUND_FLOOR": ROUND_FLOOR, "ROUND_CEIL": ROUND_CEIL}[ROUND_MODE]
    quant = Decimal(10) ** -PRECISION
    return out.quantize(quant, rounding=rm)
```

#### §3.1.7 Threshold and comparison operator

- The only threshold in this category is `high_load_threshold_ratio` (resolved at `/peak/high_load_threshold_ratio` from `PeakMetricPolicy`). It is used **upstream** by Slice B to mark high-load days in the peak window; C2 does not redefine it. Source: `backend/app/agent/schemas.py::PeakMetricPolicy.high_load_threshold_ratio` — `RESOLVED_BY_MERGED_AUTHORITY`.
- C2 emits **no** new threshold for this category. The category only converts the Slice B peak value to a daily capacity using Charles-confirmed parameters.

#### §3.1.8 Boundary / inclusivity

- The capacity value is `> 0` (or `0` if Q_in = 0). Negative values are upstream errors and produce `EVIDENCE_HASH_MISMATCH` or `UPSTREAM_BLOCKED`.
- `SAFETY = 1.0` is allowed (no margin). `SAFETY > 1.0` is forbidden (would inflate capacity beyond measured throughput).

#### §3.1.9 Rounding mode and precision

- Rounding mode: `ROUND_MODE` from CONF-007. Allowed values: `ROUND_HALF_UP`, `ROUND_HALF_EVEN`, `ROUND_FLOOR`, `ROUND_CEIL`.
- Precision: `PRECISION` from CONF-006 (integer digits after decimal point).
- Canonical serialization: `Decimal`-backed string, no scientific notation, no trailing zeros, no locale.

#### §3.1.10 Null/missing semantics

| Missing input | Effect |
|---|---|
| `/peak/peak_window_cumulative_quantity_kg/<QUANTILE_CHOSEN>` is `null` or path not resolvable | `REQUIRED_EVIDENCE_MISSING` → `BLOCKED` |
| `WINDOW_DAYS != 3` | `OUTSIDE_AUTHORIZED_SCOPE` → `NOT_APPLICABLE` (sustained window policy is not the three-day one) |
| `SAFETY` missing (no Charles confirmation) | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` |
| `UNIT_OUT` / `PRECISION` / `ROUND_MODE` missing | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` |
| Selected quantile (CONF-001) not yet confirmed | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` |

#### §3.1.11 Missing-authority blocker

If any of CONF-001 through CONF-010 is not Charles-confirmed, the entire category is `BLOCKED` with `reason_code = REQUIRED_THRESHOLD_MISSING` and a `blocker_dependency` of `RECOMMENDATION_THRESHOLD_MISSING`. The current C1 contract is `status = BLOCKED / reason_code = REQUIRED_THRESHOLD_MISSING / advisory_text = null` (Issue #99 §"Phase C1 — source-independent deterministic foundation" + amendment `4964903322`).

#### §3.1.12 APPLICABLE / NOT_APPLICABLE / BLOCKED conditions

| Condition set | Status | Reason code | Advisory text | Non-action |
|---|---|---|---|---|
| All 10 CONF items present + `/peak/peak_window_cumulative_quantity_kg/<QUANTILE_CHOSEN>` resolvable + WINDOW_DAYS == 3 | `APPLICABLE` | `RULE_APPLICABLE` | Template CONF-010 with the computed capacity value substituted | `NO_AUTOMATIC_PROCESSING_CAPACITY_CHANGE` + `ADVISORY_ONLY_NO_AUTOMATIC_EXECUTION` |
| All 10 CONF items present + WINDOW_DAYS != 3 | `NOT_APPLICABLE` | `OUTSIDE_AUTHORIZED_SCOPE` | `null` | `NO_AUTOMATIC_PROCESSING_CAPACITY_CHANGE` + `ADVISORY_ONLY_NO_AUTOMATIC_EXECUTION` |
| Any CONF-001..CONF-010 missing | `BLOCKED` | `REQUIRED_THRESHOLD_MISSING` | `null` | `NO_AUTOMATIC_PROCESSING_CAPACITY_CHANGE` + `ADVISORY_ONLY_NO_AUTOMATIC_EXECUTION` |
| `/peak/...` path not resolvable | `BLOCKED` | `REQUIRED_EVIDENCE_MISSING` | `null` | same |
| `Citation.artifact_hash` does not match resolved value | `BLOCKED` | `EVIDENCE_HASH_MISMATCH` | `null` | same |
| Pointer escapes, alias, case normalization, or fuzzy resolution attempted | `BLOCKED` | `EVIDENCE_FIELD_PATH_INVALID` | `null` | same |
| Upstream Slice B blocked (e.g. `INSUFFICIENT_HISTORY`, `PEAK_POLICY_MISSING`) | `BLOCKED` | `UPSTREAM_BLOCKED` | `null` | same (preserve original blocker dependency verbatim) |
| `RecommendationRulePolicy` not loaded or `rule_catalog_hash` mismatch | `BLOCKED` | `POLICY_UNAVAILABLE` | `null` | same |

#### §3.1.13 Reason code / risk codes / confidence

- `reason_code`: per §3.1.12 mapping.
- `risk_codes` (when `APPLICABLE`): a deterministic subset drawn from CONF-009, e.g. `SUSTAINED_PEAK_BREACH_RISK` if `Q_in` exceeds the high-load threshold, `SAFETY_FACTOR_INSUFFICIENT` if `SAFETY < 0.8` (placeholder; final thresholds for risk codes come from CONF-009). When `BLOCKED` or `NOT_APPLICABLE`, `risk_codes = []`.
- `confidence`: `HIGH | MEDIUM | LOW | null`. Default `HIGH` when `APPLICABLE` and Slice B `confidence = HIGH`. Downgrade per CONF-008 when Slice B confidence is lower or when `source_level` is 3 or worse.

#### §3.1.14 Advisory template

The advisory template (CONF-010) is a deterministic versioned text with the following required structure (placeholders shown in `<<...>>`):

```
"按当前 <<QUANTILE_CHOSEN>> 滚动 3 日到果量 <<Q_IN_KG>> 公斤、<<SAFETY_PCT>>% 安全冗余, 推荐持续处理能力 <<CAPACITY>> <<UNIT_OUT>>。此为建议, 不触发任何自动执行。"
```

(Chinese text is the working language; English mirror in implementation.) The template version and content hash are stored in `template_catalog_version` and `template_catalog_hash` per Issue #99 §"Policy schemas, identifiers, and canonical hashes".

The only numeric values permitted in `advisory_text` are:
- the computed `CAPACITY` value,
- the input `Q_IN_KG` value (in kg, rounded to the same precision as `CAPACITY`),
- the `SAFETY_PCT` value (an integer percent, computed as `round(SAFETY * 100)`).

No other numbers are permitted. No LLM paraphrasing is permitted. Any attempt to embed additional numbers produces `POLICY_UNAVAILABLE` (template version conflict).

#### §3.1.15 Citation requirements

- Every `applicability_condition` whose result is `TRUE` MUST include a `Citation` whose JSON Pointer resolves to the value the rule consumed.
- The Citation's `artifact_hash` MUST equal the SHA-256 of the canonical JSON of the resolved value.
- The Citation's `source_task` MUST be `TASK_008` through `TASK_012` (Slice B provenance) for the value fields and `TASK_013` only for blocker metadata (no numerical authority envelope, per PR #100 body §"Evidence authority and sibling ownership").

#### §3.1.16 Replay / hash surface

- `GenerateRecommendationsOutput.agent_recommendations_hash` includes the canonical capacity value, the rule_id, the rule_catalog_hash, and the applicability_conditions list. Two replays with identical inputs and identical policy/catalog identities MUST produce byte-identical `agent_recommendations_hash`.
- The rule catalog row for SUSTAINED_PROCESSING_CAPACITY is a `BUSINESS_SOURCE_REQUIRED` placeholder. Its replacement with a real rule row is a C2-A acceptance gate (Test C2-A-001).

#### §3.1.17 Required tests (this category)

| Test ID | Kind | Description | Acceptance |
|---|---|---|---|
| TEST-C2-001-01 | Unit | `sustained_processing_capacity(Decimal("30000"), 3, Decimal("0.85"), "kg/day", 0, "ROUND_HALF_UP")` returns `Decimal("8500")` (i.e. 30000/3 × 0.85 = 8500). | PASS |
| TEST-C2-001-02 | Unit | Same call with `UNIT_OUT = "t/day"` returns `Decimal("8.5")` (8500/1000 = 8.5, 1-decimal precision). | PASS |
| TEST-C2-001-03 | Unit | `WINDOW_DAYS = 5` returns `NOT_APPLICABLE` with `OUTSIDE_AUTHORIZED_SCOPE` and `advisory_text = null`. | PASS |
| TEST-C2-001-04 | Unit | `Q_in = 0` returns `Decimal("0")` (no rounding). | PASS |
| TEST-C2-001-05 | Unit | `Q_in < 0` raises `ValueError` and the recommendation stage maps it to `EVIDENCE_HASH_MISMATCH` → `BLOCKED`. | PASS |
| TEST-C2-001-06 | Unit | Missing `SAFETY` returns `BLOCKED` with `REQUIRED_THRESHOLD_MISSING`. | PASS |
| TEST-C2-001-07 | Golden | Updated `task013_slice_c_output.json` shows SUSTAINED_PROCESSING_CAPACITY with `status = BLOCKED` and exact `advisory_text = null`. SHA-256 stable. | PASS (C1 contract preserved) |
| TEST-C2-001-08 | Integration (PostgreSQL) | Real Postgres chain through Task 8 → Task 9 v2 → Task 10 → Slice B → C2 produces a byte-stable `agent_recommendations_hash` with SUSTAINED_PROCESSING_CAPACITY in `BLOCKED` state. | PASS |

---

### §3.2 RECEIVING_PEAK_CAPACITY

#### §3.2.1 Business purpose

Recommend an instantaneous receiving peak capacity (kg/hour) and an associated temporary-storage capacity (kg) and pre-cooling capacity (kg) so the plant can absorb forecast arrivals at the peak window. The category emits three capacity values, each optional, and does not embed per-hour processing instructions.

#### §3.2.2 Allowed upstream fields

- `/peak/single_day_peak/{P50,P80,P90}/volume_kg` — single-day peak volume (kg). Per Issue #99 §"RFC 6901 evidence field-path contract" example.
- `/peak/peak_window_cumulative_quantity_kg/{P50,P80,P90}` — sustained three-day window total.
- `/daily_curve/{day_index}/arrival_quantity_kg/{p50,p80,p90}` — daily arrival quantiles (before weather/Spring corrections).
- `/daily_curve/{day_index}/final_corrected_arrival_quantity_kg/{p50,p80,p90}` — corrected arrival quantiles.
- `/peak/peak_window_days_before`, `/peak/peak_window_days_after` — peak-window config.
- `/peak/peak_metric_policy_version`, `/peak/peak_metric_policy_config_hash` — policy identity.

#### §3.2.3 RFC 6901 JSON Pointer examples

```text
/peak/single_day_peak/P50/volume_kg
/peak/single_day_peak/P80/volume_kg
/peak/single_day_peak/P90/volume_kg
/daily_curve/0/arrival_quantity_kg/p50
/daily_curve/0/arrival_quantity_kg/p80
/daily_curve/0/final_corrected_arrival_quantity_kg/p50
/daily_curve/7/final_corrected_arrival_quantity_kg/p80
/peak/peak_window_days_before
/peak/peak_window_days_after
```

#### §3.2.4 Field-level source authority

| Field | Authority type | Source ID | Source version | Source effective date | Source hash | Status |
|---|---|---|---|---|---|---|
| `/peak/single_day_peak/{P50,P80,P90}/volume_kg` | `PERSISTED_UPSTREAM_MODEL_OUTPUT` (Slice B) | `forecast_peak.run_id` | Slice B `peak_metric_policy_version` | Slice B `as_of` | Slice B `peak_metric_policy_config_hash` | `RESOLVED_BY_MERGED_AUTHORITY` |
| `/daily_curve/{day_index}/arrival_quantity_kg/{p50,p80,p90}` | `PERSISTED_UPSTREAM_MODEL_OUTPUT` (Slice B) | `forecast_daily_curve.run_id` | Slice B `daily_curve_policy_version` | Slice B `as_of` | Slice B `daily_curve_policy_config_hash` | `RESOLVED_BY_MERGED_AUTHORITY` |
| Selected quantile for peak basis | `CHARLES_CONFIRMED_SOURCE` | `CONF-012` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Instantaneous receiving capacity conversion (kg/day → kg/hour) using the daily receiving hours | `APPROVED_AUDITABLE_SOURCE` | `CONF-013` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Daily receiving operating hours | `APPROVED_AUDITABLE_SOURCE` | `CONF-014` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Turnover time at receiving dock (hours) | `APPROVED_AUDITABLE_SOURCE` | `CONF-015` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Temporary-storage capacity (kg) — physical max | `APPROVED_AUDITABLE_SOURCE` | `CONF-016` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Pre-cooling capacity (kg/day or kg/hour) | `APPROVED_AUDITABLE_SOURCE` | `CONF-017` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Safety factor (receiving margin) | `CHARLES_CONFIRMED_SOURCE` | `CONF-018` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Unit (kg/hour for instantaneous; kg for storage) | `CHARLES_CONFIRMED_SOURCE` | `CONF-019` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Decimal precision | `CHARLES_CONFIRMED_SOURCE` | `CONF-020` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Rounding mode | `CHARLES_CONFIRMED_SOURCE` | `CONF-021` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Risk codes (e.g. `DOCK_TURNOVER_BREACH_RISK`, `STORAGE_OVERFLOW_RISK`, `PRECOOL_BOTTLENECK_RISK`) | `CHARLES_CONFIRMED_SOURCE` | `CONF-022` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Advisory template | `CHARLES_CONFIRMED_SOURCE` | `CONF-023` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |

#### §3.2.5 Applicability and granularity

- **Applicable grain (time)**: per requested season × resolved location × resolved varieties.
- **Applicable grain (space)**: per plant (TBD: cross-plant? CONF-024).
- **Output**: three capacity values — instantaneous receiving (kg/hour), temporary storage (kg), pre-cooling (kg/day or kg/hour per CONF-017).

#### §3.2.6 Formula skeleton

Inputs:

```
PEAK_Q      := value at /peak/single_day_peak/<QUANTILE_CHOSEN>/volume_kg   (Decimal, kg)
RECV_HOURS  := DAILY_RECEIVING_HOURS                                            (Int, hours/day)         [BUSINESS_SOURCE_REQUIRED — CONF-014]
TURNOVER_H  := TURNOVER_TIME                                                    (Decimal, hours)         [BUSINESS_SOURCE_REQUIRED — CONF-015]
STORAGE_KG  := TEMP_STORAGE_CAPACITY                                            (Decimal, kg)            [BUSINESS_SOURCE_REQUIRED — CONF-016]
PRECOOL_KGH := PRECOOLING_CAPACITY_KG_PER_HOUR                                  (Decimal, kg/hour)       [BUSINESS_SOURCE_REQUIRED — CONF-017]
SAFETY      := RECEIVING_SAFETY_FACTOR                                          (Decimal in (0, 1])      [BUSINESS_SOURCE_REQUIRED — CONF-018]
PRECISION   := PRECISION                                                        (Int)                    [BUSINESS_SOURCE_REQUIRED — CONF-020]
ROUND_MODE  := ROUND_MODE                                                       (Str)                    [BUSINESS_SOURCE_REQUIRED — CONF-021]
```

Computation:

```python
from decimal import Decimal, ROUND_HALF_UP, ROUND_HALF_EVEN, ROUND_FLOOR, ROUND_CEIL

def receiving_peak_capacities(
    PEAK_Q: Decimal, RECV_HOURS: int, TURNOVER_H: Decimal,
    STORAGE_KG: Decimal, PRECOOL_KGH: Decimal,
    SAFETY: Decimal, PRECISION: int, ROUND_MODE: str,
):
    if PEAK_Q <= 0 or RECV_HOURS <= 0 or TURNOVER_H <= 0:
        raise ValueError("REQUIRED_EVIDENCE_MISSING")
    if not (Decimal("0") < SAFETY <= Decimal("1")):
        raise ValueError("REQUIRED_THRESHOLD_MISSING")
    rm = {"ROUND_HALF_UP": ROUND_HALF_UP, "ROUND_HALF_EVEN": ROUND_HALF_EVEN,
          "ROUND_FLOOR": ROUND_FLOOR, "ROUND_CEIL": ROUND_CEIL}[ROUND_MODE]
    quant = Decimal(10) ** -PRECISION

    # Instantaneous receiving (kg/hour)
    instantaneous_raw = (PEAK_Q * SAFETY) / Decimal(RECV_HOURS)
    instantaneous    = instantaneous_raw.quantize(quant, rounding=rm)

    # Temporary storage (kg) — using peak day volume, not divided by hours
    storage_raw      = PEAK_Q * SAFETY
    storage          = storage_raw.quantize(quant, rounding=rm)

    # Pre-cooling (kg/hour) — should not bottleneck the receiving line
    precool_raw      = min(PRECOOL_KGH, instantaneous)
    precool          = precool_raw.quantize(quant, rounding=rm)

    return {
        "instantaneous_receiving_kg_per_hour": instantaneous,
        "temporary_storage_kg":               storage,
        "precooling_kg_per_hour":             precool,
    }
```

#### §3.2.7 Threshold / boundary

- No new threshold. `high_load_threshold_ratio` from `PeakMetricPolicy` is upstream-only.
- Boundary: `instantaneous >= 0`, `storage >= 0`, `precool >= 0`. Negative is upstream error.

#### §3.2.8 Null / missing semantics

| Missing input | Effect |
|---|---|
| `PEAK_Q` not resolvable | `REQUIRED_EVIDENCE_MISSING` → `BLOCKED` |
| `RECV_HOURS` missing (CONF-014) | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` |
| `TURNOVER_H` missing (CONF-015) | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` |
| `STORAGE_KG` missing (CONF-016) | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` |
| `PRECOOL_KGH` missing (CONF-017) | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` |
| `SAFETY` missing (CONF-018) | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` |
| `PRECISION` / `ROUND_MODE` missing (CONF-020/CONF-021) | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` |
| Selected quantile (CONF-012) not yet confirmed | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` |

#### §3.2.9 APPLICABLE / NOT_APPLICABLE / BLOCKED conditions

| Condition set | Status | Reason code | Advisory text | Non-action |
|---|---|---|---|---|
| All CONF-012..CONF-023 present + PEAK_Q resolvable | `APPLICABLE` | `RULE_APPLICABLE` | Template CONF-023 with three capacity values substituted | `NO_AUTOMATIC_RECEIVING_CAPACITY_CHANGE` + `ADVISORY_ONLY_NO_AUTOMATIC_EXECUTION` |
| All CONF present + plant is not a receiving plant (e.g. `OUTSIDE_AUTHORIZED_SCOPE` confirmed by Charles) | `NOT_APPLICABLE` | `OUTSIDE_AUTHORIZED_SCOPE` | `null` | same |
| Any CONF-012..CONF-023 missing | `BLOCKED` | `REQUIRED_THRESHOLD_MISSING` | `null` | same |
| `/peak/...` path not resolvable | `BLOCKED` | `REQUIRED_EVIDENCE_MISSING` | `null` | same |
| Citation hash mismatch | `BLOCKED` | `EVIDENCE_HASH_MISMATCH` | `null` | same |
| Upstream blocked | `BLOCKED` | `UPSTREAM_BLOCKED` | `null` | same (preserve original blocker dependency verbatim) |
| Policy/catalog missing | `BLOCKED` | `POLICY_UNAVAILABLE` | `null` | same |

#### §3.2.10 Reason code / risk codes / confidence

- `reason_code`: per §3.2.9.
- `risk_codes` (when `APPLICABLE`): subset of CONF-022.
- `confidence`: derived from Slice B confidence + `SAFETY` source level (CONF-018).

#### §3.2.11 Advisory template

```
"按当前 <<QUANTILE_CHOSEN>> 单日峰值 <<PEAK_KG>> 公斤、<<SAFETY_PCT>>% 冗余, 推荐接货瞬时能力 <<INSTANT>> 公斤/小时, 配套暂存 <<STORAGE>> 公斤、预冷 <<PRECOOL>> 公斤/小时。此为建议, 不触发任何自动执行。"
```

Permitted numeric placeholders: `PEAK_KG`, `SAFETY_PCT`, `INSTANT`, `STORAGE`, `PRECOOL`. No other numbers.

#### §3.2.12 Citation requirements

Same as §3.1.15. The `PEAK_Q` evidence Citation `source_task` is `TASK_010` (Task 10 Prediction Run produces single-day peak).

#### §3.2.13 Replay / hash surface

Same as §3.1.16. Rule catalog row for RECEIVING_PEAK_CAPACITY is `BUSINESS_SOURCE_REQUIRED` placeholder (Test C2-A-002).

#### §3.2.14 Required tests (this category)

| Test ID | Kind | Description | Acceptance |
|---|---|---|---|
| TEST-C2-002-01 | Unit | With all CONF present, PEAK_Q = 100000 kg, RECV_HOURS = 10, TURNOVER_H = 2, STORAGE_KG = 120000, PRECOOL_KGH = 12000, SAFETY = 0.9, PRECISION = 0, ROUND_MODE = "ROUND_HALF_UP": returns `{"instantaneous_receiving_kg_per_hour": 9000, "temporary_storage_kg": 90000, "precooling_kg_per_hour": 9000}`. | PASS |
| TEST-C2-002-02 | Unit | `PRECOOL_KGH = 5000` (smaller than `instantaneous = 9000`): precooling = 5000. | PASS |
| TEST-C2-002-03 | Unit | Missing `RECV_HOURS` → `BLOCKED / REQUIRED_THRESHOLD_MISSING`. | PASS |
| TEST-C2-002-04 | Unit | `RECV_HOURS = 0` → `REQUIRED_EVIDENCE_MISSING`. | PASS |
| TEST-C2-002-05 | Unit | `SAFETY = 1.2` → `REQUIRED_THRESHOLD_MISSING`. | PASS |
| TEST-C2-002-06 | Golden | C1 preserved: status = BLOCKED, advisory_text = null. | PASS |
| TEST-C2-002-07 | Integration (PostgreSQL) | Real chain produces stable hash with RECEIVING_PEAK_CAPACITY in BLOCKED. | PASS |

---

### §3.3 SHIFT_STAFFING

#### §3.3.1 Business purpose

Recommend a per-shift staffing headcount and a shift schedule that supports sustained processing capacity. The category emits a shift schedule (e.g. `1 / 2 / 3 shifts × N staff`) and a confidence level. The category does not assign individual people.

#### §3.3.2 Allowed upstream fields

- `/peak/peak_window_cumulative_quantity_kg/{P50,P80,P90}` — sustained throughput target.
- `/daily_curve/{day_index}/final_corrected_arrival_quantity_kg/{p50,p80,p90}` — daily arrival target.
- `/parameters/{parameter_name}/p50|p80_lower|p80_upper|p90` — `PRODUCTIVITY_PER_PERSON_KG_PER_HOUR` (CONF-026), `ATTENDANCE_RATE` (CONF-027), etc., when these parameter types are persisted by Slice B.
- `PeakMetricPolicy` (already loaded by Slice B).

#### §3.3.3 RFC 6901 JSON Pointer examples

```text
/peak/peak_window_cumulative_quantity_kg/P80
/peak/peak_window_days_before
/peak/peak_window_days_after
/daily_curve/0/final_corrected_arrival_quantity_kg/p80
/daily_curve/14/final_corrected_arrival_quantity_kg/p50
/parameters/PRODUCTIVITY_PER_PERSON_KG_PER_HOUR/p50
/parameters/PRODUCTIVITY_PER_PERSON_KG_PER_HOUR/source_level
/parameters/ATTENDANCE_RATE/p50
```

#### §3.3.4 Field-level source authority

| Field | Authority type | Source ID | Source version | Source effective date | Source hash | Status |
|---|---|---|---|---|---|---|
| Sustained throughput target | `PERSISTED_UPSTREAM_MODEL_OUTPUT` (Slice B) | `forecast_peak.run_id` | Slice B `peak_metric_policy_version` | Slice B `as_of` | Slice B hash | `RESOLVED_BY_MERGED_AUTHORITY` |
| `PRODUCTIVITY_PER_PERSON_KG_PER_HOUR` parameter (if persisted) | `PERSISTED_UPSTREAM_MODEL_OUTPUT` (Task 8/9/10 parameter inference) | parameter `parameter_id` | parameter `prior_version` | parameter `as_of` | parameter citation hash | `RESOLVED_BY_MERGED_AUTHORITY` (if present) / `BUSINESS_SOURCE_REQUIRED` (if absent) |
| `SHIFT_DURATION_HOURS` (per-shift length) | `APPROVED_AUDITABLE_SOURCE` | `CONF-025` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| `PRODUCTIVITY_PER_PERSON_KG_PER_HOUR` (explicit override) | `APPROVED_AUDITABLE_SOURCE` | `CONF-026` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` (if parameter not persisted) |
| `ATTENDANCE_RATE` (per-shift attendance ratio) | `APPROVED_AUDITABLE_SOURCE` | `CONF-027` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| `PRODUCTIVITY_BY_ROLE` map (e.g. picker vs sorter vs packer) | `APPROVED_AUDITABLE_SOURCE` | `CONF-028` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| `PEAK_PERSONNEL_BUFFER` (extra headcount fraction during high-load) | `CHARLES_CONFIRMED_SOURCE` | `CONF-029` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Number of shifts per day (TBD: 1 / 2 / 3; or dynamic) | `CHARLES_CONFIRMED_SOURCE` | `CONF-030` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Decimal precision | `CHARLES_CONFIRMED_SOURCE` | `CONF-031` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Rounding mode (for headcount: `ROUND_CEIL` to avoid under-staffing) | `CHARLES_CONFIRMED_SOURCE` | `CONF-032` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Risk codes (e.g. `STAFFING_SHORTFALL_RISK`, `PRODUCTIVITY_BELOW_BENCHMARK_RISK`) | `CHARLES_CONFIRMED_SOURCE` | `CONF-033` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Advisory template | `CHARLES_CONFIRMED_SOURCE` | `CONF-034` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |

#### §3.3.5 Applicability and granularity

- **Applicable grain (time)**: per requested season × resolved location × resolved varieties × forecast day (the category emits per-day headcount for the peak window).
- **Applicable grain (space)**: per plant × per shift role.

#### §3.3.6 Formula skeleton

Inputs:

```
TARGET_KG     := value at /peak/peak_window_cumulative_quantity_kg/<QUANTILE_CHOSEN> / <WINDOW_DAYS>  (Decimal, kg/day)
SHIFT_HOURS   := SHIFT_DURATION_HOURS                                                                (Decimal, hours) [BUSINESS_SOURCE_REQUIRED — CONF-025]
PROD_KGPH     := PRODUCTIVITY_PER_PERSON_KG_PER_HOUR                                                 (Decimal, kg/person/hour) [BUSINESS_SOURCE_REQUIRED — CONF-026 or persisted parameter]
ATTEND        := ATTENDANCE_RATE                                                                     (Decimal in (0, 1]) [BUSINESS_SOURCE_REQUIRED — CONF-027]
BUFFER        := PEAK_PERSONNEL_BUFFER                                                               (Decimal in [0, 1)) [BUSINESS_SOURCE_REQUIRED — CONF-029]
NUM_SHIFTS    := NUMBER_OF_SHIFTS                                                                    (Int in {1, 2, 3}) [BUSINESS_SOURCE_REQUIRED — CONF-030]
PRECISION     := PRECISION                                                                           (Int) [BUSINESS_SOURCE_REQUIRED — CONF-031]
ROUND_MODE    := ROUND_MODE                                                                          (Str) [BUSINESS_SOURCE_REQUIRED — CONF-032]
```

Computation:

```python
def shift_staffing(
    TARGET_KG: Decimal, SHIFT_HOURS: Decimal, PROD_KGPH: Decimal,
    ATTEND: Decimal, BUFFER: Decimal, NUM_SHIFTS: int,
    PRECISION: int, ROUND_MODE: str,
):
    if TARGET_KG <= 0 or SHIFT_HOURS <= 0 or PROD_KGPH <= 0:
        raise ValueError("REQUIRED_EVIDENCE_MISSING")
    if not (Decimal("0") < ATTEND <= Decimal("1")):
        raise ValueError("REQUIRED_THRESHOLD_MISSING")
    if not (Decimal("0") <= BUFFER < Decimal("1")):
        raise ValueError("REQUIRED_THRESHOLD_MISSING")
    if NUM_SHIFTS not in (1, 2, 3):
        raise ValueError("OUTSIDE_AUTHORIZED_SCOPE")
    rm = {"ROUND_HALF_UP": ROUND_HALF_UP, "ROUND_HALF_EVEN": ROUND_HALF_EVEN,
          "ROUND_FLOOR": ROUND_FLOOR, "ROUND_CEIL": ROUND_CEIL}[ROUND_MODE]
    quant = Decimal(10) ** -PRECISION

    # Per-day headcount (un-rounded)
    raw = (TARGET_KG / SHIFT_HOURS) / (PROD_KGPH * ATTEND) * (Decimal("1") + BUFFER)
    # Distribute across shifts
    per_shift = (raw / Decimal(NUM_SHIFTS)).quantize(Decimal("1"), rounding=rm)
    total     = per_shift * NUM_SHIFTS
    return {
        "shifts_per_day": NUM_SHIFTS,
        "headcount_per_shift": int(per_shift),
        "total_headcount_per_day": int(total),
    }
```

#### §3.3.7 Threshold / boundary

- No new threshold. Output headcount is `>= 0`. `0` means no staff required (rare, e.g. very small forecast).
- `BUFFER = 0` is allowed (no extra headcount). `BUFFER > 0.5` is forbidden by §3.3.6 (would double headcount).

#### §3.3.8 Null / missing semantics

| Missing input | Effect |
|---|---|
| `TARGET_KG` not resolvable | `REQUIRED_EVIDENCE_MISSING` → `BLOCKED` |
| `SHIFT_HOURS` missing (CONF-025) | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` |
| `PROD_KGPH` missing AND no persisted parameter | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` |
| `ATTEND` missing (CONF-027) | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` |
| `BUFFER` missing (CONF-029) | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` |
| `NUM_SHIFTS` missing (CONF-030) | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` |
| `PRECISION` / `ROUND_MODE` missing | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` |
| Selected quantile (cross-ref to §3.1.4, CONF-001) not yet confirmed | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` |

#### §3.3.9 APPLICABLE / NOT_APPLICABLE / BLOCKED conditions

| Condition set | Status | Reason code | Advisory text | Non-action |
|---|---|---|---|---|
| All CONF-001 + CONF-025..CONF-034 present + TARGET_KG resolvable + PROD_KGPH either persisted or from CONF-026 | `APPLICABLE` | `RULE_APPLICABLE` | Template CONF-034 with shift count and headcount substituted | `NO_AUTOMATIC_SHIFT_STAFFING_ACTION` + `ADVISORY_ONLY_NO_AUTOMATIC_EXECUTION` |
| All CONF present + plant has no shift operation (e.g. CONF-035 marks plant as `OUTSIDE_AUTHORIZED_SCOPE` for shift staffing) | `NOT_APPLICABLE` | `OUTSIDE_AUTHORIZED_SCOPE` | `null` | same |
| Any CONF-025..CONF-034 missing | `BLOCKED` | `REQUIRED_THRESHOLD_MISSING` | `null` | same |
| `PRODUCTIVITY_PER_PERSON_KG_PER_HOUR` parameter not persisted AND no CONF-026 | `BLOCKED` | `REQUIRED_EVIDENCE_MISSING` (parameter) + `REQUIRED_THRESHOLD_MISSING` (CONF) | `null` | same |
| Citation hash mismatch | `BLOCKED` | `EVIDENCE_HASH_MISMATCH` | `null` | same |
| Upstream blocked | `BLOCKED` | `UPSTREAM_BLOCKED` | `null` | same |

#### §3.3.10 Reason code / risk codes / confidence

- `reason_code`: per §3.3.9.
- `risk_codes` (when `APPLICABLE`): subset of CONF-033.
- `confidence`: derived from parameter `source_level` and attendance-rate source provenance.

#### §3.3.11 Advisory template

```
"按 <<QUANTILE_CHOSEN>> 滚动 3 日 <<TARGET_KG>> 公斤/天、<<BUFF_PCT>>% 高峰缓冲, 推荐 <<NUM_SHIFTS>> 班制, 每班 <<HEAD_PER_SHIFT>> 人 (合计 <<HEAD_TOTAL>> 人/天)。此为建议, 不触发任何自动执行。"
```

Permitted placeholders: `QUANTILE_CHOSEN`, `TARGET_KG`, `BUFF_PCT`, `NUM_SHIFTS`, `HEAD_PER_SHIFT`, `HEAD_TOTAL`. No other numbers.

#### §3.3.12 Citation requirements

Same as §3.1.15. Persisted parameter Citation `source_task` is `TASK_009` (Task 9 v2 harvest-state persistence) or `TASK_010` (Task 10 prediction run parameter inference).

#### §3.3.13 Replay / hash surface

Same as §3.1.16. Rule catalog row for SHIFT_STAFFING is `BUSINESS_SOURCE_REQUIRED` placeholder (Test C2-A-003).

#### §3.3.14 Required tests (this category)

| Test ID | Kind | Description | Acceptance |
|---|---|---|---|
| TEST-C2-003-01 | Unit | TARGET_KG = 30000, SHIFT_HOURS = 8, PROD_KGPH = 50, ATTEND = 0.9, BUFFER = 0.1, NUM_SHIFTS = 2, ROUND_MODE = "ROUND_CEIL": per_shift = ceil((30000/8)/(50*0.9)*(1+0.1)/2) = ceil(45.83) = 46; total = 92. | PASS |
| TEST-C2-003-02 | Unit | `NUM_SHIFTS = 4` → `OUTSIDE_AUTHORIZED_SCOPE` → `NOT_APPLICABLE`. | PASS |
| TEST-C2-003-03 | Unit | Missing `SHIFT_HOURS` → `BLOCKED / REQUIRED_THRESHOLD_MISSING`. | PASS |
| TEST-C2-003-04 | Unit | `PROD_KGPH = 0` → `REQUIRED_EVIDENCE_MISSING`. | PASS |
| TEST-C2-003-05 | Unit | `BUFFER = 0.6` → `REQUIRED_THRESHOLD_MISSING` (out of [0, 1)). | PASS |
| TEST-C2-003-06 | Golden | C1 preserved. | PASS |
| TEST-C2-003-07 | Integration (PostgreSQL) | Real chain produces stable hash with SHIFT_STAFFING in BLOCKED. | PASS |

---

### §3.4 SPRING_FESTIVAL_STAFFING

#### §3.4.1 Business purpose

Recommend an adjusted staffing headcount and lead-time during the Spring Festival window (per-day `SpringFestivalPhase` ∈ `PRE | DURING | POST`), accounting for reduced picker availability and processor lead-time. The category does not pick individuals.

#### §3.4.2 Allowed upstream fields

- `/daily_curve/{day_index}/spring_festival_phase` — per-day phase.
- `/daily_curve/{day_index}/final_corrected_arrival_quantity_kg/{p50,p80,p90}` — daily corrected arrival.
- `/parameters/PICKER_AVAILABILITY_FACTOR/p50` (if persisted) — fraction of pickers available during a phase.
- `/parameters/PROCESSOR_AVAILABILITY_FACTOR/p50` (if persisted) — fraction of processors available.
- `SPRING_FESTIVAL_CALENDAR_POLICY` (loaded by Slice B; per `BlockerCode.SPRING_FESTIVAL_CALENDAR_POLICY_MISSING`).

#### §3.4.3 RFC 6901 JSON Pointer examples

```text
/daily_curve/0/spring_festival_phase
/daily_curve/14/spring_festival_phase
/daily_curve/30/spring_festival_phase
/daily_curve/14/final_corrected_arrival_quantity_kg/p50
/parameters/PICKER_AVAILABILITY_FACTOR/p50
/parameters/PROCESSOR_AVAILABILITY_FACTOR/p50
```

#### §3.4.4 Field-level source authority

| Field | Authority type | Source ID | Source version | Source effective date | Source hash | Status |
|---|---|---|---|---|---|---|
| Per-day `spring_festival_phase` | `PERSISTED_UPSTREAM_MODEL_OUTPUT` (Slice B) | `forecast_daily_curve.run_id` | Slice B `spring_festival_calendar_policy_version` | Slice B `as_of` | Slice B `spring_festival_calendar_policy_config_hash` | `RESOLVED_BY_MERGED_AUTHORITY` |
| `PICKER_AVAILABILITY_FACTOR` (if persisted) | `PERSISTED_UPSTREAM_MODEL_OUTPUT` (Task 8/9/10) | parameter `parameter_id` | parameter `prior_version` | parameter `as_of` | parameter citation hash | `RESOLVED_BY_MERGED_AUTHORITY` (if present) / `BUSINESS_SOURCE_REQUIRED` (if absent) |
| `PROCESSOR_AVAILABILITY_FACTOR` (if persisted) | same as above | same | same | same | same | same |
| `PICKER_AVAILABILITY_FACTOR` (explicit override) | `APPROVED_AUDITABLE_SOURCE` | `CONF-036` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` (if parameter not persisted) |
| `PROCESSOR_AVAILABILITY_FACTOR` (explicit override) | `APPROVED_AUDITABLE_SOURCE` | `CONF-037` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` (if parameter not persisted) |
| `PICKER_PRODUCTIVITY_KG_PER_HOUR` | `APPROVED_AUDITABLE_SOURCE` | `CONF-038` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| `PROCESSOR_PRODUCTIVITY_KG_PER_HOUR` | `APPROVED_AUDITABLE_SOURCE` | `CONF-039` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| `PICKER_PRE_FESTIVAL_LEAD_DAYS` | `APPROVED_AUDITABLE_SOURCE` | `CONF-040` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| `PROCESSOR_DURING_FESTIVAL_LEAD_DAYS` | `APPROVED_AUDITABLE_SOURCE` | `CONF-041` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| `PICKER_POST_FESTIVAL_RECOVERY_DAYS` | `APPROVED_AUDITABLE_SOURCE` | `CONF-042` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Per-phase mapping `PRE / DURING / POST` to availability factors | `CHARLES_CONFIRMED_SOURCE` | `CONF-043` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Decimal precision / Rounding mode | `CHARLES_CONFIRMED_SOURCE` | `CONF-044` / `CONF-045` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Risk codes (e.g. `PICKER_SHORTAGE_RISK`, `PROCESSOR_LEAD_TIME_RISK`) | `CHARLES_CONFIRMED_SOURCE` | `CONF-046` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Advisory template | `CHARLES_CONFIRMED_SOURCE` | `CONF-047` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |

#### §3.4.5 Applicability and granularity

- **Applicable grain (time)**: per forecast day within Spring Festival window (per `spring_festival_phase`).
- **Applicable grain (space)**: per plant × per role (picker / processor).
- **Output**: per-day headcount for pickers and processors, plus a lead-time recommendation.

#### §3.4.6 Formula skeleton

For each day in the forecast horizon with `spring_festival_phase ∈ {PRE, DURING, POST}`:

```
PHASE          := spring_festival_phase at /daily_curve/{i}/spring_festival_phase
ARRIVAL_KG     := final_corrected_arrival_quantity_kg at /daily_curve/{i}/final_corrected_arrival_quantity_kg/p50
PICK_AVAIL     := PICKER_AVAILABILITY_FACTOR[PHASE]   (Decimal in (0, 1])
PROC_AVAIL     := PROCESSOR_AVAILABILITY_FACTOR[PHASE] (Decimal in (0, 1])
PICK_PROD      := PICKER_PRODUCTIVITY_KG_PER_HOUR    (Decimal, kg/picker/hour)
PROC_PROD      := PROCESSOR_PRODUCTIVITY_KG_PER_HOUR (Decimal, kg/processor/hour)
PICK_HOURS     := PICKER_AVAILABLE_HOURS_PER_DAY     (Decimal, hours)
PROC_HOURS     := PROCESSOR_AVAILABLE_HOURS_PER_DAY  (Decimal, hours)
```

`pickers_needed = ceil(ARRIVAL_KG / (PICK_PROD * PICK_AVAIL * PICK_HOURS))`
`processors_needed = ceil(ARRIVAL_KG / (PROC_PROD * PROC_AVAIL * PROC_HOURS))`

Lead-time outputs:
- `PRE_FESTIVAL_PICKER_LEAD_DAYS = PICKER_PRE_FESTIVAL_LEAD_DAYS` (CONF-040)
- `DURING_FESTIVAL_PROCESSOR_LEAD_DAYS = PROCESSOR_DURING_FESTIVAL_LEAD_DAYS` (CONF-041)
- `POST_FESTIVAL_PICKER_RECOVERY_DAYS = PICKER_POST_FESTIVAL_RECOVERY_DAYS` (CONF-042)

#### §3.4.7 Null / missing semantics

| Missing input | Effect |
|---|---|
| `spring_festival_phase` is `NONE` for all days | `NOT_APPLICABLE` (no Spring Festival window) with `CONDITIONS_NOT_MET` |
| Any of CONF-036..CONF-047 missing | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` |
| `spring_festival_calendar_policy` missing from upstream | `UPSTREAM_BLOCKED` (preserve `SPRING_FESTIVAL_CALENDAR_POLICY_MISSING`) → `BLOCKED` |
| Phase not in {PRE, DURING, POST} | `OUTSIDE_AUTHORIZED_SCOPE` → `NOT_APPLICABLE` |

#### §3.4.8 APPLICABLE / NOT_APPLICABLE / BLOCKED conditions

| Condition set | Status | Reason code | Advisory text | Non-action |
|---|---|---|---|---|
| All CONF-036..CONF-047 present + at least one day with `spring_festival_phase ∈ {PRE, DURING, POST}` | `APPLICABLE` | `RULE_APPLICABLE` | Template CONF-047 with per-phase lead-times and per-day headcounts substituted | `NO_AUTOMATIC_SPRING_FESTIVAL_STAFFING_ACTION` + `ADVISORY_ONLY_NO_AUTOMATIC_EXECUTION` |
| All CONF present + no day in horizon has Spring Festival phase | `NOT_APPLICABLE` | `CONDITIONS_NOT_MET` | `null` | same |
| All CONF present + at least one phase value outside {NONE, PRE, DURING, POST} | `NOT_APPLICABLE` | `OUTSIDE_AUTHORIZED_SCOPE` | `null` | same |
| Any CONF-036..CONF-047 missing | `BLOCKED` | `REQUIRED_THRESHOLD_MISSING` | `null` | same |
| Calendar policy missing | `BLOCKED` | `UPSTREAM_BLOCKED` | `null` | same |
| Citation hash mismatch | `BLOCKED` | `EVIDENCE_HASH_MISMATCH` | `null` | same |

#### §3.4.9 Reason code / risk codes / confidence

- `reason_code`: per §3.4.8.
- `risk_codes` (when `APPLICABLE`): subset of CONF-046, e.g. `PICKER_SHORTAGE_RISK` if `PICK_AVAIL < 0.6` (placeholder; final threshold from CONF-046).
- `confidence`: derived from parameter source_level.

#### §3.4.10 Advisory template

```
"春节窗口: 前期 (PRE) 需提前 <<PICK_PRE_LEAD>> 天安排采摘; 期间 (DURING) 加工提前 <<PROC_DURING_LEAD>> 天; 后期 (POST) 采摘恢复 <<PICK_POST_RECOVERY>> 天。逐日人员需求见明细 (单位: 人/天)。此为建议, 不触发任何自动执行。"
```

Permitted placeholders: `PICK_PRE_LEAD`, `PROC_DURING_LEAD`, `PICK_POST_RECOVERY`, plus a structured (not free-text) per-day `pickers_needed[i] / processors_needed[i]` block (rendered as a deterministic table). No other numbers in the prose.

#### §3.4.11 Citation requirements

Same as §3.1.15. `spring_festival_calendar_policy_config_hash` is the citation hash for the phase field.

#### §3.4.12 Replay / hash surface

Same as §3.1.16. Rule catalog row for SPRING_FESTIVAL_STAFFING is `BUSINESS_SOURCE_REQUIRED` placeholder (Test C2-A-004).

#### §3.4.13 Required tests (this category)

| Test ID | Kind | Description | Acceptance |
|---|---|---|---|
| TEST-C2-004-01 | Unit | All CONF present, 30-day horizon with PRE=D1-D3, DURING=D4-D10, POST=D11-D20, NONE=D21-D30: emits APPLICABLE with per-day table and three lead-time values. | PASS |
| TEST-C2-004-02 | Unit | All CONF present, 30-day horizon all NONE: NOT_APPLICABLE / CONDITIONS_NOT_MET. | PASS |
| TEST-C2-004-03 | Unit | Missing CONF-040 → BLOCKED / REQUIRED_THRESHOLD_MISSING. | PASS |
| TEST-C2-004-04 | Unit | Calendar policy missing (upstream) → BLOCKED / UPSTREAM_BLOCKED with original blocker preserved. | PASS |
| TEST-C2-004-05 | Unit | `pickers_needed = 0` (PICK_PROD very high): rendered as `0`, not rounded up. | PASS |
| TEST-C2-004-06 | Golden | C1 preserved. | PASS |
| TEST-C2-004-07 | Integration (PostgreSQL) | Real chain produces stable hash with SPRING_FESTIVAL_STAFFING in BLOCKED. | PASS |

---

### §3.5 VARIETY_STAGGER

#### §3.5.1 Business purpose

Identify whether forecast peak formation includes a variety-overlap component, and surface a `REVIEW_VARIETY_STAGGERING_REQUIRED` advisory if so. This category is **review-only** in C2. It MUST NOT emit pruning dates, area adjustments, batch splits, yield impacts, or any agronomic execution instructions. The only allowed `APPLICABLE` output is the review flag plus the variety-overlap evidence citation. The category does not compute or recommend agronomic actions; agronomic recommendations are explicitly out of C2 scope (Issue #99 §"Category hard boundaries and C2 blockers — VARIETY_STAGGER").

#### §3.5.2 Allowed upstream fields

- `/daily_curve/{day_index}/per_variety_contribution` — per-day, per-variety `p50|p80|p90` and `contribution_rate_p50|p80|p90`.
- `/daily_curve/{day_index}/final_corrected_arrival_quantity_kg/{p50,p80,p90}` — total arrival.
- `ForecastDailyRow.per_variety_contribution` (resolved via `VarietyContribution` in `backend/app/agent/schemas.py`).

#### §3.5.3 RFC 6901 JSON Pointer examples

```text
/daily_curve/0/per_variety_contribution/0/variety_id
/daily_curve/0/per_variety_contribution/0/p50
/daily_curve/0/per_variety_contribution/0/contribution_rate_p50
/daily_curve/7/per_variety_contribution/1/variety_id
/daily_curve/7/per_variety_contribution/1/contribution_rate_p80
/daily_curve/14/per_variety_contribution/0/p50
```

#### §3.5.4 Field-level source authority

| Field | Authority type | Source ID | Source version | Source effective date | Source hash | Status |
|---|---|---|---|---|---|---|
| Per-variety daily contribution | `PERSISTED_UPSTREAM_MODEL_OUTPUT` (Slice B) | `forecast_daily_curve.run_id` | Slice B `daily_curve_policy_version` | Slice B `as_of` | Slice B `daily_curve_policy_config_hash` | `RESOLVED_BY_MERGED_AUTHORITY` |
| Selected quantile for overlap evaluation | `CHARLES_CONFIRMED_SOURCE` | `CONF-048` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Overlap window length (days) — e.g. 3 / 5 / 7 | `CHARLES_CONFIRMED_SOURCE` | `CONF-049` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Overlap trigger: minimum number of varieties sharing the window | `CHARLES_CONFIRMED_SOURCE` | `CONF-050` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Overlap trigger: minimum `contribution_rate` of a variety within the window | `CHARLES_CONFIRMED_SOURCE` | `CONF-051` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Action formula, action rounding | `N/A` (review-only) | — | — | — | — | `NOT_APPLICABLE` (Issue #99 §"VARIETY_STAGGER") |
| Risk codes (e.g. `VARIETY_OVERLAP_RISK`) | `CHARLES_CONFIRMED_SOURCE` | `CONF-052` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Advisory template (deterministic, single sentence) | `CHARLES_CONFIRMED_SOURCE` | `CONF-053` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |

#### §3.5.5 Applicability and granularity

- **Applicable grain (time)**: per rolling overlap window (size = CONF-049 days).
- **Applicable grain (space)**: per resolved location × per forecast season.
- **Output**: single boolean flag (overlap detected or not) plus a list of contributing variety_ids within the window, plus the chosen quantile. No agronomic numbers.

#### §3.5.6 Formula skeleton

```python
def variety_stagger_overlap_detected(
    daily_curve: list[ForecastDailyRow],
    selected_quantile: str,        # "P50" | "P80" | "P90"  [BUSINESS_SOURCE_REQUIRED — CONF-048]
    window_days: int,              # >= 1                   [BUSINESS_SOURCE_REQUIRED — CONF-049]
    min_varieties: int,            # >= 2                   [BUSINESS_SOURCE_REQUIRED — CONF-050]
    min_contribution_rate: Decimal,# in (0, 1)              [BUSINESS_SOURCE_REQUIRED — CONF-051]
) -> dict:
    # For each rolling window of size `window_days` in `daily_curve`:
    #   collect (variety_id, contribution_rate) pairs at `selected_quantile`
    #   if len(unique varieties) >= min_varieties AND every variety has contribution_rate >= min_contribution_rate:
    #     overlap = True
    #     contributing_varieties = sorted list of variety_ids (lexical ascending)
    #     break
    # else: overlap = False
    # return {"overlap_detected": overlap, "contributing_varieties": contributing_varieties, "quantile": selected_quantile}
    # if overlap:
    #   advisory_text = template CONF-053 substituted with contributing_varieties
    # else:
    #   advisory_text = null
    ...
```

#### §3.5.7 Threshold / boundary

- `window_days >= 1` (sanity).
- `min_varieties >= 2` (must have at least two varieties to talk about "stagger").
- `min_contribution_rate in (0, 1)` (excludes 0 and 1; a 0% variety is irrelevant; a 100% variety is not "staggered" but "sole").

#### §3.5.8 Null / missing semantics

| Missing input | Effect |
|---|---|
| `daily_curve` empty | `NOT_APPLICABLE` / `CONDITIONS_NOT_MET` |
| Any of CONF-048..CONF-053 missing | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` |
| `per_variety_contribution` empty for some day (no variety resolved) | skip that day; do not block |

#### §3.5.9 APPLICABLE / NOT_APPLICABLE / BLOCKED conditions

| Condition set | Status | Reason code | Advisory text | Non-action |
|---|---|---|---|---|
| All CONF-048..CONF-053 present + at least one rolling window with `overlap_detected = True` | `APPLICABLE` | `RULE_APPLICABLE` | Template CONF-053 with the contributing variety list and window dates substituted | `NO_AUTOMATIC_VARIETY_STAGGER_ACTION` + `ADVISORY_ONLY_NO_AUTOMATIC_EXECUTION` |
| All CONF present + no rolling window meets overlap trigger | `APPLICABLE` | `RULE_APPLICABLE` (with `overlap_detected = False`) OR `NOT_APPLICABLE` / `CONDITIONS_NOT_MET` (TBD by Charles: CONF-054) | `null` | same |
| All CONF present + season has only one variety | `NOT_APPLICABLE` | `CONDITIONS_NOT_MET` (no "stagger" to evaluate) | `null` | same |
| Any CONF-048..CONF-053 missing | `BLOCKED` | `REQUIRED_THRESHOLD_MISSING` | `null` | same |
| Upstream blocked | `BLOCKED` | `UPSTREAM_BLOCKED` | `null` | same |
| Citation hash mismatch | `BLOCKED` | `EVIDENCE_HASH_MISMATCH` | `null` | same |

#### §3.5.10 Reason code / risk codes / confidence

- `reason_code`: per §3.5.9.
- `risk_codes` (when `APPLICABLE` and `overlap_detected = True`): `VARIETY_OVERLAP_RISK` (from CONF-052).
- `confidence`: `HIGH` if Slice B `source_level = 1` or `2`; `MEDIUM` if `3`; `LOW` if `4` or `5`.

#### §3.5.11 Advisory template

Single sentence (CONF-053):

```
"在 <<WINDOW_START>> 至 <<WINDOW_END>> 期间, 品种 <<VARIETY_LIST>> 同时进入高峰, 建议人工评审错峰安排。此为建议, 不触发任何自动执行。"
```

Permitted placeholders: `WINDOW_START`, `WINDOW_END`, `VARIETY_LIST` (a deterministic comma-separated list, lexical ascending). No numbers other than dates. No agronomic recommendations. No `prune`, `harvest`, `thin`, `delay`, `advance` action language.

#### §3.5.12 Citation requirements

Each `per_variety_contribution` in the overlap window must have a Citation whose JSON Pointer resolves to the variety's `contribution_rate` at the chosen quantile, and whose `artifact_hash` matches. The Citation's `source_task` is `TASK_010` (Task 10 prediction run).

#### §3.5.13 Replay / hash surface

Same as §3.1.16. Rule catalog row for VARIETY_STAGGER is `BUSINESS_SOURCE_REQUIRED` placeholder (Test C2-A-005).

#### §3.5.14 Required tests (this category)

| Test ID | Kind | Description | Acceptance |
|---|---|---|---|
| TEST-C2-005-01 | Unit | 7-day curve with 2 varieties, both contributing >= 0.4 to each day: overlap_detected = True, contributing_varieties = sorted list. | PASS |
| TEST-C2-005-02 | Unit | 7-day curve with 1 variety only: NOT_APPLICABLE / CONDITIONS_NOT_MET. | PASS |
| TEST-C2-005-03 | Unit | Empty daily_curve: NOT_APPLICABLE / CONDITIONS_NOT_MET. | PASS |
| TEST-C2-005-04 | Unit | Missing CONF-049 → BLOCKED / REQUIRED_THRESHOLD_MISSING. | PASS |
| TEST-C2-005-05 | Unit | `min_contribution_rate = 1.0` (forbidden): REQUIRED_THRESHOLD_MISSING. | PASS |
| TEST-C2-005-06 | Unit | Advisory contains ONLY window dates, variety list, and the fixed template text. No agronomic instructions. | PASS |
| TEST-C2-005-07 | Golden | C1 preserved. | PASS |
| TEST-C2-005-08 | Integration (PostgreSQL) | Real chain produces stable hash with VARIETY_STAGGER in BLOCKED. | PASS |

---

### §3.6 CROSS_PLANT_DISPATCH

#### §3.6.1 Business purpose

Identify whether a plant's projected peak exceeds a Charles-confirmed current-capacity trigger, and surface a `REVIEW_CROSS_PLANT_DISPATCH_REQUIRED` advisory if so. This category is **review-only** in C2. It MUST NOT query, compare, rank, or select another factory; create quantities, vehicles, routes, or plans; or cross tenant/farm/permission boundaries. The only allowed `APPLICABLE` output is the review flag plus the current-capacity evidence citation. The category does not compute or recommend cross-plant actions; cross-plant actions are explicitly out of C2 scope (Issue #99 §"Category hard boundaries and C2 blockers — CROSS_PLANT_DISPATCH").

#### §3.6.2 Allowed upstream fields

- `/peak/single_day_peak/{P50,P80,P90}/volume_kg` — single-day peak volume.
- `/peak/peak_window_cumulative_quantity_kg/{P50,P80,P90}` — sustained three-day peak.
- `/peak/peak_window_days_before`, `/peak/peak_window_days_after` — peak-window config.

#### §3.6.3 RFC 6901 JSON Pointer examples

```text
/peak/single_day_peak/P80/volume_kg
/peak/single_day_peak/P90/volume_kg
/peak/peak_window_cumulative_quantity_kg/P80
/peak/peak_window_days_before
/peak/peak_window_days_after
```

#### §3.6.4 Field-level source authority

| Field | Authority type | Source ID | Source version | Source effective date | Source hash | Status |
|---|---|---|---|---|---|---|
| Peak volume values | `PERSISTED_UPSTREAM_MODEL_OUTPUT` (Slice B) | `forecast_peak.run_id` | Slice B `peak_metric_policy_version` | Slice B `as_of` | Slice B `peak_metric_policy_config_hash` | `RESOLVED_BY_MERGED_AUTHORITY` |
| Selected quantile for trigger comparison | `CHARLES_CONFIRMED_SOURCE` | `CONF-055` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Current factory capacity (kg/day, named by plant) | `APPROVED_AUDITABLE_SOURCE` | `CONF-056` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Capacity safety factor (fraction of current capacity considered "trigger") | `CHARLES_CONFIRMED_SOURCE` | `CONF-057` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Cross-plant radius, transport time, transport loss | `N/A` (review-only) | — | — | — | — | `NOT_APPLICABLE` (Issue #99 §"CROSS_PLANT_DISPATCH") |
| Receiving factory remaining capacity | `N/A` (review-only) | — | — | — | — | `NOT_APPLICABLE` (Issue #99 §"CROSS_PLANT_DISPATCH") |
| Dispatch priority | `N/A` (review-only) | — | — | — | — | `NOT_APPLICABLE` (Issue #99 §"CROSS_PLANT_DISPATCH") |
| Risk codes (e.g. `CURRENT_PLANT_OVERLOAD_RISK`) | `CHARLES_CONFIRMED_SOURCE` | `CONF-058` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Advisory template (deterministic, single sentence) | `CHARLES_CONFIRMED_SOURCE` | `CONF-059` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |

#### §3.6.5 Applicability and granularity

- **Applicable grain (time)**: per peak window.
- **Applicable grain (space)**: per resolved location × per plant.
- **Output**: single boolean flag (trigger met or not) plus the chosen quantile. No cross-plant numbers, no destination factory, no route, no quantity.

#### §3.6.6 Formula skeleton

```python
def cross_plant_dispatch_trigger(
    peak_volume: Decimal,            # kg/day at /peak/single_day_peak/<QUANTILE>/volume_kg
    current_capacity_kg_per_day: Decimal,  # [BUSINESS_SOURCE_REQUIRED — CONF-056]
    trigger_ratio: Decimal,           # in (0, 1]        [BUSINESS_SOURCE_REQUIRED — CONF-057]
) -> dict:
    if peak_volume <= 0 or current_capacity_kg_per_day <= 0:
        raise ValueError("REQUIRED_EVIDENCE_MISSING")
    if not (Decimal("0") < trigger_ratio <= Decimal("1")):
        raise ValueError("REQUIRED_THRESHOLD_MISSING")
    threshold = current_capacity_kg_per_day * trigger_ratio
    triggered = peak_volume > threshold
    return {
        "triggered": triggered,
        "threshold_kg_per_day": threshold,
        "peak_kg_per_day": peak_volume,
    }
```

#### §3.6.7 Threshold / boundary

- `trigger_ratio in (0, 1]`. A `trigger_ratio = 1.0` means "trigger when peak equals current capacity". A `trigger_ratio = 0.9` means "trigger when peak reaches 90% of current capacity". A `trigger_ratio <= 0` is forbidden (would always trigger).
- `current_capacity_kg_per_day > 0`. Zero capacity means "no current capacity at this plant", which is `OUTSIDE_AUTHORIZED_SCOPE` → `NOT_APPLICABLE`.

#### §3.6.8 Null / missing semantics

| Missing input | Effect |
|---|---|
| `peak_volume` not resolvable | `REQUIRED_EVIDENCE_MISSING` → `BLOCKED` |
| `current_capacity_kg_per_day` missing (CONF-056) | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` |
| `trigger_ratio` missing (CONF-057) | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` |
| Selected quantile (CONF-055) not confirmed | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` |
| `current_capacity_kg_per_day = 0` | `NOT_APPLICABLE` / `OUTSIDE_AUTHORIZED_SCOPE` |
| `peak_volume = 0` | `NOT_APPLICABLE` / `CONDITIONS_NOT_MET` (no peak to dispatch) |

#### §3.6.9 APPLICABLE / NOT_APPLICABLE / BLOCKED conditions

| Condition set | Status | Reason code | Advisory text | Non-action |
|---|---|---|---|---|
| All CONF-055..CONF-059 present + `triggered = True` | `APPLICABLE` | `RULE_APPLICABLE` | Template CONF-059 with peak and current capacity substituted | `NO_AUTOMATIC_CROSS_PLANT_DISPATCH` + `ADVISORY_ONLY_NO_AUTOMATIC_EXECUTION` |
| All CONF present + `triggered = False` | `NOT_APPLICABLE` (TBD by Charles: CONF-060) | `CONDITIONS_NOT_MET` (TBD) | `null` | same |
| All CONF present + `current_capacity = 0` | `NOT_APPLICABLE` | `OUTSIDE_AUTHORIZED_SCOPE` | `null` | same |
| Any CONF-055..CONF-059 missing | `BLOCKED` | `REQUIRED_THRESHOLD_MISSING` | `null` | same |
| Citation hash mismatch | `BLOCKED` | `EVIDENCE_HASH_MISMATCH` | `null` | same |
| Upstream blocked | `BLOCKED` | `UPSTREAM_BLOCKED` | `null` | same |

#### §3.6.10 Reason code / risk codes / confidence

- `reason_code`: per §3.6.9.
- `risk_codes` (when `APPLICABLE`): subset of CONF-058.
- `confidence`: derived from `current_capacity_kg_per_day` source provenance and Slice B confidence.

#### §3.6.11 Advisory template

Single sentence (CONF-059):

```
"按 <<QUANTILE_CHOSEN>> 单日峰值 <<PEAK_KG>> 公斤/天 超出本厂当前产能触发值 <<TRIGGER_KG>> 公斤/天, 建议人工评审跨厂分流必要性。此为建议, 不触发任何自动执行。"
```

Permitted placeholders: `QUANTILE_CHOSEN`, `PEAK_KG`, `TRIGGER_KG`. No destination factory, no route, no transport time, no loss percentage, no quantity dispatched.

#### §3.6.12 Citation requirements

`peak_volume` Citation `source_task = TASK_010`. `current_capacity_kg_per_day` Citation must include `source_id = CONF-056`, `source_version`, `source_effective_date`, `source_hash` once Charles provides them.

#### §3.6.13 Replay / hash surface

Same as §3.1.16. Rule catalog row for CROSS_PLANT_DISPATCH is `BUSINESS_SOURCE_REQUIRED` placeholder (Test C2-A-006).

#### §3.6.14 Required tests (this category)

| Test ID | Kind | Description | Acceptance |
|---|---|---|---|
| TEST-C2-006-01 | Unit | peak = 100000, current_capacity = 120000, trigger_ratio = 0.9 → threshold = 108000, triggered = False (100000 < 108000), NOT_APPLICABLE (TBD by CONF-060). | PASS |
| TEST-C2-006-02 | Unit | peak = 100000, current_capacity = 100000, trigger_ratio = 0.9 → threshold = 90000, triggered = True, APPLICABLE. | PASS |
| TEST-C2-006-03 | Unit | current_capacity = 0 → NOT_APPLICABLE / OUTSIDE_AUTHORIZED_SCOPE. | PASS |
| TEST-C2-006-04 | Unit | trigger_ratio = 1.1 (forbidden) → REQUIRED_THRESHOLD_MISSING. | PASS |
| TEST-C2-006-05 | Unit | Advisory contains ONLY peak, threshold, and the fixed template text. No destination factory, no route, no transport. | PASS |
| TEST-C2-006-06 | Golden | C1 preserved. | PASS |
| TEST-C2-006-07 | Integration (PostgreSQL) | Real chain produces stable hash with CROSS_PLANT_DISPATCH in BLOCKED. | PASS |

---

## §4 Forbidden-to-assume critical parameters

This section enumerates every critical business parameter that has been named in the codebase or spec but for which **no Charles source has been provided**. Each row is `BUSINESS_SOURCE_REQUIRED` and blocks C2 activation of the corresponding category. Filling any of these with a "reasonable default" is a hard rule violation.

| # | Parameter | Current code presence | Required source | Blocks C2 category | Linked CONF ID |
|---:|---|---|---|---|---|
| 1 | Daily sustained processing capacity (kg/day) | NOT in code; only "peak volume" Slice B output | Production standard or Charles | SUSTAINED_PROCESSING_CAPACITY | CONF-001..CONF-007 |
| 2 | Single-day receiving peak capacity (kg/day) | NOT in code | Production standard or Charles | RECEIVING_PEAK_CAPACITY | CONF-012 |
| 3 | Design capacity vs actual safety-adjusted capacity reduction factor | NOT in code | Production standard | SUSTAINED_PROCESSING_CAPACITY, RECEIVING_PEAK_CAPACITY | CONF-004, CONF-018 |
| 4 | Shift duration (hours per shift) | NOT in code (only `PeakMetricPolicy.sustained_window_days = 3` for window, not shift) | Production standard | SHIFT_STAFFING | CONF-025 |
| 5 | Effective working hours per shift (excluding breaks) | NOT in code | Production standard | SHIFT_STAFFING | (extension of CONF-025) |
| 6 | Staff attendance rate (fraction) | NOT in code; only `staffing_override_value` as user input (not a default) | Production standard | SHIFT_STAFFING | CONF-027 |
| 7 | Per-role productivity (picker, sorter, packer, processor) | NOT in code; only `parameter_name`-keyed generic parameters | Production standard | SHIFT_STAFFING, SPRING_FESTIVAL_STAFFING | CONF-026, CONF-028, CONF-038, CONF-039 |
| 8 | Peak-period personnel buffer (fraction) | NOT in code | Charles | SHIFT_STAFFING | CONF-029 |
| 9 | Spring Festival per-phase picker/processor availability factor | NOT in code; only `spring_festival_phase` enum (NONE/PRE/DURING/POST) is a calendar tag | Charles | SPRING_FESTIVAL_STAFFING | CONF-036, CONF-037, CONF-043 |
| 10 | Receiving dock turnover time (hours) | NOT in code | Production standard | RECEIVING_PEAK_CAPACITY | CONF-015 |
| 11 | Daily receiving operating hours | NOT in code | Production standard | RECEIVING_PEAK_CAPACITY | CONF-014 |
| 12 | Temporary storage physical capacity (kg) | NOT in code | Production standard | RECEIVING_PEAK_CAPACITY | CONF-016 |
| 13 | Pre-cooling capacity (kg/day or kg/hour) | NOT in code | Production standard | RECEIVING_PEAK_CAPACITY | CONF-017 |
| 14 | Variety stagger overlap window length, min variety count, min contribution rate | NOT in code | Charles | VARIETY_STAGGER | CONF-049, CONF-050, CONF-051 |
| 15 | Cross-variety maturity offset days (e.g. Dx vs D12 shift) | NOT in code; only `per_variety_contribution.p50/p80/p90` is a quantity, not an offset | Charles | (VARIETY_STAGGER review-only; not consumed) | n/a (not a C2 input) |
| 16 | Cross-plant dispatch radius (km) | NOT in code | Production standard | (CROSS_PLANT_DISPATCH review-only; not consumed) | n/a (not a C2 input) |
| 17 | Cross-plant transport time (hours) | NOT in code | Production standard | (not consumed) | n/a (not a C2 input) |
| 18 | Cross-plant transport loss (fraction) | NOT in code | Production standard | (not consumed) | n/a (not a C2 input) |
| 19 | Receiving factory remaining capacity (kg/day) | NOT in code | Production standard | (not consumed) | n/a (not a C2 input) |
| 20 | Sending factory trigger threshold (fraction of current capacity) | NOT in code | Charles | CROSS_PLANT_DISPATCH | CONF-057 |
| 21 | Business rounding mode (e.g. ROUND_CEIL for headcount) | NOT in code; `decimal.quantize` is used only for Pydantic display | Charles | All 6 categories | CONF-007, CONF-021, CONF-032, CONF-045 |
| 22 | Business rounding precision (decimal digits) | NOT in code | Charles | All 6 categories | CONF-006, CONF-020, CONF-031, CONF-044 |
| 23 | Advisory template wording and version | NOT in code | Charles | All 6 categories | CONF-010, CONF-023, CONF-034, CONF-047, CONF-053, CONF-059 |
| 24 | Risk code vocabulary and trigger thresholds | NOT in code | Charles | All 6 categories | CONF-009, CONF-022, CONF-033, CONF-046, CONF-052, CONF-058 |
| 25 | Confidence downgrade rule | NOT in code (Slice B `confidence` is upstream only) | Charles | All 6 categories | CONF-008 |
| 26 | Whether `VARIETY_STAGGER` `APPLICABLE` with `overlap_detected = False` should emit `APPLICABLE` (advisory_text = null) or `NOT_APPLICABLE` | NOT in code; design leaves open | Charles | VARIETY_STAGGER | CONF-054 |
| 27 | Whether `CROSS_PLANT_DISPATCH` `APPLICABLE` with `triggered = False` should emit `APPLICABLE` (advisory_text = null) or `NOT_APPLICABLE` | NOT in code; design leaves open | Charles | CROSS_PLANT_DISPATCH | CONF-060 |

**All 27 rows are `BUSINESS_SOURCE_REQUIRED`. No row may be filled with a heuristic, default, or industry average.**

### §4.1 Anti-default policy

- "Reasonable default" is **forbidden** in C2 source definition.
- "Industry average" is **forbidden** in C2 source definition.
- "Rule of thumb" is **forbidden** in C2 source definition.
- "Web-sourced typical value" is **forbidden** in C2 source definition.
- "LLM-inferred value" is **forbidden** in C2 source definition.
- "Inferred from current output" is **forbidden** in C2 source definition.
- "Inferred from history" is **forbidden** in C2 source definition unless that history is a persisted, integrity-validated upstream model output cited via `Citation` (rank 3 in §2.1).

Any of the above in a rule catalog row produces `POLICY_UNAVAILABLE` at runtime and a `RECOMMENDATION_RULE_MISSING` blocker for that category.

---

## §5 Formula contract

### §5.1 Machine-executable form requirement

Every formula in §3 MUST be expressible in the form:

```
output := f(input_1: T1, input_2: T2, ..., input_n: Tn) -> T_out
```

where:
- `Ti` is a type drawn from `{Decimal, Int, Str, Enum, Bool, Date, DecimalString, RFC6901JsonPointer}`.
- `T_out` is `Decimal` for numeric outputs, `Bool` for trigger flags, or `List[Str]` / `List[Decimal]` for structured outputs.
- `f` is a deterministic function with no I/O, no randomness, no `now()`, no `uuid()`, no LLM call.

### §5.2 Input variable and unit contract

| Variable | Type | Unit (input) | Required citation | Allowed sources |
|---|---|---|---|---|
| Peak window cumulative volume | DecimalString | kg | Yes | `/peak/peak_window_cumulative_quantity_kg/{P50,P80,P90}` |
| Single-day peak volume | DecimalString | kg | Yes | `/peak/single_day_peak/{P50,P80,P90}/volume_kg` |
| Daily arrival quantiles | DecimalString | kg | Yes | `/daily_curve/{i}/final_corrected_arrival_quantity_kg/{p50,p80,p90}` |
| Spring Festival phase | Str (enum) | — | Yes | `/daily_curve/{i}/spring_festival_phase` |
| Per-variety contribution rate | DecimalString | fraction [0, 1] | Yes | `/daily_curve/{i}/per_variety_contribution/{j}/contribution_rate_{p50,p80,p90}` |
| Productivity per person | DecimalString | kg/person/hour | Yes (if persisted parameter) or `CONF-026/CONF-038/CONF-039` (if not) | `ParameterEstimate` or Charles |
| Attendance rate | DecimalString | fraction (0, 1] | Yes | `CONF-027` |
| Shift duration | DecimalString | hours | Yes | `CONF-025` |
| Personnel buffer | DecimalString | fraction [0, 1) | Yes | `CONF-029` |
| Number of shifts | Int | {1, 2, 3} | Yes | `CONF-030` |
| Picker/processor availability | DecimalString | fraction (0, 1] | Yes | `CONF-036/CONF-037` (or persisted parameter) |
| Receiving hours per day | Int | hours | Yes | `CONF-014` |
| Turnover time | DecimalString | hours | Yes | `CONF-015` |
| Storage capacity | DecimalString | kg | Yes | `CONF-016` |
| Pre-cooling capacity | DecimalString | kg/hour | Yes | `CONF-017` |
| Safety factor | DecimalString | fraction (0, 1] | Yes | `CONF-004/CONF-018/CONF-057` |
| Trigger ratio | DecimalString | fraction (0, 1] | Yes | `CONF-057` |
| Overlap window length | Int | days | Yes | `CONF-049` |
| Min varieties | Int | >= 2 | Yes | `CONF-050` |
| Min contribution rate | DecimalString | fraction (0, 1) | Yes | `CONF-051` |
| Current capacity (kg/day) | DecimalString | kg/day | Yes | `CONF-056` |

### §5.3 Output unit and dimension consistency

- All output values carrying a unit MUST be expressed in a unit selected from §5.2's column "Unit (input)" or a unit derived by simple scalar conversion (e.g. kg → t, kg/day → kg/hour, hours/day → hours).
- A formula whose output unit does not match the declared output unit produces `EVIDENCE_HASH_MISMATCH` (i.e. dimension error) → `BLOCKED`.
- The dimension check is unit-testable: for each formula, a test asserts the output unit for one valid input. The assertion is symbolic (the test fixture names the expected unit string), not numeric.

### §5.4 Missing input handling

- If a required input is `null` or its JSON Pointer does not resolve, the formula raises `ValueError("REQUIRED_EVIDENCE_MISSING")`.
- The recommendation stage maps this to `RecommendationDecision.status = BLOCKED, reason_code = REQUIRED_EVIDENCE_MISSING`.
- The category's `blocker_dependencies` includes one `Blocker(code=REQUIRED_CITATION_MISSING)` per unresolved input.

### §5.5 Zero handling

- A zero input is allowed for any positive-type variable except the safety factor, the attendance rate, the productivity, and the current capacity. A zero productivity, attendance rate, or current capacity is a configuration error and produces `REQUIRED_THRESHOLD_MISSING` → `BLOCKED`.
- A zero input on a quantity produces a zero output (no special handling; rounding mode applies as usual; `Decimal("0")` does not need to be rounded).

### §5.6 Negative prohibition

- A negative input on any positive-type variable is a config error or upstream error. It is NOT mapped to `NOT_APPLICABLE`. It is mapped to `EVIDENCE_HASH_MISMATCH` (or `UPSTREAM_BLOCKED` if the upstream source has an integrity gap).
- The formula MUST raise `ValueError("EVIDENCE_HASH_MISMATCH")` on a negative input.

### §5.7 Time range contract

- All formulas operate on the per-request forecast horizon (as supplied by Slice B). The horizon is NOT a C2 input. The category only iterates over the days in the horizon that satisfy the category's preconditions (e.g. Spring Festival phase ∈ {PRE, DURING, POST} for SPRING_FESTIVAL_STAFFING).
- A formula that depends on a future date beyond the horizon (e.g. a "next year's variety stagger") is `OUTSIDE_AUTHORIZED_SCOPE` → `NOT_APPLICABLE`.

### §5.8 Quantile usage rules

- A single formula MUST NOT mix quantiles across its input set unless explicitly designed to. Example: a formula that takes `peak = P80` MUST NOT internally use `arrival = P50` and then label the output as "P80-based". The label MUST match the input quantile.
- Cross-quantile mixing is allowed only in compound expressions where every intermediate quantity is itself quantile-pinned (e.g. "P80 peak minus P50 floor"). Such an expression is an explicit Charles confirmation (CONF-061, not yet raised).
- `P50 / P80 / P90` selection itself is a Charles confirmation (CONF-001 / CONF-012 / CONF-055) for the operational category.

### §5.9 Rounding order

- For a formula with multiple intermediate quantities, the rounding order is: (1) convert to canonical `Decimal`; (2) compute raw value at full precision; (3) apply unit conversion at full precision; (4) apply the final `quantize` with the chosen `ROUND_MODE` and `PRECISION` ONCE on the final value. Intermediate quantities are NOT rounded.
- This rule prevents the "double rounding" error where two sequential `quantize` calls produce a different result than a single `quantize` on the final value.

### §5.10 Canonical serialization

- All numeric values are stored and emitted as `DecimalString` (per `backend/app/agent/schemas.py::DecimalString`). No `float` is permitted in production code paths (C1 contract per PR #100).
- All string values use deterministic, deterministic-character-set encoding (UTF-8, NFC-normalized).
- All enum-like values are emitted as the `Enum.value` string, not the `Enum.name`.
- All Citation JSON is canonicalized per `backend/app/agent/schemas.py::Citation` (stable field order, no extra keys).
- The hash surface excludes runtime timestamps, database-generated IDs, hosts, paths, environment-specific values, unordered sets, and nondeterministically ordered mappings. Source: Issue #99 §"Policy schemas, identifiers, and canonical hashes".

### §5.11 Forbidden operations

- `float(...)` on any production code path.
- `math.ceil`, `math.floor`, `round(...)` on any production code path. Use `Decimal.quantize(...)` with the chosen `ROUND_MODE`.
- `random.*` in any production code path.
- `datetime.now()`, `time.time()`, `uuid.uuid4()` in any production code path.
- `requests.*`, `httpx.*`, `urllib.*` from production code paths.
- `openai.*`, `anthropic.*`, `langchain.*`, or any LLM SDK import.

---

## §6 Decision table per category

The decision table below summarizes the runtime state for every C2 condition. The table is exhaustive; any condition not listed is `POLICY_UNAVAILABLE` → `BLOCKED` until a new Charles confirmation is added.

### §6.1 SUSTAINED_PROCESSING_CAPACITY

| Condition | Status | Reason code | Advisory text | Non-action |
|---|---|---|---|---|
| All CONF-001..CONF-010 present + Q_in resolvable + WINDOW_DAYS == 3 | `APPLICABLE` | `RULE_APPLICABLE` | Template CONF-010 with capacity substituted | `NO_AUTOMATIC_PROCESSING_CAPACITY_CHANGE` + universal |
| All CONF present + WINDOW_DAYS != 3 | `NOT_APPLICABLE` | `OUTSIDE_AUTHORIZED_SCOPE` | `null` | same |
| Any CONF-001..CONF-010 missing | `BLOCKED` | `REQUIRED_THRESHOLD_MISSING` | `null` | same |
| Q_in null / pointer not resolvable | `BLOCKED` | `REQUIRED_EVIDENCE_MISSING` | `null` | same |
| Citation artifact_hash mismatch | `BLOCKED` | `EVIDENCE_HASH_MISMATCH` | `null` | same |
| Pointer escape / alias / case normalization / fuzzy | `BLOCKED` | `EVIDENCE_FIELD_PATH_INVALID` | `null` | same |
| Slice B blocked (e.g. `INSUFFICIENT_HISTORY`, `PEAK_POLICY_MISSING`) | `BLOCKED` | `UPSTREAM_BLOCKED` | `null` | same (preserve original blocker verbatim) |
| `RecommendationRulePolicy` or `rule_catalog` not loaded | `BLOCKED` | `POLICY_UNAVAILABLE` | `null` | same |

### §6.2 RECEIVING_PEAK_CAPACITY

| Condition | Status | Reason code | Advisory text | Non-action |
|---|---|---|---|---|
| All CONF-012..CONF-023 present + PEAK_Q resolvable | `APPLICABLE` | `RULE_APPLICABLE` | Template CONF-023 with three values substituted | `NO_AUTOMATIC_RECEIVING_CAPACITY_CHANGE` + universal |
| All CONF present + plant is not a receiving plant (CONF-024) | `NOT_APPLICABLE` | `OUTSIDE_AUTHORIZED_SCOPE` | `null` | same |
| Any CONF-012..CONF-023 missing | `BLOCKED` | `REQUIRED_THRESHOLD_MISSING` | `null` | same |
| PEAK_Q null | `BLOCKED` | `REQUIRED_EVIDENCE_MISSING` | `null` | same |
| Citation hash mismatch | `BLOCKED` | `EVIDENCE_HASH_MISMATCH` | `null` | same |
| Upstream blocked | `BLOCKED` | `UPSTREAM_BLOCKED` | `null` | same |
| Policy / catalog missing | `BLOCKED` | `POLICY_UNAVAILABLE` | `null` | same |

### §6.3 SHIFT_STAFFING

| Condition | Status | Reason code | Advisory text | Non-action |
|---|---|---|---|---|
| All CONF-001 + CONF-025..CONF-034 present + TARGET_KG resolvable + PROD_KGPH from parameter or CONF-026 | `APPLICABLE` | `RULE_APPLICABLE` | Template CONF-034 with shift count and headcount substituted | `NO_AUTOMATIC_SHIFT_STAFFING_ACTION` + universal |
| All CONF present + plant has no shift operation (CONF-035) | `NOT_APPLICABLE` | `OUTSIDE_AUTHORIZED_SCOPE` | `null` | same |
| Any CONF-025..CONF-034 missing | `BLOCKED` | `REQUIRED_THRESHOLD_MISSING` | `null` | same |
| PROD_KGPH not persisted AND no CONF-026 | `BLOCKED` | `REQUIRED_EVIDENCE_MISSING` + `REQUIRED_THRESHOLD_MISSING` | `null` | same |
| Upstream blocked | `BLOCKED` | `UPSTREAM_BLOCKED` | `null` | same |

### §6.4 SPRING_FESTIVAL_STAFFING

| Condition | Status | Reason code | Advisory text | Non-action |
|---|---|---|---|---|
| All CONF-036..CONF-047 present + at least one day with phase ∈ {PRE, DURING, POST} | `APPLICABLE` | `RULE_APPLICABLE` | Template CONF-047 with per-phase lead-times and per-day headcounts substituted | `NO_AUTOMATIC_SPRING_FESTIVAL_STAFFING_ACTION` + universal |
| All CONF present + no day in horizon has Spring Festival phase | `NOT_APPLICABLE` | `CONDITIONS_NOT_MET` | `null` | same |
| All CONF present + at least one phase value outside {NONE, PRE, DURING, POST} | `NOT_APPLICABLE` | `OUTSIDE_AUTHORIZED_SCOPE` | `null` | same |
| Any CONF-036..CONF-047 missing | `BLOCKED` | `REQUIRED_THRESHOLD_MISSING` | `null` | same |
| Calendar policy missing | `BLOCKED` | `UPSTREAM_BLOCKED` (preserve `SPRING_FESTIVAL_CALENDAR_POLICY_MISSING`) | `null` | same |
| Citation hash mismatch | `BLOCKED` | `EVIDENCE_HASH_MISMATCH` | `null` | same |

### §6.5 VARIETY_STAGGER

| Condition | Status | Reason code | Advisory text | Non-action |
|---|---|---|---|---|
| All CONF-048..CONF-053 present + at least one rolling window meets overlap trigger | `APPLICABLE` | `RULE_APPLICABLE` | Template CONF-053 with contributing variety list and window dates substituted | `NO_AUTOMATIC_VARIETY_STAGGER_ACTION` + universal |
| All CONF present + no rolling window meets overlap trigger (TBD by CONF-054) | `APPLICABLE` (advisory_text=null) OR `NOT_APPLICABLE` (TBD) | `RULE_APPLICABLE` OR `CONDITIONS_NOT_MET` (TBD) | `null` or `null` | same |
| All CONF present + season has only one variety | `NOT_APPLICABLE` | `CONDITIONS_NOT_MET` | `null` | same |
| Any CONF-048..CONF-053 missing | `BLOCKED` | `REQUIRED_THRESHOLD_MISSING` | `null` | same |
| Upstream blocked | `BLOCKED` | `UPSTREAM_BLOCKED` | `null` | same |
| Citation hash mismatch | `BLOCKED` | `EVIDENCE_HASH_MISMATCH` | `null` | same |

### §6.6 CROSS_PLANT_DISPATCH

| Condition | Status | Reason code | Advisory text | Non-action |
|---|---|---|---|---|
| All CONF-055..CONF-059 present + `triggered = True` | `APPLICABLE` | `RULE_APPLICABLE` | Template CONF-059 with peak and threshold substituted | `NO_AUTOMATIC_CROSS_PLANT_DISPATCH` + universal |
| All CONF present + `triggered = False` (TBD by CONF-060) | `APPLICABLE` (advisory_text=null) OR `NOT_APPLICABLE` (TBD) | `RULE_APPLICABLE` OR `CONDITIONS_NOT_MET` (TBD) | `null` or `null` | same |
| All CONF present + current_capacity = 0 | `NOT_APPLICABLE` | `OUTSIDE_AUTHORIZED_SCOPE` | `null` | same |
| Any CONF-055..CONF-059 missing | `BLOCKED` | `REQUIRED_THRESHOLD_MISSING` | `null` | same |
| Citation hash mismatch | `BLOCKED` | `EVIDENCE_HASH_MISMATCH` | `null` | same |
| Upstream blocked | `BLOCKED` | `UPSTREAM_BLOCKED` | `null` | same |

### §6.7 Common universal conditions (all categories)

| Condition | Status | Reason code | Advisory text | Non-action |
|---|---|---|---|---|
| Category outside Issue #99 authorized scope (e.g. an 8th category sneaked in) | `NOT_APPLICABLE` | `OUTSIDE_AUTHORIZED_SCOPE` | `null` | universal |
| `RecommendationRulePolicy.policy_version != "recommendation-rule-policy-v1"` | `BLOCKED` | `POLICY_UNAVAILABLE` | `null` | universal |
| `rule_catalog_version != "recommendation-rule-catalog-v1"` | `BLOCKED` | `POLICY_UNAVAILABLE` | `null` | universal |
| `rule_catalog_hash` does not match the persisted, frozen catalog | `BLOCKED` | `POLICY_UNAVAILABLE` | `null` | universal |
| Citation missing entirely from a required evidence field | `BLOCKED` | `REQUIRED_CITATION_MISSING` | `null` | universal |
| Authority envelope missing from a Citation | `BLOCKED` | `REQUIRED_AUTHORITY_MISSING` | `null` | universal |
| Provenance fields missing from a Citation | `BLOCKED` | `REQUIRED_PROVENANCE_MISSING` | `null` | universal |

---

## §7 Charles confirmation matrix

This matrix enumerates every Charles confirmation item the C2 implementation depends on. Each item is a **closed, directly-answerable question**. A wide question like "please provide the business rules" is forbidden; each row below can be answered with a value, a citation, or a "decline / out of scope" answer.

### §7.1 Master matrix

| CONF ID | Category | Candidate parameter | Candidate value (placeholder) | Candidate unit | Candidate data source | What Charles must provide or confirm | System behavior if not confirmed | Linked §3 section |
|---|---|---|---|---|---|---|---|---|
| CONF-EX-001 | Cross-cutting | Prototype label → production category mapping (CAPACITY-001 → ?; etc.) | TBD | n/a | Issue #99 amendment `4967834240` + prototype branch | The mapping from each of the 6 prototype capability blocks to one or more of the 7 `RecommendationCategory` values (or "no mapping, exploratory only") | `POLICY_UNAVAILABLE` if C2 references any prototype label | §1.4 |
| CONF-001 | SUSTAINED_PROCESSING_CAPACITY | Selected quantile (P50 / P80 / P90) for capacity basis | TBD | n/a | Charles | Which of `P50 / P80 / P90` to use for the capacity basis | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` | §3.1 |
| CONF-002 | SUSTAINED_PROCESSING_CAPACITY | `sustained_window_days` (currently hard-coded `3`) | `3` (proposed) | days | `PeakMetricPolicy.strict_three_day_window` | Confirm that the C2 capacity basis must equal the existing three-day window. If "no", provide a different window length and the production standard reference. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` (or `OUTSIDE_AUTHORIZED_SCOPE` → `NOT_APPLICABLE` if Charles picks a non-3 window) | §3.1 |
| CONF-003 | SUSTAINED_PROCESSING_CAPACITY | Single-day vs sustained-three-day basis | TBD | n/a | Charles | Whether the capacity value is the single-day equivalent or the three-day rolling average (and which one is reported in the advisory). | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` | §3.1 |
| CONF-004 | SUSTAINED_PROCESSING_CAPACITY | Safety factor | TBD | fraction (0, 1] | Production standard | A specific safety factor (e.g. 0.85) with source ID, version, effective date, and hash. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` | §3.1 |
| CONF-005 | SUSTAINED_PROCESSING_CAPACITY | Output unit | TBD | "kg/day" \| "t/day" | Charles | Whether the capacity value is reported in `kg/day` or `t/day`. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` | §3.1 |
| CONF-006 | SUSTAINED_PROCESSING_CAPACITY | Decimal precision | TBD | int >= 0 | Charles | Number of digits after the decimal point in the advisory. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` | §3.1 |
| CONF-007 | SUSTAINED_PROCESSING_CAPACITY | Rounding mode | TBD | "ROUND_HALF_UP" \| "ROUND_HALF_EVEN" \| "ROUND_FLOOR" \| "ROUND_CEIL" | Charles | The rounding mode for the final capacity value. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` | §3.1 |
| CONF-008 | SUSTAINED_PROCESSING_CAPACITY | Confidence downgrade rule | TBD | mapping | Charles | How to map Slice B `confidence` and `source_level` to the category's `confidence`. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` (or default `HIGH` if Charles confirms "no downgrade") | §3.1 |
| CONF-009 | SUSTAINED_PROCESSING_CAPACITY | Risk code vocabulary | TBD | enum list | Charles | A closed list of risk codes this category may emit, with their trigger conditions. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` (or empty list if Charles confirms "no risk codes") | §3.1 |
| CONF-010 | SUSTAINED_PROCESSING_CAPACITY | Advisory template | TBD | template_id | Charles | The deterministic, versioned advisory template text and the list of permitted placeholders. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` (or `advisory_text = null` if Charles confirms "no advisory text for this category") | §3.1 |
| CONF-011 | Cross-cutting | Cross-plant capacity reporting grain | TBD | "per_plant" \| "per_region" \| "global" | Charles | Whether each capacity value is per plant, per region, or global. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` | §3.1, §3.2, §3.3 |
| CONF-012 | RECEIVING_PEAK_CAPACITY | Selected quantile for peak basis | TBD | "P50" \| "P80" \| "P90" | Charles | Which quantile of the single-day peak to use. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` | §3.2 |
| CONF-013 | RECEIVING_PEAK_CAPACITY | Instantaneous receiving capacity conversion | TBD | formula or constant | Charles or production standard | The conversion from kg/day to kg/hour (typically `RECV_HOURS`; see CONF-014). | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` | §3.2 |
| CONF-014 | RECEIVING_PEAK_CAPACITY | Daily receiving operating hours | TBD | hours/day | Production standard | A specific number of hours (e.g. 10) with source ID, version, effective date, and hash. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` | §3.2 |
| CONF-015 | RECEIVING_PEAK_CAPACITY | Turnover time at receiving dock | TBD | hours | Production standard | A specific number (e.g. 2) with source ID, version, effective date, and hash. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` | §3.2 |
| CONF-016 | RECEIVING_PEAK_CAPACITY | Temporary storage physical capacity | TBD | kg | Production standard | A specific kg value per plant with source ID, version, effective date, and hash. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` | §3.2 |
| CONF-017 | RECEIVING_PEAK_CAPACITY | Pre-cooling capacity | TBD | kg/hour | Production standard | A specific kg/hour value per plant with source ID, version, effective date, and hash. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` | §3.2 |
| CONF-018 | RECEIVING_PEAK_CAPACITY | Receiving safety factor | TBD | fraction (0, 1] | Charles | A specific safety factor with source ID, version, effective date, and hash. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` | §3.2 |
| CONF-019 | RECEIVING_PEAK_CAPACITY | Output unit | TBD | "kg/hour" \| "kg" | Charles | Unit for instantaneous receiving; "kg" for storage; etc. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` | §3.2 |
| CONF-020 | RECEIVING_PEAK_CAPACITY | Decimal precision | TBD | int >= 0 | Charles | Number of digits after the decimal point. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` | §3.2 |
| CONF-021 | RECEIVING_PEAK_CAPACITY | Rounding mode | TBD | per §5.9 | Charles | Rounding mode for the three capacity values. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` | §3.2 |
| CONF-022 | RECEIVING_PEAK_CAPACITY | Risk code vocabulary | TBD | enum list | Charles | A closed list of risk codes with their trigger conditions. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` (or empty) | §3.2 |
| CONF-023 | RECEIVING_PEAK_CAPACITY | Advisory template | TBD | template_id | Charles | The deterministic advisory template and permitted placeholders. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` (or `null`) | §3.2 |
| CONF-024 | RECEIVING_PEAK_CAPACITY | Per-plant `OUTSIDE_AUTHORIZED_SCOPE` list | TBD | list of plant_id | Charles | A list of plants where the receiving capacity category should emit `NOT_APPLICABLE` instead of evaluating. | `RULE_APPLICABLE` (default; no list = no exceptions) | §3.2 |
| CONF-025 | SHIFT_STAFFING | Shift duration | TBD | hours | Production standard | A specific number (e.g. 8) with source ID, version, effective date, and hash. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` | §3.3 |
| CONF-026 | SHIFT_STAFFING | Productivity per person per hour | TBD | kg/person/hour | Production standard (or persisted parameter) | A specific value or the persisted `ParameterEstimate.parameter_id`. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` | §3.3 |
| CONF-027 | SHIFT_STAFFING | Attendance rate | TBD | fraction (0, 1] | Production standard | A specific fraction (e.g. 0.9) with source ID, version, effective date, and hash. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` | §3.3 |
| CONF-028 | SHIFT_STAFFING | Productivity by role | TBD | dict[role, kg/person/hour] | Production standard | A per-role map (e.g. {"picker": 50, "sorter": 80, "packer": 100}) with source ID, version, effective date, and hash. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` | §3.3 |
| CONF-029 | SHIFT_STAFFING | Peak personnel buffer | TBD | fraction [0, 1) | Charles | A specific fraction (e.g. 0.1) representing extra headcount during the peak window. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` (or 0 if Charles confirms "no buffer") | §3.3 |
| CONF-030 | SHIFT_STAFFING | Number of shifts per day | TBD | {1, 2, 3} | Charles | A specific count or a dynamic rule. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` | §3.3 |
| CONF-031 | SHIFT_STAFFING | Decimal precision | TBD | int >= 0 | Charles | Number of digits after the decimal point for the un-rounded raw value. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` | §3.3 |
| CONF-032 | SHIFT_STAFFING | Rounding mode | TBD | per §5.9 | Charles | Rounding mode for headcount (recommended: `ROUND_CEIL` to avoid under-staffing). | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` | §3.3 |
| CONF-033 | SHIFT_STAFFING | Risk code vocabulary | TBD | enum list | Charles | A closed list of risk codes. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` (or empty) | §3.3 |
| CONF-034 | SHIFT_STAFFING | Advisory template | TBD | template_id | Charles | The deterministic advisory template and permitted placeholders. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` (or `null`) | §3.3 |
| CONF-035 | SHIFT_STAFFING | Per-plant `OUTSIDE_AUTHORIZED_SCOPE` list | TBD | list of plant_id | Charles | Plants where shift staffing should emit `NOT_APPLICABLE` (e.g. plants with no shift operation). | `RULE_APPLICABLE` (default) | §3.3 |
| CONF-036 | SPRING_FESTIVAL_STAFFING | Picker availability factor | TBD | fraction (0, 1] | Production standard (or persisted parameter) | A specific value per phase, with source ID, version, effective date, and hash. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` | §3.4 |
| CONF-037 | SPRING_FESTIVAL_STAFFING | Processor availability factor | TBD | fraction (0, 1] | Production standard (or persisted parameter) | Same as CONF-036, for processor role. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` | §3.4 |
| CONF-038 | SPRING_FESTIVAL_STAFFING | Picker productivity | TBD | kg/picker/hour | Production standard | A specific value, with source ID, version, effective date, and hash. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` | §3.4 |
| CONF-039 | SPRING_FESTIVAL_STAFFING | Processor productivity | TBD | kg/processor/hour | Production standard | A specific value, with source ID, version, effective date, and hash. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` | §3.4 |
| CONF-040 | SPRING_FESTIVAL_STAFFING | Picker pre-festival lead time | TBD | days | Production standard | A specific number (e.g. 3) with source ID, version, effective date, and hash. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` | §3.4 |
| CONF-041 | SPRING_FESTIVAL_STAFFING | Processor during-festival lead time | TBD | days | Production standard | A specific number (e.g. 2) with source ID, version, effective date, and hash. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` | §3.4 |
| CONF-042 | SPRING_FESTIVAL_STAFFING | Picker post-festival recovery days | TBD | days | Production standard | A specific number (e.g. 5) with source ID, version, effective date, and hash. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` | §3.4 |
| CONF-043 | SPRING_FESTIVAL_STAFFING | Per-phase mapping | TBD | dict[phase, picker_avail, processor_avail] | Charles | The mapping from `PRE/DURING/POST` to the two availability factors, with source ID, version, effective date, and hash. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` | §3.4 |
| CONF-044 | SPRING_FESTIVAL_STAFFING | Decimal precision | TBD | int >= 0 | Charles | Number of digits after the decimal point. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` | §3.4 |
| CONF-045 | SPRING_FESTIVAL_STAFFING | Rounding mode | TBD | per §5.9 | Charles | Rounding mode for the per-day headcount (recommended: `ROUND_CEIL`). | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` | §3.4 |
| CONF-046 | SPRING_FESTIVAL_STAFFING | Risk code vocabulary | TBD | enum list | Charles | A closed list of risk codes. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` (or empty) | §3.4 |
| CONF-047 | SPRING_FESTIVAL_STAFFING | Advisory template | TBD | template_id | Charles | The deterministic advisory template and permitted placeholders. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` (or `null`) | §3.4 |
| CONF-048 | VARIETY_STAGGER | Selected quantile for overlap evaluation | TBD | "P50" \| "P80" \| "P90" | Charles | Which quantile of per-variety contribution to use. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` | §3.5 |
| CONF-049 | VARIETY_STAGGER | Overlap window length | TBD | int >= 1 | Charles | Number of consecutive days to evaluate (e.g. 3, 5, or 7). | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` | §3.5 |
| CONF-050 | VARIETY_STAGGER | Min varieties sharing the window | TBD | int >= 2 | Charles | The minimum number of distinct varieties required to flag an overlap. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` | §3.5 |
| CONF-051 | VARIETY_STAGGER | Min contribution rate | TBD | fraction (0, 1) | Charles | The minimum contribution rate of each variety within the window. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` | §3.5 |
| CONF-052 | VARIETY_STAGGER | Risk code vocabulary | TBD | enum list | Charles | A closed list of risk codes (likely just `VARIETY_OVERLAP_RISK`). | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` (or empty) | §3.5 |
| CONF-053 | VARIETY_STAGGER | Advisory template | TBD | template_id | Charles | The deterministic single-sentence advisory template. Must NOT contain agronomic instructions. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` (or `null`) | §3.5 |
| CONF-054 | VARIETY_STAGGER | `overlap_detected = False` status | TBD | "APPLICABLE_advisory_null" \| "NOT_APPLICABLE" | Charles | Whether to emit `APPLICABLE` with `advisory_text = null` or `NOT_APPLICABLE` when no overlap is detected. | One of the two; the other is `OUTSIDE_AUTHORIZED_SCOPE` → `NOT_APPLICABLE` with `advisory_text = null` | §3.5 |
| CONF-055 | CROSS_PLANT_DISPATCH | Selected quantile for trigger | TBD | "P50" \| "P80" \| "P90" | Charles | Which quantile of the single-day peak to use for the trigger check. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` | §3.6 |
| CONF-056 | CROSS_PLANT_DISPATCH | Current factory capacity | TBD | kg/day per plant | Production standard | A specific kg/day value per plant with source ID, version, effective date, and hash. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` | §3.6 |
| CONF-057 | CROSS_PLANT_DISPATCH | Trigger ratio | TBD | fraction (0, 1] | Charles | A specific fraction (e.g. 0.9). | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` | §3.6 |
| CONF-058 | CROSS_PLANT_DISPATCH | Risk code vocabulary | TBD | enum list | Charles | A closed list of risk codes. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` (or empty) | §3.6 |
| CONF-059 | CROSS_PLANT_DISPATCH | Advisory template | TBD | template_id | Charles | The deterministic single-sentence advisory template. Must NOT contain cross-plant execution details. | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` (or `null`) | §3.6 |
| CONF-060 | CROSS_PLANT_DISPATCH | `triggered = False` status | TBD | "APPLICABLE_advisory_null" \| "NOT_APPLICABLE" | Charles | Whether to emit `APPLICABLE` with `advisory_text = null` or `NOT_APPLICABLE` when the trigger is not met. | One of the two; the other is `OUTSIDE_AUTHORIZED_SCOPE` | §3.6 |
| CONF-061 | Cross-cutting | Cross-quantile mixing rule | TBD | bool + rule | Charles | Whether cross-quantile mixing is allowed in any formula; if yes, the precise rule. | Default forbidden; if Charles confirms "allowed", the rule is named. | §5.8 |

### §7.2 Open vs closed items

- Total CONF items: **62** (CONF-EX-001 + CONF-001..CONF-061; CONF-061 = 61).
- All 62 are `BUSINESS_SOURCE_REQUIRED` in this document.
- A C2 implementation may NOT begin until at least the items required for its target slice are Charles-confirmed (see §8).

### §7.3 Charles confirmation workflow

1. Charles reviews each CONF row.
2. Charles responds with one of: (a) a confirmed value, source ID, source version, source effective date, and source hash; (b) a "decline" answer indicating the category should remain `BLOCKED` indefinitely; (c) a "supersede" answer pointing to a new CONF row.
3. The new row replaces the old row in the rule catalog. The `rule_catalog_hash` is recomputed; old values are NOT auto-migrated.
4. The `agent_recommendations_hash` is recomputed for the affected category; the new hash is recorded in the audit log.

---

## §8 Implementation slices (forward-looking plan)

This section proposes a six-slice implementation plan (C2-A through C2-F). Each slice requires its own Charles authorization. The slices are independent enough to be reviewed separately, but a slice may be implemented only after the prior slice's `BUSINESS_SOURCE_REQUIRED` items are still `BUSINESS_SOURCE_REQUIRED` (i.e. they do not produce C2 results) AND the prior slice's contract tests pass.

### §8.1 C2-A — Source schemas and policy / catalog contract

| Aspect | Value |
|---|---|
| Goal | Implement the new `RecommendationDecision` schema (Issue #99 §"RecommendationDecision and reason contract"), the `RecommendationReasonCode` enum, the `BlockerCode` additions, the per-category rule-catalog rows for all 6 operational categories (in `BUSINESS_SOURCE_REQUIRED` placeholder form), and the rule catalog / template catalog hash surface. |
| Allowed files | `backend/app/agent/schemas.py`, `backend/app/agent/enums.py`, `backend/app/agent/slice_c/*.py`, new `backend/app/agent/slice_c/policy/*.py`, `backend/app/agent/slice_c/catalog/*.py` |
| Forbidden files | Any non-`backend/app/agent/slice_c/**` production code. No `alembic/**`, no `frontend/**`, no `tests/agent/test_*.py` modification (only new test files). |
| Acceptance tests | TEST-C2-001-07, TEST-C2-002-06, TEST-C2-003-06, TEST-C2-004-06, TEST-C2-005-07, TEST-C2-006-06, plus a new TEST-C2-A-001..006 (rule catalog row exists for each of the 6 categories with `BUSINESS_SOURCE_REQUIRED` placeholder). |
| Rollback boundary | Revert the slice's commits. The C1 contract is preserved because the C1 hard-coded `BLOCKED / REQUIRED_THRESHOLD_MISSING` is still in effect for all 6 categories. |
| Status | NOT AUTHORIZED in this document. |

### §8.2 C2-B — Processing and receiving capacity rules

| Aspect | Value |
|---|---|
| Goal | Activate the formulas in §3.1 and §3.2. Implement the corresponding rule-catalog rows with `BUSINESS_SOURCE_REQUIRED` placeholders that, once Charles provides the source, become live rules. |
| Allowed files | `backend/app/agent/slice_c/engines/capacity.py` (new), `backend/app/agent/slice_c/catalog/capacity.json` (new, placeholder rows), `backend/tests/agent/test_slice_c_capacity_engines.py` (new), `backend/tests/agent/golden/task013_slice_c_output.json` (regenerated) |
| Forbidden files | Anything outside `slice_c/engines/`, `slice_c/catalog/`, `tests/agent/` (new files only), and the two golden files. |
| Acceptance tests | TEST-C2-001-01..08 and TEST-C2-002-01..07. C1 contract preserved (TEST-C2-001-07 and TEST-C2-002-06). |
| Rollback boundary | Revert the slice's commits. The C1 contract is preserved because no new `APPLICABLE` decision is emitted in tests; tests are written in two modes: (a) all CONF missing → `BLOCKED`; (b) all CONF present → `APPLICABLE` (gated by a test fixture that supplies a synthetic `CHARLES_CONFIRMED_SOURCE` for the test only). |
| Status | NOT AUTHORIZED in this document. |

### §8.3 C2-C — Staffing and Spring Festival staffing rules

Same boundary as C2-B but for §3.3 and §3.4.

### §8.4 C2-D — Variety stagger and cross-plant dispatch rules

Same boundary as C2-B but for §3.5 and §3.6. Note: these are review-only categories; the implementation includes the `APPLICABLE` flag but not any execution logic.

### §8.5 C2-E — Production wiring, Goldens, and PostgreSQL acceptance

| Aspect | Value |
|---|---|
| Goal | Update the production-wired `AgentOrchestrator` path to invoke the new `GenerateRecommendationsOutput` schema end-to-end. Regenerate both golden files. Add PostgreSQL integration test coverage. |
| Allowed files | `backend/app/agent/orchestration.py`, `backend/app/agent/slice_c/__init__.py`, `backend/app/agent/slice_c/engine.py`, `backend/tests/agent/golden/*.json`, `backend/tests/integration/agent/test_slice_c_orchestration_postgres.py`, `backend/tests/integration/agent/test_orchestration_postgres.py` |
| Forbidden files | Anything outside the listed files. No `alembic/**`, no `frontend/**`, no `backend/app/api/**`. |
| Acceptance tests | TEST-C2-001-08, TEST-C2-002-07, TEST-C2-003-07, TEST-C2-004-07, TEST-C2-005-08, TEST-C2-006-07, plus golden hash stability tests. |
| Rollback boundary | Revert the slice's commits. The C1 contract is preserved by regenerating the golden files from a known C1 state if any hash check fails. |
| Status | NOT AUTHORIZED in this document. |

### §8.6 C2-F — Review fixup and closeout

| Aspect | Value |
|---|---|
| Goal | Apply review feedback and finalize the closeout comment on Issue #99. |
| Allowed files | `docs/task-013-slice-c-c2-business-rule-source-definition.md` (only if §7 confirmation items are updated), `backend/tests/agent/**` (only to add new tests per review), and Issue #99 comment (posted by Charles, not by automation). |
| Forbidden files | Any production code change not strictly required to address review feedback. |
| Acceptance tests | Re-run the full test suite; both golden SHA-256 values stable. |
| Rollback boundary | Revert the slice's commits. |
| Status | NOT AUTHORIZED in this document. |

### §8.7 Slice ordering and gate

| Predecessor slice | Required gate |
|---|---|
| C2-A | C1 contract preserved (golden hashes match); `MISSING_DATA_IMPACT` decision unchanged. |
| C2-B | C2-A accepted. C1 contract preserved. |
| C2-C | C2-A accepted. C1 contract preserved. |
| C2-D | C2-A accepted. C1 contract preserved. |
| C2-E | C2-A, C2-B, C2-C, C2-D all accepted. C1 contract preserved. PostgreSQL integration test passes against a real chain. |
| C2-F | C2-E accepted. Charles review feedback received. |

---

## §9 Source reconciliation and conflict log

This section records any conflict between sources encountered during the C2 design phase. Each row must list:
- the two (or more) conflicting sources;
- the two (or more) original wordings;
- the normalized proposal;
- why the executing side cannot decide on its own;
- the precise question for Charles.

### §9.1 Resolved conflicts (from C1 design, included for traceability)

| ID | Source conflict | Normalized direction | Status | Reference |
|---|---|---|---|---|
| SRC-C-01 | Design §19.1/19.4 vs Issue #99 sibling-ownership | Sibling top-level fields; acyclic dependency | `RESOLVED_BY_MERGED_AUTHORITY` | Issue #99 §"Sibling-stage dependency contract" |
| SRC-C-02 | Design §20.4 vs Issue #99 missing-threshold-as-blocker | `BLOCKED` (not LOW-confidence action) | `CONFIRMED_BY_CHARLES` | Issue #99 §"Blocker and propagation contract" |
| SRC-C-03 | Deferred outputs vs Issue #99 policy/catalog identities | Use new contract | `CONFIRMED_BY_CHARLES` | Issue #99 §"Policy schemas, identifiers, and canonical hashes" |
| SRC-C-04 | Existing `Recommendation` vs Issue #99 `RecommendationDecision` envelope | Implement new envelope in C2-A | `CONFIRMED_BY_CHARLES` (design) / `NOT_YET_IMPLEMENTED` (code) | Issue #99 §"RecommendationDecision and reason contract" |
| SRC-C-05 | Original design §24.1 stale season fields vs `task-013-persisted-forecast-season-identity-design-amendment.md` | Use the amendment | `RESOLVED_BY_MERGED_AUTHORITY` (per Issue #99; document file itself is NOT in current main, see §9.2 SRC-NEW-01) | Issue #99 §"Source reconciliation conflicts" |
| SRC-C-06 | Existing `BlockerCode` vs Issue #99 Slice C blocker set | Add typed blockers in C2-A | `CONFIRMED_BY_CHARLES` | Issue #99 §"Blocker and propagation contract" |
| SRC-C-07 | Mixed JSON Pointer / non-RFC paths | RFC 6901 only | `CONFIRMED_BY_CHARLES` | Issue #99 §"RFC 6901 evidence field-path contract" |
| SRC-C-08 | Slice A deferred tests permit empty outputs | Require 7 decisions, stable hashes, Goldens, production wiring | `CONFIRMED_BY_CHARLES` | Issue #99 §"Source reconciliation conflicts" |
| SRC-C-09 | Minimal-input spec names 7 categories but provides no formulas | Operational categories remain `BLOCKED` until sources exist | `BUSINESS_SOURCE_REQUIRED` | Issue #99 §"Source reconciliation conflicts" |
| SRC-C-10 | Current PostgreSQL acceptance ends at Slice B | Extend through C1 sibling stages | `CONFIRMED_BY_CHARLES` (C1 implementation in PR #100) | Issue #99 §"PostgreSQL production-wiring acceptance" |
| SRC-C-11 | Prior proposed decision shape had no reason field | Add `reason_code` + `reason_details` | `CONFIRMED_BY_CHARLES` | Issue #99 §"RecommendationDecision and reason contract" |

### §9.2 New conflicts discovered during C2 source-definition

| ID | Source conflict | Original wordings | Normalized proposal | Why execution cannot decide | Question for Charles |
|---|---|---|---|---|---|
| SRC-NEW-01 | Issue #99 body references `docs/task-013-persisted-forecast-season-identity-design-amendment.md` as a `RESOLVED_BY_MERGED_AUTHORITY` source, but the file is NOT in the current `main` (`ls docs/task-013-persisted*` returns no results). The only trace is the remote-tracking branch `origin/codex/task-013-persisted-season-identity-design` (in `.git/refs/remotes/origin/`). | (a) Issue #99 body SRC-C-05 row: "`RESOLVED_BY_MERGED_AUTHORITY`: `docs/task-013-persisted-forecast-season-identity-design-amendment.md` and `backend/app/agent/schemas.py::NormalizedAgentRequest`". (b) Current `main` at `2e860511dd9279d0aa3c64dd760bea8531fad458` filesystem: no such file. | Treat the season-identity amendment as referenced in code (`backend/app/agent/schemas.py::NormalizedAgentRequest`) but the standalone doc file is not required for C2 source-definition. C2 does not consume season-identity fields directly. | Because the issue text treats the doc as authority but the doc is not in the working tree, future implementers may be confused. Execution cannot silently recreate the doc. | (a) Confirm that C2 does not need the standalone doc. (b) Confirm whether the doc should be added to the working tree in a separate docs-only round, or whether the Issue #99 reference should be updated to remove the doc citation. |
| SRC-NEW-02 | The TASK-013 C2 Concept UI Prototype (HEAD `15d2e53`, branch `prototype/task-013-c2-concept-ui-v1`) uses 6 capability blocks named `CAPACITY-001/002`, `STAFF-001/002`, `VARIETY-001`, `DISPATCH-001`. The production `RecommendationCategory` enum has 7 values: the 6 operational categories plus `MISSING_DATA_IMPACT`. The mapping is not 1:1. | (a) Prototype labels: 6 blocks. (b) Production enum: 7 categories (6 operational + 1 data-quality). | Treat prototype as visual reference only (rank 4 in §2.1). Do not map. | Because execution cannot decide which prototype block "becomes" which production category, and any mapping would inject non-canonical labels into a Charles-confirmed enum. | See CONF-EX-001 in §7. |
| SRC-NEW-03 | The Issue #99 design and the prototype both reference "safety factor", but neither provides a value. The `PeakMetricPolicy.high_load_threshold_ratio` is an existing field that looks similar but is upstream-only (Slice B). | (a) Issue #99: no value. (b) `PeakMetricPolicy.high_load_threshold_ratio`: existing schema field, value is config-driven. (c) Prototype: no value, displays "待确认". | C2 does not consume `high_load_threshold_ratio`. C2 uses a separate `SAFETY` parameter (CONF-004, CONF-018, CONF-057). | Because conflating the two would make the advisory depend on a Slice B config value that the C2 advisory should not depend on. | Confirm that C2's `SAFETY` parameter is distinct from `PeakMetricPolicy.high_load_threshold_ratio`. |

### §9.3 Conflict log rule

Any future implementer who discovers a new conflict MUST:
1. Halt implementation.
2. Add a new row to §9.2 with the five columns filled.
3. Surface the row in the PR body of the implementation round.
4. NOT resolve the conflict silently.

A silent conflict resolution is a hard rule violation and triggers a rollback to the prior accepted state.

---

## §10 Charles confirmation count summary

| Item | Count |
|---|---|
| Total CONF items in §7 | **62** |
| `BUSINESS_SOURCE_REQUIRED` items | 62 |
| `CONFIRMED_BY_CHARLES` items | 0 (this round) |
| `RESOLVED_BY_MERGED_AUTHORITY` items | 0 (no operational source is resolved) |
| `NOT_APPLICABLE` items | 0 |
| Source-conflict rows in §9 | **3** (SRC-NEW-01, SRC-NEW-02, SRC-NEW-03) |
| Open design-choice confirmations (TBD) | 2 (CONF-054, CONF-060) |
| Cross-cutting confirmations | 2 (CONF-EX-001, CONF-061) |

---

## §11 Acceptance gates (this document)

This document is considered `C2_SOURCE_DEFINITION_DRAFT` and **not yet accepted** until ALL of the following are true:

1. The document is on a dedicated `docs/task-013-slice-c-c2-business-source-definition` branch off `origin/main` at `2e860511dd9279d0aa3c64dd760bea8531fad458`.
2. The branch is pushed to `origin` and a Draft PR is created.
3. The Draft PR body includes: (a) a non-mutation statement; (b) the §10 count summary; (c) a "no prototype values used as authority" statement; (d) the §9.2 new-conflict log.
4. The Draft PR is in `OPEN / Draft` state, NOT Ready, NOT merged.
5. The local working tree is clean after the commit.
6. No production code file has been modified.
7. No `alembic/**` file has been modified.
8. No `frontend/**` file has been modified.
9. No dependency file (`pyproject.toml`, `requirements*.txt`, `package.json`, etc.) has been modified.
10. The C1 contract is preserved: the current `backend/app/agent/slice_c/engine.py` and `backend/tests/agent/golden/task013_slice_c_output.json` are unchanged.

This document is considered `C2_SOURCE_DEFINITION_FROZEN` only after Charles confirms ALL of the above AND posts an explicit acceptance comment on Issue #99. The acceptance comment is binding on all future C2 implementation rounds.

---

## §12 Change log

| Date | Round | Author | Change |
|---|---|---|---|
| 2026-07-14 | v1 (this document) | Charles-authorized C2 design round | Initial creation. Frozen-in-C1 contract preserved; six operational categories enumerated as `BUSINESS_SOURCE_REQUIRED`; 62 CONF items listed; 3 source conflicts logged; 6-slice implementation plan proposed. |

---

## §13 Sign-off section (to be completed by Charles upon acceptance)

```text
TASK013_SLICE_C_C2_SOURCE_DEFINITION_DRAFT_REVIEWED
TASK013_SLICE_C_C2_SOURCE_DEFINITION_FROZEN_UPON_CHARLES_ACCEPTANCE
TASK013_SLICE_C_C2_IMPLEMENTATION_NOT_YET_AUTHORIZED
TASK013_SLICE_C_C2_BRANCH_AND_WORKTREE_NOT_YET_AUTHORIZED
TASK013_SLICE_C_C2_DRAFT_PR_OPEN_NOT_READY
TASK013_SLICE_C_C2_READY_NOT_AUTHORIZED
TASK013_SLICE_C_C2_MERGE_NOT_AUTHORIZED
TASK013_SLICE_C_C2_ISSUE99_REMAINS_OPEN
TASK013_SLICE_C_SLICE_D_E_NOT_AUTHORIZED
TASK013_SLICE_C_TASK_014_NOT_AUTHORIZED
```

(Charles to amend the above with explicit `ACCEPTED` or `REVISED` markers and post the result as an Issue #99 comment.)
