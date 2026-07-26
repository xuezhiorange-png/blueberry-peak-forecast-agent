#!/usr/bin/env bash
set -euo pipefail

ROUND_A_WORKTREE="${ROUND_A_WORKTREE:-$(git rev-parse --show-toplevel)}"
PACKAGE_DIR="${PACKAGE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
AUTHORIZED_FILE="${PACKAGE_DIR}/authorized-paths.txt"
: "${SOURCE_MAIN_SHA:?SOURCE_MAIN_SHA is required}"
cd "${ROUND_A_WORKTREE}"

test -f "${AUTHORIZED_FILE}"
git diff --check
mapfile -t app_paths < <(awk -F ' \\| ' '/^backend\/app\/forecast_quality\/.*\.py / {print $1}' "${AUTHORIZED_FILE}")
test "${#app_paths[@]}" = "9"
for path in "${app_paths[@]}"; do
  test -f "${path}"
done

uv run ruff check "${app_paths[@]}"
uv run ruff format --check "${app_paths[@]}"
uv run mypy backend/app/forecast_quality

for forbidden in \
  backend/app/forecast_quality/peak.py \
  backend/app/forecast_quality/quantile.py \
  backend/app/forecast_quality/comparison.py \
  backend/app/forecast_quality/persistence.py \
  backend/app/forecast_quality/repository.py \
  backend/app/forecast_quality/application.py \
  backend/alembic \
  backend/tests/integration \
  .github/workflows \
  ci-shard-manifest.yml
do
  if {
    git diff --name-only "${SOURCE_MAIN_SHA}..HEAD"
    git diff --cached --name-only
    git diff --name-only
    git ls-files --others --exclude-standard
  } | sort -u | grep -Fxq "${forbidden}"; then
    printf 'BLOCKED_PATH_PRESENT=%s\n' "${forbidden}"
    exit 1
  fi
done

blocked_symbols='(pinball_loss|quantile_coverage|prediction_interval|single_day_peak|sustained_7day_peak|season_cumulative|model_baseline_comparison|QualityEvaluationRun|NaiveBaselineRun)'
if rg -n -i "${blocked_symbols}" "${app_paths[@]}"; then
  printf 'BLOCKED_SYMBOL_PRESENT_COUNT=1\n'
  exit 1
fi

printf 'BLOCKED_PATH_PRESENT_COUNT=0\n'
printf 'BLOCKED_SYMBOL_PRESENT_COUNT=0\n'
printf 'STATIC_GATE=PASS\n'
