# Cross-season business identity decisions and authority correction proposal

Task: `CROSS_SEASON_BUSINESS_IDENTITY_DECISION_CAPTURE_AND_AUTHORITY_CORRECTION_PROPOSAL_R1`
Audit baseline: `e6c2c797c8b31c0709d793f32f5ff65aae8e6fb7`

## Decision capture

- Business questions recorded: 40 (Q01-Q40).
- Decisions are bound to the private confirmation package and decision CSV hashes in the machine evidence.
- Confirming identity was not captured; no person was inferred.
- The report omits source labels, Base names, and private row-level quantities.

## Non-authoritative simulation

The private proposal is a simulation only. Existing mapping authority, Base Registry, V0.7 evidence, model configuration, and released artifacts were not modified. The proposal CSV remains outside Git in a mode-0600 private artifact directory.

- Current mapped quantity: 90950421.578 kg.
- Proposed mapped quantity: 109010615.352 kg.
- Simulated mapped gain: 18060193.774 kg.
- Current unresolved quantity: 28634123.590 kg.
- Proposed unresolved quantity: 10573929.816 kg.
- Simulated unresolved reduction: 18060193.774 kg.
- Total source quantity: 122983150.913 kg; exact per-season reconciliation: True.

| Season | Raw kg | Current mapped kg | Current mapping rate | Proposed mapped kg | Proposed unresolved kg | Proposed mapping rate | Reconciliation delta kg |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2023-2024 | 30148211.706 | 11656395.430 | 0.3866363797518438455667649742 | 23551840.401 | 4957687.840 | 0.7812019044669501432882103299 | 0.000 |
| 2024-2025 | 42440018.628 | 30590748.252 | 0.7207995953097346505716995559 | 36755290.292 | 3924806.056 | 0.8660526427702961940368166230 | 0.000 |
| 2025-2026 | 50394920.579 | 48703277.896 | 0.9664322780239696982180256409 | 48703484.659 | 1691435.920 | 0.9664363808779403850958095981 | 0.000 |

## Decision-specific safeguards

- Q14 remains season-scoped: the 2024-2025 rejection does not propagate into 2025-2026.
- Q17 uses exact label split rules. Any unlisted label remains unresolved and makes the result partial.
- Q26 is season-scoped; 2024-2025 is not rewritten as a later-season Base.
- Q07/Q10 correct only the confirmed parent relation for the exact subfarm row. Parent totals are not copied into subfarm quantities.
- Duplicate question scopes are de-duplicated by exact source identity.
- Q17 unhandled source-label count: 0.

## V0.7 impact and limits

- Affected Base-season scopes (simulation): 18.
- Affected prior-history identity rows: 58.
- Affected validation-label identity rows: 48.
- Candidate S3 cohort overlap: 1 Base-season scope candidates; source-label lineage is not proven.
- V0.7 S3 impact is reported at Base-season scope only; exact source-label lineage to frozen S3 rows is not proven.
- If a later task authorizes applying a correction, V0.7 recomputation and Model A/B replay are required; none was executed here.

## Authority and release boundary

`MAPPING_AUTHORITY_APPLIED=false`; `MODEL_CHANGED=false`; `MODEL_RETRAINED=false`; `BACKTEST_EXECUTED=false`; `V0_7_CHANGED=false`.
This Draft PR records decisions and a proposed correction only. It does not authorize applying the proposal or changing released V0.7 artifacts.

See the adjacent machine-readable evidence for input hashes, aggregate reconciliation, affected-scope counts, and authorization flags.
