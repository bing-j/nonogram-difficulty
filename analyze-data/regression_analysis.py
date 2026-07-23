"""
regression_analysis.py
======================
Linear regression analysis of nonogram difficulty ratings against SAT solver
metrics (decisions, propagations, conflicts).

Inputs
------
- backend/logs/*.ndjson
    NDJSON event streams recorded during participant sessions.
    Relevant events:
      * session_start_three  — queue field lists 3 puzzle IDs (integers 0–5)
      * survey_submit / survey_type in {puzzle_1, puzzle_2, puzzle_3}
          answers.difficulty  → in-the-moment (initial) difficulty rating
      * survey_submit / survey_type == "post"
          answers.puzzle_N_rate_again → final (retrospective) difficulty rating
- selected_six_nonogram_stats.csv
    SAT solver metrics for the 6 research puzzles.
    The unnamed index column (0–5) is the experiment puzzle_id.
    Columns used: conflicts, decisions, propagations.
Outputs
-------
- analyze-data/out_features/figures/spearman_rank_scatter.png
    3×2 grid of BT rank vs SAT metric rank.
- analyze-data/out_features/figures/regression_per_puzzle_means.png
    Per-puzzle mean difficulty vs SAT predictor, with error bars.

Run from the repo root:
    python analyze-data/regression_analysis.py
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Any

# Force UTF-8 output on Windows so that Unicode characters (±, →, etc.)
# print correctly regardless of the console's default code page.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy.stats as stats

# BT fitting functions live in the same directory
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from spearman_ranking import build_win_matrix, fit_bradley_terry  # noqa: E402
from plot_style import PUZZLE_COLORS, NEUTRAL_COLOR, apply_style  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = REPO_ROOT / "backend" / "logs"
STATS_CSV = REPO_ROOT / "selected_six_nonogram_stats.csv"
FIGURE_DIR = REPO_ROOT / "analyze-data" / "out_features" / "figures"

PREDICTORS: list[str] = ["decisions", "propagations", "conflicts"]
RATING_TYPES: list[str] = ["final_difficulty"]

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def read_ndjson(path: Path) -> list[dict[str, Any]]:
    """Read a newline-delimited JSON file into a list of event dicts.

    Args:
        path: Absolute path to the .ndjson file.

    Returns:
        List of parsed JSON objects, in file order.

    Raises:
        FileNotFoundError: If path does not exist.
        ValueError: If a line contains invalid JSON.
    """
    if not path.exists():
        raise FileNotFoundError(f"Log file not found: {path}")
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, raw in enumerate(fh, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                events.append(json.loads(raw))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON in {path.name} at line {line_no}: {exc}"
                ) from exc
    return events


def extract_participant_ratings(
    participant_id: str, events: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Extract per-puzzle difficulty ratings for one participant.

    Maps the three position slots (puzzle_1 / puzzle_2 / puzzle_3) to actual
    puzzle IDs via the session's queue field, then collects:
      - initial_difficulty  from puzzle_N surveys
      - final_difficulty    from the post survey

    Args:
        participant_id: Human-readable label (e.g. "p1-Michael").
        events: Parsed event list from that participant's NDJSON log.

    Returns:
        List of dicts, each with keys:
          participant_id, puzzle_id, initial_difficulty, final_difficulty.
        Returns an empty list if the session_start_three event is missing.
    """
    # Locate the queue
    queue: list[int] | None = None
    for ev in events:
        if ev.get("type") == "session_start_three":
            queue = ev.get("queue")
            break

    if queue is None or len(queue) != 3:
        print(
            f"  WARNING: {participant_id} has no valid session_start_three queue; skipping.",
            file=sys.stderr,
        )
        return []

    # Collect initial difficulty ratings from per-puzzle surveys
    initial: dict[int, int | None] = {}  # position index → rating
    post_ratings: dict[int, int | None] = {}  # position index → rating

    for ev in events:
        if ev.get("type") != "survey_submit":
            continue
        survey_type = ev.get("survey_type", "")
        answers = ev.get("answers", {})

        # puzzle_N in-the-moment rating
        for pos_idx, label in enumerate(("puzzle_1", "puzzle_2", "puzzle_3")):
            if survey_type == label:
                diff = answers.get("difficulty")
                if diff is not None:
                    initial[pos_idx] = int(diff)

        # post-survey retrospective ratings
        if survey_type == "post":
            for pos_idx, key in enumerate(
                ("puzzle_1_rate_again", "puzzle_2_rate_again", "puzzle_3_rate_again")
            ):
                val = answers.get(key)
                if val is not None:
                    post_ratings[pos_idx] = int(val)

    records = []
    for pos_idx, puzzle_id in enumerate(queue):
        records.append(
            {
                "participant_id": participant_id,
                "puzzle_id": int(puzzle_id),
                "initial_difficulty": initial.get(pos_idx),
                "final_difficulty": post_ratings.get(pos_idx),
            }
        )
    return records


def load_all_ratings(log_dir: Path) -> pd.DataFrame:
    """Load ratings from all participant NDJSON logs in log_dir.

    Args:
        log_dir: Directory containing .ndjson files.

    Returns:
        DataFrame with columns:
          participant_id, puzzle_id, initial_difficulty, final_difficulty.
    """
    log_files = sorted(log_dir.glob("*.ndjson"))
    if not log_files:
        raise FileNotFoundError(f"No .ndjson files found in {log_dir}")

    all_records: list[dict[str, Any]] = []
    for path in log_files:
        participant_id = path.stem  # e.g. "p1-Michael"
        events = read_ndjson(path)
        records = extract_participant_ratings(participant_id, events)
        all_records.extend(records)
        print(f"  Loaded {len(records)} puzzle-ratings from {path.name}")

    df = pd.DataFrame(all_records)
    return df


def load_sat_stats(csv_path: Path) -> pd.DataFrame:
    """Load SAT solver metrics from CSV, using the unnamed row index as puzzle_id.

    The CSV has an unnamed integer index (0–5) that corresponds to the
    experiment puzzle IDs, and a separate 'puzzle_id' column that is an
    internal solver ID (not 0–5). We use the row index (0–5) as the
    experiment puzzle_id and drop the solver's internal puzzle_id column.

    Args:
        csv_path: Path to selected_six_nonogram_stats.csv.

    Returns:
        DataFrame with columns puzzle_id (int 0–5), conflicts, decisions,
        propagations (plus other SAT columns).

    Raises:
        FileNotFoundError: If csv_path does not exist.
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"Stats CSV not found: {csv_path}")
    df = pd.read_csv(csv_path, index_col=0)
    # The unnamed index is the experiment puzzle ID (0–5).
    # Drop the internal 'puzzle_id' column if it exists to avoid collision.
    if "puzzle_id" in df.columns:
        df = df.drop(columns=["puzzle_id"])
    df.index.name = "puzzle_id"
    df = df.reset_index()
    df["puzzle_id"] = df["puzzle_id"].astype(int)
    return df


# ---------------------------------------------------------------------------
# Merging
# ---------------------------------------------------------------------------


def merge_data(ratings: pd.DataFrame, sat_stats: pd.DataFrame) -> pd.DataFrame:
    """Merge participant ratings with SAT solver stats on puzzle_id.

    Args:
        ratings: Output of load_all_ratings().
        sat_stats: Output of load_sat_stats().

    Returns:
        Merged DataFrame; rows with NaN in all rating columns are dropped.
    """
    merged = ratings.merge(sat_stats, on="puzzle_id", how="left")
    # Drop rows where BOTH rating types are missing
    merged = merged.dropna(subset=["initial_difficulty", "final_difficulty"], how="all")
    merged["puzzle_id"] = merged["puzzle_id"].astype(int)
    return merged


# ---------------------------------------------------------------------------
# Summary statistics
# ---------------------------------------------------------------------------


def print_summary_table(df: pd.DataFrame) -> None:
    """Print a summary table of merged data, then per-puzzle statistics.

    Args:
        df: Merged DataFrame with rating + SAT columns.
    """
    print("\n" + "=" * 70)
    print("MERGED DATA SUMMARY")
    print("=" * 70)
    print(f"Total rows: {len(df)}")
    print(f"Participants: {df['participant_id'].nunique()}")
    print(f"Puzzles covered: {sorted(df['puzzle_id'].unique())}")
    null_initial = df["initial_difficulty"].isna().sum()
    null_final = df["final_difficulty"].isna().sum()
    print(f"Missing initial_difficulty: {null_initial}")
    print(f"Missing final_difficulty:   {null_final}")

    print("\nFull merged table:")
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 120)
    cols_show = [
        "participant_id",
        "puzzle_id",
        "initial_difficulty",
        "final_difficulty",
        "decisions",
        "propagations",
        "conflicts",
    ]
    print(df[cols_show].to_string(index=False))

    print("\n" + "=" * 70)
    print("PER-PUZZLE STATISTICS")
    print("=" * 70)
    for pid in sorted(df["puzzle_id"].unique()):
        sub = df[df["puzzle_id"] == pid]
        dec = sub["decisions"].iloc[0]
        prop = sub["propagations"].iloc[0]
        conf = sub["conflicts"].iloc[0]
        init_mean = sub["initial_difficulty"].mean()
        init_std = sub["initial_difficulty"].std()
        fin_mean = sub["final_difficulty"].mean()
        fin_std = sub["final_difficulty"].std()
        n_init = sub["initial_difficulty"].notna().sum()
        n_fin = sub["final_difficulty"].notna().sum()
        print(
            f"  Puzzle {pid}: "
            f"decisions={dec:4d}  propagations={prop:5d}  conflicts={conf:3d}"
            f"  |  initial={init_mean:.2f}±{init_std:.2f} (n={n_init})"
            f"  final={fin_mean:.2f}±{fin_std:.2f} (n={n_fin})"
        )


# ---------------------------------------------------------------------------
# Regression helpers
# ---------------------------------------------------------------------------


def compute_bt_ranks(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Fit Bradley-Terry model per rating type; return per-puzzle rank DataFrames.

    Returns a dict keyed by rating type (e.g. "initial_difficulty") whose
    values are DataFrames with columns:
      puzzle_id, bt_score, bt_rank, raw_mean, raw_rank
    """
    bt_dfs: dict[str, pd.DataFrame] = {}
    for rating_col in RATING_TYPES:
        valid = df[["participant_id", "puzzle_id", rating_col]].copy()
        valid[rating_col] = pd.to_numeric(valid[rating_col], errors="coerce")
        valid = valid[valid[rating_col] >= 1]

        W = build_win_matrix(valid, rating_col)
        theta = fit_bradley_terry(W)

        puzzle_ids = list(range(len(theta)))
        raw_means = (
            valid.groupby("puzzle_id")[rating_col]
            .mean()
            .reindex(puzzle_ids)
        )
        bt_df = pd.DataFrame({
            "puzzle_id": puzzle_ids,
            "bt_score": theta,
            "raw_mean": raw_means.values,
        })
        bt_df["bt_rank"] = bt_df["bt_score"].rank(method="min").astype(int)
        bt_df["raw_rank"] = bt_df["raw_mean"].rank(method="min").astype(int)
        bt_dfs[rating_col] = bt_df
    return bt_dfs


def spearman_rank_correlations(
    bt_dfs: dict[str, pd.DataFrame],
    sat_df: pd.DataFrame,
) -> dict[tuple[str, str], dict]:
    """Compute Spearman ρ between BT rank and each SAT metric rank (n=6 puzzles).

    Returns a dict keyed by (predictor, rating_type) with keys:
      rho, p_value, n, bt_ranks (array), sat_ranks (array)
    """
    results: dict[tuple[str, str], dict] = {}
    for rating_col, bt_df in bt_dfs.items():
        merged = bt_df.merge(sat_df[["puzzle_id"] + PREDICTORS], on="puzzle_id")
        for predictor in PREDICTORS:
            sub = merged[["puzzle_id", "bt_rank", predictor]].dropna()
            if len(sub) < 3:
                continue
            # Rank SAT metric explicitly so ties are handled consistently
            sat_ranks = sub[predictor].rank(method="average")
            rho, p = stats.spearmanr(sub["bt_rank"], sat_ranks)
            results[(predictor, rating_col)] = {
                "rho": rho,
                "p_value": p,
                "n": len(sub),
                "bt_ranks": sub["bt_rank"].values,
                "sat_ranks": sat_ranks.values,
                "puzzle_ids": sub["puzzle_id"].values,
            }
    return results


def print_spearman_results(
    results: dict[tuple[str, str], dict],
) -> tuple[str, str]:
    """Print Spearman rank correlation table; return key with highest |ρ|."""
    print("\n" + "=" * 70)
    print("SPEARMAN RANK CORRELATION  (BT difficulty rank vs SAT metric rank, n=6)")
    print("=" * 70)
    print(f"  {'Rating type':<22}  {'SAT metric':<14}  {'rho':>7}  {'p':>7}  {'sig'}")
    print(f"  {'-'*22}  {'-'*14}  {'-'*7}  {'-'*7}  {'-'*3}")

    best_key: tuple[str, str] | None = None
    best_abs_rho = -1.0
    for (predictor, rating), res in sorted(results.items()):
        rho = res["rho"]
        p = res["p_value"]
        sig = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else "ns"
        print(f"  {rating:<22}  {predictor:<14}  {rho:>+7.3f}  {p:>7.4f}  {sig}")
        if abs(rho) > best_abs_rho:
            best_abs_rho = abs(rho)
            best_key = (predictor, rating)

    if best_key:
        best_rho = results[best_key]["rho"]
        best_p = results[best_key]["p_value"]
        print(
            f"\n  Strongest association: {best_key[1]} ~ {best_key[0]}"
            f"  (ρ={best_rho:+.3f}, p={best_p:.4f})"
        )
        print(
            "  Note: with n=6 puzzles, |ρ| ≥ 0.886 is required for p < 0.05."
        )
    return best_key  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Plotting helpers
# ---------------------------------------------------------------------------


def _sig_label(p: float) -> str:
    return "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else "ns"


def plot_rank_scatter(
    bt_dfs: dict[str, pd.DataFrame],
    sat_df: pd.DataFrame,
    results: dict[tuple[str, str], dict],
    output_path: Path,
) -> None:
    """3×2 grid: BT difficulty rank vs SAT metric rank, one panel per combination.

    Rows: decisions, propagations, conflicts.
    Columns: initial_difficulty, final_difficulty.
    Each panel has 6 labelled points and a Spearman ρ annotation.

    Args:
        bt_dfs: Output of compute_bt_ranks().
        sat_df: SAT solver stats DataFrame.
        results: Output of spearman_rank_correlations().
        output_path: File path to save the figure.
    """
    n_cols = len(RATING_TYPES)
    fig, axes = plt.subplots(3, n_cols, figsize=(5 * n_cols, 12), squeeze=False)

    for row_idx, predictor in enumerate(PREDICTORS):
        for col_idx, rating in enumerate(RATING_TYPES):
            ax = axes[row_idx][col_idx]
            key = (predictor, rating)

            if key not in results:
                ax.text(0.5, 0.5, "Insufficient data", ha="center", va="center",
                        transform=ax.transAxes)
                continue

            res = results[key]
            bt_ranks = res["bt_ranks"]
            sat_ranks = res["sat_ranks"]
            puzzle_ids = res["puzzle_ids"]

            for bt_r, sat_r, pid in zip(bt_ranks, sat_ranks, puzzle_ids):
                ax.scatter(sat_r, bt_r, color=PUZZLE_COLORS[int(pid)], s=90, zorder=3)
                ax.annotate(
                    f"P{int(pid)}",
                    (sat_r, bt_r),
                    textcoords="offset points",
                    xytext=(6, 4),
                    fontsize=8,
                )

            # Perfect-correlation reference line
            ax.plot([1, 6], [1, 6], color="grey", linewidth=1, linestyle="--",
                    alpha=0.5, zorder=1)

            rho = res["rho"]
            p = res["p_value"]
            ax.text(
                0.03, 0.97, f"ρ={rho:+.3f}  p={p:.3f}  {_sig_label(p)}",
                transform=ax.transAxes, ha="left", va="top", fontsize=8,
                bbox=dict(boxstyle="round", facecolor="white", edgecolor="gray", alpha=0.8),
            )
            ax.set_xlabel(f"{predictor} rank", fontsize=9)
            ax.set_ylabel("BT difficulty rank", fontsize=9)
            ax.set_xticks(range(1, 7))
            ax.set_yticks(range(1, 7))
            ax.set_xlim(0.5, 6.5)
            ax.set_ylim(0.5, 6.5)
            ax.tick_params(labelsize=8)
            ax.set_aspect("equal")

    # Shared puzzle legend in bottom-right subplot
    handles = [
        plt.Line2D(
            [0], [0],
            marker="o", color="w",
            markerfacecolor=PUZZLE_COLORS[i],
            markersize=8, label=f"Puzzle {i}",
        )
        for i in range(6)
    ]
    axes[2][n_cols - 1].legend(handles=handles, title="Puzzle ID", fontsize=8,
                      title_fontsize=9, loc="upper left")

    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {output_path}")


def plot_per_puzzle_means(
    df: pd.DataFrame,
    output_path: Path,
) -> None:
    """Plot mean final difficulty vs SAT predictor per puzzle.

    3 subplots, one per predictor. Each shows final difficulty with
    error bars (±1 std) and per-puzzle labels.

    Args:
        df: Merged DataFrame.
        output_path: File path to save the figure.
    """
    # Compute per-puzzle means and stds
    grouped = (
        df.groupby("puzzle_id")[PREDICTORS + ["final_difficulty"]]
        .agg(["mean", "std"])
    )

    fig, axes = plt.subplots(1, 3, figsize=(16, 5), sharey=False)

    for ax, predictor in zip(axes, PREDICTORS):
        puzzle_ids = sorted(df["puzzle_id"].unique())
        x_vals = np.array(
            [grouped.loc[pid, (predictor, "mean")] for pid in puzzle_ids]
        )

        y_means = np.array(
            [grouped.loc[pid, ("final_difficulty", "mean")] for pid in puzzle_ids]
        )
        y_stds = np.array(
            [grouped.loc[pid, ("final_difficulty", "std")] for pid in puzzle_ids]
        )
        # Replace NaN stds (n=1 puzzles) with 0
        y_stds = np.nan_to_num(y_stds, nan=0.0)

        # Sort by SAT predictor for connected line
        sort_idx = np.argsort(x_vals)
        ax.errorbar(
            x_vals[sort_idx],
            y_means[sort_idx],
            yerr=y_stds[sort_idx],
            color=NEUTRAL_COLOR,
            marker="s",
            markersize=8,
            linewidth=1.5,
            capsize=5,
            zorder=3,
        )
        # Annotate puzzle IDs next to each point
        for i, pid in enumerate(np.array(puzzle_ids)[sort_idx]):
            ax.annotate(
                f"P{pid}",
                (x_vals[sort_idx][i], y_means[sort_idx][i]),
                textcoords="offset points",
                xytext=(5, 4),
                fontsize=8,
                color="#222222",
            )

        ax.set_xlabel(predictor, fontsize=10)
        ax.set_ylabel("Mean difficulty rating (1–5)", fontsize=10)
        ax.set_ylim(0.5, 5.5)
        ax.yaxis.set_major_locator(plt.MultipleLocator(1))

    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the full analysis pipeline."""
    print("=" * 70)
    print("NONOGRAM DIFFICULTY — SPEARMAN RANK CORRELATION ANALYSIS")
    print("=" * 70)

    apply_style()
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)

    print("\n[1/4] Loading participant ratings from logs...")
    ratings_df = load_all_ratings(LOG_DIR)

    print("\n[2/4] Loading SAT solver stats...")
    sat_df = load_sat_stats(STATS_CSV)
    print(sat_df[["puzzle_id"] + PREDICTORS].to_string(index=False))

    df = merge_data(ratings_df, sat_df)
    print_summary_table(df)

    print("\n[3/4] Fitting Bradley-Terry model and running Spearman tests...")
    bt_dfs = compute_bt_ranks(ratings_df)
    spearman_results = spearman_rank_correlations(bt_dfs, sat_df)
    print_spearman_results(spearman_results)

    print("\n[4/4] Generating figures...")
    plot_rank_scatter(bt_dfs, sat_df, spearman_results,
                      FIGURE_DIR / "spearman_rank_scatter.png")
    plot_per_puzzle_means(df, FIGURE_DIR / "regression_per_puzzle_means.png")

    print("\n" + "=" * 70)
    print("Analysis complete.")
    print("=" * 70)


if __name__ == "__main__":
    main()
