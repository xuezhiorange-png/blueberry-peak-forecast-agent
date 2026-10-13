# SYNTHETIC DEMONSTRATION — NOT REAL BLUEBERRY ACCURACY

All metrics are synthetic engineering results. Visible fruit counts are not kg.

Dataset hash: `29100d7f845c9bbd16b1c09e5cda703e53cf8fffead963752141247991dec2e5`
Report hash: `bb35ba3dd09a017993a3e4a2935d234d1a73a582b2db574759f7d3124d50c1d0`

## Baseline A: deterministic RGB connected components

Evaluated: 28; excluded: 0; missing/failed: 0; evaluated images with errors: 11.

| Scalar metric | Value |
| --- | --- |
| bbox_ap50_research_all_points | 0.750849467917799 |
| count_bias | -3.7142857142857144 |
| count_mae | 4.142857142857143 |
| count_unit | visible_fruit_per_image |
| empty_false_positive_count | 0 |
| evaluated_count | 28 |
| excluded_count | 0 |
| f1 | 0.8602150537634409 |
| fn | 125 |
| fp | 18 |
| image_count | 28 |
| precision | 0.9606986899563319 |
| precision_reason_code | None |
| reason_code | None |
| recall | 0.7787610619469026 |
| recall_reason_code | None |
| status | EVALUATED |
| total_overcount | 6 |
| total_undercount | 110 |
| tp | 440 |

Full original evaluator artifact, including AP curves, strata and failure cases: [evaluation_model-0.json](evaluation_model-0.json).
Evaluator artifact hash: `3975ec8fab0118efcbaf10734605224d49cf1e80c58e8c995ee07e032219b6c0`.

## Baseline B: synthetic-trained NumPy logistic pixel classifier

Evaluated: 28; excluded: 0; missing/failed: 0; evaluated images with errors: 12.

| Scalar metric | Value |
| --- | --- |
| bbox_ap50_research_all_points | 0.762991750187723 |
| count_bias | -3.5 |
| count_mae | 3.9285714285714284 |
| count_unit | visible_fruit_per_image |
| empty_false_positive_count | 0 |
| evaluated_count | 28 |
| excluded_count | 0 |
| f1 | 0.8649173955296404 |
| fn | 120 |
| fp | 19 |
| image_count | 28 |
| precision | 0.959051724137931 |
| precision_reason_code | None |
| reason_code | None |
| recall | 0.7876106194690266 |
| recall_reason_code | None |
| status | EVALUATED |
| total_overcount | 6 |
| total_undercount | 104 |
| tp | 445 |

Full original evaluator artifact, including AP curves, strata and failure cases: [evaluation_model-1.json](evaluation_model-1.json).
Evaluator artifact hash: `024f20e382be4f762717dba5de045744741b7e023f8ebffd420b858418d81937`.

All 23 failed/error overlays are retained in `errors_collection/`.
Full review data and all per-image outcomes: [report.json](report.json).
Open `report.html` locally. Export creates candidate JSON; GT is immutable.
