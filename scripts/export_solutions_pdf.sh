#!/usr/bin/env bash
# Export the executed educational notebooks to a single solutions PDF.
#
#   ./scripts/export_solutions_pdf.sh
#
# Uses jupyter nbconvert (LaTeX) per notebook, then merges with pdfunite into
# docs/Notebook_Solutions.pdf. Requires xelatex + pdfunite (poppler-utils).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
TMP="$(mktemp -d)"
OUT="$ROOT/docs/Notebook_Solutions.pdf"

cd "$ROOT"
for nb in notebooks/*.ipynb; do
  base="$(basename "$nb" .ipynb)"
  echo "[pdf] $base"
  "$PY" -m jupyter nbconvert --to pdf --output-dir "$TMP" --output "$base.pdf" "$nb" >/dev/null
done

pdfunite "$TMP"/01_dataset_exploration.pdf "$TMP"/02_preprocessing_splits.pdf \
         "$TMP"/03_benchmark_training.pdf "$TMP"/04_report_embeddings_webapp.pdf \
         "$TMP"/05_llm_integration.pdf "$OUT"
rm -rf "$TMP"
echo "[pdf] solutions document -> $OUT ($(du -h "$OUT" | cut -f1))"
