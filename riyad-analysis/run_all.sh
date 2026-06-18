#!/usr/bin/env bash
# Reproduce the full riyad-analysis pipeline (read-only w.r.t. the repo).
# Usage: bash riyad-analysis/run_all.sh
set -euo pipefail
cd "$(dirname "$0")"

PY=".venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "Creating virtual environment..."
  /opt/homebrew/bin/python3.12 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install pandas numpy scipy scikit-learn matplotlib statsmodels
fi

echo "== 01 export text responses =="      && $PY 01_export_text_responses.py
echo "== 02 build coded dataset =="         && $PY 02_build_coded_dataset.py
echo "== 03 analyse text =="                && $PY 03_analyze_text.py
echo "== 04 build expertise score =="       && $PY 04_build_expertise_score.py
echo "== 05 expertise adjustment =="        && $PY 05_expertise_adjustment.py
echo "Done. See riyad-analysis/derived/ and riyad-analysis/figures/."
