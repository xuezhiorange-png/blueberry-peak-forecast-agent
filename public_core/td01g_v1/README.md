# TD01G public core v1 — synthetic-only executable rehearsal

This candidate contains generic schemas/normalization, the unchanged TD-01C
independent generator, and the unchanged V0.19 pure daily-curve function.
It contains no real farm/factory mapping, business statistics, historical audit
reports, original Git history, production model or database/frontend/MCP service.
`0.0.0` is local prototype package metadata, not an engineering Release.

Use Python 3.12. All local modules are explicit in PUBLIC-CORE-MANIFEST.json.
The source guard embeds its reviewed manifest seal; JSON labels or caller hashes
cannot grant source clearance. A changed source/manifest needs a separately
reviewed candidate version. V1 checks one sealed root and checkout-shaped refs;
it does not automatically admit arbitrary future commit histories or tags.

From this clean checkout, with an output path outside it:

```sh
python tools/verify_public_core.py
python -m tools.run_public_ci --output-dir /tmp/TD01G-public-ci
```

The second command creates a new venv with system-site-packages disabled, installs
the complete hashed dependency lock, installs a Git archive of this candidate,
then executes Ruff, Format, strict Mypy, public contracts and safety negatives.
It runs two installed CLI processes from outside the checkout and compares their
actual exports. Every command exit code, log and JUnit is retained outside the
source tree. Failures propagate; existing outputs are never overwritten.

Runtime examples using the resulting environment:

```sh
/tmp/TD01G-public-ci/environment/bin/blueberry-public-core demo --seed 41 --config TD01G_SYNTHETIC_EXECUTABLE_CORE_V1 --output-dir /tmp/TD01G-demo
/tmp/TD01G-public-ci/environment/bin/blueberry-public-core curve --seed 42 --output-dir /tmp/TD01G-curve
```

Generation exports deterministic CSV/XLSX and their manifest plus quality reasons.
Blank, zero, negative, invalid-date and duplicate semantics remain visible. No
real-source path is accepted. Curve output comes from the existing algorithm,
with six-place nonnegative Decimal kg, bin mass conservation and H7/H15 prefix
checks. These are algorithm contracts, not real forecast accuracy evidence.

Always: DATA_CLASS=SYNTHETIC_ONLY, REAL_FORECAST_VALIDATED=false,
STRICT_REAL_PIT_VALIDATED=false, PRODUCTION_MODEL_ADMITTED=false.

## Environment scope

requirements.in lists direct runtime/build/test tools. requirements.lock pins the
complete 18-package resolution and records SHA256 for released wheels of those
versions, including platform alternatives. Installation uses require-hashes and
binary-only mode. This is stronger than pinning direct dependency ranges; it is
not an OS, interpreter-binary or hardware lock. The bootstrap comes from the
trusted Python 3.12 ensurepip, then pip itself is pinned. Target validation is
macOS arm64 and Linux x86_64; other platforms are not admitted by this rehearsal.
See [pip repeatability](https://pip.pypa.io/en/stable/topics/repeatable-installs/)
and [hash checking](https://pip.pypa.io/en/stable/topics/secure-installs/).

The generated Actions workflow runs the same Python command sequence. Local
success means LOCAL_CI_EQUIVALENT=PASS. ACTUAL_NEW_REMOTE_GITHUB_ACTIONS=NOT_RUN
until a separately authorized repository and actual run exist.

## Separate acceptance scope

TD-01F originally recorded 24 PASS / 1 BLOCKED. Its historical audit test and
results are unchanged in the original project. This public test entry is a new,
explicitly bounded synthetic acceptance set, with no imported audit inventory.
It does not turn that historical dependency into PASS or migrate the full app.
Original evidence stays preserved/private under the restrictive D02/D03/D06
working boundary. Publication, remote creation, visibility/history changes,
model admission and deployment remain unauthorized.
