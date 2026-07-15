# `v0_1_complete_season_case_01`

This is a synthetic, deterministic 90-day V0.1-S1 contract fixture.

- Range: `2026-03-01` through `2026-05-29`.
- Scopes: one farm, two subfarms, two varieties.
- Destination: one fixed logical factory.
- Quantiles: P50, P80, P90.
- Primary physical date: `HARVEST_BUSINESS_DATE`.
- Primary quantity: `effective_marketable_quantity_kg`.

The fixture is for contract and expected-output review only. It does not call
the not-yet-authorized V0.1-S2 through S5 production implementation.
