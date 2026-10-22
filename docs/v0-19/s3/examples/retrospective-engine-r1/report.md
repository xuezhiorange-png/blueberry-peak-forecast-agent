# SYNTHETIC retrospective numerical report

SYNTHETIC_NUMERICAL_REHEARSAL_NOT_REAL_ACCURACY_OR_MODEL_PROMOTION

Report SHA256: `33e5f666d45b1d3de43f650f041601314b9af5cabc495370bfcc8073ee920ae0`

Late computation is preserved; strict PIT=false. Real C0=0; real execution BLOCKED.

## RETROSPECTIVE_REPLAY:H15_LOCAL

| Metric | baseline | candidate | common / candidate |
| --- | --- | --- | --- |
| SEASON_TOTAL_WAPE | None | None | 0 / 8 |
| DAILY_WAPE | 0.23219911783238815374921235034656584751102709514808 | 0.33423901827347195967233774417139256458727158160050 | 6 / 8 |
| DAILY_MAE | 4.0944444444444444444444444444444444444444444444444 | 5.8937480222222222222222222222222222222222222222222 | 6 / 8 |
| SINGLE_DAY_PEAK_DATE_MAE | 2 | 2 | 4 / 8 |
| SINGLE_DAY_PEAK_QUANTITY_MAE | 8.3333333333333333333333333333333333333333333333333 | 11.708333333333333333333333333333333333333333333333 | 6 / 8 |
| ROLLING_7DAY_PEAK_START_MAE | 0 | 0 | 4 / 8 |
| ROLLING_7DAY_PEAK_QUANTITY_MAE | 35.000000 | 35.000000 | 6 / 8 |
| BASE_BREADTH | {"improved": 1, "improved_actual_kg_share": {"denominator": "1587", "numerator": "537", "value": "0.33837429111531190926275992438563327032136105860113"}, "n_base": 3, "per_base_delta": {"SYNTHETIC-BASE-A": "-24.195895", "SYNTHETIC-BASE-B": "177.875282", "SYNTHETIC-BASE-C": "8.257935"}, "status": "PASS_SYNTHETIC", "tied": 0, "worsened": 2} | — | — |
| SAMPLE_COVERAGE | {"DAILY_MAE": "0.75", "DAILY_WAPE": "0.75", "ROLLING_7DAY_PEAK_QUANTITY_MAE": "0.75", "ROLLING_7DAY_PEAK_START_MAE": "0.5", "SEASON_TOTAL_WAPE": "0", "SINGLE_DAY_PEAK_DATE_MAE": "0.5", "SINGLE_DAY_PEAK_QUANTITY_MAE": "0.75"} | — | — |
| NOT_COMPUTABLE_COUNT | {"DAILY_MAE": 2, "DAILY_WAPE": 2, "ROLLING_7DAY_PEAK_QUANTITY_MAE": 2, "ROLLING_7DAY_PEAK_START_MAE": 4, "SEASON_TOTAL_WAPE": 8, "SINGLE_DAY_PEAK_DATE_MAE": 4, "SINGLE_DAY_PEAK_QUANTITY_MAE": 2} | — | — |

### Per Base paired absolute-error delta (candidate - baseline)

- SYNTHETIC-BASE-A: -24.195895 kg
- SYNTHETIC-BASE-B: 177.875282 kg
- SYNTHETIC-BASE-C: 8.257935 kg

### Per Base numerical comparison (negative delta = lower error)

| Base | Metric | baseline | candidate | delta |
| --- | --- | --- | --- | --- |
| SYNTHETIC-BASE-A | SEASON_TOTAL_WAPE | None | None | None |
| SYNTHETIC-BASE-A | DAILY_WAPE | 0.19739292364990689013035381750465549348230912476723 | 0.15233539106145251396648044692737430167597765363128 | -0.04505753258845437616387337057728119180633147113595 |
| SYNTHETIC-BASE-A | DAILY_MAE | 3.5333333333333333333333333333333333333333333333333 | 2.7268035 | -0.8065298333333333333333333333333333333333333333333 |
| SYNTHETIC-BASE-A | SINGLE_DAY_PEAK_DATE_MAE | 4 | 1 | -3 |
| SYNTHETIC-BASE-A | SINGLE_DAY_PEAK_QUANTITY_MAE | 10.000000 | 3.250000 | -6.750000 |
| SYNTHETIC-BASE-A | ROLLING_7DAY_PEAK_START_MAE | 0 | 0 | 0 |
| SYNTHETIC-BASE-A | ROLLING_7DAY_PEAK_QUANTITY_MAE | 0.000000 | 0.000000 | 0.000000 |
| SYNTHETIC-BASE-B | SEASON_TOTAL_WAPE | None | None | None |
| SYNTHETIC-BASE-B | DAILY_WAPE | 0.000000 | 0.16940503047619047619047619047619047619047619047619 | 0.16940503047619047619047619047619047619047619047619 |
| SYNTHETIC-BASE-B | DAILY_MAE | 0.000000 | 5.9291760666666666666666666666666666666666666666667 | 5.9291760666666666666666666666666666666666666666667 |
| SYNTHETIC-BASE-B | SINGLE_DAY_PEAK_DATE_MAE | 0 | 3 | 3 |
| SYNTHETIC-BASE-B | SINGLE_DAY_PEAK_QUANTITY_MAE | 0.000000 | 13.500000 | 13.500000 |
| SYNTHETIC-BASE-B | ROLLING_7DAY_PEAK_START_MAE | 0 | 0 | 0 |
| SYNTHETIC-BASE-B | ROLLING_7DAY_PEAK_QUANTITY_MAE | 0.000000 | 0.000000 | 0.000000 |
| SYNTHETIC-BASE-C | SEASON_TOTAL_WAPE | None | None | None |
| SYNTHETIC-BASE-C | DAILY_WAPE | None | None | None |
| SYNTHETIC-BASE-C | DAILY_MAE | 8.750000 | 9.0252645 | 0.2752645 |
| SYNTHETIC-BASE-C | SINGLE_DAY_PEAK_DATE_MAE | None | None | None |
| SYNTHETIC-BASE-C | SINGLE_DAY_PEAK_QUANTITY_MAE | 15.000000 | 18.375000 | 3.375000 |
| SYNTHETIC-BASE-C | ROLLING_7DAY_PEAK_START_MAE | None | None | None |
| SYNTHETIC-BASE-C | ROLLING_7DAY_PEAK_QUANTITY_MAE | 105.000000 | 105.000000 | 0.000000 |
| SYNTHETIC-BASE-D | SEASON_TOTAL_WAPE | None | None | None |
| SYNTHETIC-BASE-D | DAILY_WAPE | None | None | None |
| SYNTHETIC-BASE-D | DAILY_MAE | None | None | None |
| SYNTHETIC-BASE-D | SINGLE_DAY_PEAK_DATE_MAE | None | None | None |
| SYNTHETIC-BASE-D | SINGLE_DAY_PEAK_QUANTITY_MAE | None | None | None |
| SYNTHETIC-BASE-D | ROLLING_7DAY_PEAK_START_MAE | None | None | None |
| SYNTHETIC-BASE-D | ROLLING_7DAY_PEAK_QUANTITY_MAE | None | None | None |

## RETROSPECTIVE_REPLAY:H7_PREFIX

| Metric | baseline | candidate | common / candidate |
| --- | --- | --- | --- |
| SEASON_TOTAL_WAPE | None | None | 0 / 8 |
| DAILY_WAPE | 0.23333333333333333333333333333333333333333333333333 | 0.309139125 | 6 / 8 |
| DAILY_MAE | 5.3333333333333333333333333333333333333333333333333 | 7.0660371428571428571428571428571428571428571428571 | 6 / 8 |
| SINGLE_DAY_PEAK_DATE_MAE | 1.5 | 1.5 | 4 / 8 |
| SINGLE_DAY_PEAK_QUANTITY_MAE | 6.6666666666666666666666666666666666666666666666667 | 10.250000 | 6 / 8 |
| ROLLING_7DAY_PEAK_START_MAE | 0 | 0 | 4 / 8 |
| ROLLING_7DAY_PEAK_QUANTITY_MAE | 29.666666666666666666666666666666666666666666666667 | 36.259391333333333333333333333333333333333333333333 | 6 / 8 |
| BASE_BREADTH | {"improved": 1, "improved_actual_kg_share": {"denominator": "960", "numerator": "320", "value": "0.33333333333333333333333333333333333333333333333333"}, "n_base": 3, "per_base_delta": {"SYNTHETIC-BASE-A": "-16.206969", "SYNTHETIC-BASE-B": "80.758195", "SYNTHETIC-BASE-C": "8.222334"}, "status": "PASS_SYNTHETIC", "tied": 0, "worsened": 2} | — | — |
| SAMPLE_COVERAGE | {"DAILY_MAE": "0.75", "DAILY_WAPE": "0.75", "ROLLING_7DAY_PEAK_QUANTITY_MAE": "0.75", "ROLLING_7DAY_PEAK_START_MAE": "0.5", "SEASON_TOTAL_WAPE": "0", "SINGLE_DAY_PEAK_DATE_MAE": "0.5", "SINGLE_DAY_PEAK_QUANTITY_MAE": "0.75"} | — | — |
| NOT_COMPUTABLE_COUNT | {"DAILY_MAE": 2, "DAILY_WAPE": 2, "ROLLING_7DAY_PEAK_QUANTITY_MAE": 2, "ROLLING_7DAY_PEAK_START_MAE": 4, "SEASON_TOTAL_WAPE": 8, "SINGLE_DAY_PEAK_DATE_MAE": 4, "SINGLE_DAY_PEAK_QUANTITY_MAE": 2} | — | — |

### Per Base paired absolute-error delta (candidate - baseline)

- SYNTHETIC-BASE-A: -16.206969 kg
- SYNTHETIC-BASE-B: 80.758195 kg
- SYNTHETIC-BASE-C: 8.222334 kg

### Per Base numerical comparison (negative delta = lower error)

| Base | Metric | baseline | candidate | delta |
| --- | --- | --- | --- | --- |
| SYNTHETIC-BASE-A | SEASON_TOTAL_WAPE | None | None | None |
| SYNTHETIC-BASE-A | DAILY_WAPE | 0.200000 | 0.149353221875 | -0.050646778125 |
| SYNTHETIC-BASE-A | DAILY_MAE | 4.5714285714285714285714285714285714285714285714286 | 3.4137879285714285714285714285714285714285714285714 | -1.1576406428571428571428571428571428571428571428572 |
| SYNTHETIC-BASE-A | SINGLE_DAY_PEAK_DATE_MAE | 3 | 0.5 | -2.5 |
| SYNTHETIC-BASE-A | SINGLE_DAY_PEAK_QUANTITY_MAE | 5.000000 | 3.250000 | -1.750000 |
| SYNTHETIC-BASE-A | ROLLING_7DAY_PEAK_START_MAE | 0 | 0 | 0 |
| SYNTHETIC-BASE-A | ROLLING_7DAY_PEAK_QUANTITY_MAE | 9.000000 | 8.2223355 | -0.7776645 |
| SYNTHETIC-BASE-B | SEASON_TOTAL_WAPE | None | None | None |
| SYNTHETIC-BASE-B | DAILY_WAPE | 0.000000 | 0.1261846796875 | 0.1261846796875 |
| SYNTHETIC-BASE-B | DAILY_MAE | 0.000000 | 5.7684425 | 5.7684425 |
| SYNTHETIC-BASE-B | SINGLE_DAY_PEAK_DATE_MAE | 0 | 2.5 | 2.5 |
| SYNTHETIC-BASE-B | SINGLE_DAY_PEAK_QUANTITY_MAE | 0.000000 | 10.000000 | 10.000000 |
| SYNTHETIC-BASE-B | ROLLING_7DAY_PEAK_START_MAE | 0 | 0 | 0 |
| SYNTHETIC-BASE-B | ROLLING_7DAY_PEAK_QUANTITY_MAE | 0.000000 | 16.4446715 | 16.4446715 |
| SYNTHETIC-BASE-C | SEASON_TOTAL_WAPE | None | None | None |
| SYNTHETIC-BASE-C | DAILY_WAPE | None | None | None |
| SYNTHETIC-BASE-C | DAILY_MAE | 11.428571428571428571428571428571428571428571428571 | 12.015881 | 0.587309571428571428571428571428571428571428571429 |
| SYNTHETIC-BASE-C | SINGLE_DAY_PEAK_DATE_MAE | None | None | None |
| SYNTHETIC-BASE-C | SINGLE_DAY_PEAK_QUANTITY_MAE | 15.000000 | 17.500000 | 2.500000 |
| SYNTHETIC-BASE-C | ROLLING_7DAY_PEAK_START_MAE | None | None | None |
| SYNTHETIC-BASE-C | ROLLING_7DAY_PEAK_QUANTITY_MAE | 80.000000 | 84.111167 | 4.111167 |
| SYNTHETIC-BASE-D | SEASON_TOTAL_WAPE | None | None | None |
| SYNTHETIC-BASE-D | DAILY_WAPE | None | None | None |
| SYNTHETIC-BASE-D | DAILY_MAE | None | None | None |
| SYNTHETIC-BASE-D | SINGLE_DAY_PEAK_DATE_MAE | None | None | None |
| SYNTHETIC-BASE-D | SINGLE_DAY_PEAK_QUANTITY_MAE | None | None | None |
| SYNTHETIC-BASE-D | ROLLING_7DAY_PEAK_START_MAE | None | None | None |
| SYNTHETIC-BASE-D | ROLLING_7DAY_PEAK_QUANTITY_MAE | None | None | None |

## SYNTHETIC_COMPLETE_CALENDAR_CONTROL:FULL_SEASON

| Metric | baseline | candidate | common / candidate |
| --- | --- | --- | --- |
| SEASON_TOTAL_WAPE | 0.16666666666666666666666666666666666666666666666667 | 0.16666666666666666666666666666666666666666666666667 | 3 / 4 |
| DAILY_WAPE | 0.23439153439153439153439153439153439153439153439153 | 0.33052478095238095238095238095238095238095238095238 | 3 / 4 |
| DAILY_MAE | 3.5158730158730158730158730158730158730158730158730 | 4.9578717142857142857142857142857142857142857142857 | 3 / 4 |
| SINGLE_DAY_PEAK_DATE_MAE | 2 | 2 | 2 / 4 |
| SINGLE_DAY_PEAK_QUANTITY_MAE | 8.3333333333333333333333333333333333333333333333333 | 11.708333333333333333333333333333333333333333333333 | 3 / 4 |
| ROLLING_7DAY_PEAK_START_MAE | 0 | 0 | 2 / 4 |
| ROLLING_7DAY_PEAK_QUANTITY_MAE | 35.000000 | 35.000000 | 3 / 4 |
| BASE_BREADTH | {"improved": 1, "improved_actual_kg_share": {"denominator": "945", "numerator": "315", "value": "0.33333333333333333333333333333333333333333333333333"}, "n_base": 3, "per_base_delta": {"SYNTHETIC-BASE-A": "-20.509236", "SYNTHETIC-BASE-B": "111.355154", "SYNTHETIC-BASE-C": "0.000000"}, "status": "PASS_SYNTHETIC", "tied": 1, "worsened": 1} | — | — |
| SAMPLE_COVERAGE | {"DAILY_MAE": "0.75", "DAILY_WAPE": "0.75", "ROLLING_7DAY_PEAK_QUANTITY_MAE": "0.75", "ROLLING_7DAY_PEAK_START_MAE": "0.5", "SEASON_TOTAL_WAPE": "0.75", "SINGLE_DAY_PEAK_DATE_MAE": "0.5", "SINGLE_DAY_PEAK_QUANTITY_MAE": "0.75"} | — | — |
| NOT_COMPUTABLE_COUNT | {"DAILY_MAE": 1, "DAILY_WAPE": 1, "ROLLING_7DAY_PEAK_QUANTITY_MAE": 1, "ROLLING_7DAY_PEAK_START_MAE": 2, "SEASON_TOTAL_WAPE": 1, "SINGLE_DAY_PEAK_DATE_MAE": 2, "SINGLE_DAY_PEAK_QUANTITY_MAE": 1} | — | — |

### Per Base paired absolute-error delta (candidate - baseline)

- SYNTHETIC-BASE-A: -20.509236 kg
- SYNTHETIC-BASE-B: 111.355154 kg
- SYNTHETIC-BASE-C: 0.000000 kg

### Per Base numerical comparison (negative delta = lower error)

| Base | Metric | baseline | candidate | delta |
| --- | --- | --- | --- | --- |
| SYNTHETIC-BASE-A | SEASON_TOTAL_WAPE | 0.000000 | 0.000000 | 0.000000 |
| SYNTHETIC-BASE-A | DAILY_WAPE | 0.20317460317460317460317460317460317460317460317460 | 0.13806591746031746031746031746031746031746031746032 | -0.06510868571428571428571428571428571428571428571428 |
| SYNTHETIC-BASE-A | DAILY_MAE | 3.0476190476190476190476190476190476190476190476190 | 2.0709887619047619047619047619047619047619047619048 | -0.9766302857142857142857142857142857142857142857142 |
| SYNTHETIC-BASE-A | SINGLE_DAY_PEAK_DATE_MAE | 4 | 1 | -3 |
| SYNTHETIC-BASE-A | SINGLE_DAY_PEAK_QUANTITY_MAE | 10.000000 | 3.250000 | -6.750000 |
| SYNTHETIC-BASE-A | ROLLING_7DAY_PEAK_START_MAE | 0 | 0 | 0 |
| SYNTHETIC-BASE-A | ROLLING_7DAY_PEAK_QUANTITY_MAE | 0.000000 | 0.000000 | 0.000000 |
| SYNTHETIC-BASE-B | SEASON_TOTAL_WAPE | 0.000000 | 0.000000 | 0.000000 |
| SYNTHETIC-BASE-B | DAILY_WAPE | 0.000000 | 0.17675421269841269841269841269841269841269841269841 | 0.17675421269841269841269841269841269841269841269841 |
| SYNTHETIC-BASE-B | DAILY_MAE | 0.000000 | 5.3026263809523809523809523809523809523809523809524 | 5.3026263809523809523809523809523809523809523809524 |
| SYNTHETIC-BASE-B | SINGLE_DAY_PEAK_DATE_MAE | 0 | 3 | 3 |
| SYNTHETIC-BASE-B | SINGLE_DAY_PEAK_QUANTITY_MAE | 0.000000 | 13.500000 | 13.500000 |
| SYNTHETIC-BASE-B | ROLLING_7DAY_PEAK_START_MAE | 0 | 0 | 0 |
| SYNTHETIC-BASE-B | ROLLING_7DAY_PEAK_QUANTITY_MAE | 0.000000 | 0.000000 | 0.000000 |
| SYNTHETIC-BASE-C | SEASON_TOTAL_WAPE | None | None | None |
| SYNTHETIC-BASE-C | DAILY_WAPE | None | None | None |
| SYNTHETIC-BASE-C | DAILY_MAE | 7.500000 | 7.500000 | 0.000000 |
| SYNTHETIC-BASE-C | SINGLE_DAY_PEAK_DATE_MAE | None | None | None |
| SYNTHETIC-BASE-C | SINGLE_DAY_PEAK_QUANTITY_MAE | 15.000000 | 18.375000 | 3.375000 |
| SYNTHETIC-BASE-C | ROLLING_7DAY_PEAK_START_MAE | None | None | None |
| SYNTHETIC-BASE-C | ROLLING_7DAY_PEAK_QUANTITY_MAE | 105.000000 | 105.000000 | 0.000000 |
| SYNTHETIC-BASE-D | SEASON_TOTAL_WAPE | None | None | None |
| SYNTHETIC-BASE-D | DAILY_WAPE | None | None | None |
| SYNTHETIC-BASE-D | DAILY_MAE | None | None | None |
| SYNTHETIC-BASE-D | SINGLE_DAY_PEAK_DATE_MAE | None | None | None |
| SYNTHETIC-BASE-D | SINGLE_DAY_PEAK_QUANTITY_MAE | None | None | None |
| SYNTHETIC-BASE-D | ROLLING_7DAY_PEAK_START_MAE | None | None | None |
| SYNTHETIC-BASE-D | ROLLING_7DAY_PEAK_QUANTITY_MAE | None | None | None |

## SYNTHETIC-BASE-A-FULL_SEASON-2000-06-30

origin=2000-06-30T23:59:59+08:00; computed_at=2002-01-01T00:00:00+00:00; historical_issued_at=None

baseline peak: {"date": "2000-07-08", "quantity_kg": "30.000000"}; rolling7: {"end_date": "2000-07-14", "quantity_kg": "210.000000", "start_date": "2000-07-08"}
candidate peak: {"date": "2000-07-11", "quantity_kg": "36.750000"}; rolling7: {"end_date": "2000-07-14", "quantity_kg": "210.000000", "start_date": "2000-07-08"}
actual peak: {"date": "2000-07-12", "quantity_kg": "40"}; rolling7: {"end_date": "2000-07-14", "quantity_kg": "210", "start_date": "2000-07-08"}

| Date | baseline kg | candidate kg | actual kg |
| --- | --- | --- | --- |
| 2000-07-01 | 10.000000 | 8.032787 | 8 |
| 2000-07-02 | 10.000000 | 8.032787 | 8 |
| 2000-07-03 | 10.000000 | 8.032787 | 8 |
| 2000-07-04 | 10.000000 | 8.032787 | 8 |
| 2000-07-05 | 10.000000 | 10.327869 | 11 |
| 2000-07-06 | 10.000000 | 12.622951 | 13 |
| 2000-07-07 | 10.000000 | 14.918032 | 14 |
| 2000-07-08 | 30.000000 | 26.250000 | 20 |
| 2000-07-09 | 30.000000 | 29.750000 | 25 |
| 2000-07-10 | 30.000000 | 33.250000 | 30 |
| 2000-07-11 | 30.000000 | 36.750000 | 35 |
| 2000-07-12 | 30.000000 | 32.375000 | 40 |
| 2000-07-13 | 30.000000 | 28.000000 | 35 |
| 2000-07-14 | 30.000000 | 23.625000 | 25 |
| 2000-07-15 | 5.000000 | 9.746835 | 7 |
| 2000-07-16 | 5.000000 | 7.531645 | 6 |
| 2000-07-17 | 5.000000 | 5.316456 | 5 |
| 2000-07-18 | 5.000000 | 3.101266 | 4 |
| 2000-07-19 | 5.000000 | 3.101266 | 3 |
| 2000-07-20 | 5.000000 | 3.101266 | 4 |
| 2000-07-21 | 5.000000 | 3.101266 | 6 |

## SYNTHETIC-BASE-A-H15_LOCAL-2000-07-03

origin=2000-07-03T23:59:59+08:00; computed_at=2002-01-01T00:00:00+00:00; historical_issued_at=None

baseline peak: {"date": "2000-07-08", "quantity_kg": "30.000000"}; rolling7: {"end_date": "2000-07-14", "quantity_kg": "210.000000", "start_date": "2000-07-08"}
candidate peak: {"date": "2000-07-11", "quantity_kg": "36.750000"}; rolling7: {"end_date": "2000-07-14", "quantity_kg": "210.000000", "start_date": "2000-07-08"}
actual peak: {"date": "2000-07-12", "quantity_kg": "40"}; rolling7: {"end_date": "2000-07-14", "quantity_kg": "210", "start_date": "2000-07-08"}

| Date | baseline kg | candidate kg | actual kg |
| --- | --- | --- | --- |
| 2000-07-04 | 10.000000 | 8.032787 | 8 |
| 2000-07-05 | 10.000000 | 10.327869 | 11 |
| 2000-07-06 | 10.000000 | 12.622951 | 13 |
| 2000-07-07 | 10.000000 | 14.918032 | 14 |
| 2000-07-08 | 30.000000 | 26.250000 | 20 |
| 2000-07-09 | 30.000000 | 29.750000 | 25 |
| 2000-07-10 | 30.000000 | 33.250000 | 30 |
| 2000-07-11 | 30.000000 | 36.750000 | 35 |
| 2000-07-12 | 30.000000 | 32.375000 | 40 |
| 2000-07-13 | 30.000000 | 28.000000 | 35 |
| 2000-07-14 | 30.000000 | 23.625000 | 25 |
| 2000-07-15 | 5.000000 | 9.746835 | 7 |
| 2000-07-16 | 5.000000 | 7.531645 | 6 |
| 2000-07-17 | 5.000000 | 5.316456 | 5 |
| 2000-07-18 | 5.000000 | 3.101266 | 4 |

## SYNTHETIC-BASE-A-H15_LOCAL-2000-07-06

origin=2000-07-06T23:59:59+08:00; computed_at=2002-01-01T00:00:00+00:00; historical_issued_at=None

baseline peak: {"date": "2000-07-08", "quantity_kg": "30.000000"}; rolling7: {"end_date": "2000-07-14", "quantity_kg": "210.000000", "start_date": "2000-07-08"}
candidate peak: {"date": "2000-07-11", "quantity_kg": "36.750000"}; rolling7: {"end_date": "2000-07-14", "quantity_kg": "210.000000", "start_date": "2000-07-08"}
actual peak: {"date": "2000-07-12", "quantity_kg": "40"}; rolling7: {"end_date": "2000-07-14", "quantity_kg": "210", "start_date": "2000-07-08"}

| Date | baseline kg | candidate kg | actual kg |
| --- | --- | --- | --- |
| 2000-07-07 | 10.000000 | 14.918032 | 14 |
| 2000-07-08 | 30.000000 | 26.250000 | 20 |
| 2000-07-09 | 30.000000 | 29.750000 | 25 |
| 2000-07-10 | 30.000000 | 33.250000 | 30 |
| 2000-07-11 | 30.000000 | 36.750000 | 35 |
| 2000-07-12 | 30.000000 | 32.375000 | 40 |
| 2000-07-13 | 30.000000 | 28.000000 | 35 |
| 2000-07-14 | 30.000000 | 23.625000 | 25 |
| 2000-07-15 | 5.000000 | 9.746835 | 7 |
| 2000-07-16 | 5.000000 | 7.531645 | 6 |
| 2000-07-17 | 5.000000 | 5.316456 | 5 |
| 2000-07-18 | 5.000000 | 3.101266 | 4 |
| 2000-07-19 | 5.000000 | 3.101266 | 3 |
| 2000-07-20 | 5.000000 | 3.101266 | 4 |
| 2000-07-21 | 5.000000 | 3.101266 | 6 |

## SYNTHETIC-BASE-A-H7_PREFIX-2000-07-03

origin=2000-07-03T23:59:59+08:00; computed_at=2002-01-01T00:00:00+00:00; historical_issued_at=None

baseline peak: {"date": "2000-07-08", "quantity_kg": "30.000000"}; rolling7: {"end_date": "2000-07-10", "quantity_kg": "130.000000", "start_date": "2000-07-04"}
candidate peak: {"date": "2000-07-10", "quantity_kg": "33.250000"}; rolling7: {"end_date": "2000-07-10", "quantity_kg": "135.151639", "start_date": "2000-07-04"}
actual peak: {"date": "2000-07-10", "quantity_kg": "30"}; rolling7: {"end_date": "2000-07-10", "quantity_kg": "121", "start_date": "2000-07-04"}

| Date | baseline kg | candidate kg | actual kg |
| --- | --- | --- | --- |
| 2000-07-04 | 10.000000 | 8.032787 | 8 |
| 2000-07-05 | 10.000000 | 10.327869 | 11 |
| 2000-07-06 | 10.000000 | 12.622951 | 13 |
| 2000-07-07 | 10.000000 | 14.918032 | 14 |
| 2000-07-08 | 30.000000 | 26.250000 | 20 |
| 2000-07-09 | 30.000000 | 29.750000 | 25 |
| 2000-07-10 | 30.000000 | 33.250000 | 30 |

## SYNTHETIC-BASE-A-H7_PREFIX-2000-07-06

origin=2000-07-06T23:59:59+08:00; computed_at=2002-01-01T00:00:00+00:00; historical_issued_at=None

baseline peak: {"date": "2000-07-08", "quantity_kg": "30.000000"}; rolling7: {"end_date": "2000-07-13", "quantity_kg": "190.000000", "start_date": "2000-07-07"}
candidate peak: {"date": "2000-07-11", "quantity_kg": "36.750000"}; rolling7: {"end_date": "2000-07-13", "quantity_kg": "201.293032", "start_date": "2000-07-07"}
actual peak: {"date": "2000-07-12", "quantity_kg": "40"}; rolling7: {"end_date": "2000-07-13", "quantity_kg": "199", "start_date": "2000-07-07"}

| Date | baseline kg | candidate kg | actual kg |
| --- | --- | --- | --- |
| 2000-07-07 | 10.000000 | 14.918032 | 14 |
| 2000-07-08 | 30.000000 | 26.250000 | 20 |
| 2000-07-09 | 30.000000 | 29.750000 | 25 |
| 2000-07-10 | 30.000000 | 33.250000 | 30 |
| 2000-07-11 | 30.000000 | 36.750000 | 35 |
| 2000-07-12 | 30.000000 | 32.375000 | 40 |
| 2000-07-13 | 30.000000 | 28.000000 | 35 |

## SYNTHETIC-BASE-B-FULL_SEASON-2000-06-30

origin=2000-06-30T23:59:59+08:00; computed_at=2002-01-01T00:00:00+00:00; historical_issued_at=None

baseline peak: {"date": "2000-07-08", "quantity_kg": "60.000000"}; rolling7: {"end_date": "2000-07-14", "quantity_kg": "420.000000", "start_date": "2000-07-08"}
candidate peak: {"date": "2000-07-11", "quantity_kg": "73.500000"}; rolling7: {"end_date": "2000-07-14", "quantity_kg": "420.000000", "start_date": "2000-07-08"}
actual peak: {"date": "2000-07-08", "quantity_kg": "60"}; rolling7: {"end_date": "2000-07-14", "quantity_kg": "420", "start_date": "2000-07-08"}

| Date | baseline kg | candidate kg | actual kg |
| --- | --- | --- | --- |
| 2000-07-01 | 20.000000 | 16.065574 | 20 |
| 2000-07-02 | 20.000000 | 16.065574 | 20 |
| 2000-07-03 | 20.000000 | 16.065574 | 20 |
| 2000-07-04 | 20.000000 | 16.065574 | 20 |
| 2000-07-05 | 20.000000 | 20.655738 | 20 |
| 2000-07-06 | 20.000000 | 25.245901 | 20 |
| 2000-07-07 | 20.000000 | 29.836065 | 20 |
| 2000-07-08 | 60.000000 | 52.500000 | 60 |
| 2000-07-09 | 60.000000 | 59.500000 | 60 |
| 2000-07-10 | 60.000000 | 66.500000 | 60 |
| 2000-07-11 | 60.000000 | 73.500000 | 60 |
| 2000-07-12 | 60.000000 | 64.750000 | 60 |
| 2000-07-13 | 60.000000 | 56.000000 | 60 |
| 2000-07-14 | 60.000000 | 47.250000 | 60 |
| 2000-07-15 | 10.000000 | 19.493671 | 10 |
| 2000-07-16 | 10.000000 | 15.063291 | 10 |
| 2000-07-17 | 10.000000 | 10.632911 | 10 |
| 2000-07-18 | 10.000000 | 6.202532 | 10 |
| 2000-07-19 | 10.000000 | 6.202532 | 10 |
| 2000-07-20 | 10.000000 | 6.202532 | 10 |
| 2000-07-21 | 10.000000 | 6.202531 | 10 |

## SYNTHETIC-BASE-B-H15_LOCAL-2000-07-03

origin=2000-07-03T23:59:59+08:00; computed_at=2002-01-01T00:00:00+00:00; historical_issued_at=None

baseline peak: {"date": "2000-07-08", "quantity_kg": "60.000000"}; rolling7: {"end_date": "2000-07-14", "quantity_kg": "420.000000", "start_date": "2000-07-08"}
candidate peak: {"date": "2000-07-11", "quantity_kg": "73.500000"}; rolling7: {"end_date": "2000-07-14", "quantity_kg": "420.000000", "start_date": "2000-07-08"}
actual peak: {"date": "2000-07-08", "quantity_kg": "60"}; rolling7: {"end_date": "2000-07-14", "quantity_kg": "420", "start_date": "2000-07-08"}

| Date | baseline kg | candidate kg | actual kg |
| --- | --- | --- | --- |
| 2000-07-04 | 20.000000 | 16.065574 | 20 |
| 2000-07-05 | 20.000000 | 20.655738 | 20 |
| 2000-07-06 | 20.000000 | 25.245901 | 20 |
| 2000-07-07 | 20.000000 | 29.836065 | 20 |
| 2000-07-08 | 60.000000 | 52.500000 | 60 |
| 2000-07-09 | 60.000000 | 59.500000 | 60 |
| 2000-07-10 | 60.000000 | 66.500000 | 60 |
| 2000-07-11 | 60.000000 | 73.500000 | 60 |
| 2000-07-12 | 60.000000 | 64.750000 | 60 |
| 2000-07-13 | 60.000000 | 56.000000 | 60 |
| 2000-07-14 | 60.000000 | 47.250000 | 60 |
| 2000-07-15 | 10.000000 | 19.493671 | 10 |
| 2000-07-16 | 10.000000 | 15.063291 | 10 |
| 2000-07-17 | 10.000000 | 10.632911 | 10 |
| 2000-07-18 | 10.000000 | 6.202532 | 10 |

## SYNTHETIC-BASE-B-H15_LOCAL-2000-07-06

origin=2000-07-06T23:59:59+08:00; computed_at=2002-01-01T00:00:00+00:00; historical_issued_at=None

baseline peak: {"date": "2000-07-08", "quantity_kg": "60.000000"}; rolling7: {"end_date": "2000-07-14", "quantity_kg": "420.000000", "start_date": "2000-07-08"}
candidate peak: {"date": "2000-07-11", "quantity_kg": "73.500000"}; rolling7: {"end_date": "2000-07-14", "quantity_kg": "420.000000", "start_date": "2000-07-08"}
actual peak: {"date": "2000-07-08", "quantity_kg": "60"}; rolling7: {"end_date": "2000-07-14", "quantity_kg": "420", "start_date": "2000-07-08"}

| Date | baseline kg | candidate kg | actual kg |
| --- | --- | --- | --- |
| 2000-07-07 | 20.000000 | 29.836065 | 20 |
| 2000-07-08 | 60.000000 | 52.500000 | 60 |
| 2000-07-09 | 60.000000 | 59.500000 | 60 |
| 2000-07-10 | 60.000000 | 66.500000 | 60 |
| 2000-07-11 | 60.000000 | 73.500000 | 60 |
| 2000-07-12 | 60.000000 | 64.750000 | 60 |
| 2000-07-13 | 60.000000 | 56.000000 | 60 |
| 2000-07-14 | 60.000000 | 47.250000 | 60 |
| 2000-07-15 | 10.000000 | 19.493671 | 10 |
| 2000-07-16 | 10.000000 | 15.063291 | 10 |
| 2000-07-17 | 10.000000 | 10.632911 | 10 |
| 2000-07-18 | 10.000000 | 6.202532 | 10 |
| 2000-07-19 | 10.000000 | 6.202532 | 10 |
| 2000-07-20 | 10.000000 | 6.202532 | 10 |
| 2000-07-21 | 10.000000 | 6.202531 | 10 |

## SYNTHETIC-BASE-B-H7_PREFIX-2000-07-03

origin=2000-07-03T23:59:59+08:00; computed_at=2002-01-01T00:00:00+00:00; historical_issued_at=None

baseline peak: {"date": "2000-07-08", "quantity_kg": "60.000000"}; rolling7: {"end_date": "2000-07-10", "quantity_kg": "260.000000", "start_date": "2000-07-04"}
candidate peak: {"date": "2000-07-10", "quantity_kg": "66.500000"}; rolling7: {"end_date": "2000-07-10", "quantity_kg": "270.303278", "start_date": "2000-07-04"}
actual peak: {"date": "2000-07-08", "quantity_kg": "60"}; rolling7: {"end_date": "2000-07-10", "quantity_kg": "260", "start_date": "2000-07-04"}

| Date | baseline kg | candidate kg | actual kg |
| --- | --- | --- | --- |
| 2000-07-04 | 20.000000 | 16.065574 | 20 |
| 2000-07-05 | 20.000000 | 20.655738 | 20 |
| 2000-07-06 | 20.000000 | 25.245901 | 20 |
| 2000-07-07 | 20.000000 | 29.836065 | 20 |
| 2000-07-08 | 60.000000 | 52.500000 | 60 |
| 2000-07-09 | 60.000000 | 59.500000 | 60 |
| 2000-07-10 | 60.000000 | 66.500000 | 60 |

## SYNTHETIC-BASE-B-H7_PREFIX-2000-07-06

origin=2000-07-06T23:59:59+08:00; computed_at=2002-01-01T00:00:00+00:00; historical_issued_at=None

baseline peak: {"date": "2000-07-08", "quantity_kg": "60.000000"}; rolling7: {"end_date": "2000-07-13", "quantity_kg": "380.000000", "start_date": "2000-07-07"}
candidate peak: {"date": "2000-07-11", "quantity_kg": "73.500000"}; rolling7: {"end_date": "2000-07-13", "quantity_kg": "402.586065", "start_date": "2000-07-07"}
actual peak: {"date": "2000-07-08", "quantity_kg": "60"}; rolling7: {"end_date": "2000-07-13", "quantity_kg": "380", "start_date": "2000-07-07"}

| Date | baseline kg | candidate kg | actual kg |
| --- | --- | --- | --- |
| 2000-07-07 | 20.000000 | 29.836065 | 20 |
| 2000-07-08 | 60.000000 | 52.500000 | 60 |
| 2000-07-09 | 60.000000 | 59.500000 | 60 |
| 2000-07-10 | 60.000000 | 66.500000 | 60 |
| 2000-07-11 | 60.000000 | 73.500000 | 60 |
| 2000-07-12 | 60.000000 | 64.750000 | 60 |
| 2000-07-13 | 60.000000 | 56.000000 | 60 |

## SYNTHETIC-BASE-C-FULL_SEASON-2000-06-30

origin=2000-06-30T23:59:59+08:00; computed_at=2002-01-01T00:00:00+00:00; historical_issued_at=None

baseline peak: {"date": "2000-07-08", "quantity_kg": "15.000000"}; rolling7: {"end_date": "2000-07-14", "quantity_kg": "105.000000", "start_date": "2000-07-08"}
candidate peak: {"date": "2000-07-11", "quantity_kg": "18.375000"}; rolling7: {"end_date": "2000-07-14", "quantity_kg": "105.000000", "start_date": "2000-07-08"}
actual peak: {"date": null, "quantity_kg": "0"}; rolling7: {"end_date": null, "quantity_kg": "0", "start_date": null}

| Date | baseline kg | candidate kg | actual kg |
| --- | --- | --- | --- |
| 2000-07-01 | 5.000000 | 4.016394 | 0 |
| 2000-07-02 | 5.000000 | 4.016394 | 0 |
| 2000-07-03 | 5.000000 | 4.016394 | 0 |
| 2000-07-04 | 5.000000 | 4.016393 | 0 |
| 2000-07-05 | 5.000000 | 5.163934 | 0 |
| 2000-07-06 | 5.000000 | 6.311475 | 0 |
| 2000-07-07 | 5.000000 | 7.459016 | 0 |
| 2000-07-08 | 15.000000 | 13.125000 | 0 |
| 2000-07-09 | 15.000000 | 14.875000 | 0 |
| 2000-07-10 | 15.000000 | 16.625000 | 0 |
| 2000-07-11 | 15.000000 | 18.375000 | 0 |
| 2000-07-12 | 15.000000 | 16.187500 | 0 |
| 2000-07-13 | 15.000000 | 14.000000 | 0 |
| 2000-07-14 | 15.000000 | 11.812500 | 0 |
| 2000-07-15 | 2.500000 | 4.873417 | 0 |
| 2000-07-16 | 2.500000 | 3.765823 | 0 |
| 2000-07-17 | 2.500000 | 2.658228 | 0 |
| 2000-07-18 | 2.500000 | 1.550633 | 0 |
| 2000-07-19 | 2.500000 | 1.550633 | 0 |
| 2000-07-20 | 2.500000 | 1.550633 | 0 |
| 2000-07-21 | 2.500000 | 1.550633 | 0 |

## SYNTHETIC-BASE-C-H15_LOCAL-2000-07-03

origin=2000-07-03T23:59:59+08:00; computed_at=2002-01-01T00:00:00+00:00; historical_issued_at=None

baseline peak: {"date": "2000-07-08", "quantity_kg": "15.000000"}; rolling7: {"end_date": "2000-07-14", "quantity_kg": "105.000000", "start_date": "2000-07-08"}
candidate peak: {"date": "2000-07-11", "quantity_kg": "18.375000"}; rolling7: {"end_date": "2000-07-14", "quantity_kg": "105.000000", "start_date": "2000-07-08"}
actual peak: {"date": null, "quantity_kg": "0"}; rolling7: {"end_date": null, "quantity_kg": "0", "start_date": null}

| Date | baseline kg | candidate kg | actual kg |
| --- | --- | --- | --- |
| 2000-07-04 | 5.000000 | 4.016393 | 0 |
| 2000-07-05 | 5.000000 | 5.163934 | 0 |
| 2000-07-06 | 5.000000 | 6.311475 | 0 |
| 2000-07-07 | 5.000000 | 7.459016 | 0 |
| 2000-07-08 | 15.000000 | 13.125000 | 0 |
| 2000-07-09 | 15.000000 | 14.875000 | 0 |
| 2000-07-10 | 15.000000 | 16.625000 | 0 |
| 2000-07-11 | 15.000000 | 18.375000 | 0 |
| 2000-07-12 | 15.000000 | 16.187500 | 0 |
| 2000-07-13 | 15.000000 | 14.000000 | 0 |
| 2000-07-14 | 15.000000 | 11.812500 | 0 |
| 2000-07-15 | 2.500000 | 4.873417 | 0 |
| 2000-07-16 | 2.500000 | 3.765823 | 0 |
| 2000-07-17 | 2.500000 | 2.658228 | 0 |
| 2000-07-18 | 2.500000 | 1.550633 | 0 |

## SYNTHETIC-BASE-C-H15_LOCAL-2000-07-06

origin=2000-07-06T23:59:59+08:00; computed_at=2002-01-01T00:00:00+00:00; historical_issued_at=None

baseline peak: {"date": "2000-07-08", "quantity_kg": "15.000000"}; rolling7: {"end_date": "2000-07-14", "quantity_kg": "105.000000", "start_date": "2000-07-08"}
candidate peak: {"date": "2000-07-11", "quantity_kg": "18.375000"}; rolling7: {"end_date": "2000-07-14", "quantity_kg": "105.000000", "start_date": "2000-07-08"}
actual peak: {"date": null, "quantity_kg": "0"}; rolling7: {"end_date": null, "quantity_kg": "0", "start_date": null}

| Date | baseline kg | candidate kg | actual kg |
| --- | --- | --- | --- |
| 2000-07-07 | 5.000000 | 7.459016 | 0 |
| 2000-07-08 | 15.000000 | 13.125000 | 0 |
| 2000-07-09 | 15.000000 | 14.875000 | 0 |
| 2000-07-10 | 15.000000 | 16.625000 | 0 |
| 2000-07-11 | 15.000000 | 18.375000 | 0 |
| 2000-07-12 | 15.000000 | 16.187500 | 0 |
| 2000-07-13 | 15.000000 | 14.000000 | 0 |
| 2000-07-14 | 15.000000 | 11.812500 | 0 |
| 2000-07-15 | 2.500000 | 4.873417 | 0 |
| 2000-07-16 | 2.500000 | 3.765823 | 0 |
| 2000-07-17 | 2.500000 | 2.658228 | 0 |
| 2000-07-18 | 2.500000 | 1.550633 | 0 |
| 2000-07-19 | 2.500000 | 1.550633 | 0 |
| 2000-07-20 | 2.500000 | 1.550633 | 0 |
| 2000-07-21 | 2.500000 | 1.550633 | 0 |

## SYNTHETIC-BASE-C-H7_PREFIX-2000-07-03

origin=2000-07-03T23:59:59+08:00; computed_at=2002-01-01T00:00:00+00:00; historical_issued_at=None

baseline peak: {"date": "2000-07-08", "quantity_kg": "15.000000"}; rolling7: {"end_date": "2000-07-10", "quantity_kg": "65.000000", "start_date": "2000-07-04"}
candidate peak: {"date": "2000-07-10", "quantity_kg": "16.625000"}; rolling7: {"end_date": "2000-07-10", "quantity_kg": "67.575818", "start_date": "2000-07-04"}
actual peak: {"date": null, "quantity_kg": "0"}; rolling7: {"end_date": null, "quantity_kg": "0", "start_date": null}

| Date | baseline kg | candidate kg | actual kg |
| --- | --- | --- | --- |
| 2000-07-04 | 5.000000 | 4.016393 | 0 |
| 2000-07-05 | 5.000000 | 5.163934 | 0 |
| 2000-07-06 | 5.000000 | 6.311475 | 0 |
| 2000-07-07 | 5.000000 | 7.459016 | 0 |
| 2000-07-08 | 15.000000 | 13.125000 | 0 |
| 2000-07-09 | 15.000000 | 14.875000 | 0 |
| 2000-07-10 | 15.000000 | 16.625000 | 0 |

## SYNTHETIC-BASE-C-H7_PREFIX-2000-07-06

origin=2000-07-06T23:59:59+08:00; computed_at=2002-01-01T00:00:00+00:00; historical_issued_at=None

baseline peak: {"date": "2000-07-08", "quantity_kg": "15.000000"}; rolling7: {"end_date": "2000-07-13", "quantity_kg": "95.000000", "start_date": "2000-07-07"}
candidate peak: {"date": "2000-07-11", "quantity_kg": "18.375000"}; rolling7: {"end_date": "2000-07-13", "quantity_kg": "100.646516", "start_date": "2000-07-07"}
actual peak: {"date": null, "quantity_kg": "0"}; rolling7: {"end_date": null, "quantity_kg": "0", "start_date": null}

| Date | baseline kg | candidate kg | actual kg |
| --- | --- | --- | --- |
| 2000-07-07 | 5.000000 | 7.459016 | 0 |
| 2000-07-08 | 15.000000 | 13.125000 | 0 |
| 2000-07-09 | 15.000000 | 14.875000 | 0 |
| 2000-07-10 | 15.000000 | 16.625000 | 0 |
| 2000-07-11 | 15.000000 | 18.375000 | 0 |
| 2000-07-12 | 15.000000 | 16.187500 | 0 |
| 2000-07-13 | 15.000000 | 14.000000 | 0 |

## SYNTHETIC-BASE-D-FULL_SEASON-2000-06-30

origin=2000-06-30T23:59:59+08:00; computed_at=2002-01-01T00:00:00+00:00; historical_issued_at=None

Failure/reason: MISSING_REGISTERED_INPUT / IDENTITY_OR_SOURCE_HASH_MISMATCH

## SYNTHETIC-BASE-D-H15_LOCAL-2000-07-03

origin=2000-07-03T23:59:59+08:00; computed_at=2002-01-01T00:00:00+00:00; historical_issued_at=None

Failure/reason: MISSING_REGISTERED_INPUT / IDENTITY_OR_SOURCE_HASH_MISMATCH

## SYNTHETIC-BASE-D-H15_LOCAL-2000-07-06

origin=2000-07-06T23:59:59+08:00; computed_at=2002-01-01T00:00:00+00:00; historical_issued_at=None

Failure/reason: MISSING_REGISTERED_INPUT / IDENTITY_OR_SOURCE_HASH_MISMATCH

## SYNTHETIC-BASE-D-H7_PREFIX-2000-07-03

origin=2000-07-03T23:59:59+08:00; computed_at=2002-01-01T00:00:00+00:00; historical_issued_at=None

Failure/reason: MISSING_REGISTERED_INPUT / IDENTITY_OR_SOURCE_HASH_MISMATCH

## SYNTHETIC-BASE-D-H7_PREFIX-2000-07-06

origin=2000-07-06T23:59:59+08:00; computed_at=2002-01-01T00:00:00+00:00; historical_issued_at=None

Failure/reason: MISSING_REGISTERED_INPUT / IDENTITY_OR_SOURCE_HASH_MISMATCH
