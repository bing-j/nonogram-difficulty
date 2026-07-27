"""
regression_analysis.py
======================
Step 5 - Raw per-puzzle mean difficulty vs. SAT solver metrics, with error
bars. The deliberately narrow companion to Step 4 (spearman_ranking.py).

This used to also re-derive Bradley-Terry rankings and Spearman rho vs. SAT
metrics from scratch, via an independently-written raw-.ndjson-log parser
(load_all_ratings/extract_participant_ratings) and its own BT computation
(compute_bt_ranks) -- duplicating Step 4's exact analysis through a second,
separately-implemented data path. That's a real risk for a paper: two
independently-written extraction pipelines computing "the same" BT-vs-SAT
correlation could silently diverge (different missing-data handling, a bug
in one path but not the other), leaving no single authoritative number to
cite. Removed. This script now consumes behavioral_features.csv (Step 2)
like every other downstream step, computes only the one thing that ISN'T
already in Step 4 -- raw (non-BT) per-puzzle mean difficulty -- and Step 4's
stats_bt_vs_sat.csv / bt_difficulty_vs_sat.csv remain the single source of
truth for the BT-based claim.

Inputs
------
- analyze-data/out_features/behavioral_features.csv
- selected_six_nonogram_stats.csv

Outputs
-------
- analyze-data/out_features/figures/regression_per_puzzle_means.png
    Per-puzzle mean final_difficulty vs SAT predictor, with error bars.

Usage
-----
  python analyze-data/regression_analysis.py
  python analyze-data/regression_analysis.py --features_csv ... --solver_csv ... --out_dir ...
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plot_style import NEUTRAL_COLOR, apply_style  # noqa: E402
from spearman_ranking import SAT_METRICS, load_features, load_solver_stats  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FEATURES_CSV = REPO_ROOT / "analyze-data" / "out_features" / "behavioral_features.csv"
DEFAULT_SOLVER_CSV = REPO_ROOT / "selected_six_nonogram_stats.csv"
DEFAULT_OUT_DIR = REPO_ROOT / "analyze-data" / "out_features"


def plot_per_puzzle_means(merged: pd.DataFrame, output_path: Path) -> None:
    """Mean final_difficulty ± SD vs. SAT predictor, one subplot per metric."""
    grouped = merged.groupby("puzzle_id")[SAT_METRICS + ["final_difficulty"]].agg(["mean", "std"])
    puzzle_ids = sorted(merged["puzzle_id"].unique())

    fig, axes = plt.subplots(1, len(SAT_METRICS), figsize=(16, 5), sharey=False)

    for ax, predictor in zip(axes, SAT_METRICS):
        x_vals = np.array([grouped.loc[pid, (predictor, "mean")] for pid in puzzle_ids])
        y_means = np.array([grouped.loc[pid, ("final_difficulty", "mean")] for pid in puzzle_ids])
        y_stds = np.nan_to_num(
            np.array([grouped.loc[pid, ("final_difficulty", "std")] for pid in puzzle_ids]), nan=0.0
        )

        sort_idx = np.argsort(x_vals)
        ax.errorbar(
            x_vals[sort_idx], y_means[sort_idx], yerr=y_stds[sort_idx],
            color=NEUTRAL_COLOR, marker="s", markersize=8, linewidth=1.5,
            capsize=5, zorder=3,
        )
        for i, pid in enumerate(np.array(puzzle_ids)[sort_idx]):
            ax.annotate(
                f"P{pid}", (x_vals[sort_idx][i], y_means[sort_idx][i]),
                textcoords="offset points", xytext=(5, 4), fontsize=8, color="#222222",
            )

        ax.set_xlabel(predictor, fontsize=10)
        ax.set_ylabel("Mean difficulty rating (1-5)", fontsize=10)
        ax.set_ylim(0.5, 5.5)
        ax.yaxis.set_major_locator(plt.MultipleLocator(1))

    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {output_path}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Raw per-puzzle mean difficulty vs. SAT solver metrics."
    )
    ap.add_argument("--features_csv", type=Path, default=DEFAULT_FEATURES_CSV)
    ap.add_argument("--solver_csv", type=Path, default=DEFAULT_SOLVER_CSV)
    ap.add_argument("--out_dir", type=Path, default=DEFAULT_OUT_DIR)
    args = ap.parse_args()

    apply_style()

    if not args.features_csv.exists():
        print(f"Features CSV not found: {args.features_csv}")
        print("Run extract_behavioral_features.py first.")
        return

    fig_dir = args.out_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("NONOGRAM DIFFICULTY — RAW PER-PUZZLE MEANS vs. SAT METRICS")
    print("=" * 60)

    features_df = load_features(args.features_csv)
    solver_df = load_solver_stats(args.solver_csv)
    merged = features_df.merge(solver_df, on="puzzle_id", how="left")
    merged = merged.dropna(subset=["final_difficulty"])

    print(f"\nLoaded {len(merged)} rows, "
          f"{merged['participant_id'].nunique()} participants, "
          f"puzzles {sorted(merged['puzzle_id'].unique().tolist())}")

    print("\nPer-puzzle mean final_difficulty:")
    summary = merged.groupby("puzzle_id").agg(
        n=("final_difficulty", "count"),
        mean_difficulty=("final_difficulty", "mean"),
        std_difficulty=("final_difficulty", "std"),
        **{m: (m, "first") for m in SAT_METRICS},
    )
    print(summary.to_string())

    plot_per_puzzle_means(merged, fig_dir / "regression_per_puzzle_means.png")

    print("\nDone.")


if __name__ == "__main__":
    main()
