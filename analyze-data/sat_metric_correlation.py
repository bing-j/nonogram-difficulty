"""
SAT metric redundancy check: how correlated are decisions, propagations, and
conflicts -- the three SAT solver metrics used throughout this pipeline
(regression_analysis.py's PREDICTORS, spearman_ranking.py's SAT_METRICS,
moderation_analysis.py's SAT_METRICS) -- with each other?

If the three are highly redundant, `conflicts` alone may capture nearly the
same information as all three combined, which would justify simplifying the
downstream regression/ranking models to a single predictor and would explain
away any multicollinearity in the current 3-predictor specifications. This
script doesn't make that change -- it just quantifies the redundancy so the
decision can be made from numbers.

Run on two samples:
  - "pool": the full 1000-puzzle candidate pool (nonogram_solver_stats.csv).
    The only place in this pipeline with enough N for a reliable correlation
    estimate.
  - "selected_six": the 6 study puzzles (selected_six_nonogram_stats.csv).
    Too few points for a reliable estimate on its own, but it's the actual
    sample every downstream regression model runs on, so it's reported
    alongside the pool for comparison.

For each sample:
  - Pairwise Pearson r + p (the downstream models are all linear -- OLS/LMM
    -- in these predictors, so Pearson is the directly relevant measure)
  - Pairwise Spearman rho + p (this repo's dominant convention elsewhere for
    these skewed count metrics, e.g. spearman_ranking.py)
  - R^2 of decisions/propagations regressed on conflicts alone (for a single
    predictor, R^2 is just the squared Pearson r of that pair -- the most
    directly interpretable "how much does conflicts alone capture" number)
  - VIF for each metric in the full 3-predictor design (standard
    multicollinearity diagnostic; VIF > 5 or 10 is the common rule-of-thumb
    concern threshold)

Inputs
------
- nonogram_solver_stats.csv       (full 1000-puzzle pool)
- selected_six_nonogram_stats.csv (the 6 study puzzles)

Outputs
-------
- analyze-data/out_features/stats_sat_metric_correlation.csv
- analyze-data/out_features/stats_sat_metric_vif.csv
- analyze-data/out_features/figures/sat_metric_correlation.png

Usage
-----
  python analyze-data/sat_metric_correlation.py
  python analyze-data/sat_metric_correlation.py --pool_csv ... --selected_csv ... --out_dir ...
"""

from __future__ import annotations

import argparse
import io
import itertools
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy.stats as stats
from statsmodels.stats.outliers_influence import variance_inflation_factor
from statsmodels.tools.tools import add_constant

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plot_style import ACCENT_COLOR, NEUTRAL_COLOR, apply_style  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_POOL_CSV = REPO_ROOT / "nonogram_solver_stats.csv"
DEFAULT_SELECTED_CSV = REPO_ROOT / "selected_six_nonogram_stats.csv"
DEFAULT_OUT_DIR = REPO_ROOT / "analyze-data" / "out_features"

# Same three metrics used downstream by regression_analysis.py, spearman_ranking.py,
# moderation_analysis.py, and behavioral_regression.py.
SAT_METRICS = ["decisions", "propagations", "conflicts"]
METRIC_LABELS = {
    "decisions": "Decisions",
    "propagations": "Propagations",
    "conflicts": "Conflicts",
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_samples(pool_csv: Path, selected_csv: Path) -> dict[str, pd.DataFrame]:
    pool_df = pd.read_csv(pool_csv)[SAT_METRICS]
    selected_df = pd.read_csv(selected_csv)[SAT_METRICS]
    return {"pool": pool_df, "selected_six": selected_df}


# ---------------------------------------------------------------------------
# Correlation + redundancy stats
# ---------------------------------------------------------------------------

def compute_pairwise_stats(df: pd.DataFrame, sample: str) -> list[dict]:
    rows = []
    for metric_a, metric_b in itertools.combinations(SAT_METRICS, 2):
        x, y = df[metric_a], df[metric_b]
        pearson_r, pearson_p = stats.pearsonr(x, y)
        spearman_rho, spearman_p = stats.spearmanr(x, y)
        r_squared_vs_conflicts = (
            pearson_r ** 2 if "conflicts" in (metric_a, metric_b) else np.nan
        )
        rows.append({
            "sample": sample,
            "metric_a": metric_a,
            "metric_b": metric_b,
            "pearson_r": pearson_r,
            "pearson_p": pearson_p,
            "spearman_rho": spearman_rho,
            "spearman_p": spearman_p,
            "r_squared_vs_conflicts": r_squared_vs_conflicts,
        })
    return rows


def compute_vif(df: pd.DataFrame, sample: str) -> list[dict]:
    X = add_constant(df[SAT_METRICS].astype(float))
    rows = []
    for i, metric in enumerate(SAT_METRICS, start=1):  # column 0 is the constant
        vif = variance_inflation_factor(X.values, i)
        rows.append({"sample": sample, "metric": metric, "vif": vif})
    return rows


# ---------------------------------------------------------------------------
# Console summary
# ---------------------------------------------------------------------------

def print_summary(corr_df: pd.DataFrame, vif_df: pd.DataFrame, sample: str, n: int) -> None:
    print(f"\n{'=' * 72}")
    print(f"SAMPLE: {sample} (n={n})")
    print(f"{'=' * 72}")

    sub = corr_df[corr_df["sample"] == sample]
    for _, r in sub.iterrows():
        print(
            f"  {METRIC_LABELS[r['metric_a']]:<13} vs {METRIC_LABELS[r['metric_b']]:<13} "
            f"Pearson r={r['pearson_r']:+.3f} (p={r['pearson_p']:.4f})  "
            f"Spearman rho={r['spearman_rho']:+.3f} (p={r['spearman_p']:.4f})"
        )

    print("\n  Can conflicts alone stand in for the others?")
    conflicts_rows = sub[sub["r_squared_vs_conflicts"].notna()]
    for _, r in conflicts_rows.iterrows():
        other = r["metric_a"] if r["metric_b"] == "conflicts" else r["metric_b"]
        print(
            f"    conflicts alone explains {r['r_squared_vs_conflicts']:.1%} "
            f"of the variance in {other}"
        )

    print("\n  Variance Inflation Factor (3-predictor design: decisions + propagations + conflicts):")
    vsub = vif_df[vif_df["sample"] == sample]
    for _, r in vsub.iterrows():
        flag = " -- high multicollinearity (rule of thumb: VIF > 5-10)" if r["vif"] > 5 else ""
        print(f"    {METRIC_LABELS[r['metric']]:<13} VIF={r['vif']:.2f}{flag}")


# ---------------------------------------------------------------------------
# Visualisation (full pool only -- the only sample with enough N to plot)
# ---------------------------------------------------------------------------

def plot_correlation(df: pd.DataFrame, fig_dir: Path) -> None:
    pairs = list(itertools.combinations(SAT_METRICS, 2))
    fig, axes = plt.subplots(1, 1 + len(pairs), figsize=(4.5 * (1 + len(pairs)), 4.5))

    corr_matrix = df[SAT_METRICS].corr()
    ax_heat = axes[0]
    im = ax_heat.imshow(corr_matrix.values, cmap="RdBu_r", vmin=-1, vmax=1)
    ax_heat.grid(which="major", visible=False)  # apply_style's major grid would bisect cells at their centers
    ax_heat.set_xticks(range(len(SAT_METRICS)))
    ax_heat.set_xticklabels([METRIC_LABELS[m] for m in SAT_METRICS], rotation=30, ha="right")
    ax_heat.set_yticks(range(len(SAT_METRICS)))
    ax_heat.set_yticklabels([METRIC_LABELS[m] for m in SAT_METRICS])
    for i in range(len(SAT_METRICS)):
        for j in range(len(SAT_METRICS)):
            text_color = "white" if abs(corr_matrix.values[i, j]) > 0.5 else "black"
            ax_heat.text(j, i, f"{corr_matrix.values[i, j]:.2f}", ha="center", va="center",
                         fontsize=9, color=text_color)
    ax_heat.set_title("Pearson r (full pool)", fontsize=10)
    fig.colorbar(im, ax=ax_heat, fraction=0.046, pad=0.04)

    for ax, (metric_a, metric_b) in zip(axes[1:], pairs):
        x, y = df[metric_a], df[metric_b]
        ax.scatter(x, y, color=NEUTRAL_COLOR, s=10, alpha=0.3, zorder=2)
        m, b = np.polyfit(x.values.astype(float), y.values.astype(float), 1)
        xline = np.linspace(x.min(), x.max(), 100)
        ax.plot(xline, m * xline + b, color=ACCENT_COLOR, linewidth=1, linestyle="--", alpha=0.7, zorder=3)
        r, p = stats.pearsonr(x, y)
        ax.text(
            0.97, 0.03, f"r={r:+.3f}  p={p:.3g}",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=8,
            bbox=dict(boxstyle="round", facecolor="white", edgecolor="gray", alpha=0.8),
        )
        ax.set_xlabel(METRIC_LABELS[metric_a], fontsize=9)
        ax.set_ylabel(METRIC_LABELS[metric_b], fontsize=9)
        ax.set_title(f"{METRIC_LABELS[metric_a]} vs {METRIC_LABELS[metric_b]}", fontsize=10)

    fig.tight_layout()
    out_path = fig_dir / "sat_metric_correlation.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"\n  Saved: {out_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Check redundancy among the three SAT solver metrics used downstream."
    )
    ap.add_argument("--pool_csv", type=Path, default=DEFAULT_POOL_CSV)
    ap.add_argument("--selected_csv", type=Path, default=DEFAULT_SELECTED_CSV)
    ap.add_argument("--out_dir", type=Path, default=DEFAULT_OUT_DIR)
    args = ap.parse_args()

    apply_style()

    if not args.pool_csv.exists():
        print(f"Pool CSV not found: {args.pool_csv}")
        return
    if not args.selected_csv.exists():
        print(f"Selected-six CSV not found: {args.selected_csv}")
        return

    fig_dir = args.out_dir / "figures"
    args.out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("SAT METRIC REDUNDANCY CHECK: decisions / propagations / conflicts")
    print("=" * 60)

    samples = load_samples(args.pool_csv, args.selected_csv)

    corr_rows, vif_rows = [], []
    for sample, df in samples.items():
        corr_rows.extend(compute_pairwise_stats(df, sample))
        vif_rows.extend(compute_vif(df, sample))

    corr_df = pd.DataFrame(corr_rows)
    vif_df = pd.DataFrame(vif_rows)

    for sample, df in samples.items():
        print_summary(corr_df, vif_df, sample, n=len(df))

    corr_out = args.out_dir / "stats_sat_metric_correlation.csv"
    vif_out = args.out_dir / "stats_sat_metric_vif.csv"
    corr_df.to_csv(corr_out, index=False)
    vif_df.to_csv(vif_out, index=False)
    print(f"\nSaved: {corr_out}")
    print(f"Saved: {vif_out}")

    print("\nGenerating figure (full pool)...")
    plot_correlation(samples["pool"], fig_dir)

    print("\nDone.")


if __name__ == "__main__":
    main()
