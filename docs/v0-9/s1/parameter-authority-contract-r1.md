# V0.9-S1 Parameter Authority Contract

**Contract:** `PARAMETER_AUTHORITY_CONTRACT_VERSION=V0_9_S1_R1`  
**Status:** provenance/lifecycle definition only; no production parameter is created.

## 1. Required parameter record

Every numerical or categorical model parameter must record:

`parameter_id`, `parameter_name`, `value_or_unbound`, `unit`, `authority_type`, `source_id`, `cultivar_scope`, `production_system_scope`, `climate_scope`, `calibration_status`, `valid_from`, `version`, and `parameter_hash`.

`source_id` may be a registered S0 source or a later authorized business/data-calibration record. Scope is explicit; a blank scope is not a global scope. `value_or_unbound` is either a typed value or the literal `UNBOUND`, never a guessed default.

## 2. Authority types

| Type | Meaning | Production use at S1 |
|---|---|---|
| `BUSINESS_CONFIRMED` | Explicitly confirmed operational value/scope with evidence | Not automatically a biological parameter; use only for its confirmed scope. |
| `DIRECT_OBSERVED` | Measured parameter with instrument/protocol and source | Observation first; model use needs declared mapping and quality. |
| `DATA_CALIBRATED` | Estimated from identified, eligible data with frozen calibration protocol | Not available until an authorized later task establishes calibration. |
| `LITERATURE_PRIOR` | Literature value or candidate prior, with source and study scope | Never a production default by itself. |
| `MODEL_ASSUMPTION` | Explicit structural assumption used by a named model version | Must be labeled, bounded, reviewed, and not represented as biology. |
| `UNBOUND` | No authorized value | Required default for chill/forcing thresholds and other uncalibrated numerical parameters. |

`LITERATURE_PRIOR != PRODUCTION_PARAMETER`. Promotion requires a separately authorized business confirmation, data calibration, or prospective validation, with new provenance and lifecycle status. S0's `literature-parameter-candidate-register-r1.csv` remains literature evidence only.

## 3. Calibration status vocabulary

Allowed status values are `UNBOUND`, `LITERATURE_CANDIDATE`, `OBSERVED_NOT_CALIBRATED`, `CALIBRATED_TRAINING_ONLY`, `PROSPECTIVELY_VALIDATED`, `REJECTED`, and `SUPERSEDED`. A status change creates a new immutable parameter version; it does not overwrite the cited source or prior value.

## 4. Scope and units

Parameters whose effects may vary by blueberry type, cultivar, production system, climate, substrate, age, or intervention protocol must declare each applicable scope. Unknown scope is `UNBOUND`, not wildcard. Units are explicit and dimensionally checked. Chill hours, Utah chill units, and chill portions are different types; they cannot be coerced by relabeling. Base temperature, upper temperature, chill thresholds, forcing thresholds, pruning response, thinning response, source-sink response, and fruit-development kernels remain unbound in S1.

## 5. Deterministic parameter hash

`parameter_hash` is SHA-256 over UTF-8 canonical JSON containing all parameter fields except `parameter_hash` itself, with keys sorted lexicographically, finite JSON numbers only, no NaN/Infinity, compact separators, and no trailing whitespace. Decimal values serialize as canonical decimal strings to avoid binary-float drift. The parameter ID, value, unit, scopes, authority, calibration status, validity, and version are all included in the preimage.

## 6. Prohibited inference

S1 must not convert a reported paper temperature, chill requirement, GDD, bloom-to-ripe duration, pruning intensity, flower/leaf ratio, fruit set percentage, berry weight, or yield effect into a production default. It must not create a Yunnan default, select a global chill model, pick a source-sink formula, or infer missing values from a neighboring cultivar/system. Exact formulas and coefficients belong to later authorized calibration/model work.

## 7. Versioning

`PARAMETER_AUTHORITY_CONTRACT_VERSION=V0_9_S1_R1`. Contract serialization and hash semantics are versioned. A parameter's source, scope, unit, or authority change creates a new record/version rather than an in-place edit.
