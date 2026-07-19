# Changelog

## Unreleased — planned V0.2.0 Forecast Quality Trial

The next release scope is frozen in `docs/v0-2/development-plan.md`.

V0.2 contains exactly five planned slices:

- **S1 — Actual-harvest atomic commit**
- **S2 — Point-in-time actual labels and historical backtest**
- **S3 — Forecast-quality metrics and one naive baseline**
- **S4 — Frontend application API**
- **S5 — Two-page responsive trial frontend and browser E2E**

V0.2 must provide a browser-complete flow from forecast creation through actual-harvest import, forecast-versus-actual quality comparison, baseline comparison, and export.

Planning does not authorize implementation. S1 requires a separate implementation authorization; Issue #99, model changes, operational recommendations, and complex administration interfaces remain outside V0.2.

An open Issue or project backlog item does not extend a frozen release scope.

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
