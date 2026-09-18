# V0.5 area-forecast productization (R10)

This document freezes the first callable BASE-grain inference boundary. It is
an engineering integration of the closed R1–R9 research artifacts; it does
not retrain, tune, or replace a model.

## Frozen composition

```text
reference Base area + immediate prior Base yield
    -> BASE_AWARE_BASELINE_R1 season total
season total + AREA_DAILY_RIDGE_V1_FROZEN_REFERENCE normalized shape
    -> daily curve
daily curve
    -> deterministic single-day and rolling-7-day peaks
```

The product requires an exact registered `base_id` or exact registered base
name and a positive decimal-string `target_area_mu`. A registered Base with no
frozen immediate-prior yield fails closed. There is no global-yield fallback,
fuzzy identity match, weather input, or future-plan input.

The default business window is July 1 through April 15 inclusive. A caller may
provide a contiguous seven-day-or-longer sub-window inside that season. The
daily curve is normalized over the requested window and all peaks are derived
from that final curve with the existing earliest-date tie break.

## Frozen artifacts

| Artifact | File SHA256 | Canonical payload hash |
| --- | --- | --- |
| Base reference registry | `0d382e644b271df4d9b8e7f31f8e4148816135faf70aa1e21a97ee2eb6374b85` | `5e52493160f9e11bc9980ab7601be85d0aef43240f0cb2d3917d66afa958810b` |
| R10A corrected inference/model artifact | `cf0e1c4bffc4acc404dd0479c36b02f78df893ef25dda819359eaa317157dabf` | `399c38f81abdea0122097cd5a68bc25147cc55f58dc51e1393b9282e5bc4cbad` |

The registry snapshot records the user-provided workbook identity
`基地位置亩数.xlsx` (`73329a1f7315f81ce7cf24d59dc7b3a49507520cd179a205b7267a5b430db7d7`),
39 Bases, and 41,335.000000 mu. The model artifact binds the accepted
identity-reconstruction history-yield facts and the exact fitted Ridge
coefficients. The R1/R9 research manifests, identity mapping, and source XLS
hashes are recorded in the artifact. Private raw business workbooks and
private research output are not committed. The pre-fix R10 artifact
(`b2659007...` / `45512d7d...`) is retained only as forensic evidence and is
not an accepted product authority.

## Output status and limitations

```ini
MODEL_STATUS=EXPERIMENTAL
SEASON_TOTAL_STATUS=EXPERIMENTAL
DAILY_CURVE_STATUS=EXPLORATORY
SINGLE_DAY_PEAK_STATUS=EXPLORATORY
ROLLING_7DAY_PEAK_STATUS=EXPLORATORY
WEATHER_USED=false
FUTURE_PLAN_USED=false
```

Frozen evidence remains: known-Base total WAPE 0.379265725, stable-history
total WAPE 0.251107822, daily WAPE 0.694130360, peak-date MAE 22.230769 days,
and rolling-7-day peak-start MAE 20.769231 days. These are research metrics,
not a confidence interval or production approval.

## Callable entry point

The additive CLI form is:

```bash
python -m backend.app.cli area-forecast \
  --base "保山杨柳基地" \
  --area-mu 394.000000 \
  --season 2025-2026
```

The legacy `area-forecast --input <farm-grain-request.json>` mode is retained.
When `--output <path>` is supplied to the BASE form, the result is written as
an immutable canonical JSON document. Reload verifies the daily dates, share
sum, mass balance, deterministic peaks, and result hash without rerunning the
forecast or loading current authority.

## Real registered-Base replay (pre-fix forensic record)

The local acceptance run used `保山杨柳基地`, target area `394.000000` mu, and
target season `2025-2026` (there is a frozen 2024-2025 immediate prior yield).
It produced 289 daily rows, predicted season total `223540.014148` kg, single
day peak `2026-04-15` / `5771.185798` kg, rolling 7-day peak
`2026-04-09..2026-04-15` / `38625.006568` kg, and result hash
`be5fdd4b196a60f38a69b5e47c1feb101c11fd2faae916a8b4830245d8ba2ec7`.

This historical R10 value is retained to identify the stale partial-subtotal
bug; it is not an accepted post-fix result. A target season without a frozen
immediate-prior Base yield, such as Yangliu
2026-2027 in this artifact snapshot, is rejected rather than using an older
season or a global fallback.

## R10A provenance correction

The pre-fix lookup used the old active-date partial subtotal for Yangliu
2024-2025 (`223540.014000` kg). R10A now binds all 43 history rows to the
accepted rows in `HISTORICAL_IDENTITY_RECONSTRUCTION_R1`, using the two
source-file hashes `8fa003b4...` (2023-2024) and `f4ffba4...` (2024-2025),
and identity-mapping hash
`8d17880141485c407d2e011d70c12d1f828b1966abba32a42b201c33bc4a5044`.
The Ridge coefficients are unchanged and no model was refit.

The corrected Yangliu representative inference uses the 2024-2025 mapped
quantity `448751.251000` kg and yields:

* predicted season total: `448751.251004` kg;
* single-day peak: `2026-04-15` / `11585.517951` kg;
* rolling 7-day peak: `2026-04-09..2026-04-15` / `77538.780175` kg;
* result hash: `7b7ba71ab01b3a34559ec65740811a025569de8234949bf711676d70fcf01aad`.

The current artifact has 39 registry bases and 43 accepted base-season
history rows; provenance validation found zero stale rows and zero mismatched
base IDs. This is a representative inference for the already-ended
2025-2026 interval, not a real-time forecast. For an execution on
`2026-09-18`, `REAL_FORECAST_EXECUTED=false` and
`REPRESENTATIVE_INFERENCE_EXECUTED=true`.

The full-season temporal artifact is not clipped: the single-day peak happens
at the forecast-end boundary, but `temporal_curve_truncated=false`,
`renormalization_applied=false`, and `clipped_mass_reallocated=false`.
For an explicitly shorter window, the in-window shape is normalized without
moving clipped probability mass to the final day.

## R10B final acceptance

The target-area sensitivity acceptance uses the Yangliu Base reference area
(`394.000000` mu) and target-area factors `0.5`, `1.0`, and `1.5`. The frozen
temporal artifact is evaluated at the reference area, so target-area changes
scale season total, daily quantities, and peak quantities without changing
normalized shares or peak dates. Each scaled result has a distinct result
hash.

The requested future-season CLI inference for `2026-2027` was attempted with
the same registered Base and target area. It fails closed with
`PRIOR_SEASON_HISTORY_MISSING`: the frozen productization history authority
contains accepted `2023-2024` and `2024-2025` rows only. No older-season
fallback or fabricated `2025-2026` row was used. Therefore this acceptance
does not mark V0.5 complete.

The product now exposes `peak_at_forecast_boundary` metadata. A boundary peak
is retained as computed; no quantity is moved to the final day. Daily
serialization continues to use the existing mass-balance tolerance.
