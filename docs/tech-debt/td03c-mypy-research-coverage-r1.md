# TD-03C — strict Mypy application and research coverage

Task: `BLUEBERRY_TECH_DEBT_TD03C_MYPY_RESEARCH_COVERAGE_R1`.
Owner scope is implementation and one Draft PR, without Ready/Merge/Release/Deploy.
Base main is `83085ff77363a39f5144116637977590dbc29dc5`, which merged PR #770.
[Main CI 40977794722](https://github.com/xuezhiorange-png/blueberry-peak-forecast-agent/actions/runs/40977794722)
completed successfully: eight successful and eight normally skipped jobs.

## Gap and minimal correction

`strict = true` sets checking rules, but the old static command only named
`backend/app`. Research imports followed from application code do not guarantee
that every research entry point is selected as a root. `VERSIONING.md` already
recommends both directories.

The existing Mypy step now runs `mypy backend/app backend/research`. No new job,
event, matrix, shard, dependency version, type ignore, configuration override,
failure suppression or success criterion is introduced. `pyproject.toml` remains
unchanged, including Python 3.12, strict mode and existing third-party overrides.

## Actual local checks

| Check | Result |
| --- | --- |
| Original `python -m mypy backend/app` | 601 source files, zero errors |
| Expanded application + research check | 637 source files, zero errors |
| Expanded check targeting Linux | 637 source files, zero errors |
| Explicit verbose root-source inventory | All 601 application and 36 research Python files match exactly |

The expanded inventory was collected with `--verbose --no-incremental` and a
fresh cache; `__init__.py` files are included. Full logs and the root-source list
are retained outside Git. No application or research annotation repair was needed.

Local checks use CPython 3.12.13 and Mypy 2.1.0, installed with the same
`pip -c backend/constraints-ci.txt -e '.[dev]'` command as CI. The local uv catalog
did not provide 3.12.15; this patch difference is recorded rather than hidden.
The Mypy language target remains 3.12; the final GitHub run separately validates
the committed change on its existing Linux/Python 3.12 environment.

## Contract and execution boundaries

The new contract checks both roots, strict configuration, the PR static-job
condition and failure propagation. Removing either root, skipping the step/job,
adding `continue-on-error`, or masking the exit code fails the contract.

It also executes the actual CI Mypy command through a failing shell against new
synthetic Python packages and a copy of the real configuration. Valid source
returns zero; an annotated assignment error in the synthetic research package
returns one. No business code or model calculation is executed by this fixture.

Existing CI parity and historical evidence contracts remain in place. Historical
CI hashes use their already-approved fixed Git bytes; no hash/contract adaptation
is added here. TD-03B ownership code and all frozen research sources/results are
unchanged. The two TD-01 XLS paths remain untracked. No real data, training,
database change, TD-03D or V0.22 work is included.

Final contract counts, Ruff/format results and exact-head CI results belong in
the PR receipt; queued/in-progress CI is not reported as success.
