# V0.7-S1 Formal Multi-Season Baseline Validation

## Status

`TASK_ID=V0_7_S1_FORMAL_MULTI_SEASON_BASELINE_VALIDATION_R1`

This is the formal historical out-of-time validation of the frozen V0.5
Model A. It is an engineering and evidence result, not a production-accuracy
approval.

The run was based on `origin/main=9eda9dffdcb5f88195f511c7802c831724fcc73c`.
The V0.7 plan is present in `docs/v0-7/`, and the PR #644 merge is in the
main ancestry.

## Frozen model and scope

| Item | Frozen value |
| --- | --- |
| Model A | `AREA_PLUS_HISTORICAL_HARVEST` |
| Total model | `BASE_AWARE_BASELINE_R1` |
| Temporal model | `AREA_DAILY_RIDGE_V1_FROZEN_REFERENCE` |
| Rolling refit | Past seasons only; same algorithm and objective |
| Weather | Not used; no weather feature generated |
| Model B | Not created |
| Hyperparameter/model-family search | Disabled |
| Business accuracy threshold | `NOT_FROZEN` |
| Production accuracy approval | `false` |

No validation-season label was used to choose a Base, date scope, model,
feature, objective, or parameter before prediction sealing.

## Authorities

The validation reuses the existing source and identity authorities. The
reference area is explicitly retained as the frozen Model A proxy; it is not
upgraded to season-specific actual productive area by this task.

| Authority | SHA256 / value |
| --- | --- |
| 2023-2024 source | `8fa003b4abdea0b0bd9c50a9fbd619ad15ea5c9a2e790faa5e5b3353a2a01d20` |
| 2024-2025 source | `f4ffba4b10a3129c768871bc5f3dfa2845534bc0e7eb04e166ba97211fa92dd6` |
| 2025-2026 source | `fc83859871c544b584b3999b6796ddd518cdc8bb8dd9754f5b5c9d6ae62db81a` |
| Versioned Base Registry file | `0d382e644b271df4d9b8e7f31f8e4148816135faf70aa1e21a97ee2eb6374b85` |
| Base Registry source workbook | `73329a1f7315f81ce7cf24d59dc7b3a49507520cd179a205b7267a5b430db7d7` |
| Historical identity mapping | `8d17880141485c407d2e011d70c12d1f828b1966abba32a42b201c33bc4a5044` |
| Current Base member mapping for 2025-2026 | `d40dbc3a1328d79e10670999ee613fcef8fa3ee32659db16dfe67db3e6b91b5b` |
| Combined identity authority | `c46e198cda2e6c4296db184af5c2e1f3b200a944309aa43039fa3be42a0bbd0e` |
| Frozen temporal config | `cf0e1c4bffc4acc404dd0479c36b02f78df893ef25dda819359eaa317157dabf` |

Coverage semantics are fail-closed: confirmed zero is comparable, while
unknown/missing/unresolved rows are not converted to zero. Complete
season-total, single-day peak, and rolling-seven-day metrics require complete
actual coverage.

## Label-blind protocol

Each fold follows the same boundary:

1. Load only past training authorities and frozen model configuration.
2. Generate and persist prediction rows and the prediction manifest.
3. Seal prediction, training-input, artifact-manifest, and model identities.
4. Only then load the validation source and score it.

The generated manifests record:

```ini
PREDICTIONS_SEALED_BEFORE_VALIDATION_LABEL_SCORING=true
VALIDATION_LABEL_LEAKAGE=false
VALIDATION_BLINDNESS=PASS
POST_PREDICTION_SCORING_ONLY=true
```

Changing validation actuals after sealing changes score evidence only; it does
not change the prediction hash. A fresh Python process reproduced both fold
prediction and metric hashes.

## Fold results

WAPE values below are pooled absolute error divided by pooled actual, never an
arithmetic mean of Base-level or fold-level WAPEs. Bias is predicted minus
actual; negative means underprediction.

| Fold | Train | Validate | Predicted Base count | Actual Base count | Comparable daily rows | Unknown rows | Complete Base-season rows |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| A | 2023-2024 | 2024-2025 | 39 | 30 | 2,968 | 8,303 | 0 |
| B | 2023-2024 + 2024-2025 | 2025-2026 | 39 | 39 | 6,368 | 4,903 | 0 |

All 39 validation Base-seasons in both folds are `PARTIAL`; none qualifies for
complete season-total or peak truth under the frozen authority policy.

| Metric | Fold A | Fold B | Combined OOT |
| --- | ---: | ---: | ---: |
| Season-total WAPE | `NOT_COMPUTABLE_NO_COMPLETE_TOTAL_AUTHORITY` | `NOT_COMPUTABLE_NO_COMPLETE_TOTAL_AUTHORITY` | `NOT_COMPUTABLE_NO_COMPLETE_TOTAL_AUTHORITY` |
| Daily WAPE | 0.6198167169628233647543879985 | 0.7168968026307904576336715891 | 0.6902328745020899423136283210 |
| Daily Bias (kg/row) | -1649.135154259770889487870620 | -4227.739054537374371859296482 | -3407.977231912703513281919452 |
| Single-day peak quantity WAPE | `NOT_COMPUTABLE_NO_COMPLETE_PEAK_AUTHORITY` | `NOT_COMPUTABLE_NO_COMPLETE_PEAK_AUTHORITY` | `NOT_COMPUTABLE_NO_COMPLETE_PEAK_AUTHORITY` |
| Single-day peak date absolute error | `NOT_COMPUTABLE_NO_COMPLETE_PEAK_AUTHORITY` | `NOT_COMPUTABLE_NO_COMPLETE_PEAK_AUTHORITY` | `NOT_COMPUTABLE_NO_COMPLETE_PEAK_AUTHORITY` |
| Rolling-7 quantity WAPE | `NOT_COMPUTABLE_NO_COMPLETE_ROLLING7_AUTHORITY` | `NOT_COMPUTABLE_NO_COMPLETE_ROLLING7_AUTHORITY` | `NOT_COMPUTABLE_NO_COMPLETE_ROLLING7_AUTHORITY` |
| Rolling-7 start-date absolute error | `NOT_COMPUTABLE_NO_COMPLETE_ROLLING7_AUTHORITY` | `NOT_COMPUTABLE_NO_COMPLETE_ROLLING7_AUTHORITY` | `NOT_COMPUTABLE_NO_COMPLETE_ROLLING7_AUTHORITY` |

Combined daily WAPE uses 9,336 comparable rows, with pooled actual
`66,273,244.767 kg` and pooled absolute error `45,743,972.238107 kg`.

Daily absolute-error distributions are:

| View | Median kg | P75 kg | P90 kg | Max kg |
| --- | ---: | ---: | ---: | ---: |
| Fold A | 2,748.7083275 | 5,341.92389150 | 9,015.2017915 | 25,528.179851 |
| Fold B | 3,350.0872365 | 7,583.53006875 | 13,475.5605327 | 51,414.621936 |
| Combined | 3,126.8383665 | 6,725.42738700 | 11,817.9435415 | 51,414.621936 |

## Area and coverage report

Every prediction uses the versioned 39-Base reference-area registry with
`area_status=FROZEN_ACCEPTED_PROXY` and `area_semantics=REFERENCE_AREA`.
No new historical area proxy was accepted.

| Fold | Train area-eligible | Train proxy | Validation area-eligible | Validation proxy | Area missing | Area conflicting |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 13 | 13 | 39 | 39 | 0 | 0 |
| B | 30 unique Base / 43 Base-season samples | 43 | 39 | 39 | 0 | 0 |

Unknown actual status counts are retained in the machine-readable evidence:

- Fold A: `UNKNOWN_GLOBAL_NO_RECORD=312`, `UNKNOWN_MEMBER_COVERAGE=4563`,
  `UNKNOWN_MISSING=3428`.
- Fold B: `UNKNOWN_GLOBAL_NO_RECORD=2379`, `UNKNOWN_MISSING=2524`.

The full 78 Base-season per-Base diagnostics contain predicted totals and
daily rows, coverage status, known/unknown row counts, unknown status counts,
and the computable/not-computable metric objects. They remain in the private
generated artifact set; this repository commits only manifests, hashes, and
summary evidence.

## Sealed artifacts

| Artifact | Prediction/score identity |
| --- | --- |
| Fold A prediction hash | `72b2d5fa21fc0fab84d6e3c054576c66353899c1526a2b219272d54737c8ab73` |
| Fold A artifact manifest hash | `3642d39bb8ad479964b588b2350dc11fd5738d48a3003957d39ba39a75aa9a85` |
| Fold A score hash | `a86da0536c3ee18274cc73b664d847f6944c25cc9e844e37381ea100f6a0a356` |
| Fold B prediction hash | `1a3fede069dcf53ae8631428d000466bfffb904a5d3efb9cd7fae3f8ca4332ed` |
| Fold B artifact manifest hash | `3993ee942d135b99287bab386b5c1fe8ce91e3b93d51aaf02184ad69ef9bfaf2` |
| Fold B score hash | `a1adc38b19923a636bb355aa68567a4b469c21e5d4dfbd98f2ee0d18c63f5a11` |
| Private replay evidence canonical hash | `a215cd45a7521c54b700527f7f5ba3169641a99186d88e563660323f00b9356d` |

The complete machine-readable summary is
[`s1-formal-multi-season-baseline-validation.json`](../evidence/s1-formal-multi-season-baseline-validation.json).

## Formal conclusion

```ini
THREE_SEASON_DATA_AUTHORITY_PASS=PASS
ROLLING_OOT_FOLD_A_PASS=PASS
ROLLING_OOT_FOLD_B_PASS=PASS
VALIDATION_LABEL_LEAKAGE=false
VALIDATION_BLINDNESS=PASS
PREDICTIONS_SEALED_BEFORE_VALIDATION_LABEL_SCORING=true
MODEL_A_FORMAL_HISTORICAL_BASELINE_ESTABLISHED=true
CURRENT_AREA_MODEL_VALIDATION_STATUS=VALIDATED_WITH_MEASURED_DAILY_ERROR;COMPLETE_TOTAL_AND_PEAK_METRICS_COVERAGE_LIMITED
PRODUCTION_ACCURACY_APPROVED=false
WEATHER_USED=false
MODEL_B_CREATED=false
```

This establishes a reproducible, label-blind historical baseline and exposes
the measured daily error. It does not establish a complete-season accuracy
approval because the supplied actual authority has no complete Base-season
coverage for either validation fold. It also does not authorize S2, weather
features, Model B, tuning, Ready, or Merge.
