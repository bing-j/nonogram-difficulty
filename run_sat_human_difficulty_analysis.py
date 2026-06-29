"""
One-command entry point for the SAT-vs-human Nonogram difficulty analysis.

Run from the repository root:
    python3 run_sat_human_difficulty_analysis.py

This delegates to the full analysis script in analyze-data/ and regenerates
all CSV outputs, figures, and the Markdown report under outputs/.
"""

from __future__ import annotations

import runpy
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
ANALYSIS_SCRIPT = REPO_ROOT / "analyze-data" / "build_clean_participant_puzzle_data.py"


def main() -> None:
    # Keep the full implementation in one analysis script while exposing a
    # simple root-level command for reproducibility.
    runpy.run_path(str(ANALYSIS_SCRIPT), run_name="__main__")


if __name__ == "__main__":
    main()
