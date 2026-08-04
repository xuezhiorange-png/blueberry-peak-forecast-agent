# Changelog

## 0.2.0 — Forecast Quality Trial (2026-08-04)

V0.2 is delivered as an `ENGINEERING_TRIAL`, not a production business
deployment. It closes the five-slice browser trial loop within the frozen
`FORECAST_QUALITY_TRIAL` version boundary:

- **S1 — Actual-harvest atomic commit**
- **S2 — Point-in-time actual labels and historical backtest**
- **S3 — Forecast-quality metrics and one naive baseline**
- **S4 — Frontend application API**
- **S5 — Two-page responsive trial frontend and browser E2E**

The engineering trial provides:

- browser forecast creation;
- daily curve and peak inspection;
- CSV/XLSX actual-harvest trial import;
- validation and atomic commit;
- point-in-time label snapshots;
- historical backtest;
- forecast-versus-actual metrics;
- naive baseline comparison;
- CSV export;
- PostgreSQL 16 E2E;
- desktop/mobile browser E2E;
- deterministic replay and persisted readback.

The accepted engineering evidence demonstrates a runnable product flow,
valid data contracts, correct database behavior, deterministic calculations,
and usable browser workflows. It does not claim validated real-production
forecast accuracy, business representativeness, formal business-owner
endorsement, production-system data integration, or commercial launch
acceptance.

Real business data acceptance, source-owner attestation, and business
representativeness are deferred to the business pilot or V0.3:

```text
REAL_BUSINESS_DATA_ACCEPTANCE_DEFERRED=true
REAL_BUSINESS_DATA_ACCEPTANCE_TARGET=BUSINESS_PILOT_OR_V0_3
WARNING_FINAL_CLASSIFICATION_COMPLETE=true
WARNING_RELEASE_CLEARANCE=true
```

## 0.1.0 — Core forecast

Release boundary: `235bde1407bdd0b86f2b31ad75ba1c3b8dc5ba61` (PR #112 merge, 2026-07-16).

V0.1 contains the five frozen Core Forecast slices:

- **S1 — Contract and complete-season oracle:** freeze the physical-quantity contract and the deterministic 90-day, 1,080-row acceptance fixture.
- **S2 — Complete daily marketable curve:** compose the full daily P50/P80/P90 effective-marketable forecast curve from the existing Task 8 and Task 9 authorities.
- **S3 — Canonical metrics:** calculate single-day peak, strict rolling seven-calendar-day cumulative peak, and season cumulative quantity with deterministic tie-breaking and exact Decimal arithmetic.
- **S4 — Persistence and recalculation:** persist immutable forecast runs, daily rows, and metrics; support deterministic lookup, idempotent reuse, integrity-checked reload, and explicit-input reruns.
- **S5 — Unified execution and E2E acceptance:** expose the Core Forecast CLI and prove full-season PostgreSQL execution, persistence/reload parity, zero-write blocked paths, and canonical result hashes.

Canonical V0.1 evidence:

- Version: `0.1.0` in both `pyproject.toml` and `backend/app/core/version.py`.
- Fixture: `v0_1_complete_season_case_01`.
- Calendar: 90 dates.
- Scope series: 12.
- Daily rows: 1,080.
- Source curve hash: `de81bfa3a23efcef0398758e5105199eede9222adb0aff4acda67f3fe9697687`.
- Metrics hash: `cfba5f2af9236e907527ef72d2d8e0a34b99f2cad29aaac502e6159c1d6d586a`.
- Persisted result hash: `802504d0798f6ce1f46978806a4b986eefe2ff733616b60af7143ff3e641535a`.

Explicit V0.1 exclusions:

- actual-harvest ingestion and commit lifecycle;
- revision-winner and cutoff-bound label snapshots;
- historical forecast-quality scoring and backtest runner;
- operational recommendation expansion;
- model changes;
- multi-factory routing, allocation optimization, frontend, dashboards, and reports.
