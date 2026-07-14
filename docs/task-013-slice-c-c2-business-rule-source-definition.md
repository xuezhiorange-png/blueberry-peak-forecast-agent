# TASK-013 Slice C Phase C2 — Business-Rule Source Definition and Design Freeze

| Field | Value |
|---|---|
| Document ID | `task-013-slice-c-c2-business-rule-source-definition` |
| Document version | v1.1 (P0 fixup, see §12) |
| Document status | `DRAFT — P0 fixup applied, awaiting Charles re-review` |
| Tracking Issue | `#99` (OPEN) |
| C1 baseline merge commit | `2e860511dd9279d0aa3c64dd760bea8531fad458` |
| C1 baseline branch | `codex/task-013-slice-c-c1-deterministic-foundation` (PR #100, merged) |
| Working base for C2 design | `origin/main` at `2e860511dd9279d0aa3c64dd760bea8531fad458` |
| Reviewed Head (v1) | `d5ed336df8293bbab23a656e9299fbaed402f34f` |
| Review ID for v1 | `4694215238` |
| Review verdict for v1 | `PR101_DESIGN_REVIEW_P0_FIXUP_REQUIRED` |
| C2 implementation | NOT AUTHORIZED in this document |
| C2 production implementation branch | NOT AUTHORIZED in this document |
| C2 production implementation worktree | NOT AUTHORIZED in this document |
| C2 production implementation PR | NOT AUTHORIZED in this document |
| Ready | NOT AUTHORIZED in this document |
| Merge | NOT AUTHORIZED in this document |
| TASK-014+ | NOT AUTHORIZED in this document |

> This document is the **current C2 source-definition baseline**. Future revisions are possible through explicit amendment rounds with separate Charles authorization. This wording replaces the earlier "only design artifact that may be merged" phrasing.

---

## §1 Scope and non-scope

### §1.1 In scope

This document freezes the **business-rule source definition** for TASK-013 Slice C Phase C2. It defines, for each of the six C2 operational categories, the source authority, required upstream fields, RFC 6901 JSON Pointer, source identity, formula candidate (see §5), decision table, and Charles confirmation items. C2 activation (i.e. transitioning a category from `BUSINESS_SOURCE_REQUIRED` to a real `APPLICABLE` or `NOT_APPLICABLE` decision) is **not** authorized in this document. C2 activation requires a future implementation round with separate Charles authorization.

This document is the **current C2 source-definition baseline**. Future revisions are possible through explicit amendment rounds with separate Charles authorization.

### §1.2 Out of scope (explicit exclusions)

C2 source-definition does not authorize and does not produce:

1. Any modification of `backend/app/**` production code.
2. Any modification of `backend/tests/agent/**` or `backend/tests/integration/agent/**` to embed operational formulas.
3. Any modification of `backend/app/agent/slice_c/**` to activate operational rules.
4. Any new persistence table, Alembic migration, or Alembic revision.
5. Any HTTP API endpoint, CLI command, or frontend widget.
6. Any Slice D, Slice E, or TASK-014+ design or implementation.
7. Any LLM call, prompt, or free-form natural-language generation.
8. Any automatic operational execution, TASK-012 POST, or external side effect.
9. Any change to TASK-008 through TASK-012 numerical semantics.
10. Any authority reselection, cross-run substitution, or implicit latest/current/best/default authority.
11. Any business formula, threshold, coefficient, productivity, turnover, shift duration, capacity conversion, or business rounding value **without** an approved source ID in the Charles confirmation matrix (§7).
12. Any C2 production implementation, production implementation branch, production implementation worktree, production implementation Draft PR, Ready transition, or merge.
13. Any closure of Issue #99.
14. Any **production implementation** branch mutation, worktree deletion, or worktree creation. (The docs-only branch `docs/task-013-slice-c-c2-business-source-definition`, its worktree, and Draft PR #101 are explicitly authorized by Charles's earlier authorization and are not affected by this exclusion.)

### §1.3 What this document does produce

1. A C2 category-by-category source authority contract with required upstream fields, JSON Pointer paths, and source identity fields.
2. A six-category `BUSINESS_SOURCE_REQUIRED` matrix enumerating which parameters must come from Charles before C2 activation.
3. A formula candidate (NOT frozen; see §5) and decision table for each category that software must implement exactly when sources become available.
4. A Charles confirmation matrix of closed, directly-answerable questions, classified into `RESOLVED_BY_MERGED_AUTHORITY` / `DESIGN_CONFIRMATION_REQUIRED` / `BUSINESS_SOURCE_REQUIRED`.
5. A proposed six-slice implementation plan (C2-A through C2-F) for future rounds.

### §1.4 Authority of the prototype UI

The TASK-013 C2 Concept UI Prototype v1 (branch `prototype/task-013-c2-concept-ui-v1`, HEAD `15d2e53076ec30ba56f5a2f6657de50a5bd5abdf`, Issue #99 amendment comment `4967834240`) is a **visual business-workflow validation prototype only**. It is `PROTOTYPE_VISUAL_REFERENCE` (rank 4 in §2). It is **not** a source authority.

The prototype:

- MUST NOT be cited as a source ID, source version, source effective date, source hash, formula, threshold, coefficient, or rounding mode.
- MUST NOT be quoted to justify any `APPLICABLE` decision in C2.
- The prototype's six capability blocks (CAPACITY-001/002, STAFF-001/002, VARIETY-001, DISPATCH-001) are exploratory labels and do **not** map one-to-one to the seven `RecommendationCategory` enum values in `backend/app/agent/enums.py::RecommendationCategory`. CONF-EX-001 is `RESOLVED_BY_MERGED_AUTHORITY` (no production mapping; the prototype remains visual-only).
- The prototype MAY be cited only as `prototype_visual_reference: <branch>@<sha>` in the audit log of a Charles confirmation item when Charles confirms a parameter.

### §1.5 Status of "branch / worktree / PR not authorized" wording

When this document says "branch / worktree / PR not authorized" or similar wording, it means **C2 production implementation** branch, worktree, and PR. The docs-only branch `docs/task-013-slice-c-c2-business-source-definition`, its worktree, and Draft PR #101 are explicitly authorized by Charles and already exist; they are not affected by such exclusion clauses.

---

## §2 Source authority hierarchy

All business-rule values in C2 must resolve to a source from the following five-level hierarchy. Lower-priority sources MAY NOT be silently promoted to higher-priority authority.

### §2.1 Hierarchy (highest to lowest)

| Rank | Authority | Description | Allowed as source for | Frozen status |
|---:|---|---|---|---|
| 1 | `CHARLES_CONFIRMED_SOURCE` | Charles has explicitly confirmed a specific business rule, source identity, formula, threshold, rounding, or non-action. Captured in the Charles confirmation matrix (§7) with a confirmation ID `CONF-*`. | Any C2 category field. | PENDING this round |
| 2 | `APPROVED_AUDITABLE_SOURCE` | A frozen, audit-traceable corporate rule, production standard, planning parameter, or equipment specification that has been approved through Charles's normal governance process and can be cited by source ID, version, effective date, and content hash. | Any C2 category field. | NOT YET PROVIDED for any C2 parameter — all C2-B01..B06 remain `BUSINESS_SOURCE_REQUIRED` |
| 3 | `PERSISTED_UPSTREAM_MODEL_OUTPUT` | A value already persisted and integrity-validated by TASK-008 through TASK-012 in the Slice B `AgentForecastOutput`. This includes `parameters`, `daily_curve`, and `peak` payloads. C2 category fields whose RFC 6901 JSON Pointer resolves to a Slice B value. Examples: `/peak/peak_window_cumulative_quantity_kg/P80`, `/daily_curve/7/final_corrected_arrival_quantity_kg/p50`. | C2 category fields with valid pointer resolution. | RESOLVED — Slice B persistence chain Task 8 → Task 9 v2 → Task 10 → Slice B is `RESOLVED_BY_MERGED_AUTHORITY` (PR #100) |
| 4 | `PROTOTYPE_VISUAL_REFERENCE` | The TASK-013 C2 Concept UI Prototype v1 visual labels, placeholder text, and interaction flow. NOT a source of values, formulas, or thresholds. | Audit-log annotation only, never as a primary source. | NOT A PRIMARY AUTHORITY (CONF-EX-001: no production mapping) |
| 5 | `INDUSTRY_HEURISTIC_OR_DEFAULT` | Industry average, rule of thumb, "common practice", web-sourced default, or LLM-inferred default. | FORBIDDEN — MUST NOT be used as authority. C2 activation requires promotion of every such candidate to rank 1 or 2 via Charles confirmation. | EXPLICITLY FORBIDDEN |

### §2.2 Promotion rule

- A value at rank 5 MUST NOT be silently promoted to rank 3 or above.
- A value at rank 4 MUST NOT be silently promoted to rank 3 or above.
- A value at rank 3 MAY be cited only with a valid Slice B Citation whose JSON Pointer resolves to the value, whose `agent_artifact_hash` matches, whose `source_tasks` (plural, list) contains the producing TASK, and whose `authorities` list contains a typed authority envelope (`TASK_8_AUTHORITY` through `TASK_12_AUTHORITY`).
- A value at rank 2 MAY be cited only with a Charles-provided `source_id`, `source_version`, `source_effective_date`, and `source_hash`.
- A value at rank 1 (Charles confirmation) is binding until explicitly revised by Charles; revision requires a new CONF-* row with `supersedes` linkage.

### §2.3 Conflict resolution (corrected per review 4694215238)

When two sources at the same rank disagree:

1. **The conflict is `SOURCE_CONFLICT` and the decision is `BLOCKED`** with `reason_code = REQUIRED_EVIDENCE_MISSING` (or with a typed `source_conflict` blocker) until Charles explicitly resolves it. There is no automatic tie-break.
2. Automatic resolution is allowed only when one of the following is established:
   1. **Explicit supersession**: the new source is named as a `supersedes` of the older one in the same source family, with the supersession declaration approved by Charles.
   2. **Approval lineage**: the two sources are linked through a documented version/approval lineage in the Charles confirmation matrix.
   3. **Same source family**: the two sources are clearly revisions of one original authority (e.g. a policy document and its amended version), and the newer effective date is named in the same source family record.
3. A content hash is an **identity**, not a **priority signal**. "Lexicographically larger hash wins" and "more recent effective date wins" are both forbidden as automatic tie-breakers across different source families.
4. Different source families at the same rank MUST block. The blocker code is `SOURCE_CONFLICT` and is reported through `blocker_dependencies`.
5. Charles or a formal approval lineage may specify a winner; that specification is then encoded in a Charles confirmation row.
6. Source hashes are computed from canonical source content (e.g. canonical JSON of the policy document, signed PDF SHA-256, etc.). Hashes are never manually assigned as decision values.

---

## §3 Six operational category source-definition

### §3.0 Common contract applied to all six categories

The following items are identical for all six operational categories. Any category-specific deviation is explicitly stated in §3.1–§3.6.

#### §3.0.1 Output envelope (all categories)

| Field | Value | Source | Status |
|---|---|---|---|
| Output shape | Single `RecommendationDecision` with 17 fields (`category`, `kind`, `status`, `reason_code`, `reason_details`, `priority_rank`, `rule_id`, `template_id`, `advisory_text`, `applicability_conditions`, `evidence`, `risk_codes`, `confidence`, `confidence_boundary`, `blocker_dependencies`, `non_action`, plus inherited `frozen=True` and `extra="forbid"`). | `backend/app/agent/schemas.py::RecommendationDecision` (PR #100) | `RESOLVED_BY_MERGED_AUTHORITY` |
| Output container | `GenerateRecommendationsOutput.decisions: list[RecommendationDecision]` (7 entries). | `backend/app/agent/schemas.py::GenerateRecommendationsOutput` | `RESOLVED_BY_MERGED_AUTHORITY` |
| Output count | Exactly seven `RecommendationDecision` objects per `GenerateRecommendationsOutput`, in canonical category order (§3.0.2). | `backend/app/agent/slice_c/engine.py` (PR #100) | `RESOLVED_BY_MERGED_AUTHORITY` |
| Status / reason compatibility | `APPLICABLE` ↔ `RULE_APPLICABLE`; `NOT_APPLICABLE` ↔ `CONDITIONS_NOT_MET` or `OUTSIDE_AUTHORIZED_SCOPE`; `BLOCKED` ↔ `REQUIRED_THRESHOLD_MISSING` / `REQUIRED_EVIDENCE_MISSING` / `UPSTREAM_BLOCKED` / `POLICY_UNAVAILABLE`. Enforced by `_status_reason_contract` validator. | `schemas.py::RecommendationDecision._status_reason_contract` | `RESOLVED_BY_MERGED_AUTHORITY` |
| `APPLICABLE` requires non-null `advisory_text` | Enforced by validator. | `schemas.py::RecommendationDecision._status_reason_contract` | `RESOLVED_BY_MERGED_AUTHORITY` |
| `BLOCKED` requires non-empty `blocker_dependencies` | Enforced by validator. | `schemas.py::RecommendationDecision._status_reason_contract` | `RESOLVED_BY_MERGED_AUTHORITY` |
| Non-APPLICABLE requires null `advisory_text` | Enforced by validator. | same | `RESOLVED_BY_MERGED_AUTHORITY` |
| NonAction | 4 fields: `required: Literal[True]`, `code: Literal["ADVISORY_ONLY_NO_AUTOMATIC_EXECUTION"]`, `text: Literal["This output is advisory only and does not trigger any external action."]`, `category_specific_code: str`. | `schemas.py::NonAction` | `RESOLVED_BY_MERGED_AUTHORITY` |
| C1 six-op state (current) | `status="BLOCKED"`, `reason_code="REQUIRED_THRESHOLD_MISSING"`, `reason_details={"source_package": "C2-B0X"}`, `priority_rank=1..6`, `rule_id="c1-blocked-{category.lower()}"`, `template_id="operational-source-required-v1"`, `advisory_text=None`, `blocker_dependencies=[Blocker(code=RECOMMENDATION_THRESHOLD_MISSING, message="C2 business source package is unavailable", details={"category": category, "phase": "C1"}, retry_hint="CONTACT_OPS")]`, `non_action=NonAction(category_specific_code=...)`. | `slice_c/engine.py::_operational_decision` | `RESOLVED_BY_MERGED_AUTHORITY` |
| Citation reuse | `RecommendationEvidence.citation: Citation` reuses the canonical `Citation` schema (`schemas.py::Citation`). No shorthand citation is permitted. | `schemas.py::Citation` + `RecommendationEvidence` | `RESOLVED_BY_MERGED_AUTHORITY` |
| Field-path policy | RFC 6901 JSON Pointer, version `slice-c-json-pointer-policy-v1`. | Issue #99 §"RFC 6901 evidence field-path contract" | `RESOLVED_BY_MERGED_AUTHORITY` (C1) |
| Forbidden action language | `execute`, `dispatch now`, `schedule automatically`, `assign staff`, `modify pruning plan`, `change capacity`, `submit order`, `trigger POST` are forbidden unless they appear in an explicit non-action or prohibition statement. | Issue #99 §"Unified non-action contract" | `RESOLVED_BY_MERGED_AUTHORITY` (C1) |

#### §3.0.2 Canonical category order

| Rank | Category | Kind | C1 priority_rank | C2 priority_rank (proposed) | Frozen status |
|---:|---|---|---:|---:|---|
| 1 | `SUSTAINED_PROCESSING_CAPACITY` | `OPERATIONAL` | 1 | 1 (proposed) | `BUSINESS_SOURCE_REQUIRED` (operational) |
| 2 | `RECEIVING_PEAK_CAPACITY` | `OPERATIONAL` | 2 | 2 (proposed) | `BUSINESS_SOURCE_REQUIRED` (operational) |
| 3 | `SHIFT_STAFFING` | `OPERATIONAL` | 3 | 3 (proposed) | `BUSINESS_SOURCE_REQUIRED` (operational) |
| 4 | `SPRING_FESTIVAL_STAFFING` | `OPERATIONAL` | 4 | 4 (proposed) | `BUSINESS_SOURCE_REQUIRED` (operational) |
| 5 | `VARIETY_STAGGER` | `OPERATIONAL` | 5 | 5 (proposed) | `BUSINESS_SOURCE_REQUIRED` (operational) |
| 6 | `CROSS_PLANT_DISPATCH` | `OPERATIONAL` | 6 | 6 (proposed) | `BUSINESS_SOURCE_REQUIRED` (operational) |
| 7 | `MISSING_DATA_IMPACT` | `DATA_QUALITY` | 7 | 7 | `RESOLVED_BY_MERGED_AUTHORITY` (C1) |

Source: `backend/app/agent/enums.py::RecommendationCategory` + `backend/app/agent/slice_c/engine.py::OPERATIONAL_CATEGORIES` + `CATEGORY_ORDER` (PR #100). Status: `RESOLVED_BY_MERGED_AUTHORITY`.

#### §3.0.3 Common blocker / reason mapping (all categories)

| Status | Allowed reason codes (single scalar) |
|---|---|
| `APPLICABLE` | `RULE_APPLICABLE` |
| `NOT_APPLICABLE` | `CONDITIONS_NOT_MET`, `OUTSIDE_AUTHORIZED_SCOPE` |
| `BLOCKED` | `REQUIRED_THRESHOLD_MISSING`, `REQUIRED_EVIDENCE_MISSING`, `UPSTREAM_BLOCKED`, `POLICY_UNAVAILABLE` |

Source: `schemas.py::RecommendationDecision._status_reason_contract` (PR #100). Status: `RESOLVED_BY_MERGED_AUTHORITY`.

> **Hard rule**: `reason_code` is a single scalar and uses only the seven values above. Blocker codes (e.g. `EVIDENCE_HASH_MISMATCH`, `EVIDENCE_FIELD_PATH_INVALID`, `REQUIRED_CITATION_MISSING`, `REQUIRED_AUTHORITY_MISSING`, `REQUIRED_PROVENANCE_MISSING`, `RECOMMENDATION_THRESHOLD_MISSING`) MUST NOT appear in `reason_code`. They belong in `blocker_dependencies` as typed `Blocker` entries with `code: BlockerCode`. When multiple blockers exist, see §3.0.4 for deterministic ordering; the `reason_code` itself remains a single scalar (no compound reason code, no two-reason-code list).

#### §3.0.4 Common decision rules (all categories)

- Exactly seven decisions are emitted in merged category order; no category is omitted.
- Rules are ordered by category canonical rank, then `priority_rank`, then `rule_id` lexical ascending.
- The first rule whose `applicability_conditions` are all `TRUE` wins.
- Any `UNKNOWN` `ConditionResult` caused by missing required evidence produces `BLOCKED` (with the missing-pointer evidence blocker in `blocker_dependencies`).
- If every evaluated condition is `FALSE`, the decision is `NOT_APPLICABLE` with `reason_code = CONDITIONS_NOT_MET`.
- Only `APPLICABLE` permits non-null `advisory_text`.
- `NOT_APPLICABLE` has `advisory_text = null` and uses an allowed stable reason.
- `BLOCKED` has `advisory_text = null`, emits no action number, and carries a non-empty `blocker_dependencies` list.
- No new severity taxonomy; only `priority_rank` is used.

**Deterministic ordering when multiple blockers exist** (review 4694215238 P0-3):

1. Sort by `code` (the `BlockerCode.value` string), lexical ascending.
2. Then by `message`, lexical ascending.
3. Then by canonicalized `details` JSON, deterministic.
4. Then by canonicalized `citation` JSON (if present), deterministic.
5. Then by `retry_hint` lexical ascending.

Deduplication occurs only when the complete canonical blocker payload (code + message + details + citation + retry_hint) is identical. The single `reason_code` is chosen independently as the highest-priority reason per §3.0.3 (e.g. if any blocker indicates a missing source, the `reason_code` is `REQUIRED_THRESHOLD_MISSING`; if any blocker is an upstream blocker, the `reason_code` is `UPSTREAM_BLOCKED`; if multiple reasons are tied, `UPSTREAM_BLOCKED` takes precedence over `REQUIRED_THRESHOLD_MISSING` which takes precedence over `POLICY_UNAVAILABLE` which takes precedence over `REQUIRED_EVIDENCE_MISSING`).

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
| `EVIDENCE_HASH_MISMATCH` | Resolved value's hash did not match citation's `agent_artifact_hash`. | All 7 |

Source: Issue #99 §"Blocker and propagation contract" — `CONFIRMED_BY_CHARLES`.

#### §3.0.6 Common replay / hash surface

- `agent_recommendations_hash = sha256(canonical JSON of the complete GenerateRecommendationsOutput excluding agent_recommendations_hash)`. Source: Issue #99 §"GenerateRecommendations contract" + `schemas.py::GenerateRecommendationsOutput`.
- The rule catalog is itself hashed: `rule_catalog_hash = sha256(canonical JSON of the complete ordered rule catalog excluding rule_catalog_hash itself)`. Source: Issue #99 §"Policy schemas, identifiers, and canonical hashes".
- The hash surface excludes runtime timestamps, database-generated IDs, hosts, paths, environment-specific values, unordered sets, and nondeterministically ordered mappings. Source: same.
- Hashes are computed from final canonical payloads and are never manually assigned. Source: same.

#### §3.0.7 JSON Pointer / parameters array note (review 4694215238 P0-2)

The C1 `RecommendationDecision.evidence` field is a `list[RecommendationEvidence]`. `RecommendationEvidence` itself has `affected_field_paths: list[RFC6901JsonPointer]` (min_length=1) and a nested `Citation`. C2 implementation must construct pointers in the form documented per category below.

**Critical: `parameters` is `list[ParameterEstimate]`, NOT a map.** RFC 6901 cannot search a list by `parameter_name`. C2 must:

- (A) Use stable array indices, e.g. `/parameters/{index}/p50`, where `{index}` is the `ParameterEstimate` position in the validated Slice B `parameters: list[ParameterEstimate]` payload; **or**
- (B) Define a separate deterministic parameter-lookup step that consumes the source payload and returns a stable `parameter_index: int` for the named parameter, then use the array index in subsequent pointers; **or**
- (C) If neither (A) nor (B) is feasible (e.g. the parameter is not currently persisted at all), mark the field as a **source capability gap** and leave the category `BLOCKED` with `REQUIRED_EVIDENCE_MISSING` (or `REQUIRED_THRESHOLD_MISSING` if the parameter is part of a formula).

The current document presents (B) as the **proposed** approach; the actual implementation choice is a `DESIGN_CONFIRMATION_REQUIRED` item (see CONF-EX-002 in §7.1.2). Until the design is confirmed, no pointer to a parameter-by-name path is authoritative.

#### §3.0.8 Citation field contract (corrected per review 4694215238 P0-2)

The merged `Citation` schema is (from `schemas.py::Citation`):

```yaml
Citation:
  source_tasks: list[CitationSourceTask]            # NOT source_task (singular)
  source_tool: CitationSourceTool
  authorities: list[CitationAuthorityEntry]         # NOT a single authority
  agent_artifact_hash: SHA256Hex | None             # NOT artifact_hash
  field_path: str                                   # RFC 6901 reference
  effective_as_of_date: date
  confidence_evidence: dict[str, Any] | None
  tags: list[Literal["OVERRIDE_APPLIED"]]
  override_refs: list[CitationOverrideRef]
```

The earlier draft used non-existent `Citation.artifact_hash` and singular `Citation.source_task`. The corrected pointers use the actual field names: `agent_artifact_hash` and `source_tasks` (list).

---

### §3.1 SUSTAINED_PROCESSING_CAPACITY

#### §3.1.1 Business purpose

Recommend a sustained (multi-day) processing capacity that the receiving plant can rely on across the peak window, based on a forecast daily curve and a Charles-confirmed safety factor. The category emits a single capacity value (or `BLOCKED`) and does not embed per-day processing instructions.

#### §3.1.2 Allowed upstream fields

- `/peak/peak_window_cumulative_quantity_kg/{P50,P80,P90}` — three-day rolling peak total (kg).
- `/peak/peak_window_days_before`, `/peak/peak_window_days_after` — window configuration.
- `/peak/peak_metric_policy_version`, `/peak/peak_metric_policy_config_hash` — policy identity.
- `/daily_curve/{day_index}/final_corrected_arrival_quantity_kg/{p50,p80,p90}` — daily corrected arrivals.

> **Pointer caveat**: `/peak/single_day_peak/{P50,P80,P90}/volume_kg` is referenced by Issue #99 §"RFC 6901 evidence field-path contract" as an example, but the merged `ForecastPeakOutput` schema exposes the single-day peak through a different field path. The exact pointer must be re-validated against the current `ForecastPeakOutput` schema when this category is implemented. Until then, the exact path is a `DESIGN_CONFIRMATION_REQUIRED` item (CONF-EX-003 in §7.1.2).

#### §3.1.3 RFC 6901 JSON Pointer examples (currently authoritative)

```text
/peak/peak_window_cumulative_quantity_kg/P50
/peak/peak_window_cumulative_quantity_kg/P80
/peak/peak_window_cumulative_quantity_kg/P90
/peak/peak_window_days_before
/peak/peak_window_days_after
/daily_curve/0/final_corrected_arrival_quantity_kg/p80
/daily_curve/7/final_corrected_arrival_quantity_kg/p50
```

#### §3.1.4 Field-level source authority

| Field | Authority type | Source ID | Source version | Source effective date | Source hash | Status |
|---|---|---|---|---|---|---|
| `/peak/peak_window_cumulative_quantity_kg/P50` | `PERSISTED_UPSTREAM_MODEL_OUTPUT` (Slice B) | typed `Task10Authority` envelope | Slice B `peak_metric_policy_version` | Slice B `as_of` | Slice B `peak_metric_policy_config_hash` (compared to `Citation.agent_artifact_hash`) | `RESOLVED_BY_MERGED_AUTHORITY` |
| Same for `/P80` and `/P90` | same | same | same | same | same | `RESOLVED_BY_MERGED_AUTHORITY` |
| Selected quantile (`P50` / `P80` / `P90`) for capacity basis | `CHARLES_CONFIRMED_SOURCE` | `CONF-001` | TBD on confirmation | TBD | TBD on confirmation | `BUSINESS_SOURCE_REQUIRED` |
| `sustained_window_days` (currently hard-coded `3` by `PeakMetricPolicy.strict_three_day_window`) | `RESOLVED_BY_MERGED_AUTHORITY` (engineering contract) / business value for the window basis | `CONF-002` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Single-day vs sustained-three-day basis choice | `CHARLES_CONFIRMED_SOURCE` | `CONF-003` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Safety / reserve / utilization factor (see §3.1.6 — semantic not yet chosen) | `APPROVED_AUDITABLE_SOURCE` or `CHARLES_CONFIRMED_SOURCE` | `CONF-004` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Unit (kg/day) and display unit (t/day) | `CHARLES_CONFIRMED_SOURCE` | `CONF-005` | TBD | TBD | TBD | `DESIGN_CONFIRMATION_REQUIRED` (cross-cutting rounding/precision policy; see §7.1.2) |
| Decimal precision (display digits after decimal) | `CHARLES_CONFIRMED_SOURCE` | `CONF-006` | TBD | TBD | TBD | `DESIGN_CONFIRMATION_REQUIRED` (cross-cutting precision policy) |
| Business rounding mode (e.g. `ROUND_HALF_UP`, `ROUND_FLOOR`, `ROUND_CEIL`) | `CHARLES_CONFIRMED_SOURCE` | `CONF-007` | TBD | TBD | TBD | `DESIGN_CONFIRMATION_REQUIRED` (cross-cutting rounding policy) |
| Confidence downgrade rule (e.g. if `confidence_score` below threshold, set `confidence = MEDIUM`) | `CHARLES_CONFIRMED_SOURCE` | `CONF-008` | TBD | TBD | TBD | `DESIGN_CONFIRMATION_REQUIRED` (cross-cutting confidence presentation policy) |
| Risk codes (e.g. `SUSTAINED_PEAK_BREACH_RISK`, `SAFETY_FACTOR_INSUFFICIENT`) | `CHARLES_CONFIRMED_SOURCE` | `CONF-009` | TBD | TBD | TBD | `DESIGN_CONFIRMATION_REQUIRED` (cross-cutting risk vocabulary; see §7.1.2) |
| Advisory template (deterministic, versioned text) | `CHARLES_CONFIRMED_SOURCE` | `CONF-010` | TBD | TBD | TBD | `DESIGN_CONFIRMATION_REQUIRED` (cross-cutting template governance) |

#### §3.1.5 Applicability and granularity

- **Applicable grain (time)**: per requested season × resolved location × resolved varieties.
- **Applicable grain (space)**: per plant (TBD: cross-plant? CONF-EX-004 in §7.1.2).
- **Unit (output)**: kg/day, optionally display in t/day (rounded). Source: CONF-005.
- **Quantile (output)**: a single quantile selected by CONF-001.

#### §3.1.6 Formula candidate (NOT frozen — see §5)

The exact business semantic of "safety factor" is not yet chosen. The candidate set is:

- **(A) Utilization factor**: `required_capacity = demand / utilization_factor` (factor > 1 inflates demand, then capacity is the inflated demand).
- **(B) Reserve ratio**: `required_capacity = demand × (1 + reserve_ratio)` (reserve_ratio in [0, 1) inflates demand).
- **(C) Capacity derating**: `usable_capacity = nameplate_capacity × derating_factor` (derating_factor in (0, 1] derates an existing capacity downward).

The earlier `required_capacity = demand × 0.85` example conflates reserve and derating: it both shrinks the *demand* (by treating 0.85 as a utilization factor) and was described in prose as a 15% safety margin (which would be `1 + 0.15 = 1.15` under interpretation B). This contradiction must be resolved by Charles. The current `0.85` value is `NON_AUTHORITATIVE_MECHANICS_EXAMPLE` only.

Per §3.1.6, the C2 implementation may not select among (A), (B), (C) until Charles confirms the business semantic, the dimension semantics, and the corresponding source value. Until then, the formula is `CANDIDATE_FORMULA / BUSINESS_SOURCE_REQUIRED`.

#### §3.1.7 Pointer validation note

The earlier `0.85` example and the test cases built on it are `NON_AUTHORITATIVE_MECHANICS_EXAMPLE`. They are NOT evidence that a Charles-confirmed source value is `0.85`. They are not in the Golden. They do not constitute `CHARLES_CONFIRMED_SOURCE` or `APPROVED_AUDITABLE_SOURCE`.

#### §3.1.8 Threshold and comparison operator

- The only threshold in this category is `high_load_threshold_ratio` (resolved at `/peak/high_load_threshold_ratio` from `PeakMetricPolicy`). It is used **upstream** by Slice B to mark high-load days in the peak window; C2 does not redefine it. Source: `schemas.py::PeakMetricPolicy.high_load_threshold_ratio` — `RESOLVED_BY_MERGED_AUTHORITY`.
- C2 emits **no** new threshold for this category.

#### §3.1.9 Boundary / inclusivity

- The capacity value is `> 0` (or `0` if Q_in = 0). Negative values are upstream errors and produce `EVIDENCE_HASH_MISMATCH` (in `blocker_dependencies`) with `reason_code = UPSTREAM_BLOCKED`.
- Under interpretation (A), `utilization_factor > 0`. Under (B), `reserve_ratio in [0, 1)`. Under (C), `derating_factor in (0, 1]`. Each interpretation has different boundaries that Charles must confirm.

#### §3.1.10 Rounding mode and precision

- Rounding mode: cross-cutting policy (CONF-007 → see §7.1.2 cross-cutting normalization). Allowed values: `ROUND_HALF_UP`, `ROUND_HALF_EVEN`, `ROUND_FLOOR`, `ROUND_CEIL`.
- Precision: cross-cutting precision policy.
- Canonical serialization: `Decimal`-backed string, no scientific notation, no trailing zeros, no locale.

#### §3.1.11 Null/missing semantics

| Missing input | Effect |
|---|---|
| `/peak/peak_window_cumulative_quantity_kg/<QUANTILE_CHOSEN>` is `null` or path not resolvable | `REQUIRED_EVIDENCE_MISSING` in `blocker_dependencies`; `reason_code = REQUIRED_EVIDENCE_MISSING` (not `REQUIRED_THRESHOLD_MISSING`, per §3.0.3 single-reason rule) |
| `WINDOW_DAYS != 3` (engineering decision: NOT_APPLICABLE per the strict window policy) | `OUTSIDE_AUTHORIZED_SCOPE` → `NOT_APPLICABLE` (no `advisory_text`; no `blocker_dependencies`) |
| `SAFETY` (or selected semantic equivalent) missing | `RECOMMENDATION_THRESHOLD_MISSING` in `blocker_dependencies`; `reason_code = REQUIRED_THRESHOLD_MISSING` |
| `UNIT_OUT` / `PRECISION` / `ROUND_MODE` missing | `REQUIRED_THRESHOLD_MISSING` (if any one of the cross-cutting policies is missing) |
| Selected quantile (CONF-001) not yet confirmed | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` |

#### §3.1.12 APPLICABLE / NOT_APPLICABLE / BLOCKED conditions

| Condition set | Status | Reason code | Advisory text | Non-action |
|---|---|---|---|---|
| All applicable CONF items present + Q_in resolvable + WINDOW_DAYS == 3 + selected formula semantic confirmed | `APPLICABLE` | `RULE_APPLICABLE` | Template CONF-010 with computed capacity substituted (non-null) | `NO_AUTOMATIC_PROCESSING_CAPACITY_CHANGE` + `ADVISORY_ONLY_NO_AUTOMATIC_EXECUTION` |
| All applicable CONF present + WINDOW_DAYS != 3 | `NOT_APPLICABLE` | `OUTSIDE_AUTHORIZED_SCOPE` | `null` | same |
| Any required CONF missing (or selected formula semantic not yet chosen) | `BLOCKED` | `REQUIRED_THRESHOLD_MISSING` | `null` | same |
| Q_in not resolvable | `BLOCKED` | `REQUIRED_EVIDENCE_MISSING` | `null` | same |
| `Citation.agent_artifact_hash` does not match resolved value's hash | `BLOCKED` | `UPSTREAM_BLOCKED` (blocker code = `EVIDENCE_HASH_MISMATCH`) | `null` | same |
| Pointer escape / alias / case normalization / fuzzy attempted | `BLOCKED` | `UPSTREAM_BLOCKED` (blocker code = `EVIDENCE_FIELD_PATH_INVALID`) | `null` | same |
| Slice B blocked (e.g. `INSUFFICIENT_HISTORY`, `PEAK_POLICY_MISSING`) | `BLOCKED` | `UPSTREAM_BLOCKED` (preserve original blocker dependency verbatim in `blocker_dependencies`) | `null` | same |
| `RecommendationRulePolicy` or `rule_catalog` not loaded | `BLOCKED` | `POLICY_UNAVAILABLE` | `null` | same |

#### §3.1.13 Reason code / risk codes / confidence

- `reason_code`: per §3.0.3 (single scalar; per §3.1.12 mapping).
- `risk_codes` (when `APPLICABLE`): a deterministic subset drawn from CONF-009.
- `confidence`: `HIGH | MEDIUM | LOW | None`. Per C1 frozen: BLOCKED decisions use `confidence=None` and `confidence_boundary=None`. APPLICABLE confidence downgrade rule is `DESIGN_CONFIRMATION_REQUIRED` (cross-cutting).

#### §3.1.14 Advisory template

The advisory template (CONF-010 → cross-cutting template governance) is a deterministic versioned text. The C2 implementation MUST NOT add numbers beyond the three permitted placeholders (`Q_IN_KG`, `SAFETY_PCT`, `CAPACITY`) without amending the template. No LLM paraphrasing is permitted. Any attempt to embed additional numbers produces `POLICY_UNAVAILABLE`.

#### §3.1.15 Citation requirements

- Every `applicability_condition` whose result is `TRUE` MUST include a `Citation` whose `field_path` is an RFC 6901 JSON Pointer resolving to the value the rule consumed.
- The `Citation.agent_artifact_hash` MUST equal the SHA-256 of the canonical JSON of the resolved value.
- The `Citation.source_tasks` (list) MUST contain the producing TASK from `TASK_008`..`TASK_012` for value fields; `TASK_013` appears only in blocker metadata (no numerical authority envelope, per PR #100 body §"Evidence authority and sibling ownership").
- The `Citation.authorities` (list) MUST contain at least one typed authority envelope (`TASK_8_AUTHORITY`..`TASK_12_AUTHORITY`).

#### §3.1.16 Replay / hash surface

- `GenerateRecommendationsOutput.agent_recommendations_hash` includes the canonical capacity value, the `rule_id`, the `rule_catalog_hash`, and the `applicability_conditions` list. Two replays with identical inputs and identical policy/catalog identities MUST produce byte-identical `agent_recommendations_hash`.
- The rule catalog row for SUSTAINED_PROCESSING_CAPACITY is currently the C1 placeholder (`c1-blocked-sustained_processing_capacity` with `template_id="operational-source-required-v1"`). Its replacement with a real C2 rule row is C2-A acceptance gate Test C2-A-001.

#### §3.1.17 Required tests (this category)

| Test ID | Kind | Description | Acceptance |
|---|---|---|---|
| TEST-C2-001-01 | Unit | Mechanical mechanics test of the `sustained_processing_capacity` function with placeholder inputs only. | `PLANNED` (not yet run; mechanics example only — see §5) |
| TEST-C2-001-02 | Unit | Same with `UNIT_OUT = "t/day"`. | `PLANNED` |
| TEST-C2-001-03 | Unit | `WINDOW_DAYS = 5` returns `NOT_APPLICABLE / OUTSIDE_AUTHORIZED_SCOPE`. | `PLANNED` |
| TEST-C2-001-04 | Unit | `Q_in = 0` returns `Decimal("0")`. | `PLANNED` |
| TEST-C2-001-05 | Unit | `Q_in < 0` raises a typed evidence error and the recommendation stage maps it to a blocker with `EVIDENCE_HASH_MISMATCH`. | `PLANNED` |
| TEST-C2-001-06 | Unit | Missing safety-equivalent parameter returns `BLOCKED / REQUIRED_THRESHOLD_MISSING`. | `PLANNED` |
| TEST-C2-001-07 | Golden (C1 regression) | Updated `task013_slice_c_output.json` shows SUSTAINED_PROCESSING_CAPACITY with `status = BLOCKED`, `reason_code = REQUIRED_THRESHOLD_MISSING`, `advisory_text = null`. | `PASS` (C1 contract preserved; current Golden shows exactly this — see §11 verification) |
| TEST-C2-001-08 | Integration (PostgreSQL) | Real Postgres chain through Task 8 → Task 9 v2 → Task 10 → Slice B → C2 produces a byte-stable `agent_recommendations_hash` with SUSTAINED_PROCESSING_CAPACITY in `BLOCKED` state. | `PLANNED` (C1 acceptance proves the chain; C2-specific assertion is `BLOCKED_BY_DESIGN_CONFIRMATION` until §3.1.6 is resolved) |

> Per review 4694215238 P0-5: any test that has not actually been executed against the current Head is `PLANNED`, `BLOCKED_BY_BUSINESS_SOURCE`, or `BLOCKED_BY_DESIGN_CONFIRMATION`. `PASS` is reserved for tests that have actually run and been observed to pass. The C1 regression Golden test (TEST-C2-001-07) is the only one for which `PASS` is presently claimable, and only because the current C1 Golden already exhibits the expected `BLOCKED` state. Numeric examples (0.85, 0.9, 0.1, 50 kg/person/hour) used in the test descriptions are `NON_AUTHORITATIVE_MECHANICS_EXAMPLE`; they are not source values, not Golden values, and not production-wiring acceptance evidence.

---

### §3.2 RECEIVING_PEAK_CAPACITY

#### §3.2.1 Business purpose

Recommend an instantaneous receiving peak capacity (kg/hour) and a separate temporary-storage capacity (kg) and pre-cooling capacity (kg/hour) so the plant can absorb forecast arrivals at the peak window. The category emits three capacity values, each optional, and does not embed per-hour processing instructions.

#### §3.2.2 Allowed upstream fields

- `/peak/peak_window_cumulative_quantity_kg/{P50,P80,P90}` — sustained three-day window total.
- `/peak/peak_window_days_before`, `/peak/peak_window_days_after` — peak-window config.
- `/daily_curve/{day_index}/arrival_quantity_kg/{p50,p80,p90}` — daily arrival quantiles (before weather/Spring corrections).
- `/daily_curve/{day_index}/final_corrected_arrival_quantity_kg/{p50,p80,p90}` — corrected arrival quantiles.
- `PeakMetricPolicy` (already loaded by Slice B; per `BlockerCode.PEAK_POLICY_MISSING`).

#### §3.2.3 RFC 6901 JSON Pointer examples (currently authoritative)

```text
/peak/peak_window_cumulative_quantity_kg/P50
/peak/peak_window_cumulative_quantity_kg/P80
/peak/peak_window_cumulative_quantity_kg/P90
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
| Peak-window cumulative volumes (P50/P80/P90) | `PERSISTED_UPSTREAM_MODEL_OUTPUT` (Slice B) | typed `Task10Authority` | Slice B `peak_metric_policy_version` | Slice B `as_of` | Slice B `peak_metric_policy_config_hash` | `RESOLVED_BY_MERGED_AUTHORITY` |
| `/daily_curve/{i}/arrival_quantity_kg/{p50,p80,p90}` | `PERSISTED_UPSTREAM_MODEL_OUTPUT` (Slice B) | typed Task authority | Slice B `daily_curve_policy_version` (TBD on schema validation) | Slice B `as_of` | Slice B hash (TBD on schema validation) | `RESOLVED_BY_MERGED_AUTHORITY` (engine contract) / pointer resolution to be re-validated in C2-A against actual `ForecastDailyRow.arrival_quantity_kg` schema |
| Selected quantile for peak basis | `CHARLES_CONFIRMED_SOURCE` | `CONF-012` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Daily receiving operating hours | `APPROVED_AUDITABLE_SOURCE` | `CONF-013` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Turnover time at receiving dock (hours) | `APPROVED_AUDITABLE_SOURCE` | `CONF-014` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Temporary-storage physical capacity (kg) — physical maximum | `APPROVED_AUDITABLE_SOURCE` | `CONF-015` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Pre-cooling capacity (kg/hour) | `APPROVED_AUDITABLE_SOURCE` | `CONF-016` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Safety factor (receiving margin) | `CHARLES_CONFIRMED_SOURCE` | `CONF-017` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Output unit, precision, rounding, risk vocabulary, advisory template | n/a | n/a | n/a | n/a | n/a | `DESIGN_CONFIRMATION_REQUIRED` (cross-cutting; see §7.1.2) |

#### §3.2.5 Applicability and granularity

- **Applicable grain (time)**: per requested season × resolved location × resolved varieties.
- **Applicable grain (space)**: per plant (cross-plant grain: `DESIGN_CONFIRMATION_REQUIRED`, CONF-EX-004).
- **Output (candidate, not frozen)**: three capacity values — instantaneous receiving (kg/hour), temporary storage (kg), pre-cooling (kg/hour).

#### §3.2.6 Formula candidate (NOT frozen — see §5)

The earlier draft had four correctness issues (review 4694215238 P0-4 §2):

- `TURNOVER_H` was accepted as input but never used in the formula.
- `STORAGE_KG` was treated as the *required* storage; it must be the *available* storage. The required storage is a derived value (forecast peak × safety).
- `precool = min(physical_capacity, required_rate)` reports the lesser value; that hides a bottleneck rather than identifying it.
- The single composite output structure must be split into **requirement**, **available capacity**, **gap**, and **status** candidates.

The corrected candidate structure is:

```text
Inputs:
  PEAK_Q              := /peak/peak_window_cumulative_quantity_kg/<QUANTILE>/WINDOW_DAYS    (Decimal, kg/day)
  RECV_HOURS          := DAILY_RECEIVING_HOURS                                               (hours/day)   [CONF-013]
  TURNOVER_H          := TURNOVER_TIME                                                       (hours)       [CONF-014]
  STORAGE_AVAIL_KG    := TEMP_STORAGE_AVAILABILITY                                            (kg)          [CONF-015]
  PRECOOL_AVAIL_KGH   := PRECOOLING_AVAILABILITY_KG_PER_HOUR                                  (kg/hour)     [CONF-016]
  SAFETY              := RECEIVING_SAFETY_FACTOR                                             (Decimal)     [CONF-017]

Derived requirement candidates (formulas NOT frozen):
  instantaneous_required_kgph  = (PEAK_Q × SAFETY) / RECV_HOURS
  storage_required_kg          = PEAK_Q × SAFETY
  precool_required_kgph        = instantaneous_required_kgph

Available capacity (from sources):
  instantaneous_available_kgph = derived from PEAK_Q vs plant limits; TBD with Charles
  storage_available_kg         = STORAGE_AVAIL_KG
  precool_available_kgph       = PRECOOL_AVAIL_KGH

Output structure candidates (NOT frozen):
  - "requirement" alone (single value per capacity)
  - "available" alone
  - "gap = available - requirement" plus "APPLICABLE if gap >= 0, NOT_APPLICABLE if gap < 0"
  - "bottleneck identification": name the dimension with the smallest `available - requirement`
```

The final output structure is `DESIGN_CONFIRMATION_REQUIRED` (CONF-EX-005 in §7.1.2). The current `precool = min(available, required)` reporting is NOT a recommendation; it hides a bottleneck and is forbidden in C2.

#### §3.2.7 Threshold / boundary

- No new threshold. `high_load_threshold_ratio` from `PeakMetricPolicy` is upstream-only.
- Boundary: `instantaneous >= 0`, `storage >= 0`, `precool >= 0`. Negative is upstream error and produces `EVIDENCE_HASH_MISMATCH` in `blocker_dependencies`.

#### §3.2.8 Null / missing semantics

| Missing input | Effect |
|---|---|
| `PEAK_Q` not resolvable | `REQUIRED_EVIDENCE_MISSING` in `blocker_dependencies`; `reason_code = REQUIRED_EVIDENCE_MISSING` |
| `RECV_HOURS` missing (CONF-013) | `RECOMMENDATION_THRESHOLD_MISSING` in `blocker_dependencies`; `reason_code = REQUIRED_THRESHOLD_MISSING` |
| `TURNOVER_H` missing (CONF-014) | same |
| `STORAGE_AVAIL_KG` missing (CONF-015) | same |
| `PRECOOL_AVAIL_KGH` missing (CONF-016) | same |
| `SAFETY` missing (CONF-017) | same |
| Cross-cutting precision / rounding / template missing | `RECOMMENDATION_THRESHOLD_MISSING` (cross-cutting) |
| Selected quantile (CONF-012) not yet confirmed | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` |

#### §3.2.9 APPLICABLE / NOT_APPLICABLE / BLOCKED conditions

| Condition set | Status | Reason code | Advisory text | Non-action |
|---|---|---|---|---|
| All applicable CONF present + PEAK_Q resolvable + output structure confirmed by Charles | `APPLICABLE` | `RULE_APPLICABLE` | Template (cross-cutting) with three capacity values substituted | `NO_AUTOMATIC_RECEIVING_CAPACITY_CHANGE` + `ADVISORY_ONLY_NO_AUTOMATIC_EXECUTION` |
| All applicable CONF present + plant is not a receiving plant (CONF-EX-006) | `NOT_APPLICABLE` | `OUTSIDE_AUTHORIZED_SCOPE` | `null` | same |
| Any applicable CONF missing | `BLOCKED` | `REQUIRED_THRESHOLD_MISSING` | `null` | same |
| PEAK_Q not resolvable | `BLOCKED` | `REQUIRED_EVIDENCE_MISSING` | `null` | same |
| Citation hash mismatch | `BLOCKED` | `UPSTREAM_BLOCKED` (blocker code = `EVIDENCE_HASH_MISMATCH`) | `null` | same |
| Upstream blocked | `BLOCKED` | `UPSTREAM_BLOCKED` (preserve original blocker dependency verbatim) | `null` | same |
| Policy / catalog missing | `BLOCKED` | `POLICY_UNAVAILABLE` | `null` | same |

#### §3.2.10 Reason code / risk codes / confidence

- `reason_code`: per §3.0.3 (single scalar).
- `risk_codes` (when `APPLICABLE`): subset of cross-cutting risk vocabulary (CONF-EX-007).
- `confidence`: derived from Slice B confidence + source-level provenance.

#### §3.2.11 Advisory template

Template governance is cross-cutting (§7.1.2). The C2 implementation MUST NOT add numbers beyond the cross-cutting placeholder set without amending the template.

#### §3.2.12 Citation requirements

Same as §3.1.15. The peak-window cumulative volume `Citation.source_tasks` (list) contains `TASK_010` (Task 10 Prediction Run produces the cumulative peak).

#### §3.2.13 Replay / hash surface

Same as §3.1.16. Rule catalog row for RECEIVING_PEAK_CAPACITY is currently the C1 placeholder (`c1-blocked-receiving_peak_capacity` with `template_id="operational-source-required-v1"`). Its replacement is C2-A acceptance gate Test C2-A-002.

#### §3.2.14 Required tests (this category)

| Test ID | Kind | Description | Acceptance |
|---|---|---|---|
| TEST-C2-002-01..05 | Unit | Mechanical mechanics of the formula candidate. | `PLANNED` (mechanics example; not source value) |
| TEST-C2-002-06 | Golden (C1 regression) | Current `task013_slice_c_output.json` shows RECEIVING_PEAK_CAPACITY `BLOCKED / REQUIRED_THRESHOLD_MISSING / advisory_text = null`. | `PASS` (C1 contract preserved) |
| TEST-C2-002-07 | Integration (PostgreSQL) | Real chain produces stable hash with RECEIVING_PEAK_CAPACITY in `BLOCKED`. | `PLANNED` (C2-specific assertions `BLOCKED_BY_DESIGN_CONFIRMATION` until §3.2.6 structure is resolved) |

---

### §3.3 SHIFT_STAFFING

#### §3.3.1 Business purpose

Recommend a per-shift staffing headcount and a shift schedule that supports sustained processing capacity. The category emits a shift schedule (e.g. `1 / 2 / 3 shifts × N staff`) and a confidence level. The category does not assign individual people.

#### §3.3.2 Allowed upstream fields

- `/peak/peak_window_cumulative_quantity_kg/{P50,P80,P90}` — sustained throughput target.
- `/daily_curve/{day_index}/final_corrected_arrival_quantity_kg/{p50,p80,p90}` — daily arrival target.
- `/parameters/{index}/p50|p80_lower|p80_upper|p90` — persisted `ParameterEstimate` values, including `PRODUCTIVITY_PER_PERSON_KG_PER_HOUR` (CONF-018, persisted if available) and `ATTENDANCE_RATE` (CONF-019, persisted if available). RFC 6901 cannot search a list by `parameter_name`; see §3.0.7.

#### §3.3.3 RFC 6901 JSON Pointer examples (currently authoritative)

```text
/peak/peak_window_cumulative_quantity_kg/P80
/peak/peak_window_days_before
/peak/peak_window_days_after
/daily_curve/0/final_corrected_arrival_quantity_kg/p80
/daily_curve/14/final_corrected_arrival_quantity_kg/p50
/parameters/0/p50
/parameters/0/source_level
/parameters/1/p50
```

Pointer caveat: per §3.0.7, C2 must define a deterministic parameter-lookup step (CONF-EX-002) before using `/parameters/{parameter_name}/...` pointers. The above `/parameters/{index}/p50` form is conditional on CONF-EX-002 being resolved; until then, the lookup is a source capability gap and the category remains `BLOCKED`.

#### §3.3.4 Field-level source authority

| Field | Authority type | Source ID | Source version | Source effective date | Source hash | Status |
|---|---|---|---|---|---|---|
| Sustained throughput target | `PERSISTED_UPSTREAM_MODEL_OUTPUT` (Slice B) | typed `Task10Authority` | Slice B `peak_metric_policy_version` | Slice B `as_of` | Slice B hash | `RESOLVED_BY_MERGED_AUTHORITY` |
| `PRODUCTIVITY_PER_PERSON_KG_PER_HOUR` (if persisted) | `PERSISTED_UPSTREAM_MODEL_OUTPUT` (Task 8/9/10 parameter inference) | parameter `parameter_id` (via lookup step per §3.0.7) | parameter `prior_version` | parameter `as_of` | parameter citation hash | `RESOLVED_BY_MERGED_AUTHORITY` (engineering contract) / business value `BUSINESS_SOURCE_REQUIRED` until confirmed |
| `SHIFT_DURATION_HOURS` (nominal shift length, in hours) | `APPROVED_AUDITABLE_SOURCE` | `CONF-018` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| `EFFECTIVE_WORKING_HOURS_PER_SHIFT` (excluding breaks) | `APPROVED_AUDITABLE_SOURCE` | `CONF-019` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| `PRODUCTIVITY_PER_PERSON_KG_PER_HOUR` (explicit override, if not persisted) | `APPROVED_AUDITABLE_SOURCE` | `CONF-020` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| `ATTENDANCE_RATE` (per-shift attendance ratio) | `APPROVED_AUDITABLE_SOURCE` | `CONF-021` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| `PRODUCTIVITY_BY_ROLE` map (picker / sorter / packer / processor) | `APPROVED_AUDITABLE_SOURCE` | `CONF-022` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| `PEAK_PERSONNEL_BUFFER` | `CHARLES_CONFIRMED_SOURCE` | `CONF-023` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| `NUMBER_OF_SHIFTS_PER_DAY` (1/2/3) | `CHARLES_CONFIRMED_SOURCE` | `CONF-024` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Precision, rounding, risk vocabulary, advisory template | n/a | n/a | n/a | n/a | n/a | `DESIGN_CONFIRMATION_REQUIRED` (cross-cutting) |

#### §3.3.5 Applicability and granularity

- **Applicable grain (time)**: per requested season × resolved location × resolved varieties × forecast day (per-day headcount for the peak window).
- **Applicable grain (space)**: per plant × per shift role.

#### §3.3.6 Formula candidate (NOT frozen — see §5)

The earlier draft had two correctness issues (review 4694215238 P0-4 §3):

- Code permitted `BUFFER < 1` but prose said `BUFFER > 0.5` is forbidden. The boundary is `BUFFER in [0, 1)`. The text is corrected here; the code constant will be validated in C2-A.
- Effective working hours were conflated with nominal shift duration. They are now separate inputs (`SHIFT_DURATION_HOURS` vs `EFFECTIVE_WORKING_HOURS_PER_SHIFT`).
- `headcount` must use *effective* working hours, not nominal shift duration.
- `PRODUCTIVITY_BY_ROLE` (per-role productivity map) is a separate source row, distinct from the aggregate `PRODUCTIVITY_PER_PERSON_KG_PER_HOUR`.

The candidate formula:

```text
Inputs:
  TARGET_KG          := /peak/peak_window_cumulative_quantity_kg/<Q>/WINDOW_DAYS  (kg/day)
  SHIFT_HOURS        := SHIFT_DURATION_HOURS                                       (hours)         [CONF-018]
  EFF_HOURS          := EFFECTIVE_WORKING_HOURS_PER_SHIFT                          (hours)         [CONF-019]
  PROD_KGPH          := PRODUCTIVITY_PER_PERSON_KG_PER_HOUR                        (kg/p/h)        [CONF-020, or persisted parameter]
  PROD_BY_ROLE       := PRODUCTIVITY_BY_ROLE                                       (dict)          [CONF-022]
  ATTEND             := ATTENDANCE_RATE                                            (fraction)      [CONF-021]
  BUFFER             := PEAK_PERSONNEL_BUFFER                                      (fraction)      [CONF-023]
  NUM_SHIFTS         := NUMBER_OF_SHIFTS_PER_DAY                                   (int 1..3)      [CONF-024]

Derivation:
  raw = (TARGET_KG / EFF_HOURS) / (PROD_KGPH * ATTEND) * (1 + BUFFER)
  per_shift = ROUND(raw / NUM_SHIFTS)        # cross-cutting rounding mode
  total = per_shift * NUM_SHIFTS
```

`raw <= 0` is mapped to `BLOCKED / REQUIRED_EVIDENCE_MISSING` (per §3.0.3 single-reason rule). `raw > 0` but `TARGET_KG <= 0` is `NOT_APPLICABLE / CONDITIONS_NOT_MET`. The complete decision table must be re-derived in C2-A and re-confirmed here; the current decision table reflects the candidate only.

#### §3.3.7 Threshold / boundary

- `BUFFER in [0, 1)`. `BUFFER >= 1` is forbidden.
- `NUM_SHIFTS in {1, 2, 3}`. `NUM_SHIFTS = 4` is `OUTSIDE_AUTHORIZED_SCOPE` → `NOT_APPLICABLE`.
- `EFF_HOURS <= SHIFT_HOURS` (effective hours cannot exceed nominal).
- Output headcount is `>= 0`. `0` means no staff required (rare, e.g. very small forecast).

#### §3.3.8 Null / missing semantics

| Missing input | Effect |
|---|---|
| `TARGET_KG` not resolvable | `REQUIRED_EVIDENCE_MISSING`; `reason_code = REQUIRED_EVIDENCE_MISSING` |
| `SHIFT_HOURS` missing (CONF-018) | `REQUIRED_THRESHOLD_MISSING`; `reason_code = REQUIRED_THRESHOLD_MISSING` |
| `EFF_HOURS` missing (CONF-019) | `REQUIRED_THRESHOLD_MISSING` |
| `PROD_KGPH` missing AND no persisted parameter | `REQUIRED_THRESHOLD_MISSING` |
| `PROD_BY_ROLE` missing when role-based output is required | `REQUIRED_THRESHOLD_MISSING` |
| `ATTEND` missing (CONF-021) | `REQUIRED_THRESHOLD_MISSING` |
| `BUFFER` missing (CONF-023) | `REQUIRED_THRESHOLD_MISSING` |
| `NUM_SHIFTS` missing (CONF-024) | `REQUIRED_THRESHOLD_MISSING` |
| Cross-cutting precision / rounding / template missing | `REQUIRED_THRESHOLD_MISSING` |

#### §3.3.9 APPLICABLE / NOT_APPLICABLE / BLOCKED conditions

| Condition set | Status | Reason code | Advisory text | Non-action |
|---|---|---|---|---|
| All applicable CONF present + TARGET_KG resolvable + PROD_KGPH either persisted or from CONF-020 | `APPLICABLE` | `RULE_APPLICABLE` | Template (cross-cutting) with shift count and headcount substituted (non-null) | `NO_AUTOMATIC_SHIFT_STAFFING_ACTION` + `ADVISORY_ONLY_NO_AUTOMATIC_EXECUTION` |
| All applicable CONF present + plant has no shift operation (CONF-EX-008) | `NOT_APPLICABLE` | `OUTSIDE_AUTHORIZED_SCOPE` | `null` | same |
| Any applicable CONF missing | `BLOCKED` | `REQUIRED_THRESHOLD_MISSING` | `null` | same |
| `PRODUCTIVITY_PER_PERSON_KG_PER_HOUR` parameter not persisted AND no CONF-020 | `BLOCKED` | `REQUIRED_EVIDENCE_MISSING` (parameter) + `REQUIRED_THRESHOLD_MISSING` (CONF) | `null` | same |
| Upstream blocked | `BLOCKED` | `UPSTREAM_BLOCKED` | `null` | same |
| Citation hash mismatch | `BLOCKED` | `UPSTREAM_BLOCKED` (blocker code = `EVIDENCE_HASH_MISMATCH`) | `null` | same |

#### §3.3.10 Reason code / risk codes / confidence

- `reason_code`: per §3.0.3 (single scalar).
- `risk_codes` (when `APPLICABLE`): cross-cutting risk vocabulary.
- `confidence`: derived from parameter `source_level` and attendance-rate source provenance.

#### §3.3.11 Advisory template

Template governance is cross-cutting (§7.1.2).

#### §3.3.12 Citation requirements

Same as §3.1.15. Persisted parameter `Citation.source_tasks` (list) is `TASK_009` (Task 9 v2 harvest-state persistence) or `TASK_010` (Task 10 prediction run parameter inference).

#### §3.3.13 Replay / hash surface

Same as §3.1.16. Rule catalog row for SHIFT_STAFFING is currently the C1 placeholder (`c1-blocked-shift_staffing` with `template_id="operational-source-required-v1"`). Its replacement is C2-A acceptance gate Test C2-A-003.

#### §3.3.14 Required tests (this category)

| Test ID | Kind | Description | Acceptance |
|---|---|---|---|
| TEST-C2-003-01..05 | Unit | Mechanical mechanics with placeholder inputs only. | `PLANNED` (mechanics example; not source value) |
| TEST-C2-003-06 | Golden (C1 regression) | C1 Golden shows SHIFT_STAFFING `BLOCKED / REQUIRED_THRESHOLD_MISSING / advisory_text = null`. | `PASS` (C1 contract preserved) |
| TEST-C2-003-07 | Integration (PostgreSQL) | Real chain produces stable hash with SHIFT_STAFFING in `BLOCKED`. | `PLANNED` |

> Numeric examples in the test descriptions (`0.85`, `0.9`, `0.1`, `50 kg/person/hour`) are `NON_AUTHORITATIVE_MECHANICS_EXAMPLE`. The C1 regression Golden test is the only one for which `PASS` is presently claimable.

---

### §3.4 SPRING_FESTIVAL_STAFFING

#### §3.4.1 Business purpose

Recommend an adjusted staffing headcount and lead-time during the Spring Festival window (per-day `SpringFestivalPhase` ∈ `PRE | DURING | POST`), accounting for reduced picker availability and processor lead-time. The category does not pick individuals.

#### §3.4.2 Allowed upstream fields

- `/daily_curve/{day_index}/spring_festival_phase` — per-day phase.
- `/daily_curve/{day_index}/final_corrected_arrival_quantity_kg/{p50,p80,p90}` — daily corrected arrival.
- `/parameters/{index}/p50|p80_lower|p80_upper|p90` — persisted `ParameterEstimate` values, including `PICKER_AVAILABILITY_FACTOR` (CONF-025, persisted if available) and `PROCESSOR_AVAILABILITY_FACTOR` (CONF-026, persisted if available). RFC 6901 cannot search a list by `parameter_name`; see §3.0.7.
- `SPRING_FESTIVAL_CALENDAR_POLICY` (loaded by Slice B; per `BlockerCode.SPRING_FESTIVAL_CALENDAR_POLICY_MISSING`).

#### §3.4.3 RFC 6901 JSON Pointer examples (currently authoritative)

```text
/daily_curve/0/spring_festival_phase
/daily_curve/14/spring_festival_phase
/daily_curve/30/spring_festival_phase
/daily_curve/14/final_corrected_arrival_quantity_kg/p50
/parameters/0/p50
/parameters/1/p50
```

Pointer caveat: per §3.0.7, the `/parameters/{parameter_name}/...` form requires a parameter-lookup step (CONF-EX-002).

#### §3.4.4 Field-level source authority

| Field | Authority type | Source ID | Source version | Source effective date | Source hash | Status |
|---|---|---|---|---|---|---|
| Per-day `spring_festival_phase` | `PERSISTED_UPSTREAM_MODEL_OUTPUT` (Slice B) | typed Task authority | Slice B `spring_festival_calendar_policy_version` | Slice B `as_of` | Slice B `spring_festival_calendar_policy_config_hash` | `RESOLVED_BY_MERGED_AUTHORITY` |
| `PICKER_AVAILABILITY_FACTOR` (if persisted) | `PERSISTED_UPSTREAM_MODEL_OUTPUT` (Task 8/9/10) | parameter `parameter_id` (via lookup step per §3.0.7) | parameter `prior_version` | parameter `as_of` | parameter citation hash | `RESOLVED_BY_MERGED_AUTHORITY` (engineering contract) / business value `BUSINESS_SOURCE_REQUIRED` until confirmed |
| `PROCESSOR_AVAILABILITY_FACTOR` (if persisted) | same | same | same | same | same | same |
| `PICKER_AVAILABILITY_FACTOR` (explicit override, if not persisted) | `APPROVED_AUDITABLE_SOURCE` | `CONF-025` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| `PROCESSOR_AVAILABILITY_FACTOR` (explicit override, if not persisted) | `APPROVED_AUDITABLE_SOURCE` | `CONF-026` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| `PICKER_PRODUCTIVITY_KG_PER_HOUR` | `APPROVED_AUDITABLE_SOURCE` | `CONF-027` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| `PROCESSOR_PRODUCTIVITY_KG_PER_HOUR` | `APPROVED_AUDITABLE_SOURCE` | `CONF-028` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| `PICKER_AVAILABLE_HOURS_PER_DAY` | `APPROVED_AUDITABLE_SOURCE` | `CONF-029` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` (separate row per review 4694215238 P0-4 §4) |
| `PROCESSOR_AVAILABLE_HOURS_PER_DAY` | `APPROVED_AUDITABLE_SOURCE` | `CONF-030` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` (separate row per review 4694215238 P0-4 §4) |
| `PICKER_PRE_FESTIVAL_LEAD_DAYS` | `APPROVED_AUDITABLE_SOURCE` | `CONF-031` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| `PROCESSOR_DURING_FESTIVAL_LEAD_DAYS` | `APPROVED_AUDITABLE_SOURCE` | `CONF-032` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| `PICKER_POST_FESTIVAL_RECOVERY_DAYS` | `APPROVED_AUDITABLE_SOURCE` | `CONF-033` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Per-phase availability mapping `PRE / DURING / POST` | `CHARLES_CONFIRMED_SOURCE` | `CONF-034` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Precision, rounding, risk vocabulary, advisory template | n/a | n/a | n/a | n/a | n/a | `DESIGN_CONFIRMATION_REQUIRED` (cross-cutting) |

> Per review 4694215238 P0-4 §4: `PICKER_AVAILABLE_HOURS_PER_DAY` (CONF-029) and `PROCESSOR_AVAILABLE_HOURS_PER_DAY` (CONF-030) are now separate confirmation rows, distinct from productivity and availability factor.

#### §3.4.5 Applicability and granularity

- **Applicable grain (time)**: per forecast day within Spring Festival window (per `spring_festival_phase`).
- **Applicable grain (space)**: per plant × per role (picker / processor).
- **Output**: per-day headcount for pickers and processors, plus lead-time values.

#### §3.4.6 Formula candidate (NOT frozen — see §5)

For each day with `spring_festival_phase ∈ {PRE, DURING, POST}`:

```text
PHASE      := /daily_curve/{i}/spring_festival_phase
ARRIVAL_KG := /daily_curve/{i}/final_corrected_arrival_quantity_kg/p50
PICK_AVAIL := PICKER_AVAILABILITY_FACTOR[PHASE]      [CONF-025]
PROC_AVAIL := PROCESSOR_AVAILABILITY_FACTOR[PHASE]   [CONF-026]
PICK_PROD  := PICKER_PRODUCTIVITY_KG_PER_HOUR        [CONF-027]
PROC_PROD  := PROCESSOR_PRODUCTIVITY_KG_PER_HOUR     [CONF-028]
PICK_HRS   := PICKER_AVAILABLE_HOURS_PER_DAY         [CONF-029]
PROC_HRS   := PROCESSOR_AVAILABLE_HOURS_PER_DAY      [CONF-030]

pickers_needed    = ceil(ARRIVAL_KG / (PICK_PROD * PICK_AVAIL * PICK_HRS))
processors_needed = ceil(ARRIVAL_KG / (PROC_PROD * PROC_AVAIL * PROC_HRS))
```

Lead-time outputs (literal values from sources):
- `PRE_FESTIVAL_PICKER_LEAD_DAYS = PICKER_PRE_FESTIVAL_LEAD_DAYS` (CONF-031)
- `DURING_FESTIVAL_PROCESSOR_LEAD_DAYS = PROCESSOR_DURING_FESTIVAL_LEAD_DAYS` (CONF-032)
- `POST_FESTIVAL_PICKER_RECOVERY_DAYS = PICKER_POST_FESTIVAL_RECOVERY_DAYS` (CONF-033)

Five distinct concept rows are now separate: **availability factor** (CONF-025/026), **productivity** (CONF-027/028), **available working hours** (CONF-029/030), **lead days** (CONF-031/032), **recovery days** (CONF-033). The formula does not consume any parameter that is not in the source matrix.

#### §3.4.7 Null / missing semantics

| Missing input | Effect |
|---|---|
| `spring_festival_phase` is `NONE` for all days | `NOT_APPLICABLE` (no Spring Festival window) with `CONDITIONS_NOT_MET` |
| Any of CONF-025..CONF-034 missing | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` |
| `spring_festival_calendar_policy` missing from upstream | `UPSTREAM_BLOCKED` (preserve `SPRING_FESTIVAL_CALENDAR_POLICY_MISSING`) → `BLOCKED` |
| Phase not in {PRE, DURING, POST} | `OUTSIDE_AUTHORIZED_SCOPE` → `NOT_APPLICABLE` |

#### §3.4.8 APPLICABLE / NOT_APPLICABLE / BLOCKED conditions

| Condition set | Status | Reason code | Advisory text | Non-action |
|---|---|---|---|---|
| All applicable CONF present + at least one day with `spring_festival_phase ∈ {PRE, DURING, POST}` | `APPLICABLE` | `RULE_APPLICABLE` | Template (cross-cutting) with per-phase lead-times and per-day headcounts substituted (non-null) | `NO_AUTOMATIC_SPRING_FESTIVAL_STAFFING_ACTION` + `ADVISORY_ONLY_NO_AUTOMATIC_EXECUTION` |
| All applicable CONF present + no day in horizon has Spring Festival phase | `NOT_APPLICABLE` | `CONDITIONS_NOT_MET` | `null` | same |
| All applicable CONF present + at least one phase value outside {NONE, PRE, DURING, POST} | `NOT_APPLICABLE` | `OUTSIDE_AUTHORIZED_SCOPE` | `null` | same |
| Any applicable CONF missing | `BLOCKED` | `REQUIRED_THRESHOLD_MISSING` | `null` | same |
| Calendar policy missing | `BLOCKED` | `UPSTREAM_BLOCKED` (preserve `SPRING_FESTIVAL_CALENDAR_POLICY_MISSING`) | `null` | same |
| Citation hash mismatch | `BLOCKED` | `UPSTREAM_BLOCKED` (blocker code = `EVIDENCE_HASH_MISMATCH`) | `null` | same |

#### §3.4.9 Reason code / risk codes / confidence

- `reason_code`: per §3.0.3 (single scalar).
- `risk_codes` (when `APPLICABLE`): cross-cutting risk vocabulary.
- `confidence`: derived from parameter `source_level`.

#### §3.4.10 Advisory template

Template governance is cross-cutting (§7.1.2).

#### §3.4.11 Citation requirements

Same as §3.1.15. `spring_festival_calendar_policy_config_hash` is the `agent_artifact_hash` for the phase field.

#### §3.4.12 Replay / hash surface

Same as §3.1.16. Rule catalog row for SPRING_FESTIVAL_STAFFING is currently the C1 placeholder (`c1-blocked-spring_festival_staffing` with `template_id="operational-source-required-v1"`). Its replacement is C2-A acceptance gate Test C2-A-004.

#### §3.4.13 Required tests (this category)

| Test ID | Kind | Description | Acceptance |
|---|---|---|---|
| TEST-C2-004-01..05 | Unit | Mechanical mechanics with placeholder inputs only. | `PLANNED` |
| TEST-C2-004-06 | Golden (C1 regression) | C1 Golden shows SPRING_FESTIVAL_STAFFING `BLOCKED / REQUIRED_THRESHOLD_MISSING / advisory_text = null`. | `PASS` (C1 contract preserved) |
| TEST-C2-004-07 | Integration (PostgreSQL) | Real chain produces stable hash with SPRING_FESTIVAL_STAFFING in `BLOCKED`. | `PLANNED` |

---

### §3.5 VARIETY_STAGGER

#### §3.5.1 Business purpose

Identify whether forecast peak formation includes a variety-overlap component, and surface a `REVIEW_VARIETY_STAGGERING_REQUIRED` advisory if so. This category is **review-only** in C2. It MUST NOT emit pruning dates, area adjustments, batch splits, yield impacts, or any agronomic execution instructions. The only allowed `APPLICABLE` output is the review flag plus the variety-overlap evidence citation. The category does not compute or recommend agronomic actions; agronomic recommendations are explicitly out of C2 scope (Issue #99 §"Category hard boundaries and C2 blockers — VARIETY_STAGGER").

#### §3.5.2 Allowed upstream fields

- `/daily_curve/{day_index}/per_variety_contribution/{j}` — per-day, per-variety; `VarietyContribution` exposes `volume_kg_p50`, `volume_kg_p80`, `volume_kg_p90`, `contribution_rate_p50`, `contribution_rate_p80`, `contribution_rate_p90` (NOT `p50/p80/p90` alone, per review 4694215238 P0-2 §2). Array index `{j}` is the position in the `per_variety_contribution: list[VarietyContribution]` payload.
- `/daily_curve/{day_index}/final_corrected_arrival_quantity_kg/{p50,p80,p90}` — total arrival.

#### §3.5.3 RFC 6901 JSON Pointer examples (corrected per review 4694215238 P0-2)

```text
/daily_curve/0/per_variety_contribution/0/variety_id
/daily_curve/0/per_variety_contribution/0/volume_kg_p50
/daily_curve/0/per_variety_contribution/0/contribution_rate_p50
/daily_curve/7/per_variety_contribution/1/variety_id
/daily_curve/7/per_variety_contribution/1/volume_kg_p80
/daily_curve/7/per_variety_contribution/1/contribution_rate_p80
/daily_curve/14/per_variety_contribution/0/volume_kg_p50
```

> The earlier draft used `p50/p80/p90` (without the `volume_kg_` and `contribution_rate_` prefixes) on the `VarietyContribution` payload. The corrected pointers use the actual field names. The earlier form is invalid; the corrected form is the only one permitted.

#### §3.5.4 Field-level source authority

| Field | Authority type | Source ID | Source version | Source effective date | Source hash | Status |
|---|---|---|---|---|---|---|
| Per-variety daily contribution | `PERSISTED_UPSTREAM_MODEL_OUTPUT` (Slice B) | typed Task authority | Slice B `daily_curve_policy_version` (TBD on schema validation) | Slice B `as_of` | Slice B hash (TBD on schema validation) | `RESOLVED_BY_MERGED_AUTHORITY` (engineering contract) / pointer resolution re-validated in C2-A against actual `ForecastDailyRow.per_variety_contribution` schema |
| Selected quantile for overlap evaluation | `CHARLES_CONFIRMED_SOURCE` | `CONF-035` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Overlap window length (days) | `CHARLES_CONFIRMED_SOURCE` | `CONF-036` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Minimum number of varieties sharing the window | `CHARLES_CONFIRMED_SOURCE` | `CONF-037` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Minimum `contribution_rate` of a variety within the window | `CHARLES_CONFIRMED_SOURCE` | `CONF-038` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Action formula, action rounding | n/a (review-only) | n/a | n/a | n/a | n/a | `NOT_APPLICABLE` (Issue #99 §"VARIETY_STAGGER") |
| Risk vocabulary, advisory template | n/a | n/a | n/a | n/a | n/a | `DESIGN_CONFIRMATION_REQUIRED` (cross-cutting) |

#### §3.5.5 APPLICABLE / NOT_APPLICABLE / BLOCKED conditions (corrected per review 4694215238 P0-3)

| Condition set | Status | Reason code | Advisory text | Non-action |
|---|---|---|---|---|
| All applicable CONF present + at least one rolling window with `overlap_detected = True` | `APPLICABLE` | `RULE_APPLICABLE` | Template (cross-cutting) with the contributing variety list and window dates substituted (non-null) | `NO_AUTOMATIC_VARIETY_STAGGER_ACTION` + `ADVISORY_ONLY_NO_AUTOMATIC_EXECUTION` |
| All applicable CONF present + no rolling window meets overlap trigger | `NOT_APPLICABLE` | `CONDITIONS_NOT_MET` | `null` (validator forbids `APPLICABLE / advisory_text = null`; CONF-039 removed) | same |
| All applicable CONF present + season has only one variety | `NOT_APPLICABLE` | `CONDITIONS_NOT_MET` (no "stagger" to evaluate) | `null` | same |
| Any applicable CONF missing | `BLOCKED` | `REQUIRED_THRESHOLD_MISSING` | `null` | same |
| Upstream blocked | `BLOCKED` | `UPSTREAM_BLOCKED` | `null` | same |
| Citation hash mismatch | `BLOCKED` | `UPSTREAM_BLOCKED` (blocker code = `EVIDENCE_HASH_MISMATCH`) | `null` | same |

> Per review 4694215238 P0-3: the merged validator requires every `APPLICABLE` decision to have non-null `advisory_text`. CONF-039 and CONF-040 (the prior "APPLICABLE with advisory_text=null" choices) are removed and replaced by `NOT_APPLICABLE / CONDITIONS_NOT_MET` (now `RESOLVED_BY_MERGED_AUTHORITY`).

#### §3.5.6 Formula candidate (NOT frozen — see §5)

```python
def variety_stagger_overlap_detected(
    daily_curve,                  # list[ForecastDailyRow]
    selected_quantile: str,       # "P50" | "P80" | "P90"   [BUSINESS_SOURCE_REQUIRED — CONF-035]
    window_days: int,             # >= 1                    [BUSINESS_SOURCE_REQUIRED — CONF-036]
    min_varieties: int,           # >= 2                    [BUSINESS_SOURCE_REQUIRED — CONF-037]
    min_contribution_rate: Decimal,# in (0, 1)              [BUSINESS_SOURCE_REQUIRED — CONF-038]
) -> dict:
    # For each rolling window of size `window_days` in `daily_curve`:
    #   collect (variety_id, contribution_rate_<selected_quantile>) pairs
    #   if len(unique varieties) >= min_varieties AND every variety has contribution_rate >= min_contribution_rate:
    #     overlap = True
    #     contributing_varieties = sorted list of variety_ids (lexical ascending)
    #     break
    # else: overlap = False
    # return {"overlap_detected": overlap, "contributing_varieties": contributing_varieties, "quantile": selected_quantile}
    ...
```

If `overlap_detected = True` AND all CONF present → `APPLICABLE` with non-null `advisory_text`. Otherwise `NOT_APPLICABLE / CONDITIONS_NOT_MET` (no APPLICABLE-with-null-advisory path).

#### §3.5.7 Threshold / boundary

- `window_days >= 1` (sanity).
- `min_varieties >= 2` (must have at least two varieties to talk about "stagger").
- `min_contribution_rate in (0, 1)` (excludes 0 and 1).

#### §3.5.8 Citation requirements

Each `per_variety_contribution` in the overlap window must have a `Citation` whose `field_path` is the corrected pointer (§3.5.3), whose `agent_artifact_hash` matches, and whose `source_tasks` (list) contains `TASK_010` (Task 10 prediction run).

#### §3.5.9 Replay / hash surface

Same as §3.1.16. Rule catalog row for VARIETY_STAGGER is currently the C1 placeholder (`c1-blocked-variety_stagger` with `template_id="operational-source-required-v1"`). Its replacement is C2-A acceptance gate Test C2-A-005.

#### §3.5.10 Required tests (this category)

| Test ID | Kind | Description | Acceptance |
|---|---|---|---|
| TEST-C2-005-01..06 | Unit | Mechanical mechanics with placeholder inputs only. | `PLANNED` |
| TEST-C2-005-07 | Golden (C1 regression) | C1 Golden shows VARIETY_STAGGER `BLOCKED / REQUIRED_THRESHOLD_MISSING / advisory_text = null`. | `PASS` (C1 contract preserved) |
| TEST-C2-005-08 | Integration (PostgreSQL) | Real chain produces stable hash with VARIETY_STAGGER in `BLOCKED`. | `PLANNED` |

---

### §3.6 CROSS_PLANT_DISPATCH

#### §3.6.1 Business purpose

Identify whether a plant's projected peak exceeds a Charles-confirmed current-capacity trigger, and surface a `REVIEW_CROSS_PLANT_DISPATCH_REQUIRED` advisory if so. This category is **review-only** in C2. It MUST NOT query, compare, rank, or select another factory; create quantities, vehicles, routes, or plans; or cross tenant/farm/permission boundaries. The only allowed `APPLICABLE` output is the review flag plus the current-capacity evidence citation. The category does not compute or recommend cross-plant actions; cross-plant actions are explicitly out of C2 scope (Issue #99 §"Category hard boundaries and C2 blockers — CROSS_PLANT_DISPATCH").

#### §3.6.2 Allowed upstream fields

- `/peak/peak_window_cumulative_quantity_kg/{P50,P80,P90}` — sustained three-day peak.
- `/peak/peak_window_days_before`, `/peak/peak_window_days_after` — peak-window config.

> The earlier `single_day_peak/{P50,P80,P90}/volume_kg` pointer is from Issue #99 example but does not match the merged `ForecastPeakOutput` schema. The exact pointer must be re-validated against the current schema (CONF-EX-009).

#### §3.6.3 RFC 6901 JSON Pointer examples (currently authoritative)

```text
/peak/peak_window_cumulative_quantity_kg/P50
/peak/peak_window_cumulative_quantity_kg/P80
/peak/peak_window_cumulative_quantity_kg/P90
/peak/peak_window_days_before
/peak/peak_window_days_after
```

#### §3.6.4 Field-level source authority

| Field | Authority type | Source ID | Source version | Source effective date | Source hash | Status |
|---|---|---|---|---|---|---|
| Peak window cumulative volumes | `PERSISTED_UPSTREAM_MODEL_OUTPUT` (Slice B) | typed `Task10Authority` | Slice B `peak_metric_policy_version` | Slice B `as_of` | Slice B hash | `RESOLVED_BY_MERGED_AUTHORITY` |
| Selected quantile for trigger comparison | `CHARLES_CONFIRMED_SOURCE` | `CONF-041` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Current factory capacity (kg/day, named by plant) | `APPROVED_AUDITABLE_SOURCE` | `CONF-042` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Capacity safety factor (fraction of current capacity considered "trigger") | `CHARLES_CONFIRMED_SOURCE` | `CONF-043` | TBD | TBD | TBD | `BUSINESS_SOURCE_REQUIRED` |
| Trigger comparison operator (`>` vs `>=`) | n/a | `CONF-EX-010` | TBD | TBD | TBD | `DESIGN_CONFIRMATION_REQUIRED` |
| Cross-plant radius, transport time, transport loss, receiving factory remaining capacity, dispatch priority | n/a (review-only) | n/a | n/a | n/a | n/a | `NOT_APPLICABLE` (Issue #99 §"CROSS_PLANT_DISPATCH") |
| Risk vocabulary, advisory template | n/a | n/a | n/a | n/a | n/a | `DESIGN_CONFIRMATION_REQUIRED` (cross-cutting) |

#### §3.6.5 Boundary (corrected per review 4694215238 P0-4 §5)

- `trigger_ratio in (0, 1]`. `trigger_ratio = 1.0` means "trigger when peak equals capacity" (`>=` operator). `trigger_ratio = 0.9` means "trigger when peak reaches 90% of capacity" (still `>=` for the 0.9 threshold; the `>` operator is a separate `DESIGN_CONFIRMATION_REQUIRED` item).
- `current_capacity_kg_per_day > 0`. `current_capacity_kg_per_day = 0` is `OUTSIDE_AUTHORIZED_SCOPE` → `NOT_APPLICABLE` (consistent across function skeleton, null semantics, decision table, and test plan).

#### §3.6.6 Formula candidate (NOT frozen — see §5)

```python
def cross_plant_dispatch_trigger(
    peak_volume_kg_per_day: Decimal,            # /peak/peak_window_cumulative_quantity_kg/<Q>/WINDOW_DAYS
    current_capacity_kg_per_day: Decimal,      # [BUSINESS_SOURCE_REQUIRED — CONF-042]
    trigger_ratio: Decimal,                     # in (0, 1]   [BUSINESS_SOURCE_REQUIRED — CONF-043]
    operator: str,                              # ">=" | ">"   [DESIGN_CONFIRMATION_REQUIRED — CONF-EX-010]
) -> dict:
    if peak_volume_kg_per_day <= 0 or current_capacity_kg_per_day <= 0:
        raise ValueError("REQUIRED_EVIDENCE_MISSING")
    if not (Decimal("0") < trigger_ratio <= Decimal("1")):
        raise ValueError("REQUIRED_THRESHOLD_MISSING")
    threshold = current_capacity_kg_per_day * trigger_ratio
    if operator == ">=":
        triggered = peak_volume_kg_per_day >= threshold
    elif operator == ">":
        triggered = peak_volume_kg_per_day > threshold
    else:
        raise ValueError("OUTSIDE_AUTHORIZED_SCOPE")
    return {
        "triggered": triggered,
        "threshold_kg_per_day": threshold,
        "peak_kg_per_day": peak_volume_kg_per_day,
        "operator": operator,
    }
```

The `operator` is a frozen contract element per `DESIGN_CONFIRMATION_REQUIRED` (CONF-EX-010). Until confirmed, the C2 implementation is `BLOCKED` with `REQUIRED_THRESHOLD_MISSING`.

#### §3.6.7 Null / missing semantics

| Missing input | Effect |
|---|---|
| `peak_volume_kg_per_day` not resolvable | `REQUIRED_EVIDENCE_MISSING` → `BLOCKED` |
| `current_capacity_kg_per_day` missing (CONF-042) | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` |
| `trigger_ratio` missing (CONF-043) | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` |
| `operator` not confirmed (CONF-EX-010) | `REQUIRED_THRESHOLD_MISSING` → `BLOCKED` |
| `current_capacity_kg_per_day = 0` | `OUTSIDE_AUTHORIZED_SCOPE` → `NOT_APPLICABLE` |
| `peak_volume_kg_per_day = 0` | `CONDITIONS_NOT_MET` → `NOT_APPLICABLE` (no peak to dispatch) |

#### §3.6.8 APPLICABLE / NOT_APPLICABLE / BLOCKED conditions (corrected per review 4694215238 P0-3)

| Condition set | Status | Reason code | Advisory text | Non-action |
|---|---|---|---|---|
| All applicable CONF present + `triggered = True` | `APPLICABLE` | `RULE_APPLICABLE` | Template (cross-cutting) with peak and threshold substituted (non-null) | `NO_AUTOMATIC_CROSS_PLANT_DISPATCH` + `ADVISORY_ONLY_NO_AUTOMATIC_EXECUTION` |
| All applicable CONF present + `triggered = False` | `NOT_APPLICABLE` | `CONDITIONS_NOT_MET` | `null` (validator forbids `APPLICABLE / advisory_text = null`; CONF-044 removed) | same |
| All applicable CONF present + `current_capacity_kg_per_day = 0` | `NOT_APPLICABLE` | `OUTSIDE_AUTHORIZED_SCOPE` | `null` | same |
| Any applicable CONF missing (or `operator` not confirmed) | `BLOCKED` | `REQUIRED_THRESHOLD_MISSING` | `null` | same |
| Citation hash mismatch | `BLOCKED` | `UPSTREAM_BLOCKED` (blocker code = `EVIDENCE_HASH_MISMATCH`) | `null` | same |
| Upstream blocked | `BLOCKED` | `UPSTREAM_BLOCKED` (preserve original blocker dependency verbatim) | `null` | same |

> Per review 4694215238 P0-3: CONF-044 (the prior "APPLICABLE with advisory_text=null" choice) is removed. The no-trigger outcome is `NOT_APPLICABLE / CONDITIONS_NOT_MET` (now `RESOLVED_BY_MERGED_AUTHORITY`).

#### §3.6.9 Reason code / risk codes / confidence

- `reason_code`: per §3.0.3 (single scalar).
- `risk_codes` (when `APPLICABLE`): cross-cutting risk vocabulary.
- `confidence`: derived from `current_capacity_kg_per_day` source provenance and Slice B confidence.

#### §3.6.10 Advisory template

Template governance is cross-cutting (§7.1.2). The advisory MUST NOT contain destination factory, route, transport time, loss percentage, or quantity dispatched.

#### §3.6.11 Citation requirements

`peak_volume` `Citation.source_tasks` (list) contains `TASK_010`. `current_capacity_kg_per_day` `Citation` must include `source_id = CONF-042`, `source_version`, `source_effective_date`, `source_hash` once Charles provides them.

#### §3.6.12 Replay / hash surface

Same as §3.1.16. Rule catalog row for CROSS_PLANT_DISPATCH is currently the C1 placeholder (`c1-blocked-cross_plant_dispatch` with `template_id="operational-source-required-v1"`). Its replacement is C2-A acceptance gate Test C2-A-006.

#### §3.6.13 Required tests (this category)

| Test ID | Kind | Description | Acceptance |
|---|---|---|---|
| TEST-C2-006-01..05 | Unit | Mechanical mechanics with placeholder inputs only. | `PLANNED` |
| TEST-C2-006-06 | Golden (C1 regression) | C1 Golden shows CROSS_PLANT_DISPATCH `BLOCKED / REQUIRED_THRESHOLD_MISSING / advisory_text = null`. | `PASS` (C1 contract preserved) |
| TEST-C2-006-07 | Integration (PostgreSQL) | Real chain produces stable hash with CROSS_PLANT_DISPATCH in `BLOCKED`. | `PLANNED` |

---

## §4 Forbidden-to-assume critical parameters

This section enumerates every critical business parameter that has been named in the codebase or spec but for which **no Charles source has been provided**. Each row is `BUSINESS_SOURCE_REQUIRED` and blocks C2 activation of the corresponding category. Filling any of these with a "reasonable default" is a hard rule violation.

| # | Parameter | Current code presence | Required source | Blocks C2 category | Linked CONF ID |
|---:|---|---|---|---|---|
| 1 | Daily sustained processing capacity (kg/day) | NOT in code; only "peak volume" Slice B output | Production standard or Charles | SUSTAINED_PROCESSING_CAPACITY | CONF-001..CONF-007 |
| 2 | Single-day receiving peak capacity (kg/day) | NOT in code | Production standard or Charles | RECEIVING_PEAK_CAPACITY | CONF-012 |
| 3 | Safety / reserve / utilization factor (semantic not yet chosen) | NOT in code | Production standard | SUSTAINED_PROCESSING_CAPACITY, RECEIVING_PEAK_CAPACITY | CONF-004, CONF-017 |
| 4 | Nominal shift duration (hours per shift) | NOT in code | Production standard | SHIFT_STAFFING | CONF-018 |
| 5 | Effective working hours per shift (excluding breaks) | NOT in code | Production standard | SHIFT_STAFFING | CONF-019 |
| 6 | Staff attendance rate (fraction) | NOT in code; only `staffing_override_value` as user input | Production standard | SHIFT_STAFFING | CONF-021 |
| 7 | Per-role productivity (picker, sorter, packer, processor) | NOT in code | Production standard | SHIFT_STAFFING, SPRING_FESTIVAL_STAFFING | CONF-020, CONF-022, CONF-027, CONF-028 |
| 8 | Peak-period personnel buffer (fraction) | NOT in code | Charles | SHIFT_STAFFING | CONF-023 |
| 9 | Spring Festival per-phase picker/processor availability factor | NOT in code | Charles | SPRING_FESTIVAL_STAFFING | CONF-025, CONF-026, CONF-034 |
| 10 | Receiving dock turnover time (hours) | NOT in code | Production standard | RECEIVING_PEAK_CAPACITY | CONF-014 |
| 11 | Daily receiving operating hours | NOT in code | Production standard | RECEIVING_PEAK_CAPACITY | CONF-013 |
| 12 | Temporary storage physical capacity (kg, *available*) | NOT in code | Production standard | RECEIVING_PEAK_CAPACITY | CONF-015 |
| 13 | Pre-cooling capacity (kg/hour, *available*) | NOT in code | Production standard | RECEIVING_PEAK_CAPACITY | CONF-016 |
| 14 | Variety stagger overlap window length, min variety count, min contribution rate | NOT in code | Charles | VARIETY_STAGGER | CONF-036, CONF-037, CONF-038 |
| 15 | Cross-variety maturity offset days | NOT in code; only `per_variety_contribution.volume_kg_*` quantities | Charles | (VARIETY_STAGGER review-only; not consumed) | n/a (not a C2 input) |
| 16 | Cross-plant dispatch radius (km) | NOT in code | Production standard | (CROSS_PLANT_DISPATCH review-only; not consumed) | n/a (not a C2 input) |
| 17 | Cross-plant transport time (hours) | NOT in code | Production standard | (not consumed) | n/a (not a C2 input) |
| 18 | Cross-plant transport loss (fraction) | NOT in code | Production standard | (not consumed) | n/a (not a C2 input) |
| 19 | Receiving factory remaining capacity (kg/day) | NOT in code | Production standard | (not consumed) | n/a (not a C2 input) |
| 20 | Sending factory trigger ratio (fraction of current capacity) | NOT in code | Charles | CROSS_PLANT_DISPATCH | CONF-043 |
| 21 | Cross-plant trigger comparison operator (`>` vs `>=`) | NOT in code | Charles | CROSS_PLANT_DISPATCH | CONF-EX-010 |
| 22 | Picker/processor available working hours per day | NOT in code (separate row per review 4694215238 P0-4 §4) | Production standard | SPRING_FESTIVAL_STAFFING | CONF-029, CONF-030 |
| 23 | Spring Festival lead days (pre / during / post) | NOT in code | Production standard | SPRING_FESTIVAL_STAFFING | CONF-031, CONF-032, CONF-033 |
| 24 | Business rounding mode | NOT in code | Charles (cross-cutting) | All 6 categories | cross-cutting CONF-EX-007..CONF-EX-009 |
| 25 | Business rounding precision (decimal digits) | NOT in code | Charles (cross-cutting) | All 6 categories | cross-cutting |
| 26 | Advisory template wording and version | NOT in code | Charles (cross-cutting) | All 6 categories | cross-cutting |
| 27 | Risk code vocabulary and trigger thresholds | NOT in code | Charles (cross-cutting) | All 6 categories | cross-cutting |
| 28 | Confidence downgrade presentation rule | NOT in code (C1 BLOCKED decisions use `confidence=None`) | Charles (cross-cutting) | All 6 categories | cross-cutting |

**All 28 rows are `BUSINESS_SOURCE_REQUIRED`. No row may be filled with a heuristic, default, or industry average.**

### §4.1 Anti-default policy

- "Reasonable default" is **forbidden** in C2 source definition.
- "Industry average" is **forbidden** in C2 source definition.
- "Rule of thumb" is **forbidden** in C2 source definition.
- "Web-sourced typical value" is **forbidden** in C2 source definition.
- "LLM-inferred value" is **forbidden** in C2 source definition.
- "Inferred from current output" is **forbidden** in C2 source definition.
- "Inferred from history" is **forbidden** in C2 source definition unless that history is a persisted, integrity-validated upstream model output cited via `Citation` (rank 3 in §2.1).

Any of the above in a rule catalog row produces `POLICY_UNAVAILABLE` at runtime and a `RECOMMENDATION_RULE_MISSING` blocker for that category.

### §4.2 Mechanics example policy

Numeric values used in formula mechanics examples (e.g. `0.85`, `0.9`, `0.1`, `50 kg/person/hour`, `120000 kg`, `2 hours`, `10000 kg/day`) are `NON_AUTHORITATIVE_MECHANICS_EXAMPLE`. They:

- are NOT a Charles source;
- are NOT a business default;
- are NOT in the Golden;
- are NOT in production-wiring acceptance;
- do NOT constitute `CHARLES_CONFIRMED_SOURCE` or `APPROVED_AUDITABLE_SOURCE`.

Mechanical unit tests may use these values, but they must be named `NON_AUTHORITATIVE_TEST_FIXTURE` and must NOT flow through production wiring, the Golden, or persisted authority.

---

## §5 Formula contract

### §5.1 CANDIDATE vs FROZEN

Every formula in §3 falls into one of two classes:

- **`CANDIDATE_FORMULA`** — the formula is documented for review and C2-A implementation, but its inputs, dimensions, business interpretation, boundary operator, and output meaning are NOT frozen. The formula may not be implemented in production until Charles confirms all required source rows.
- **`FROZEN_FORMULA`** — the formula is fully frozen, its source rows are confirmed, and the implementation may run with `APPLICABLE` decisions. No formula in this document is currently `FROZEN_FORMULA`; all are `CANDIDATE_FORMULA / BUSINESS_SOURCE_REQUIRED` (or `DESIGN_CONFIRMATION_REQUIRED` for the cross-cutting policies).

### §5.2 Machine-executable form requirement

Every `CANDIDATE_FORMULA` is expressed in a Python pseudocode form that names:

- input variable (typed, with unit and required source);
- output variable (typed, with unit);
- intermediate quantity (typed, with unit);
- the dimension check that validates unit consistency;
- the missing-input raise;
- the zero / negative / null handling;
- the rounding step (single `quantize` at the end);
- the canonical serialization (Decimal-string).

C2-A implementation MUST lift these pseudocode functions to the actual rule catalog without changing the dimension semantics.

### §5.3 Input variable and unit contract

| Variable | Type | Unit (input) | Required citation | Allowed sources |
|---|---|---|---|---|
| Peak window cumulative volume | DecimalString | kg | Yes | `/peak/peak_window_cumulative_quantity_kg/{P50,P80,P90}` |
| Daily arrival quantiles | DecimalString | kg | Yes | `/daily_curve/{i}/final_corrected_arrival_quantity_kg/{p50,p80,p90}` |
| Spring Festival phase | Str (enum) | — | Yes | `/daily_curve/{i}/spring_festival_phase` |
| Per-variety contribution rate | DecimalString | fraction [0, 1] | Yes | `/daily_curve/{i}/per_variety_contribution/{j}/contribution_rate_{p50,p80,p90}` |
| Per-variety volume | DecimalString | kg | Yes | `/daily_curve/{i}/per_variety_contribution/{j}/volume_kg_{p50,p80,p90}` |
| Productivity per person | DecimalString | kg/person/hour | Yes (if persisted parameter, see §3.0.7) or `CONF-020` (if not) | `ParameterEstimate` (via lookup step) or Charles |
| Attendance rate | DecimalString | fraction (0, 1] | Yes | `CONF-021` |
| Nominal shift duration | DecimalString | hours | Yes | `CONF-018` |
| Effective working hours per shift | DecimalString | hours | Yes | `CONF-019` |
| Personnel buffer | DecimalString | fraction [0, 1) | Yes | `CONF-023` |
| Number of shifts | Int | {1, 2, 3} | Yes | `CONF-024` |
| Picker/processor availability | DecimalString | fraction (0, 1] | Yes | `CONF-025/CONF-026` (or persisted parameter) |
| Picker/processor available hours per day | DecimalString | hours | Yes | `CONF-029/CONF-030` |
| Receiving hours per day | Int | hours | Yes | `CONF-013` |
| Turnover time | DecimalString | hours | Yes | `CONF-014` |
| Storage availability (kg) | DecimalString | kg | Yes | `CONF-015` |
| Pre-cooling availability (kg/hour) | DecimalString | kg/hour | Yes | `CONF-016` |
| Safety / reserve / utilization factor | DecimalString | depends on semantic (A)/(B)/(C) | Yes | `CONF-004/CONF-017` |
| Trigger ratio | DecimalString | fraction (0, 1] | Yes | `CONF-043` |
| Trigger operator | Str | ">=" \| ">" | n/a (engineering contract) | `CONF-EX-010` |
| Overlap window length | Int | days | Yes | `CONF-036` |
| Min varieties | Int | >= 2 | Yes | `CONF-037` |
| Min contribution rate | DecimalString | fraction (0, 1) | Yes | `CONF-038` |
| Current capacity (kg/day) | DecimalString | kg/day | Yes | `CONF-042` |

### §5.4 Output unit and dimension consistency

- All output values carrying a unit MUST be expressed in a unit selected from §5.3's "Unit (input)" column or a unit derived by simple scalar conversion (e.g. kg → t, kg/day → kg/hour, hours/day → hours).
- A formula whose output unit does not match the declared output unit produces `EVIDENCE_HASH_MISMATCH` (in `blocker_dependencies`) with `reason_code = UPSTREAM_BLOCKED`.
- The dimension check is unit-testable: for each formula, a test asserts the output unit for one valid input. The assertion is symbolic (the test fixture names the expected unit string), not numeric.

### §5.5 Missing input handling

- If a required input is `null` or its JSON Pointer does not resolve, the formula raises `ValueError` with a code that the recommendation stage maps to a typed `Blocker`. The `reason_code` follows §3.0.3: `REQUIRED_EVIDENCE_MISSING` for pointer / value resolution failure, `REQUIRED_THRESHOLD_MISSING` for source-row absence.

### §5.6 Zero handling

- A zero input is allowed for any positive-type variable except the safety / reserve / utilization factor, the attendance rate, the productivity, and the current capacity. A zero productivity, attendance rate, or current capacity is a configuration error and produces `REQUIRED_THRESHOLD_MISSING` → `BLOCKED`.
- A zero input on a quantity produces a zero output (no special handling; rounding mode applies as usual; `Decimal("0")` does not need to be rounded).
- `raw <= 0` in §3.3.6 (staffing) is `BLOCKED / REQUIRED_EVIDENCE_MISSING`. `raw > 0` but `TARGET_KG <= 0` is `NOT_APPLICABLE / CONDITIONS_NOT_MET`.

### §5.7 Negative prohibition

- A negative input on any positive-type variable is a config error or upstream error. It is NOT mapped to `NOT_APPLICABLE`. It is mapped to `EVIDENCE_HASH_MISMATCH` (in `blocker_dependencies`) with `reason_code = UPSTREAM_BLOCKED`.
- The formula MUST raise `ValueError` with a code that the recommendation stage maps to a typed blocker.

### §5.8 Time range contract

- All formulas operate on the per-request forecast horizon (as supplied by Slice B). The horizon is NOT a C2 input. The category only iterates over the days in the horizon that satisfy the category's preconditions (e.g. Spring Festival phase ∈ {PRE, DURING, POST} for SPRING_FESTIVAL_STAFFING).
- A formula that depends on a future date beyond the horizon (e.g. a "next year's variety stagger") is `OUTSIDE_AUTHORIZED_SCOPE` → `NOT_APPLICABLE`.

### §5.9 Quantile usage rules

- A single formula MUST NOT mix quantiles across its input set unless explicitly designed to. Example: a formula that takes `peak = P80` MUST NOT internally use `arrival = P50` and then label the output as "P80-based". The label MUST match the input quantile.
- Cross-quantile mixing is **forbidden by default** (`RESOLVED_BY_MERGED_AUTHORITY` for the default rule). Allowing cross-quantile mixing requires a future amendment with explicit Charles authorization.
- `P50 / P80 / P90` selection itself is `BUSINESS_SOURCE_REQUIRED` (CONF-001 / CONF-012 / CONF-035 / CONF-041) for the operational category.

### §5.10 Rounding order

- For a formula with multiple intermediate quantities, the rounding order is: (1) convert to canonical `Decimal`; (2) compute raw value at full precision; (3) apply unit conversion at full precision; (4) apply the final `quantize` with the chosen `ROUND_MODE` and `PRECISION` ONCE on the final value. Intermediate quantities are NOT rounded.
- This rule prevents the "double rounding" error where two sequential `quantize` calls produce a different result than a single `quantize` on the final value.

### §5.11 Canonical serialization

- All numeric values are stored and emitted as `DecimalString` (per `schemas.py::DecimalString`). No `float` is permitted in production code paths (C1 contract per PR #100).
- All string values use deterministic, NFC-normalized UTF-8 encoding.
- All enum-like values are emitted as the `Enum.value` string, not the `Enum.name`.
- All Citation JSON is canonicalized per `schemas.py::Citation` (stable field order, no extra keys).
- The hash surface excludes runtime timestamps, database-generated IDs, hosts, paths, environment-specific values, unordered sets, and nondeterministically ordered mappings. Source: Issue #99 §"Policy schemas, identifiers, and canonical hashes".

### §5.12 Forbidden operations

- `float(...)` on any production code path.
- `math.ceil`, `math.floor`, `round(...)` on any production code path. Use `Decimal.quantize(...)` with the chosen `ROUND_MODE`.
- `random.*` in any production code path.
- `datetime.now()`, `time.time()`, `uuid.uuid4()` in any production code path.
- `requests.*`, `httpx.*`, `urllib.*` from production code paths.
- `openai.*`, `anthropic.*`, `langchain.*`, or any LLM SDK import.

### §5.13 Sourcing rule for hash surfaces

- The `agent_recommendations_hash` and `rule_catalog_hash` are computed from the canonical rule catalog content; they are never manually assigned.
- The `Citation.agent_artifact_hash` is computed from the canonical JSON of the cited value; it is never manually assigned.

---

## §6 Decision table per category

The decision table below summarizes the runtime state for every C2 condition. The table is exhaustive; any condition not listed is `POLICY_UNAVAILABLE` → `BLOCKED` until a new Charles confirmation is added.

> The single-`reason_code` rule (per §3.0.3) and the multiple-`blocker_dependencies` rule (per §3.0.4) are applied uniformly. Blocker codes (e.g. `EVIDENCE_HASH_MISMATCH`, `EVIDENCE_FIELD_PATH_INVALID`, `REQUIRED_CITATION_MISSING`, `REQUIRED_AUTHORITY_MISSING`, `REQUIRED_PROVENANCE_MISSING`, `RECOMMENDATION_THRESHOLD_MISSING`) appear in `blocker_dependencies` as typed `Blocker.code`, NOT in `reason_code`.

### §6.1 SUSTAINED_PROCESSING_CAPACITY

| Condition | Status | Reason code | Blocker code (in `blocker_dependencies`) | Advisory text | Non-action |
|---|---|---|---|---|---|
| All applicable CONF present + Q_in resolvable + WINDOW_DAYS == 3 + formula semantic confirmed | `APPLICABLE` | `RULE_APPLICABLE` | (empty) | Template (cross-cutting) with capacity substituted (non-null) | `NO_AUTOMATIC_PROCESSING_CAPACITY_CHANGE` + universal |
| All applicable CONF present + WINDOW_DAYS != 3 | `NOT_APPLICABLE` | `OUTSIDE_AUTHORIZED_SCOPE` | (empty) | `null` | same |
| Any applicable CONF missing (or selected formula semantic not yet chosen) | `BLOCKED` | `REQUIRED_THRESHOLD_MISSING` | `RECOMMENDATION_THRESHOLD_MISSING` | `null` | same |
| Q_in null / pointer not resolvable | `BLOCKED` | `REQUIRED_EVIDENCE_MISSING` | `REQUIRED_CITATION_MISSING` (or `EVIDENCE_FIELD_PATH_INVALID` if pointer is malformed) | `null` | same |
| `Citation.agent_artifact_hash` does not match resolved value's hash | `BLOCKED` | `UPSTREAM_BLOCKED` | `EVIDENCE_HASH_MISMATCH` | `null` | same |
| Pointer escape / alias / case normalization / fuzzy | `BLOCKED` | `UPSTREAM_BLOCKED` | `EVIDENCE_FIELD_PATH_INVALID` | `null` | same |
| Slice B blocked (e.g. `INSUFFICIENT_HISTORY`, `PEAK_POLICY_MISSING`) | `BLOCKED` | `UPSTREAM_BLOCKED` | original blocker preserved verbatim | `null` | same |
| `RecommendationRulePolicy` or `rule_catalog` not loaded | `BLOCKED` | `POLICY_UNAVAILABLE` | `RECOMMENDATION_POLICY_MISSING` or `RECOMMENDATION_RULE_MISSING` | `null` | same |

### §6.2 RECEIVING_PEAK_CAPACITY

Same structure as §6.1. Specific blocker codes follow the same mapping (`EVIDENCE_HASH_MISMATCH`, `EVIDENCE_FIELD_PATH_INVALID`, `REQUIRED_CITATION_MISSING`, `RECOMMENDATION_THRESHOLD_MISSING`, `UPSTREAM_BLOCKED` preserved verbatim).

### §6.3 SHIFT_STAFFING

Same structure as §6.1, with the addition that `PRODUCTIVITY_PER_PERSON_KG_PER_HOUR` parameter not persisted AND no CONF-020 produces a `REQUIRED_EVIDENCE_MISSING` blocker (parameter) plus a `RECOMMENDATION_THRESHOLD_MISSING` blocker (CONF), with `reason_code = UPSTREAM_BLOCKED` (per §3.0.3 single-reason precedence; upstream takes priority over threshold-missing).

### §6.4 SPRING_FESTIVAL_STAFFING

Same structure as §6.1, with the addition that calendar policy missing produces an `UPSTREAM_BLOCKED` decision preserving the original `SPRING_FESTIVAL_CALENDAR_POLICY_MISSING` blocker.

### §6.5 VARIETY_STAGGER

| Condition | Status | Reason code | Blocker code (in `blocker_dependencies`) | Advisory text | Non-action |
|---|---|---|---|---|---|
| All applicable CONF present + at least one rolling window with `overlap_detected = True` | `APPLICABLE` | `RULE_APPLICABLE` | (empty) | Template (cross-cutting) with contributing variety list and window dates substituted (non-null) | `NO_AUTOMATIC_VARIETY_STAGGER_ACTION` + universal |
| All applicable CONF present + no rolling window meets overlap trigger | `NOT_APPLICABLE` | `CONDITIONS_NOT_MET` | (empty) | `null` | same |
| All applicable CONF present + season has only one variety | `NOT_APPLICABLE` | `CONDITIONS_NOT_MET` | (empty) | `null` | same |
| Any applicable CONF missing | `BLOCKED` | `REQUIRED_THRESHOLD_MISSING` | `RECOMMENDATION_THRESHOLD_MISSING` | `null` | same |
| Upstream blocked | `BLOCKED` | `UPSTREAM_BLOCKED` | original blocker preserved verbatim | `null` | same |
| Citation hash mismatch | `BLOCKED` | `UPSTREAM_BLOCKED` | `EVIDENCE_HASH_MISMATCH` | `null` | same |

### §6.6 CROSS_PLANT_DISPATCH

| Condition | Status | Reason code | Blocker code (in `blocker_dependencies`) | Advisory text | Non-action |
|---|---|---|---|---|---|
| All applicable CONF present + `triggered = True` | `APPLICABLE` | `RULE_APPLICABLE` | (empty) | Template (cross-cutting) with peak and threshold substituted (non-null) | `NO_AUTOMATIC_CROSS_PLANT_DISPATCH` + universal |
| All applicable CONF present + `triggered = False` | `NOT_APPLICABLE` | `CONDITIONS_NOT_MET` | (empty) | `null` | same |
| All applicable CONF present + `current_capacity_kg_per_day = 0` | `NOT_APPLICABLE` | `OUTSIDE_AUTHORIZED_SCOPE` | (empty) | `null` | same |
| Any applicable CONF missing (or `operator` not confirmed) | `BLOCKED` | `REQUIRED_THRESHOLD_MISSING` | `RECOMMENDATION_THRESHOLD_MISSING` | `null` | same |
| Citation hash mismatch | `BLOCKED` | `UPSTREAM_BLOCKED` | `EVIDENCE_HASH_MISMATCH` | `null` | same |
| Upstream blocked | `BLOCKED` | `UPSTREAM_BLOCKED` | original blocker preserved verbatim | `null` | same |

### §6.7 Common universal conditions (all categories)

| Condition | Status | Reason code | Blocker code (in `blocker_dependencies`) | Advisory text | Non-action |
|---|---|---|---|---|---|
| Category outside Issue #99 authorized scope | `NOT_APPLICABLE` | `OUTSIDE_AUTHORIZED_SCOPE` | (empty) | `null` | universal |
| `RecommendationRulePolicy.policy_version != "recommendation-rule-policy-v1"` | `BLOCKED` | `POLICY_UNAVAILABLE` | `RECOMMENDATION_POLICY_MISSING` | `null` | universal |
| `rule_catalog_version != "recommendation-rule-catalog-v1"` | `BLOCKED` | `POLICY_UNAVAILABLE` | `RECOMMENDATION_POLICY_MISSING` | `null` | universal |
| `rule_catalog_hash` does not match the persisted, frozen catalog | `BLOCKED` | `POLICY_UNAVAILABLE` | `RECOMMENDATION_POLICY_MISSING` | `null` | universal |
| Citation missing entirely from a required evidence field | `BLOCKED` | `UPSTREAM_BLOCKED` | `REQUIRED_CITATION_MISSING` | `null` | universal |
| Authority envelope missing from a Citation | `BLOCKED` | `UPSTREAM_BLOCKED` | `REQUIRED_AUTHORITY_MISSING` | `null` | universal |
| Provenance fields missing from a Citation | `BLOCKED` | `UPSTREAM_BLOCKED` | `REQUIRED_PROVENANCE_MISSING` | `null` | universal |

---

## §7 Charles confirmation matrix

This matrix enumerates every Charles confirmation item the C2 implementation depends on. Each item is a **closed, directly-answerable question** that maps to one of three classes:

- `RESOLVED_BY_MERGED_AUTHORITY` — already frozen by merged C1 / Issue #99 / PR #100 / C1 design-confirmation.
- `DESIGN_CONFIRMATION_REQUIRED` — design decision not yet frozen; one Charles answer is enough.
- `BUSINESS_SOURCE_REQUIRED` — needs a Charles-provided business value + source ID + version + date + hash.

The matrix is **normalized** per review 4694215238 P1: cross-cutting policy rows (quantile selection, rounding, precision, risk vocabulary, template governance, confidence downgrade presentation, source provenance, cross-quantile prohibition) are stated once as cross-cutting items, and each category carries only the category-specific overrides or values.

### §7.1 RESOLVED_BY_MERGED_AUTHORITY items

#### §7.1.1 From C1 design + PR #100

| CONF ID | Category | Statement | Authority reference |
|---|---|---|---|
| CONF-RMA-001 | Cross-cutting | Seven `RecommendationCategory` values and exact order: `SUSTAINED_PROCESSING_CAPACITY`, `RECEIVING_PEAK_CAPACITY`, `SHIFT_STAFFING`, `SPRING_FESTIVAL_STAFFING`, `VARIETY_STAGGER`, `CROSS_PLANT_DISPATCH`, `MISSING_DATA_IMPACT`. | `enums.py::RecommendationCategory` + `slice_c/engine.py::CATEGORY_ORDER` (PR #100) |
| CONF-RMA-002 | Cross-cutting | `RecommendationDecision` shape with 17 fields (`category`, `kind`, `status`, `reason_code`, `reason_details`, `priority_rank`, `rule_id`, `template_id`, `advisory_text`, `applicability_conditions`, `evidence`, `risk_codes`, `confidence`, `confidence_boundary`, `blocker_dependencies`, `non_action`, plus inherited `frozen=True` and `extra="forbid"`). | `schemas.py::RecommendationDecision` (PR #100) |
| CONF-RMA-003 | Cross-cutting | `RecommendationReasonCode` 7-value literal. | `enums.py::RecommendationReasonCode` (PR #100) |
| CONF-RMA-004 | Cross-cutting | `RecommendationStatus` 3-value literal. | `enums.py::RecommendationStatus` (PR #100) |
| CONF-RMA-005 | Cross-cutting | Status / reason compatibility enforced by `_status_reason_contract` validator: `APPLICABLE` ↔ `RULE_APPLICABLE`; `NOT_APPLICABLE` ↔ `CONDITIONS_NOT_MET` or `OUTSIDE_AUTHORIZED_SCOPE`; `BLOCKED` ↔ `REQUIRED_THRESHOLD_MISSING` / `REQUIRED_EVIDENCE_MISSING` / `UPSTREAM_BLOCKED` / `POLICY_UNAVAILABLE`. | `schemas.py::RecommendationDecision._status_reason_contract` (PR #100) |
| CONF-RMA-006 | Cross-cutting | `APPLICABLE` requires non-null `advisory_text`; non-APPLICABLE requires null `advisory_text`; `BLOCKED` requires non-empty `blocker_dependencies`. | same |
| CONF-RMA-007 | Cross-cutting | `NonAction` 4-field shape: `required: Literal[True]`, `code: Literal["ADVISORY_ONLY_NO_AUTOMATIC_EXECUTION"]`, `text: Literal["This output is advisory only and does not trigger any external action."]`, `category_specific_code: str`. | `schemas.py::NonAction` (PR #100) |
| CONF-RMA-008 | Cross-cutting | `ConditionEvaluation` 7-field shape: `field_path`, `operator`, `observed_value`, `threshold_value`, `unit`, `result`, `citation`. | `schemas.py::ConditionEvaluation` (PR #100) |
| CONF-RMA-009 | Cross-cutting | `RecommendationEvidence` 4-field shape: `citation`, `affected_field_paths` (min_length=1), `missing_data_code`, `threshold`. | `schemas.py::RecommendationEvidence` (PR #100) |
| CONF-RMA-010 | Cross-cutting | `GenerateRecommendationsOutput` contains exactly 7 decisions, in canonical category order, with rule catalog identity and hash. | `schemas.py::GenerateRecommendationsOutput` + `slice_c/engine.py::build_recommendations` (PR #100) |
| CONF-RMA-011 | Cross-cutting | `Citation` 9-field shape: `source_tasks` (list), `source_tool`, `authorities` (list), `agent_artifact_hash`, `field_path`, `effective_as_of_date`, `confidence_evidence`, `tags`, `override_refs`. | `schemas.py::Citation` (PR #100) |
| CONF-RMA-012 | Cross-cutting | `Blocker` 5-field shape: `code`, `message`, `details`, `citation`, `retry_hint`. | `schemas.py::Blocker` (PR #100) |
| CONF-RMA-013 | Cross-cutting | Blockers ordered by `code` lexical ascending, then `message`, then canonicalized `details`, then canonicalized `citation`, then `retry_hint`. | Issue #99 §"Blocker and propagation contract" + `slice_c/engine.py::canonical_blockers` |
| CONF-RMA-014 | Cross-cutting | Slice C blocker codes (10) defined as a frozen set. | Issue #99 §"Blocker and propagation contract" |
| CONF-RMA-015 | Cross-cutting | RFC 6901 JSON Pointer policy `slice-c-json-pointer-policy-v1`. | Issue #99 §"RFC 6901 evidence field-path contract" |
| CONF-RMA-016 | Cross-cutting | Determinism, hash surface, and forbidden operation set. | `schemas.py` (PR #100) + Issue #99 §"Policy schemas, identifiers, and canonical hashes" |
| CONF-RMA-017 | Cross-cutting | Prototype (C2 Concept UI v1) is NOT a production authority; no production mapping from prototype labels to `RecommendationCategory`. | `§1.4` of this document |
| CONF-RMA-018 | Cross-cutting | Cross-quantile mixing is **forbidden by default**. | `§5.9` of this document |
| CONF-RMA-019 | Cross-cutting | `VARIETY_STAGGER` with no overlap detected emits `NOT_APPLICABLE / CONDITIONS_NOT_MET` (NOT `APPLICABLE / advisory_text = null`). | review 4694215238 P0-3 + `§3.5.5` |
| CONF-RMA-020 | Cross-cutting | `CROSS_PLANT_DISPATCH` with trigger not met emits `NOT_APPLICABLE / CONDITIONS_NOT_MET` (NOT `APPLICABLE / advisory_text = null`). | review 4694215238 P0-3 + `§3.6.8` |
| CONF-RMA-021 | Cross-cutting | `blocker_dependencies` carries integrity / path failures; `reason_code` is a single scalar. | review 4694215238 P0-3 + `§3.0.3` + `§3.0.4` |
| CONF-RMA-022 | Cross-cutting | Same-rank source conflict blocks by default; content hash is identity, not priority. | review 4694215238 P0-6 + `§2.3` |

#### §7.1.2 Open design-confirmation items (not in §7.1.1, not business values)

| CONF ID | Category | Question | Default if not confirmed |
|---|---|---|---|
| CONF-EX-001 | Cross-cutting | CONFIRMED (CONF-RMA-017): no production mapping from prototype labels to `RecommendationCategory`; prototype remains visual-only. | — |
| CONF-EX-002 | Cross-cutting | Should C2 use (A) stable array indices, (B) a separate deterministic parameter-lookup step, or (C) mark the field as a source capability gap? | Until confirmed, no pointer to a parameter-by-name path is authoritative; the lookup is a source capability gap and the category is `BLOCKED`. |
| CONF-EX-003 | SUSTAINED_PROCESSING_CAPACITY | Re-validate the exact pointer to the single-day peak against the current `ForecastPeakOutput` schema. | Until confirmed, the exact path is `DESIGN_CONFIRMATION_REQUIRED` and the category remains `BLOCKED`. |
| CONF-EX-004 | Cross-cutting | Reporting grain: per plant, per region, or global? | Default: per plant. |
| CONF-EX-005 | RECEIVING_PEAK_CAPACITY | Output structure: "requirement alone", "available alone", "gap + status", or "bottleneck identification"? | Default: `BLOCKED` until chosen. |
| CONF-EX-006 | RECEIVING_PEAK_CAPACITY | Per-plant list of "not a receiving plant" exceptions. | Default: empty list (no exceptions). |
| CONF-EX-007 | Cross-cutting | Risk code vocabulary (closed list per category). | Default: empty. |
| CONF-EX-008 | SHIFT_STAFFING | Per-plant list of "no shift operation" exceptions. | Default: empty list. |
| CONF-EX-009 | CROSS_PLANT_DISPATCH | Re-validate the exact pointer to the single-day peak against the current `ForecastPeakOutput` schema. | Until confirmed, the exact path is `DESIGN_CONFIRMATION_REQUIRED` and the category remains `BLOCKED`. |
| CONF-EX-010 | CROSS_PLANT_DISPATCH | Trigger comparison operator: `>=` (trigger when peak ≥ threshold) or `>` (trigger when peak > threshold)? | Default: `>=` (consistent with `trigger_ratio = 1.0` semantically meaning "trigger at equality"). |
| CONF-EX-011 | Cross-cutting | Cross-cutting rounding mode (one mode for all categories unless category override). | Default: `ROUND_HALF_UP`. |
| CONF-EX-012 | Cross-cutting | Cross-cutting decimal precision (one precision for all categories unless category override). | Default: `0`. |
| CONF-EX-013 | Cross-cutting | Cross-cutting advisory template governance. | Default: empty template. |
| CONF-EX-014 | Cross-cutting | Cross-cutting confidence downgrade presentation rule. | Default: C1 BLOCKED uses `confidence=None`; no downgrade in this round. |
| CONF-EX-015 | Cross-cutting | Cross-cutting source provenance requirements (which fields are required on every `Citation`). | Default: per `§3.1.15`. |

### §7.2 BUSINESS_SOURCE_REQUIRED items (Charles-provided business values)

These rows are pure business values; each must come with a `source_id`, `source_version`, `source_effective_date`, and `source_hash` from Charles.

| CONF ID | Category | Parameter | Allowed unit | Source description |
|---|---|---|---|---|
| CONF-001 | SUSTAINED_PROCESSING_CAPACITY | Selected quantile for capacity basis (P50 / P80 / P90) | n/a | Production standard or Charles |
| CONF-002 | SUSTAINED_PROCESSING_CAPACITY | `sustained_window_days` (currently hard-coded `3` by `PeakMetricPolicy`) | days | Production standard or Charles |
| CONF-003 | SUSTAINED_PROCESSING_CAPACITY | Single-day vs sustained-three-day basis | n/a | Charles |
| CONF-004 | SUSTAINED_PROCESSING_CAPACITY | Safety / reserve / utilization factor (semantic A/B/C chosen by Charles) | fraction (range depends on semantic) | Production standard or Charles |
| CONF-012 | RECEIVING_PEAK_CAPACITY | Selected quantile for peak basis (P50 / P80 / P90) | n/a | Charles |
| CONF-013 | RECEIVING_PEAK_CAPACITY | Daily receiving operating hours | hours/day | Production standard |
| CONF-014 | RECEIVING_PEAK_CAPACITY | Turnover time at receiving dock | hours | Production standard |
| CONF-015 | RECEIVING_PEAK_CAPACITY | Temporary-storage physical capacity (kg, *available*) | kg | Production standard |
| CONF-016 | RECEIVING_PEAK_CAPACITY | Pre-cooling capacity (kg/hour, *available*) | kg/hour | Production standard |
| CONF-017 | RECEIVING_PEAK_CAPACITY | Safety factor (receiving margin) | fraction (0, 1] | Charles |
| CONF-018 | SHIFT_STAFFING | Nominal shift duration | hours | Production standard |
| CONF-019 | SHIFT_STAFFING | Effective working hours per shift | hours | Production standard |
| CONF-020 | SHIFT_STAFFING | `PRODUCTIVITY_PER_PERSON_KG_PER_HOUR` (explicit override, if not persisted) | kg/person/hour | Production standard |
| CONF-021 | SHIFT_STAFFING | Attendance rate | fraction (0, 1] | Production standard |
| CONF-022 | SHIFT_STAFFING | `PRODUCTIVITY_BY_ROLE` map | dict | Production standard |
| CONF-023 | SHIFT_STAFFING | Peak personnel buffer | fraction [0, 1) | Charles |
| CONF-024 | SHIFT_STAFFING | Number of shifts per day | int 1..3 | Charles |
| CONF-025 | SPRING_FESTIVAL_STAFFING | Picker availability factor (explicit override) | fraction (0, 1] | Production standard |
| CONF-026 | SPRING_FESTIVAL_STAFFING | Processor availability factor (explicit override) | fraction (0, 1] | Production standard |
| CONF-027 | SPRING_FESTIVAL_STAFFING | Picker productivity | kg/picker/hour | Production standard |
| CONF-028 | SPRING_FESTIVAL_STAFFING | Processor productivity | kg/processor/hour | Production standard |
| CONF-029 | SPRING_FESTIVAL_STAFFING | Picker available hours per day | hours/day | Production standard |
| CONF-030 | SPRING_FESTIVAL_STAFFING | Processor available hours per day | hours/day | Production standard |
| CONF-031 | SPRING_FESTIVAL_STAFFING | Picker pre-festival lead days | days | Production standard |
| CONF-032 | SPRING_FESTIVAL_STAFFING | Processor during-festival lead days | days | Production standard |
| CONF-033 | SPRING_FESTIVAL_STAFFING | Picker post-festival recovery days | days | Production standard |
| CONF-034 | SPRING_FESTIVAL_STAFFING | Per-phase mapping `PRE / DURING / POST` | dict | Charles |
| CONF-035 | VARIETY_STAGGER | Selected quantile for overlap evaluation | "P50" / "P80" / "P90" | Charles |
| CONF-036 | VARIETY_STAGGER | Overlap window length | int >= 1 | Charles |
| CONF-037 | VARIETY_STAGGER | Minimum number of varieties sharing the window | int >= 2 | Charles |
| CONF-038 | VARIETY_STAGGER | Minimum `contribution_rate` of a variety within the window | fraction (0, 1) | Charles |
| CONF-041 | CROSS_PLANT_DISPATCH | Selected quantile for trigger | "P50" / "P80" / "P90" | Charles |
| CONF-042 | CROSS_PLANT_DISPATCH | Current factory capacity | kg/day per plant | Production standard |
| CONF-043 | CROSS_PLANT_DISPATCH | Trigger ratio | fraction (0, 1] | Charles |

### §7.3 Reclassified from v1

| v1 CONF ID | Reclassified to | Reason |
|---|---|---|
| CONF-005, CONF-006, CONF-007 | `DESIGN_CONFIRMATION_REQUIRED` (cross-cutting) | rounding, precision, template governance are cross-cutting per review P1 |
| CONF-008, CONF-009, CONF-010 | `DESIGN_CONFIRMATION_REQUIRED` (cross-cutting) | confidence downgrade, risk vocabulary, advisory template are cross-cutting |
| CONF-011, CONF-024, CONF-035 | `DESIGN_CONFIRMATION_REQUIRED` (cross-cutting) | cross-plant grain and `OUTSIDE_AUTHORIZED_SCOPE` per-plant lists are cross-cutting |
| CONF-039, CONF-040 | removed (replaced by `RESOLVED_BY_MERGED_AUTHORITY` CONF-RMA-019 / CONF-RMA-020) | validator forbids `APPLICABLE / advisory_text = null` |
| CONF-044 | removed (replaced by `RESOLVED_BY_MERGED_AUTHORITY` CONF-RMA-020) | same |
| CONF-054, CONF-060 | removed (replaced by `RESOLVED_BY_MERGED_AUTHORITY`) | same |
| CONF-061 | moved to `RESOLVED_BY_MERGED_AUTHORITY` (CONF-RMA-018) | cross-quantile mixing is forbidden by default |
| CONF-EX-001 | moved to `RESOLVED_BY_MERGED_AUTHORITY` (CONF-RMA-017) | prototype is not production authority |

### §7.4 Charles confirmation workflow

1. Charles reviews each CONF row.
2. Charles responds with one of: (a) a confirmed value, source ID, source version, source effective date, and source hash; (b) a "decline" answer indicating the category should remain `BLOCKED` indefinitely; (c) a "supersede" answer pointing to a new CONF row.
3. The new row replaces the old row in the rule catalog. The `rule_catalog_hash` is recomputed; old values are NOT auto-migrated.
4. The `agent_recommendations_hash` is recomputed for the affected category; the new hash is recorded in the audit log.

### §7.5 Counts

- `RESOLVED_BY_MERGED_AUTHORITY` items: **22** (CONF-RMA-001..022).
- `DESIGN_CONFIRMATION_REQUIRED` items: **15** (CONF-EX-002..015, plus CONF-EX-001 which is `RESOLVED_BY_MERGED_AUTHORITY`).
- `BUSINESS_SOURCE_REQUIRED` items: **38** (CONF-001..004 + CONF-012..017 + CONF-018..024 + CONF-025..034 + CONF-035..038 + CONF-041..043). This is the actual count of business values that need Charles-provided source ID + version + date + hash.
- `REMOVED_AS_DUPLICATE` items (reclassified to cross-cutting): **9** (CONF-005..010, CONF-011, CONF-024, CONF-035) — these were the per-category duplicates of the cross-cutting rounding/precision/template/confidence/risk/grain policies; they are replaced by the cross-cutting CONF-EX-011..015.
- `REMOVED_AS_INVALID` items: **4** (CONF-039, CONF-040, CONF-044, CONF-054, CONF-060) — removed because they offered schema states the merged validator forbids. Note CONF-061 (cross-quantile) is now `RESOLVED_BY_MERGED_AUTHORITY` (CONF-RMA-018), not "removed".

The v1 `62` total is decomposed as: 22 (RMA) + 15 (DCR) + 38 (BSR) + 9 (DUPLICATE) − 22 RMA contains the items v1 had marked BUSINESS_SOURCE_REQUIRED but which are now RMA (e.g. the design-confirmation items that v1 split out as CONF-005..010, CONF-011, etc. and the prototype-mapping item).

The matrix is canonical: any future round that adds or removes a row must update this count summary.

---

## §8 Implementation slices (forward-looking plan)

This section proposes a six-slice implementation plan (C2-A through C2-F). Each slice requires its own Charles authorization. The slices are independent enough to be reviewed separately, but a slice may be implemented only after the **predecessor contracts are accepted** AND the **target slice's source confirmations are answered**.

### §8.0 Predecessor gate (corrected per review 4694215238 P1)

A target slice may be implemented when:

1. The target slice's own source confirmations are Charles-confirmed (or explicitly declined).
2. The predecessor contracts (golden hashes, schema contracts, CI ownership) are accepted by Charles.
3. The predecessor slices' `BUSINESS_SOURCE_REQUIRED` items do NOT need to remain `BUSINESS_SOURCE_REQUIRED`; the gate is on the **target slice's** source confirmations.

### §8.1 C2-A — Source schemas, rule-catalog extension, and policy loading

| Aspect | Value |
|---|---|
| Goal | Extend the rule catalog to hold C2 rule rows for the six operational categories. Wire `source_id`, `source_version`, `source_effective_date`, and `source_hash` for each `APPROVED_AUDITABLE_SOURCE` row. Implement the parameter-lookup step (CONF-EX-002) when the design is confirmed. Load `business_policy` artifacts. Reuse the merged `RecommendationDecision`, `RecommendationReasonCode`, `BlockerCode`, `NonAction`, and `GenerateRecommendationsOutput` schemas; do NOT introduce a parallel schema or enum. |
| Allowed files | `backend/app/agent/slice_c/`, `backend/app/agent/slice_c/catalog/`, `backend/app/agent/slice_c/policy/`, new test files only. |
| Forbidden files | Any non-`backend/app/agent/slice_c/**` production code. No `alembic/**`, no `frontend/**`, no `tests/agent/test_*.py` modification (only new test files). |
| Acceptance tests | TEST-C2-001-07, TEST-C2-002-06, TEST-C2-003-06, TEST-C2-004-06, TEST-C2-005-07, TEST-C2-006-06 (C1 regression — `PASS`), plus TEST-C2-A-001..006 (placeholder rule row for each of the 6 categories). |
| Rollback boundary | Revert the slice's commits. The C1 contract is preserved because the C1 hard-coded `BLOCKED / REQUIRED_THRESHOLD_MISSING` is still in effect for all 6 categories. |
| Status | NOT AUTHORIZED in this document. |

### §8.2 C2-B — Processing and receiving capacity rules

| Aspect | Value |
|---|---|
| Goal | Lift the §3.1 and §3.2 candidate formulas into actual rule rows. Implement the requirement/available/gap output structure for RECEIVING_PEAK_CAPACITY. |
| Allowed files | `backend/app/agent/slice_c/engines/capacity.py` (new), `backend/app/agent/slice_c/catalog/capacity.json` (new, real rows), new test files only, the two golden files (regenerated). |
| Forbidden files | Anything outside `slice_c/engines/`, `slice_c/catalog/`, `tests/agent/` (new files only), and the two golden files. |
| Acceptance tests | C1 regression (PASS) plus the new tests in §3.1.17 / §3.2.14. |
| Rollback boundary | Revert the slice's commits. The C1 contract is preserved. |
| Status | NOT AUTHORIZED in this document. |

### §8.3 C2-C — Staffing and Spring Festival staffing rules

Same boundary as C2-B but for §3.3 and §3.4.

### §8.4 C2-D — Variety stagger and cross-plant dispatch rules

Same boundary as C2-B but for §3.5 and §3.6. Note: these are review-only categories; the implementation includes the `APPLICABLE` flag but not any execution logic.

### §8.5 C2-E — Production wiring, Goldens, and PostgreSQL acceptance

| Aspect | Value |
|---|---|
| Goal | Update the production-wired `AgentOrchestrator` path to invoke the new rule catalog end-to-end. Regenerate both golden files. Add PostgreSQL integration test coverage. |
| Allowed files | `backend/app/agent/orchestration.py`, `backend/app/agent/slice_c/__init__.py`, `backend/app/agent/slice_c/engine.py`, `backend/tests/agent/golden/*.json`, `backend/tests/integration/agent/test_slice_c_orchestration_postgres.py`, `backend/tests/integration/agent/test_orchestration_postgres.py` |
| Forbidden files | Anything outside the listed files. No `alembic/**`, no `frontend/**`, no `backend/app/api/**`. |
| Acceptance tests | C1 regression (PASS) plus the new tests in §3.1.17 / §3.2.14 / §3.3.14 / §3.4.13 / §3.5.10 / §3.6.13, plus golden hash stability tests. |
| Rollback boundary | Revert the slice's commits. The C1 contract is preserved by regenerating the golden files from a known C1 state if any hash check fails. |
| Status | NOT AUTHORIZED in this document. |

### §8.6 C2-F — Review fixup and closeout

| Aspect | Value |
|---|---|
| Goal | Apply review feedback and finalize the C2 source-definition closeout. C2-F does **not** include Issue #99 closure (Issue #99 remains open until C2 production implementation is complete) and does **not** include merge of any C2 production implementation PR. C2-F may include updates to the C2 source-definition document and review-thread resolution. |
| Allowed files | `docs/task-013-slice-c-c2-business-rule-source-definition.md` (only if §7 confirmation items are updated), `backend/tests/agent/**` (only to add new tests per review), and Issue #99 comment (posted by Charles, not by automation). |
| Forbidden files | Any production code change not strictly required to address review feedback. |
| Acceptance tests | Re-run the full test suite; both golden SHA-256 values stable. |
| Rollback boundary | Revert the slice's commits. |
| Status | NOT AUTHORIZED in this document. |

### §8.7 Slice ordering and gate

| Predecessor slice | Required gate |
|---|---|
| C2-A | C1 contract preserved (golden hashes match); `MISSING_DATA_IMPACT` decision unchanged. |
| C2-B | C2-A accepted. C1 contract preserved. Target slice's source confirmations (CONF-001..004, CONF-012..017) answered. |
| C2-C | C2-A accepted. C1 contract preserved. Target slice's source confirmations (CONF-018..024, CONF-025..034) answered. |
| C2-D | C2-A accepted. C1 contract preserved. Target slice's source confirmations (CONF-035..038, CONF-041..043, CONF-EX-010) answered. |
| C2-E | C2-A, C2-B, C2-C, C2-D all accepted. C1 contract preserved. PostgreSQL integration test passes against a real chain. |
| C2-F | C2-E accepted. Charles review feedback received. |

---

## §9 Source reconciliation and conflict log

### §9.1 Resolved conflicts (from C1 design, included for traceability)

| ID | Source conflict | Normalized direction | Status | Reference |
|---|---|---|---|---|
| SRC-C-01 | Design §19.1/19.4 vs Issue #99 sibling-ownership | Sibling top-level fields; acyclic dependency | `RESOLVED_BY_MERGED_AUTHORITY` | Issue #99 §"Sibling-stage dependency contract" |
| SRC-C-02 | Design §20.4 vs Issue #99 missing-threshold-as-blocker | `BLOCKED` (not LOW-confidence action) | `RESOLVED_BY_MERGED_AUTHORITY` | Issue #99 §"Blocker and propagation contract" |
| SRC-C-03 | Deferred outputs vs Issue #99 policy/catalog identities | Use new contract | `RESOLVED_BY_MERGED_AUTHORITY` | Issue #99 §"Policy schemas, identifiers, and canonical hashes" |
| SRC-C-04 | Existing `Recommendation` vs Issue #99 `RecommendationDecision` envelope | Reuse merged envelope | `RESOLVED_BY_MERGED_AUTHORITY` (PR #100) | `schemas.py::RecommendationDecision` |
| SRC-C-05 | Original design §24.1 stale season fields vs `task-013-persisted-forecast-season-identity-design-amendment.md` | Use the amendment; authority comes from current `main` and from PR #97 (the amendment's PR); the file is not required in the current `main` working tree as long as the season identity is already frozen into `schemas.py::NormalizedAgentRequest` and the Slice C engines | `RESOLVED_BY_MERGED_AUTHORITY` (per Issue #99; superseded by `schemas.py::NormalizedAgentRequest`) | Issue #99 §"Source reconciliation conflicts"; `git show origin/main:backend/app/agent/schemas.py::NormalizedAgentRequest` |
| SRC-C-06 | Existing `BlockerCode` vs Issue #99 Slice C blocker set | Use merged typed blockers | `RESOLVED_BY_MERGED_AUTHORITY` (PR #100) | `enums.py::BlockerCode` |
| SRC-C-07 | Mixed JSON Pointer / non-RFC paths | RFC 6901 only | `RESOLVED_BY_MERGED_AUTHORITY` (PR #100) | Issue #99 §"RFC 6901 evidence field-path contract" |
| SRC-C-08 | Slice A deferred tests permit empty outputs | Require 7 decisions, stable hashes, Goldens, production wiring | `RESOLVED_BY_MERGED_AUTHORITY` (PR #100) | Issue #99 §"Source reconciliation conflicts" |
| SRC-C-09 | Minimal-input spec names 7 categories but provides no formulas | Operational categories remain `BLOCKED` until sources exist | `BUSINESS_SOURCE_REQUIRED` | Issue #99 §"Source reconciliation conflicts" |
| SRC-C-10 | Current PostgreSQL acceptance ends at Slice B | Extend through C1 sibling stages | `RESOLVED_BY_MERGED_AUTHORITY` (PR #100) | Issue #99 §"PostgreSQL production-wiring acceptance" |
| SRC-C-11 | Prior proposed decision shape had no reason field | Use merged `reason_code` + `reason_details` | `RESOLVED_BY_MERGED_AUTHORITY` (PR #100) | `schemas.py::RecommendationDecision` |

### §9.2 New conflicts discovered during C2 source-definition (corrected per review 4694215238 P1 / SRC-NEW-01)

Per review 4694215238 P1, SRC-NEW-01 was previously based only on local `ls`. The corrected evidence comes from multiple sources, not just local `ls`:

| ID | Source conflict | Original wordings | Normalized proposal | Why execution cannot decide | Question for Charles |
|---|---|---|---|---|---|
| SRC-NEW-01 | Issue #99 body references `docs/task-013-persisted-forecast-season-identity-design-amendment.md` as a `RESOLVED_BY_MERGED_AUTHORITY` source. The file is NOT in the current `main` working tree. Evidence: (a) `ls docs/task-013-persisted*` on `origin/main` returns no result; (b) the only Git trace is the remote-tracking branch `origin/codex/task-013-persisted-season-identity-design` in `.git/refs/remotes/origin/`; (c) Issue #99 SRC-C-05 row states `RESOLVED_BY_MERGED_AUTHORITY`; (d) PR #97 (`codex/task-013-persisted-season-identity-design`) is the PR that introduced the season identity; (e) the season identity is currently consumed through `backend/app/agent/schemas.py::NormalizedAgentRequest` which lives on `main`. | (a) Issue #99 body SRC-C-05: "`RESOLVED_BY_MERGED_AUTHORITY`: `docs/task-013-persisted-forecast-season-identity-design-amendment.md` and `backend/app/agent/schemas.py::NormalizedAgentRequest`". (b) Current `main` filesystem: no such file. (c) `git log` for the file shows it was created in PR #97 and not merged into main. | Treat the season identity as already resolved through `backend/app/agent/schemas.py::NormalizedAgentRequest` (which is on `main`). C2 does not consume the standalone doc file. | Because the issue text treats the doc as authority but the doc is not in the working tree, future implementers may be confused. Execution cannot silently recreate the doc. | (a) Confirm that C2 does not need the standalone doc. (b) Confirm whether the doc should be added to the working tree in a separate docs-only round, or whether the Issue #99 reference should be updated to remove the doc citation. |
| SRC-NEW-02 | The TASK-013 C2 Concept UI Prototype (HEAD `15d2e53`, branch `prototype/task-013-c2-concept-ui-v1`) uses 6 capability blocks named `CAPACITY-001/002`, `STAFF-001/002`, `VARIETY-001`, `DISPATCH-001`. The production `RecommendationCategory` enum has 7 values. The mapping is not 1:1. | (a) Prototype labels: 6 blocks. (b) Production enum: 7 categories. | CONF-RMA-017: no production mapping; the prototype remains visual-only (rank 4 in §2.1). | Because execution cannot decide which prototype block "becomes" which production category, and any mapping would inject non-canonical labels into a Charles-confirmed enum. | None — closed as `RESOLVED_BY_MERGED_AUTHORITY` (CONF-RMA-017). |
| SRC-NEW-03 | "Safety factor" appears in Issue #99 and the prototype, but neither provides a value. The existing `PeakMetricPolicy.high_load_threshold_ratio` is an upstream-only Slice B field. | (a) Issue #99: no value. (b) `PeakMetricPolicy.high_load_threshold_ratio`: existing schema field, value is config-driven. (c) Prototype: no value, displays "待确认". | C2 does not consume `high_load_threshold_ratio`. C2 uses a separate `SAFETY` (or reserve / utilization) parameter, with the semantic chosen by Charles from set {A, B, C} per §3.1.6. | Because conflating the two would make the advisory depend on a Slice B config value that the C2 advisory should not depend on. | Charles to choose the semantic (A/B/C) per §3.1.6 and the value via CONF-004. |
| SRC-NEW-04 | The earlier `parameters/PRODUCTIVITY_PER_PERSON_KG_PER_HOUR/p50` pointer assumed `parameters` is a map. The merged schema has `parameters: list[ParameterEstimate]`. | (a) Earlier draft: `parameters` treated as map. (b) Merged schema: `list[ParameterEstimate]`. | Per §3.0.7: C2 must define a deterministic parameter-lookup step (CONF-EX-002) before using `/parameters/{parameter_name}/...` pointers. Until confirmed, the lookup is a source capability gap. | Because RFC 6901 cannot search a list by `parameter_name`. | See CONF-EX-002. |
| SRC-NEW-05 | The earlier `Citation.source_task` and `Citation.artifact_hash` are non-existent fields. The merged `Citation` has `source_tasks` (list) and `agent_artifact_hash`. | (a) Earlier draft: singular `source_task` and `artifact_hash`. (b) Merged schema: `source_tasks` (list) and `agent_artifact_hash`. | Use the merged field names. | Because execution cannot silently invent fields. | None — closed. |
| SRC-NEW-06 | The earlier `VarietyContribution` `p50/p80/p90` is non-existent. The merged schema has `volume_kg_p50/p80/p90` and `contribution_rate_p50/p80/p90`. | (a) Earlier draft: `p50/p80/p90`. (b) Merged schema: prefix-bearing names. | Use the merged field names. | Because execution cannot silently invent fields. | None — closed. |
| SRC-NEW-07 | The earlier source-conflict resolution (§2.3) used "lexicographically larger hash wins" and "more recent date wins" as automatic tie-breakers. Content hash is identity, not priority. | (a) Earlier §2.3: hash-based tie-break. (b) Corrected §2.3: same-rank conflict blocks by default. | Per §2.3 (corrected). | Because a content hash does not encode business priority. | None — closed. |

### §9.3 Conflict log rule

Any future implementer who discovers a new conflict MUST:

1. Halt implementation.
2. Add a new row to §9.2 with the five columns filled.
3. Surface the row in the PR body of the implementation round.
4. NOT resolve the conflict silently.

A silent conflict resolution is a hard rule violation and triggers a rollback to the prior accepted state.

---

## §10 Charles confirmation count summary (corrected per review 4694215238 P1)

| Item | Count |
|---|---|
| Total `RESOLVED_BY_MERGED_AUTHORITY` items | **22** (CONF-RMA-001..022) |
| Total `DESIGN_CONFIRMATION_REQUIRED` items | **15** (CONF-EX-002..015; CONF-EX-001 is now `RESOLVED_BY_MERGED_AUTHORITY`) |
| Total `BUSINESS_SOURCE_REQUIRED` items | **38** (CONF-001..004 + CONF-012..017 + CONF-018..024 + CONF-025..034 + CONF-035..038 + CONF-041..043) |
| Total `REMOVED_AS_DUPLICATE` items (reclassified to cross-cutting) | **9** (CONF-005..010, CONF-011, CONF-024, CONF-035 from the v1 list) |
| Total `REMOVED_AS_INVALID` items | **4** (CONF-039, CONF-040, CONF-044, CONF-054, CONF-060; see §7.3) |
| Source-conflict rows in §9.2 (new) | **7** (SRC-NEW-01..07) |
| Source-conflict rows in §9.1 (C1 historical) | **11** (SRC-C-01..11) |
| `CANDIDATE_FORMULA` count | **6** (one per category) |
| `FROZEN_FORMULA` count | **0** (all formulas are `CANDIDATE_FORMULA / BUSINESS_SOURCE_REQUIRED` or `DESIGN_CONFIRMATION_REQUIRED`) |
| `PLANNED` tests (C2 future acceptance) | All C2 unit / formula / integration tests except the C1 regression Golden tests (which are `PASS`). |
| `PASS` tests (currently claimable) | TEST-C2-001-07, TEST-C2-002-06, TEST-C2-003-06, TEST-C2-004-06, TEST-C2-005-07, TEST-C2-006-06 (C1 regression Golden tests). |
| `BLOCKED_BY_DESIGN_CONFIRMATION` tests | All C2 unit / formula tests that depend on unresolved design decisions. |
| `BLOCKED_BY_BUSINESS_SOURCE` tests | All C2 tests that depend on unresolved business values. |

---

## §11 Acceptance gates (this document)

This document is considered `C2_SOURCE_DEFINITION_DRAFT` and **not yet accepted** until ALL of the following are true:

1. The document is on a dedicated `docs/task-013-slice-c-c2-business-source-definition` branch off `origin/main` at `2e860511dd9279d0aa3c64dd760bea8531fad458`.
2. The branch is pushed to `origin` and a Draft PR is open.
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
| 2026-07-14 | v1 | Charles-authorized C2 design round | Initial creation. Frozen-in-C1 contract preserved; six operational categories enumerated as `BUSINESS_SOURCE_REQUIRED`; 62 CONF items listed; 3 source conflicts logged; 6-slice implementation plan proposed. |
| 2026-07-14 | v1.1 (this document) | Charles-authorized C2 design P0 fixup | (1) `RESOLVED_BY_MERGED_AUTHORITY` reclassification for all C1-merged schema/enum/validator items per review 4694215238 P0-1. (2) RFC 6901 pointer corrections: parameters array (§3.0.7 + SRC-NEW-04), VarietyContribution field names (§3.5.3 + SRC-NEW-06), Citation field names (§3.0.8 + SRC-NEW-05), removed invented `forecast_peak.run_id` / `forecast_daily_curve.run_id` / `daily_curve_policy_*` / `parameter_id` / `parameter as_of` references (moved to CONF-EX-003 / CONF-EX-009). (3) Status / reason / blocker reconciliation: single-`reason_code` rule, `blocker_dependencies` carries integrity / path blockers (§3.0.3, §3.0.4, §6.1..6.7); CONF-039/040/044/054/060 removed; no-overlap / no-trigger now `RESOLVED_BY_MERGED_AUTHORITY` as `NOT_APPLICABLE / CONDITIONS_NOT_MET` (CONF-RMA-019, CONF-RMA-020). (4) All formulas reclassified as `CANDIDATE_FORMULA` (§5.1); sustained-processing safety semantic split into A/B/C (§3.1.6); receiving-peak structure split into requirement/available/gap/status (§3.2.6); shift staffing split nominal vs effective hours + role vs aggregate productivity (§3.3.6); spring festival split availability/productivity/hours/lead/recovery into 5 distinct rows (§3.4.4); cross-plant trigger operator unified (`>=` default per CONF-EX-010, §3.6.5); `current_capacity = 0` handled consistently across function skeleton, null semantics, decision table, and test plan (§3.6.5..6.6). (5) Test status corrected: only C1 regression Golden tests are `PASS`; all C2 future tests are `PLANNED` / `BLOCKED_BY_DESIGN_CONFIRMATION` / `BLOCKED_BY_BUSINESS_SOURCE`; numeric mechanics examples explicitly labeled `NON_AUTHORITATIVE_MECHANICS_EXAMPLE` (§4.2); `synthetic CHARLES_CONFIRMED_SOURCE` rollback language removed from C2-B. (6) Source-conflict resolution corrected (§2.3): same-rank conflict blocks by default; hash is identity, not priority; explicit supersession / approval lineage / same source family required for automatic resolution. (7) 62-item confirmation matrix reclassified into `RESOLVED_BY_MERGED_AUTHORITY` (22) / `DESIGN_CONFIRMATION_REQUIRED` (15) / `BUSINESS_SOURCE_REQUIRED` (38) / `REMOVED_AS_DUPLICATE` (9) / `REMOVED_AS_INVALID` (4) per review 4694215238 P1. (8) Wording corrections: "current C2 source-definition baseline; future revisions possible" (§1); "branch/worktree/PR" wording clarified to mean **production implementation** (§1.5); slice gate language corrected (§8.0); C2-F wording corrected to exclude Issue #99 closure and merge (§8.6). (9) SRC-NEW-01 evidence expanded with multiple sources, not just local `ls` (§9.2). |

---

## §13 Sign-off section (to be completed by Charles upon acceptance)

```text
TASK013_SLICE_C_C2_SOURCE_DEFINITION_DRAFT_V1_1_REVIEWED
TASK013_SLICE_C_C2_SOURCE_DEFINITION_FROZEN_UPON_CHARLES_ACCEPTANCE
TASK013_SLICE_C_C2_IMPLEMENTATION_NOT_YET_AUTHORIZED
TASK013_SLICE_C_C2_PRODUCTION_IMPLEMENTATION_BRANCH_NOT_YET_AUTHORIZED
TASK013_SLICE_C_C2_PRODUCTION_IMPLEMENTATION_WORKTREE_NOT_YET_AUTHORIZED
TASK013_SLICE_C_C2_PRODUCTION_IMPLEMENTATION_PR_NOT_YET_AUTHORIZED
TASK013_SLICE_C_C2_DRAFT_PR_101_OPEN_NOT_READY
TASK013_SLICE_C_C2_READY_NOT_AUTHORIZED
TASK013_SLICE_C_C2_MERGE_NOT_AUTHORIZED
TASK013_SLICE_C_C2_ISSUE99_REMAINS_OPEN
TASK013_SLICE_C_SLICE_D_E_NOT_AUTHORIZED
TASK013_SLICE_C_TASK_014_NOT_AUTHORIZED
```

(Charles to amend the above with explicit `ACCEPTED` or `REVISED` markers and post the result as an Issue #99 comment.)
