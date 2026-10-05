#!/usr/bin/env bash
# Sequential HLS-CMDS benchmark campaign: runs all four stages per task and
# applies the adopt/skip gate (>=1 point improvement). All decisions are
# recorded in runs/metrics.json and a WandB benchmark-summary run.
#
# Usage:
#   ./run_sequential.sh                 # all tasks (sound, heart, lung)
#   ./run_sequential.sh heart lung      # selected tasks
#   SMOKE=1 ./run_sequential.sh         # smoke mode (2 folds / 2 epochs)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PY="$ROOT/.venv/bin/python"
ML="$ROOT/ml"

cd "$ML"
ARGS=("--tasks" "$@")
if [ "${SMOKE:-0}" = "1" ]; then
  ARGS+=("--smoke")
fi
"$PY" scripts/sequential.py "${ARGS[@]}"
