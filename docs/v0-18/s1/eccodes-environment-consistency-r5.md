# R5 — ecCodes native dependency consistency

TASK_ID=V0_18_S1_ECCODESLIB_ENVIRONMENT_CONSISTENCY_CLOSURE_R5

This is a minimal dependency correction on existing Draft PR #717, not a new
authentication implementation. Starting HEAD is
`cdcbf70339dd98b65d5c40f2cad8d08d2ed36872`; main remains
`320f2046e3105b1b55da9cb037892571110b584a`.

## Verified cause and correction

The official ecCodes 2.48.0 universal wheel declares
`Requires-Dist: eccodeslib; platform_system != "Windows"`. The Windows CPython
3.12 wheel does not declare that dependency and bundles its native library.
The version-level PyPI metadata likewise omits it. The original lock contains
only attrs, cffi, findlibs and numpy for ecCodes. This proves an artifact metadata
discrepancy and the lock's missing native dependency; it does not prove which
internal cache or metadata selection produced the historical lock.

Sources: [ECMWF installation](https://confluence.ecmwf.int/display/ECC/ecCodes+installation),
[ecCodes 2.48.0](https://pypi.org/project/eccodes/2.48.0/),
[ecCodes native package](https://pypi.org/project/eccodeslib/2.48.0.26/),
[eckit native package](https://pypi.org/project/eckitlib/2.1.1.26/).

Pin ecCodes to its existing 2.48.0 version and explicitly declare
`eccodeslib==2.48.0.26` only on Linux/macOS. Its metadata requires
`eckitlib==2.1.1.26`, which is resolved transitively. No pre-existing lock package
version changes. CI constraints receive the same two direct pins. MCP 2.2.0,
AnyIO 4.14.2 and PyJWT 2.15.0 remain unchanged.

## Installation and native acceptance

A new CPython 3.12.13 environment was seeded with pip as a validation tool and
rebuilt using `uv sync --frozen --inexact --extra dev`. The `--inexact` option
retains seeded pip; it does not relax the frozen application lock. Before the
correction, both pip and uv reported the missing eccodeslib dependency.

After the correction, `python -m pip check`, `uv pip check`, `uv lock --check`
and `python -m eccodes selfcheck` succeed. Selfcheck loads ecCodes 2.48.0 from
the environment's eccodeslib package, with embedded `/MEMFS` definitions and
samples. The regression subprocess removes private ecCodes and dynamic-loader
overrides before checking the native library's location.

The new runtime test constructs real GRIB2 messages using the bundled
`regular_ll_sfc_grib2` sample, sets explicitly synthetic constant values, encodes
twice, compares exact bytes, decodes standard metadata and values, and releases
all native handles in finally blocks. No weather product or actual harvest is
downloaded, read or imported. Existing provider and future-weather feature
regressions remain unchanged.

## Platform scope

CPython 3.12 wheels are published for macOS 13+ arm64/x86_64 and glibc 2.28+
Linux arm64/x86_64. eckit publishes compatible macOS 13+ and manylinux 2.27/2.28
wheels. Actual local runtime acceptance is macOS arm64; the new native tests
also run in Linux x86_64 GitHub CI. Other architectures are metadata-verified,
not runtime-validated. Windows retains the existing bundled-library route and
is not runtime-validated. musl, older systems and other Python ABIs are not
claimed supported by this acceptance.

## Audit and historical preservation

The fresh environment's public Python dependency scan reports no known
vulnerabilities, including eccodes, eccodeslib and eckitlib. The unpublished
first-party package is not audited by the public package database. This is not
a complete native-library CVE, application security or production-safety claim.
The audit archive retains the original JSON payload with a final newline; raw
and archived digests are recorded separately.

Frontend installation reports seven pre-existing npm advisories (two moderate,
five high). They are outside the ecCodes-only authorization, are not corrected
or represented as closed, and do not alter the scoped Python audit conclusion.

R4's evidence and audit snapshot remain available at its immutable commit.
The current runtime evidence only refreshes approved current source bindings
and adds an R5 pointer, preserving all R3/R4 results and failure facts. All 260
frozen historical documents/evidence are checked without updating their hashes.
Authentication production files, security policies, migrations, forecasting
math, weather providers, MCP and Dashboard runtime are unchanged by R5.

The prior `/tmp/blueberry-v018-s1-local-auth-runtime-r1` checkout and PostgreSQL
temporary directory are absent. No worktree was cleaned, reset or pruned. A
fresh isolated checkout uses the exact remote PR branch and tracked R4 bytes;
lost untracked local outputs are not claimed recovered or preserved. New tests
use a newly created loopback-only synthetic PostgreSQL cluster.

## Governance and exact-head validation

The accompanying canonical JSON records actual local results and hashes. The
final GitHub CI receipt is posted on PR #717 after the exact pushed HEAD finishes;
the committed candidate does not predeclare that future result. The unchanged
A01–A20 tests are rerun against synthetic PostgreSQL, separately from native
dependency acceptance. Full-suite Canary and Frontend E2E are required on the
new HEAD, not inherited from R4's green run.

PR remains Draft. D03 real administrator and organization authority is PENDING;
S1 formal completion and production readiness remain unapproved. No production
database migration, real administrator/grant creation, deployment, Ready/Merge,
Tag/Release or V0.18 S2–S6 work is performed.
