import os
import sys

import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(__file__))
from plot_style import ACCENT_COLOR, ACCENT_COLOR_2, NEUTRAL_COLOR, apply_style  # noqa: E402

apply_style()

OUTPUT_DIR = os.path.join("analyze-data", "out_features", "figures", "solver_stats_diagnostics")
STATS_OUT_DIR = os.path.join("analyze-data", "out_features")

SAT_METRICS = ["decisions", "propagations", "conflicts"]


def select_six(df: pd.DataFrame) -> pd.DataFrame:
    """Select six puzzles from the 1000 based on defining characteristics."""

    # Drop the outliers in number of conflicts
    filtered_df = df[df['conflicts'] < df['conflicts'].quantile(0.95)]

    # Pick the puzzles with the lowest, median, and highest number of conflicts
    lowest_conflicts = filtered_df.nsmallest(2, 'conflicts')
    median_conflicts = filtered_df.iloc[(filtered_df['conflicts'] - filtered_df['conflicts'].median()).abs().argsort()[:2]]
    highest_conflicts = filtered_df.nlargest(2, 'conflicts')
    selected = pd.concat([lowest_conflicts, median_conflicts, highest_conflicts])
    return selected


def plot_conflicts_distribution(
    pool_df: pd.DataFrame, selected_df: pd.DataFrame, fig_out_dir: str,
) -> None:
    """Distribution of SAT-solver conflicts across the full 1000-puzzle pool,
    with a KDE overlay and the 6 already-selected study puzzles marked.

    Conflicts is a non-negative integer count, so unit-width bins (one bin
    per integer value, via discrete=True) are the logical binning choice for
    count data -- matches this repo's other count-variable histograms (e.g.
    plot_gap_distribution.py's pause-gap histograms).
    """
    selected = selected_df.reset_index().rename(columns={"index": "experiment_id"})

    fig, ax = plt.subplots(figsize=(9, 5.5), dpi=160)
    # Wider (binwidth=2) bins than one-per-integer: with conflicts ranging up
    # to ~45 the unit-width bins produced a long run of barely-visible single
    # counts in the tail. Matches the white-edged NEUTRAL_COLOR bar look used
    # by expertise_composite_distribution.png.
    sns.histplot(pool_df["conflicts"], binwidth=2, kde=True, color=NEUTRAL_COLOR,
                 alpha=1, edgecolor="white", linewidth=0.8, ax=ax)
    # line_kws={"color": ...} is silently ignored by this seaborn version (the
    # KDE line inherits `color` above instead) -- set it directly on the line.
    for line in ax.get_lines():
        line.set_color(ACCENT_COLOR)

    # Group selected puzzles sharing the same conflicts value so their marker
    # labels don't overlap (e.g. two puzzles both landed at conflicts=0).
    ymax = ax.get_ylim()[1]
    for conflicts_val, group in selected.groupby("conflicts"):
        ax.axvline(conflicts_val, color=ACCENT_COLOR_2, linestyle="--", linewidth=1.2, zorder=3)
        puzzles = ", ".join(f"P{int(eid)}" for eid in sorted(group["experiment_id"]))
        label = f"{puzzles} ({int(conflicts_val)})"
        ax.text(conflicts_val, ymax * 0.97, label, rotation=90, fontsize=10,
                 va="top", ha="right", color=ACCENT_COLOR_2)

    ax.set_xlabel("Number of Conflicts", fontsize=12)
    ax.set_ylabel("Frequency", fontsize=12)
    ax.tick_params(axis="both", labelsize=11)
    fig.tight_layout()
    fig_path = os.path.join(fig_out_dir, "solver_stats_conflicts_distribution.png")
    fig.savefig(fig_path, bbox_inches="tight")
    print(f"Saved: {fig_path}")


def plot_selection_representativeness(
    pool_df: pd.DataFrame, selected_df: pd.DataFrame, stats_out_dir: str, fig_out_dir: str,
) -> pd.DataFrame:
    """Where do the 6 already-selected puzzles fall within the full ~1000-
    puzzle pool, across all three SAT metrics -- not just `conflicts`, the
    only metric select_six() stratified on. Purely descriptive: does not
    touch the frozen, commented-out selection logic above. Quantifies a
    limitation for the paper -- puzzles matched on `conflicts` can still
    diverge substantially on `decisions`/`propagations` (e.g. the two
    "median-conflicts" puzzles here differ by ~60% on `decisions`), and the
    top-5% conflicts band was excluded from selection entirely, so the
    "highest" selected puzzle is not actually near the hardest in the pool by
    that metric. Saves headlessly (no plt.show()), unlike the rest of this
    script, so it can join the batch pipeline."""
    selected = selected_df.reset_index().rename(columns={"index": "experiment_id"})

    rows = []
    for _, row in selected.iterrows():
        rec = {"experiment_id": int(row["experiment_id"]), "pool_puzzle_id": int(row["puzzle_id"])}
        for metric in SAT_METRICS:
            val = row[metric]
            percentile = 100.0 * (pool_df[metric] < val).mean()
            rec[f"{metric}_value"] = val
            rec[f"{metric}_percentile"] = percentile
        rows.append(rec)
    result = pd.DataFrame(rows).sort_values("experiment_id")

    stats_path = os.path.join(stats_out_dir, "stats_puzzle_selection_representativeness.csv")
    result.to_csv(stats_path, index=False)
    print(f"Saved: {stats_path}")

    fig, axes = plt.subplots(1, len(SAT_METRICS), figsize=(5 * len(SAT_METRICS), 4.5))
    for ax, metric in zip(axes, SAT_METRICS):
        ax.hist(pool_df[metric], bins=40, color=NEUTRAL_COLOR, alpha=0.6, edgecolor="white")
        ymax = ax.get_ylim()[1]
        for _, r in result.iterrows():
            ax.axvline(r[f"{metric}_value"], color=ACCENT_COLOR_2, linestyle="--", linewidth=1)
            ax.text(r[f"{metric}_value"], ymax * 0.97, f"P{int(r['experiment_id'])}",
                    rotation=90, fontsize=7, va="top", ha="right")
        ax.set_xlabel(metric)
        ax.set_ylabel("Count (full pool, n=1000)")
        ax.set_title(metric)
    fig.suptitle("Selected 6 puzzles vs. full solver-stats pool, by SAT metric")
    fig.tight_layout()
    fig_path = os.path.join(fig_out_dir, "puzzle_selection_representativeness.png")
    fig.savefig(fig_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {fig_path}")

    return result


if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Load solver statistics from CSV
    df = pd.read_csv("nonogram_solver_stats.csv")
    selected_df = pd.read_csv("selected_six_nonogram_stats.csv", index_col=0)

    # Display basic statistics
    print("Solver Statistics Summary:")
    print(df.describe())

    # Analyze correlations between different metrics
    correlation_matrix = df.drop(columns=['puzzle_id']).corr()
    print("\nCorrelation Matrix:")
    print(correlation_matrix)

    # Display the correlation matrix in a heatmap
    fig = plt.figure(figsize=(10, 8))
    ax = sns.heatmap(correlation_matrix, annot=True, fmt=".2f", cmap="RdBu_r")
    ax.grid(False)  # apply_style's major grid would bisect cells at their centers
    fig.savefig(os.path.join(OUTPUT_DIR, "solver_stats_correlation_matrix.png"), bbox_inches="tight")
    plt.show()

    # Distribution of conflicts across the full pool, with a KDE fit and the
    # already-selected six study puzzles marked.
    plot_conflicts_distribution(df, selected_df, OUTPUT_DIR)
    plt.show()

    # Representativeness of the already-selected 6 puzzles vs. the full pool,
    # across all 3 SAT metrics (not just the `conflicts` selection stratified
    # on). Headless (no plt.show()) -- reads the already-finalized
    # selected_six_nonogram_stats.csv, doesn't touch select_six() above.
    plot_selection_representativeness(df, selected_df, STATS_OUT_DIR, OUTPUT_DIR)

    # Select six representative puzzles

    # CAREFUL: The following code is commented out to prevent overwriting existing files.
    
    # selected_puzzles_df = select_six(df)
    # selected_puzzles_df = selected_puzzles_df.reset_index(drop=True)
    # print("\nSelected Six Representative Puzzles:")
    # print(selected_puzzles_df)
    # selected_puzzles_df.to_csv("selected_six_nonogram_stats.csv", index=True)  # The index will be the id used in the nonogram file

    # import json
    # selected_ids = selected_puzzles_df['puzzle_id'].tolist()
    # puzzles = json.load(open('unique_solution_nonograms_1000.json', 'r'))
    # print(len(puzzles))
    # selected_puzzles = [p for p in puzzles if p['id'] in selected_ids]
    # print(len(selected_puzzles))
    # # overwrite ids to be 0-5
    # for i in range(len(selected_puzzles)):
    #     selected_puzzles[i]['id'] = i
    # with open('nonograms_6.json', 'w') as f:
    #     json.dump(selected_puzzles, f, indent=4)