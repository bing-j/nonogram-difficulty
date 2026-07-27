"""
expertise_adjustment.py
========================
Does participant expertise predict behavior/difficulty? Correlates
`expertise_composite` against behavioral outcomes and retrospective
difficulty rating, aggregated to participant-level means.

A per-puzzle "expertise-adjusted difficulty" via OLS residualization used to
live here too (the M2 method from an earlier standalone exploratory
analysis), producing a per-puzzle mean of (residual + grand mean). It was
removed: the whole point of that residualization was to correct raw
per-puzzle *means* for imbalanced rater composition (e.g. a puzzle
disproportionately rated by novices looking harder than it "really" is), but
this pipeline's actual per-puzzle difficulty measure is the Bradley-Terry
ranking in spearman_ranking.py, not raw means. BT's within-participant
pairwise design already cancels out participant-level traits that are
constant across a session (like expertise) -- a participant's own expertise
can't bias which of two puzzles *they* judged harder, since it's identical on
both sides of that comparison. So the residualize-on-expertise-then-average
approach was solving a problem BT doesn't have, and composing it into BT
(residualize, then fit BT on the residuals) would have had literally zero
effect on the resulting ranking.

Runs 6 Spearman tests (expertise vs. each of 6 outcomes), corrected as one
Benjamini-Hochberg FDR family (`spearman_p_fdr` column) -- previously
uncorrected. CSV-only; the scatter-grid figure is unchanged.

Inputs
------
- analyze-data/out_features/behavioral_features.csv

Outputs
-------
- analyze-data/out_features/expertise_vs_outcomes.csv
- analyze-data/out_features/figures/expertise_vs_outcomes.png

Usage
-----
  python analyze-data/expertise_adjustment.py
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
import scipy.stats as stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plot_style import ACCENT_COLOR, NEUTRAL_COLOR, apply_style  # noqa: E402
from stats_utils import benjamini_hochberg  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FEATURES_CSV = REPO_ROOT / "analyze-data" / "out_features" / "behavioral_features.csv"
DEFAULT_OUT_DIR = REPO_ROOT / "analyze-data" / "out_features"

# Same behavioral signals as behavioral_regression.py's BEHAVIORAL_FEATURES.
BEHAVIORAL_FEATURES = ["time_to_solve_sec", "pause_count", "error_count", "hint_count"]
OUTCOME_LABELS = {
    "time_to_solve_sec": "Mean time to solve (s)",
    "pause_count": "Mean pause count",
    "error_count": "Mean error count",
    "hint_count": "Mean hints used",
    "final_difficulty": "Mean final difficulty",
}


def load_features(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    for col in BEHAVIORAL_FEATURES + ["final_difficulty", "expertise_composite"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["final_difficulty"] = df["final_difficulty"].where(df["final_difficulty"] >= 1, np.nan)
    df["puzzle_id"] = df["puzzle_id"].astype(int)
    return df


def spearman(x: pd.Series, y: pd.Series) -> tuple[float, float, int]:
    d = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(d) < 3 or d["x"].nunique() < 2 or d["y"].nunique() < 2:
        return float("nan"), float("nan"), len(d)
    rho, p = stats.spearmanr(d["x"], d["y"])
    return float(rho), float(p), len(d)


# ---------------------------------------------------------------------------
# Part 1: expertise vs. behavior/difficulty
# ---------------------------------------------------------------------------

def run_expertise_vs_outcomes(df: pd.DataFrame, out_dir: Path, fig_dir: Path) -> pd.DataFrame:
    outcome_cols = BEHAVIORAL_FEATURES + ["final_difficulty"]
    perf = df.groupby("participant_id").agg(
        expertise=("expertise_composite", "first"),
        time_to_solve_sec=("time_to_solve_sec", "mean"),
        pause_count=("pause_count", "mean"),
        error_count=("error_count", "mean"),
        hint_count=("hint_count", "mean"),
        final_difficulty=("final_difficulty", "mean"),
    ).reset_index()

    rows = []
    for col in outcome_cols:
        rho, p, n = spearman(perf["expertise"], perf[col])
        rows.append({"outcome": OUTCOME_LABELS[col], "column": col, "spearman_rho": rho, "spearman_p": p, "n": n})
    stat = pd.DataFrame(rows)
    stat["spearman_p_fdr"] = benjamini_hochberg(stat["spearman_p"].tolist())
    stat.to_csv(out_dir / "expertise_vs_outcomes.csv", index=False)

    fig, axes = plt.subplots(2, 3, figsize=(15, 9), dpi=150)
    for ax, col in zip(axes.ravel(), outcome_cols):
        d = perf[["expertise", col]].dropna()
        ax.scatter(d["expertise"], d[col], color=NEUTRAL_COLOR, alpha=0.6)
        if len(d) > 3 and d["expertise"].nunique() > 1:
            m, b = np.polyfit(d["expertise"], d[col], 1)
            xs = np.array([d["expertise"].min(), d["expertise"].max()])
            ax.plot(xs, m * xs + b, "--", color=ACCENT_COLOR)
            rho, p, _ = spearman(d["expertise"], d[col])
            ax.text(0.97, 0.03, f"rho={rho:.2f}\np={p:.3f}",
                    transform=ax.transAxes, ha="right", va="bottom", fontsize=8,
                    bbox=dict(boxstyle="round", facecolor="white", edgecolor="gray", alpha=0.8))
        ax.set_xlabel("Composite expertise (z)")
        ax.set_ylabel(OUTCOME_LABELS[col])
        ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(fig_dir / "expertise_vs_outcomes.png", bbox_inches="tight")
    plt.close(fig)
    return stat


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Expertise vs. behavioral outcomes and retrospective difficulty rating."
    )
    ap.add_argument("--features_csv", type=Path, default=DEFAULT_FEATURES_CSV)
    ap.add_argument("--out_dir", type=Path, default=DEFAULT_OUT_DIR)
    args = ap.parse_args()

    apply_style()

    if not args.features_csv.exists():
        print(f"Features CSV not found: {args.features_csv}")
        print("Run extract_behavioral_features.py first.")
        return

    fig_dir = args.out_dir / "figures"
    args.out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    df = load_features(args.features_csv)

    print("=" * 60)
    print("EXPERTISE vs. BEHAVIOR AND DIFFICULTY")
    print("=" * 60)
    outcomes = run_expertise_vs_outcomes(df, args.out_dir, fig_dir)
    print(outcomes.to_string(index=False))

    print("\nDone.")


if __name__ == "__main__":
    main()
