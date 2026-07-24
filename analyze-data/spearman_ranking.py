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

A second, order-adjusted variant is also fit: `final_difficulty ~ C(order)` is
residualized first (so within-session presentation order can no longer bias
which puzzle "wins" a comparison), then BT is fit on those residuals instead
of the raw ratings. Participant-level traits that are constant across a
session (e.g. expertise) are *not* worth residualizing this way — they cancel
out exactly in a within-participant pairwise difference, so BT's design is
already robust to them without any adjustment. Order does vary within a
session, so it's the one covariate where this composition actually changes
the ranking.

Outputs
-------
- Console: win matrix, BT scores (raw + order-adjusted), Spearman ρ table
- analyze-data/out_features/bt_scores.png                  — bar chart of BT scores (raw + order-adjusted panels)
- analyze-data/out_features/bt_ranking_vs_sat.png          — BT score vs SAT metrics (raw + order-adjusted rows)
- analyze-data/out_features/stats_bt_vs_sat.csv            — Spearman ρ/p per rating variant, SAT metric, and behavioral aggregate
- analyze-data/out_features/bt_difficulty_vs_sat.csv       — per-puzzle BT scores (raw + order-adjusted) alongside SAT metrics
- analyze-data/out_features/order_adjustment_model_params.csv — OLS coefficients for the order-only residualization model

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
import statsmodels.formula.api as smf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plot_style import NEUTRAL_COLOR, apply_style  # noqa: E402

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
# Order-adjusted ratings (for the second BT variant)
# ---------------------------------------------------------------------------

def build_order_residualized_ratings(
    df: pd.DataFrame, rating_col: str, out_dir: Optional[Path] = None
) -> pd.DataFrame:
    """Return a copy of df with an order-residualized version of rating_col.

    Regresses rating_col ~ C(order) and adds the grand mean back onto the
    residuals, so the result stays on the original rating scale but has
    within-session presentation-order effects partialed out before BT sees it.

    If out_dir is given, also saves the OLS model's coefficients (term, coef,
    se, p_value) to order_adjustment_model_params.csv -- the order-only
    analogue of the expertise+order model params the old expertise-adjustment
    step used to save.
    """
    work = df.dropna(subset=[rating_col, "order"]).copy()
    grand = work[rating_col].mean()
    model = smf.ols(f"{rating_col} ~ C(order)", data=work).fit()
    work[f"{rating_col}_order_adj"] = model.resid + grand

    if out_dir is not None:
        params = pd.DataFrame({
            "term": model.params.index,
            "coef": model.params.values,
            "se": model.bse.values,
            "p_value": model.pvalues.values,
        })
        out_path = out_dir / "order_adjustment_model_params.csv"
        params.to_csv(out_path, index=False)
        print(f"  Saved: {out_path}")

    return work


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


def _rating_variant_key(rating_col: str) -> str:
    """Short column-name-safe variant tag, paired with _rating_label below."""
    suffix = "_order_adjusted"
    return "order_adjusted" if rating_col.endswith(suffix) else "raw"


def build_bt_vs_sat_df(bt_dfs: dict[str, pd.DataFrame], solver_df: pd.DataFrame) -> pd.DataFrame:
    """Per-puzzle BT scores (raw + order-adjusted) alongside SAT metrics.

    The BT-based analogue of the old expertise_adjusted_puzzle_difficulty.csv:
    one row per puzzle, one BT score/rank column pair per rating variant, plus
    the SAT solver metrics for direct eyeballing alongside the correlation
    tests in stats_bt_vs_sat.csv.
    """
    combined: Optional[pd.DataFrame] = None
    for rating_col, bt_df in bt_dfs.items():
        variant = _rating_variant_key(rating_col)
        sub = bt_df[["puzzle_id", "bt_score", "bt_rank"]].rename(
            columns={"bt_score": f"bt_score_{variant}", "bt_rank": f"bt_rank_{variant}"}
        )
        combined = sub if combined is None else combined.merge(sub, on="puzzle_id")
    return combined.merge(solver_df, on="puzzle_id", how="left")


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
    out_dir: Optional[Path] = None,
) -> pd.DataFrame:
    """Print Spearman ρ table for BT rankings vs SAT metrics and behavioral aggregates.

    Also returns (and, if out_dir is given, saves to CSV) the same rows that get
    printed, so downstream LaTeX rendering has exact reproducible numbers instead
    of console-only output.
    """

    print(f"\n{'='*72}")
    print("SPEARMAN CORRELATION: Bradley-Terry rank vs predictor rank")
    print(f"{'='*72}")
    print(f"  {'Rating type':<22}  {'Predictor':<22}  {'rho':>7}  {'p':>7}  {'sig':>4}  {'BT vs raw'}")
    print(f"  {'-'*22}  {'-'*22}  {'-'*7}  {'-'*7}  {'-'*4}  {'-'*10}")

    rows = []

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
            rows.append({
                "rating_col": rating_col,
                "predictor_type": "sat_metric",
                "predictor": metric,
                "bt_rho": rho_bt,
                "bt_p": p_bt,
                "raw_rho": rho_raw,
                "raw_p": p_raw,
                "n": len(common),
            })

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
            rows.append({
                "rating_col": rating_col,
                "predictor_type": "behavioral_aggregate",
                "predictor": feat,
                "bt_rho": rho_bt,
                "bt_p": p_bt,
                "raw_rho": rho_raw,
                "raw_p": p_raw,
                "n": len(common),
            })

        print()  # blank line between rating types

    result = pd.DataFrame(rows)
    if out_dir is not None:
        out_path = out_dir / "stats_bt_vs_sat.csv"
        result.to_csv(out_path, index=False)
        print(f"  Saved: {out_path}")
    return result


# ---------------------------------------------------------------------------
# Visualisation
# ---------------------------------------------------------------------------

def _rating_label(rating_col: str) -> str:
    """Human-readable panel label distinguishing raw vs. order-adjusted BT."""
    suffix = "_order_adjusted"
    if rating_col.endswith(suffix):
        return f"{rating_col[: -len(suffix)]} (order-adjusted)"
    return f"{rating_col} (raw)"


def plot_bt_scores(bt_dfs: dict[str, pd.DataFrame], out_dir: Path) -> None:
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
            color=NEUTRAL_COLOR,
            edgecolor="black",
            linewidth=0.7,
        )
        ax.set_title(_rating_label(rating_col), fontsize=11)
        ax.set_xlabel("Puzzle", fontsize=10)
        ax.set_ylabel("BT strength score θ", fontsize=10)
        ax.axhline(1.0, color="black", linewidth=0.8, linestyle="--", alpha=0.5)

        for bar, (_, row) in zip(bars, sorted_df.iterrows()):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.01,
                f"#{int(row['bt_rank'])}",
                ha="center", va="bottom", fontsize=9,
            )

    fig.tight_layout()
    out_path = out_dir / "bt_scores.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {out_path}")


def plot_bt_vs_sat(
    bt_dfs: dict[str, pd.DataFrame],
    solver_df: pd.DataFrame,
    out_dir: Path,
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

        row_label = _rating_label(rating_col)
        for col_idx, metric in enumerate(SAT_METRICS):
            ax_bt = axes[row_idx][col_idx]
            ylabel = "BT score θ" if col_idx > 0 else f"BT score θ\n[{row_label}]"
            _scatter_panel(
                ax=ax_bt,
                x=merged[metric],
                y=merged["bt_score"],
                labels=merged["puzzle_id"].astype(int),
                xlabel=metric,
                ylabel=ylabel,
                y_series_for_spearman=merged["bt_rank"],
                x_series_for_spearman=merged[metric],
            )

    fig.tight_layout()
    out_path = out_dir / "bt_ranking_vs_sat.png"
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
    y_series_for_spearman: pd.Series,
    x_series_for_spearman: pd.Series,
) -> None:
    for xi, yi, label in zip(x, y, labels):
        ax.scatter(xi, yi, color=NEUTRAL_COLOR, s=80, zorder=3)
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
    ax.text(
        0.97, 0.03, f"ρ={rho:+.3f}  p={p:.3f} {sig}",
        transform=ax.transAxes, ha="right", va="bottom", fontsize=8,
        bbox=dict(boxstyle="round", facecolor="white", edgecolor="gray", alpha=0.8),
    )
    ax.set_xlabel(xlabel, fontsize=9)
    ax.set_ylabel(ylabel, fontsize=9)
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

    apply_style()

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

        order_adj_label = f"{rating_col}_order_adjusted"
        order_adj_df = build_order_residualized_ratings(features_df, rating_col, out_dir=args.out_dir)
        order_adj_col = f"{rating_col}_order_adj"
        W_adj = build_win_matrix(order_adj_df, order_adj_col)
        theta_adj = fit_bradley_terry(W_adj)
        bt_adj_df = build_bt_df(order_adj_df, order_adj_col, theta_adj)
        bt_dfs[order_adj_label] = bt_adj_df
        print_bt_summary(bt_adj_df, order_adj_label, W_adj)

    run_spearman_tests(bt_dfs, solver_df, features_df, out_dir=args.out_dir)

    bt_vs_sat_df = build_bt_vs_sat_df(bt_dfs, solver_df)
    bt_vs_sat_path = args.out_dir / "bt_difficulty_vs_sat.csv"
    bt_vs_sat_df.to_csv(bt_vs_sat_path, index=False)
    print(f"  Saved: {bt_vs_sat_path}")

    print("\nGenerating figures...")
    plot_bt_scores(bt_dfs, args.out_dir)
    plot_bt_vs_sat(bt_dfs, solver_df, args.out_dir)

    print("\nDone.")


if __name__ == "__main__":
    main()
