# R5 execution workpaper

Base: `a41ffcc76840ecc6f02fa63ec1c4d75d965be781`, existing Draft #607.
Implementation: `c4679ab170c4a8186289c3f07130fb03351eaf73`.

1. Revalidated PR/branch identity and clean base; preserved all earlier evidence.
2. Added deterministic empirical authority, distinct Task9 input, immutable
   persistence, normal forecast API dispatch and fresh-session readback.
3. Synthetic-only tests proved original Task8 golden behavior and new mass balance.
4. Read-only operational-table checks returned zero; applied migration 0033 to
   the existing non-production acceptance database on port 55437.
5. `scripts.register_banna_empirical_authority_r5` hash-verified only the pinned
   2024/25 source, resolved existing Farm/Factory/Variety identities, created the
   policy-derived forecast season via canonical master-data service, and persisted
   empirical authority. No parameter library or Task8 model was forged.
6. Started the existing acceptance runtime on port 8007 with normal server-owned
   actor configuration. Health ready and forecast POST both returned HTTP 200.
7. Fresh-session GET returned the identical result hash. All 207 rows conserve
   inventory and satisfy capacity. Normal forecast execution count is one.
8. Targeted regressions: 1226 passed. Ruff, formatting, mypy, JSON and diff checks
   passed. Exact-head GitHub CI details belong to the live PR body/final handoff.

Authority hash: `723aac97a66e577a737c7fd62d42149e1d66d1108f1142709b13a83aeb9c6911`.
Curve hash: `ef79a5e42154b8df33b21b0081ccb81a7e036c958de1102f55f42fc77b52a0c8`.
Task9 hash: `61b3870bf7cb5e1ddc28b2bb1c2cc946a59d47472cf472096a198b1ecfa2eef1`.
Forecast hash: `8cba604985f5229b31bf729b4503da2175cfb277c2a9950e1273a5d70059b9be`.

No raw confidential business rows or credentials are committed. Stored daily
results remain in the acceptance database. Daily P50/P80/P90 scenarios are
identical uncalibrated point scenarios, not coverage claims. No production
rollout, S4 reopening, TEST read, validation scoring or budget mutation occurred.

FINAL_STOP_GATE=COORDINATOR_FIRST_REAL_FORECAST_R5_REVIEW
