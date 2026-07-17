"""
Bradley-Terry ranking + Spearman correlation tests.

Each participant sees 3 of the 6 research puzzles and rates each on a 1–5
difficulty scale.  Raw per-puzzle means are biased by which subset a participant
saw, so we use a Bradley-Terry pairwise comparison model instead:

  * Within each participant's session every pair of puzzles they rated generates
    one implicit comparison — the higher-rated puzzle "wins".  Ties are split
    as 0.5 wins each.
  * A global strength score θ_i is estimated per puzzle via MLE
    (P(i harder than j) = θ_i / (θ_i + θ_j)).
  * The resulting ranking is tested for Spearman correlation against SAT solver
    metrics (decisions, propagations, conflicts) and behavioral aggregates.

Outputs
-------
- Console: win matrix, BT scores, Spearman ρ table (BT vs raw-mean comparison)
- analyze-data/out_features/bt_scores.png                  — bar chart of BT scores (all participants)
- analyze-data/out_features/bt_ranking_vs_sat.png          — BT score vs SAT metrics (all participants)
- analyze-data/out_features/bt_scores_{group}.png          — per experience group (beginner/intermediate/experienced)
- analyze-data/out_features/bt_ranking_vs_sat_{group}.png  — per experience group

Usage
-----
  python analyze-data/spearman_ranking.py
  python analyze-data/spearman_ranking.py --features_csv ... --solver_csv ... --out_dir ...
"""

from __future__ import annotations

import argparse
import io
import sys
import warnings
from itertools import combinations
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy.optimize as opt
import scipy.stats as stats

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FEATURES_CSV = REPO_ROOT / "analyze-data" / "out_features" / "behavioral_features.csv"
DEFAULT_SOLVER_CSV = REPO_ROOT / "selected_six_nonogram_stats.csv"
DEFAULT_OUT_DIR = REPO_ROOT / "analyze-data" / "out_features"

SAT_METRICS = ["decisions", "propagations", "conflicts"]
RATING_COLS = ["final_difficulty"]
BEHAVIORAL_AGGREGATES = ["time_to_solve_sec", "error_count", "hint_count"]

PUZZLE_COLORS = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b",
]

EXPERIENCE_BINS   = [0, 3, 6, 10]   # right-inclusive: (0,3], (3,6], (6,10]
EXPERIENCE_LABELS = ["beginner", "intermediate", "experienced"]
MIN_OBS = 5  # minimum participants to run per-group analysis


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_features(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    for col in RATING_COLS + BEHAVIORAL_AGGREGATES:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in RATING_COLS:
        if col in df.columns:
            df[col] = df[col].where(df[col] >= 1, np.nan)
    df["puzzle_id"] = df["puzzle_id"].astype(int)
    return df


def load_solver_stats(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, index_col=0)
    if "puzzle_id" in df.columns:
        df = df.drop(columns=["puzzle_id"])
    df.index.name = "puzzle_id"
    df = df.reset_index()
    df["puzzle_id"] = df["puzzle_id"].astype(int)
    return df[["puzzle_id"] + SAT_METRICS]


def assign_groups(df: pd.DataFrame) -> pd.DataFrame:
    """Add an 'experience_group' column based on skill_nonogram (1–10 scale).

    Groups:
      beginner     — skill_nonogram 1–3
      intermediate — skill_nonogram 4–6
      experienced  — skill_nonogram 7–10
    """
    df = df.copy()
    df["experience_group"] = pd.cut(
        pd.to_numeric(df["skill_nonogram"], errors="coerce"),
        bins=EXPERIENCE_BINS,
        labels=EXPERIENCE_LABELS,
        right=True,
    )
    return df


# ---------------------------------------------------------------------------
# Bradley-Terry model
# ---------------------------------------------------------------------------

def build_win_matrix(df: pd.DataFrame, rating_col: str, n_puzzles: int = 6) -> np.ndarray:
    """Build W[i][j] = weighted wins of puzzle i over puzzle j.

    For each participant, every pair of puzzles they rated generates one
    comparison.  Ties are split as 0.5 wins each way.
    """
    W = np.zeros((n_puzzles, n_puzzles))

    for pid, group in df.groupby("participant_id"):
        valid = group[["puzzle_id", rating_col]].dropna()
        if len(valid) < 2:
            continue
        rows = list(valid.itertuples(index=False))
        for (pid_i, r_i), (pid_j, r_j) in combinations(rows, 2):
            i, j = int(pid_i), int(pid_j)
            if r_i > r_j:
                W[i][j] += 1.0
            elif r_j > r_i:
                W[j][i] += 1.0
            else:
                W[i][j] += 0.5
                W[j][i] += 0.5

    return W


def _neg_log_likelihood(lam_free: np.ndarray, W: np.ndarray) -> float:
    """Negative log-likelihood for Bradley-Terry in log-space.

    lam_free: λ_1 … λ_{n-1}  (λ_0 is fixed at 0 for identifiability)
    W[i][j]: wins of puzzle i over puzzle j
    """
    lam = np.concatenate([[0.0], lam_free])
    n = len(lam)
    nll = 0.0
    for i in range(n):
        for j in range(n):
            if i == j or W[i][j] == 0:
                continue
            # log P(i beats j) = λ_i - log(exp(λ_i) + exp(λ_j))
            log_p = lam[i] - np.logaddexp(lam[i], lam[j])
            nll -= W[i][j] * log_p
    return nll


def fit_bradley_terry(W: np.ndarray) -> np.ndarray:
    """Fit Bradley-Terry model; return θ array (one score per puzzle)."""
    n = W.shape[0]

    # Connectivity check
    total_comparisons = W + W.T
    isolated = np.where(total_comparisons.sum(axis=1) == 0)[0]
    if len(isolated):
        warnings.warn(
            f"Puzzles {isolated.tolist()} have no pairwise comparisons — "
            "BT scores for them will be 1.0 (uninformative)."
        )

    x0 = np.zeros(n - 1)
    result = opt.minimize(
        _neg_log_likelihood,
        x0,
        args=(W,),
        method="L-BFGS-B",
        options={"maxiter": 1000, "ftol": 1e-12},
    )
    if not result.success:
        warnings.warn(f"BT optimisation did not fully converge: {result.message}")

    lam = np.concatenate([[0.0], result.x])
    # Centre so geometric mean is 1
    lam -= lam.mean()
    return np.exp(lam)


# ---------------------------------------------------------------------------
# Summary table
# ---------------------------------------------------------------------------

def build_bt_df(
    features_df: pd.DataFrame,
    rating_col: str,
    theta: np.ndarray,
) -> pd.DataFrame:
    """Return a per-puzzle DataFrame with BT scores, BT ranks, and raw means."""
    puzzle_ids = list(range(len(theta)))

    raw_means = (
        features_df.groupby("puzzle_id")[rating_col]
        .mean()
        .reindex(puzzle_ids)
    )

    df = pd.DataFrame({
        "puzzle_id": puzzle_ids,
        "bt_score": theta,
        "raw_mean": raw_means.values,
    })
    df["bt_rank"] = df["bt_score"].rank(method="min").astype(int)
    df["raw_rank"] = df["raw_mean"].rank(method="min").astype(int)
    return df


def print_bt_summary(bt_df: pd.DataFrame, rating_col: str, W: np.ndarray) -> None:
    n = W.shape[0]
    print(f"\n{'='*60}")
    print(f"BRADLEY-TERRY RANKING  ({rating_col})")
    print(f"{'='*60}")

    print("\nWin matrix W[i][j] = wins of puzzle i over puzzle j:")
    header = "      " + "  ".join(f"P{j}" for j in range(n))
    print(header)
    for i in range(n):
        row = "  ".join(f"{W[i][j]:4.1f}" for j in range(n))
        print(f"  P{i}  {row}")

    print(f"\n{'Puzzle':>8}  {'BT score':>10}  {'BT rank':>8}  {'Raw mean':>9}  {'Raw rank':>9}")
    print(f"  {'--':>6}  {'--------':>10}  {'-------':>8}  {'--------':>9}  {'--------':>9}")
    for _, row in bt_df.sort_values("bt_rank").iterrows():
        changed = " <-" if row["bt_rank"] != row["raw_rank"] else ""
        print(
            f"  Puzzle {int(row['puzzle_id'])}"
            f"  {row['bt_score']:>10.4f}"
            f"  {int(row['bt_rank']):>8}"
            f"  {row['raw_mean']:>9.3f}"
            f"  {int(row['raw_rank']):>9}"
            f"{changed}"
        )


# ---------------------------------------------------------------------------
# Spearman tests
# ---------------------------------------------------------------------------

def _sig_stars(p: float) -> str:
    if p < 0.001:
        return "***"
    if p < 0.01:
        return "**"
    if p < 0.05:
        return "*"
    return "ns"


def run_spearman_tests(
    bt_dfs: dict[str, pd.DataFrame],
    solver_df: pd.DataFrame,
    features_df: pd.DataFrame,
) -> None:
    """Print Spearman ρ table for BT rankings vs SAT metrics and behavioral aggregates."""

    print(f"\n{'='*72}")
    print("SPEARMAN CORRELATION: Bradley-Terry rank vs predictor rank")
    print(f"{'='*72}")
    print(f"  {'Rating type':<22}  {'Predictor':<22}  {'rho':>7}  {'p':>7}  {'sig':>4}  {'BT vs raw'}")
    print(f"  {'-'*22}  {'-'*22}  {'-'*7}  {'-'*7}  {'-'*4}  {'-'*10}")

    for rating_col, bt_df in bt_dfs.items():
        bt_ranks = bt_df.set_index("puzzle_id")["bt_rank"]
        raw_ranks = bt_df.set_index("puzzle_id")["raw_rank"]

        # SAT metrics
        for metric in SAT_METRICS:
            sat_vals = solver_df.set_index("puzzle_id")[metric]
            common = bt_ranks.index.intersection(sat_vals.index)
            if len(common) < 3:
                continue
            rho_bt, p_bt = stats.spearmanr(bt_ranks[common], sat_vals[common])
            rho_raw, p_raw = stats.spearmanr(raw_ranks[common], sat_vals[common])
            delta = f"rho {rho_bt - rho_raw:+.3f}"
            print(
                f"  {rating_col:<22}  {metric:<22}  {rho_bt:>+7.3f}  {p_bt:>7.4f}"
                f"  {_sig_stars(p_bt):>4}  {delta}"
            )

        # Behavioral aggregates (per-puzzle mean)
        for feat in BEHAVIORAL_AGGREGATES:
            if feat not in features_df.columns:
                continue
            agg = features_df.groupby("puzzle_id")[feat].mean()
            common = bt_ranks.index.intersection(agg.index)
            if len(common) < 3:
                continue
            rho_bt, p_bt = stats.spearmanr(bt_ranks[common], agg[common])
            rho_raw, p_raw = stats.spearmanr(raw_ranks[common], agg[common])
            delta = f"rho {rho_bt - rho_raw:+.3f}"
            print(
                f"  {rating_col:<22}  {feat:<22}  {rho_bt:>+7.3f}  {p_bt:>7.4f}"
                f"  {_sig_stars(p_bt):>4}  {delta}"
            )

        print()  # blank line between rating types


# ---------------------------------------------------------------------------
# Visualisation
# ---------------------------------------------------------------------------

def plot_bt_scores(bt_dfs: dict[str, pd.DataFrame], out_dir: Path, suffix: str = "") -> None:
    """Bar chart of BT scores per puzzle for each rating type."""
    n_ratings = len(bt_dfs)
    fig, axes = plt.subplots(1, n_ratings, figsize=(5 * n_ratings, 4), sharey=False)
    if n_ratings == 1:
        axes = [axes]

    for ax, (rating_col, bt_df) in zip(axes, bt_dfs.items()):
        sorted_df = bt_df.sort_values("puzzle_id")
        bars = ax.bar(
            [f"P{i}" for i in sorted_df["puzzle_id"]],
            sorted_df["bt_score"],
            color=[PUZZLE_COLORS[i] for i in sorted_df["puzzle_id"]],
            edgecolor="black",
            linewidth=0.7,
        )
        ax.set_xlabel("Puzzle", fontsize=10)
        ax.set_ylabel("BT strength score θ", fontsize=10)
        ax.set_title(f"Bradley-Terry scores\n({rating_col})", fontsize=11)
        ax.axhline(1.0, color="black", linewidth=0.8, linestyle="--", alpha=0.5)
        ax.grid(axis="y", linestyle="--", alpha=0.4)

        for bar, (_, row) in zip(bars, sorted_df.iterrows()):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.01,
                f"#{int(row['bt_rank'])}",
                ha="center", va="bottom", fontsize=9,
            )

    fig.tight_layout()
    out_path = out_dir / f"bt_scores{suffix}.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {out_path}")


def plot_bt_vs_sat(
    bt_dfs: dict[str, pd.DataFrame],
    solver_df: pd.DataFrame,
    out_dir: Path,
    suffix: str = "",
) -> None:
    """Scatter grid: BT score vs SAT metrics, one row per rating type."""
    n_metrics = len(SAT_METRICS)
    n_rows = len(bt_dfs)

    fig, axes = plt.subplots(
        n_rows, n_metrics,
        figsize=(4.5 * n_metrics, 3.8 * n_rows),
        squeeze=False,
    )

    for row_idx, (rating_col, bt_df) in enumerate(bt_dfs.items()):
        merged = bt_df.merge(solver_df, on="puzzle_id")

        for col_idx, metric in enumerate(SAT_METRICS):
            ax_bt = axes[row_idx][col_idx]
            _scatter_panel(
                ax=ax_bt,
                x=merged[metric],
                y=merged["bt_score"],
                labels=merged["puzzle_id"].astype(int),
                xlabel=metric,
                ylabel="BT score θ",
                title=f"BT score vs {metric}\n({rating_col})",
                y_series_for_spearman=merged["bt_rank"],
                x_series_for_spearman=merged[metric],
            )

    fig.suptitle(
        "Bradley-Terry score vs SAT metrics",
        fontsize=13, fontweight="bold", y=1.01,
    )
    fig.tight_layout()
    out_path = out_dir / f"bt_ranking_vs_sat{suffix}.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {out_path}")


def _scatter_panel(
    ax: plt.Axes,
    x: pd.Series,
    y: pd.Series,
    labels: pd.Series,
    xlabel: str,
    ylabel: str,
    title: str,
    y_series_for_spearman: pd.Series,
    x_series_for_spearman: pd.Series,
) -> None:
    for xi, yi, label in zip(x, y, labels):
        ax.scatter(xi, yi, color=PUZZLE_COLORS[int(label)], s=80, zorder=3)
        ax.annotate(
            f"P{label}", (xi, yi),
            textcoords="offset points", xytext=(6, 4),
            fontsize=8,
        )

    if len(x) >= 2:
        m, b = np.polyfit(x.values.astype(float), y.values.astype(float), 1)
        xline = np.linspace(x.min(), x.max(), 100)
        ax.plot(xline, m * xline + b, color="black", linewidth=1, linestyle="--", alpha=0.6)

    rho, p = stats.spearmanr(y_series_for_spearman, x_series_for_spearman)
    sig = _sig_stars(p)
    ax.set_title(f"{title}\nSpearman ρ={rho:+.3f}  p={p:.3f} {sig}", fontsize=9)
    ax.set_xlabel(xlabel, fontsize=9)
    ax.set_ylabel(ylabel, fontsize=9)
    ax.grid(True, linestyle="--", alpha=0.3)
    ax.tick_params(labelsize=8)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Bradley-Terry ranking and Spearman correlation tests."
    )
    ap.add_argument("--features_csv", type=Path, default=DEFAULT_FEATURES_CSV)
    ap.add_argument("--solver_csv", type=Path, default=DEFAULT_SOLVER_CSV)
    ap.add_argument("--out_dir", type=Path, default=DEFAULT_OUT_DIR)
    args = ap.parse_args()

    if not args.features_csv.exists():
        print(f"Features CSV not found: {args.features_csv}")
        print("Run extract_behavioral_features.py first.")
        return

    args.out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("NONOGRAM DIFFICULTY — BRADLEY-TERRY + SPEARMAN")
    print("=" * 60)

    features_df = load_features(args.features_csv)
    solver_df = load_solver_stats(args.solver_csv)

    print(f"\nLoaded {len(features_df)} rows, "
          f"{features_df['participant_id'].nunique()} participants, "
          f"puzzles {sorted(features_df['puzzle_id'].unique().tolist())}")

    bt_dfs: dict[str, pd.DataFrame] = {}

    for rating_col in RATING_COLS:
        W = build_win_matrix(features_df, rating_col)
        theta = fit_bradley_terry(W)
        bt_df = build_bt_df(features_df, rating_col, theta)
        bt_dfs[rating_col] = bt_df
        print_bt_summary(bt_df, rating_col, W)

    run_spearman_tests(bt_dfs, solver_df, features_df)

    print("\nGenerating figures...")
    plot_bt_scores(bt_dfs, args.out_dir)
    plot_bt_vs_sat(bt_dfs, solver_df, args.out_dir)

    # ── Per-experience-group analysis ────────────────────────────────────────
    if "skill_nonogram" not in features_df.columns:
        print(
            "\n[WARNING] 'skill_nonogram' column not found in features CSV. "
            "Re-run extract_behavioral_features.py to add it, then re-run this script."
        )
    else:
        df_grouped = assign_groups(features_df)
        print("\n" + "=" * 60)
        print("EXPERIENCE GROUP BREAKDOWN")
        print("=" * 60)
        for label in EXPERIENCE_LABELS:
            group_df = df_grouped[df_grouped["experience_group"] == label]
            n_participants = group_df["participant_id"].nunique()
            print(f"  {label:<14}: {n_participants:>2} participants, {len(group_df):>3} rows")

        for label in EXPERIENCE_LABELS:
            group_df = df_grouped[df_grouped["experience_group"] == label].copy()
            n_participants = group_df["participant_id"].nunique()
            if n_participants < MIN_OBS:
                print(f"\n  [{label}] only {n_participants} participants — skipping (need {MIN_OBS})")
                continue

            print(f"\n{'=' * 60}")
            print(f"GROUP: {label.upper()}  ({n_participants} participants, {len(group_df)} rows)")
            print(f"{'=' * 60}")

            bt_dfs_group: dict[str, pd.DataFrame] = {}
            for rating_col in RATING_COLS:
                W_g = build_win_matrix(group_df, rating_col)
                theta_g = fit_bradley_terry(W_g)
                bt_df_g = build_bt_df(group_df, rating_col, theta_g)
                bt_dfs_group[rating_col] = bt_df_g
                print_bt_summary(bt_df_g, rating_col, W_g)

            run_spearman_tests(bt_dfs_group, solver_df, group_df)

            suffix = f"_{label}"
            plot_bt_scores(bt_dfs_group, args.out_dir, suffix=suffix)
            plot_bt_vs_sat(bt_dfs_group, solver_df, args.out_dir, suffix=suffix)

    print("\nDone.")


if __name__ == "__main__":
    main()
