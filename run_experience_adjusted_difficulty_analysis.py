"""
Expertise-adjusted puzzle difficulty analysis.

Run from the repository root:
    python3 run_experience_adjusted_difficulty_analysis.py

Reads analyze-data/out_features/behavioral_features.csv (participant-puzzle
ratings + the continuous expertise_composite score -- see analyze-data/
expertise.py) merged with selected_six_nonogram_stats.csv, estimates puzzle
difficulty adjusted for participant expertise and order, and writes new
outputs without modifying raw data.
"""

from __future__ import annotations

import itertools
import math
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/nonogram-difficulty-matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/private/tmp/nonogram-difficulty-cache")
os.environ.setdefault("MPLBACKEND", "Agg")
import matplotlib.pyplot as plt

# Single-series marks/lines that aren't doing identity-coding work (matches
# analyze-data/plot_style.py's NEUTRAL_COLOR -- kept as a local constant here
# since this script otherwise has no dependency on analyze-data/).
NEUTRAL_COLOR = "#4D4D4D"

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 10,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.color": "#cccccc",
    "grid.linewidth": 0.6,
    "grid.linestyle": "-",
    "axes.axisbelow": True,
})


REPO_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = REPO_ROOT / "outputs"
FEATURES_CSV = REPO_ROOT / "analyze-data" / "out_features" / "behavioral_features.csv"
SOLVER_CSV = REPO_ROOT / "selected_six_nonogram_stats.csv"

SAT_VARIABLES = [
    "conflicts",
    "decisions",
    "propagations",
    "sat_time_to_solve",
    "log_conflicts",
    "log_decisions",
    "log_propagations",
    "log_sat_time",
]


def load_solver_stats() -> pd.DataFrame:
    """Load SAT solver metrics, using the unnamed row index as puzzle_id."""
    df = pd.read_csv(SOLVER_CSV, index_col=0)
    if "puzzle_id" in df.columns:
        df = df.drop(columns=["puzzle_id"])
    df.index.name = "puzzle_id"
    df = df.reset_index()
    df["puzzle_id"] = df["puzzle_id"].astype(int)
    df = df.rename(columns={"solving_time": "sat_time_to_solve"})
    df["log_conflicts"] = np.log1p(df["conflicts"])
    df["log_decisions"] = np.log1p(df["decisions"])
    df["log_propagations"] = np.log1p(df["propagations"])
    df["log_sat_time"] = np.log1p(df["sat_time_to_solve"])
    return df[["puzzle_id"] + SAT_VARIABLES]


def load_working_frame() -> pd.DataFrame:
    """Build the participant-puzzle working frame from analyze-data's
    behavioral_features.csv merged with SAT solver stats.

    Replaces the deleted analyze-data/build_clean_participant_puzzle_data.py
    generator, which used to produce outputs/clean_participant_puzzle_data.csv.
    """
    if not FEATURES_CSV.exists():
        raise FileNotFoundError(
            f"{FEATURES_CSV} not found. Run "
            "analyze-data/extract_behavioral_features.py first."
        )
    df = pd.read_csv(FEATURES_CSV)
    df = df.rename(columns={"final_difficulty": "final_rating"})
    df["expertise_composite"] = pd.to_numeric(df["expertise_composite"], errors="coerce")
    df["final_rating"] = pd.to_numeric(df["final_rating"], errors="coerce")
    solver = load_solver_stats()
    return df.merge(solver, on="puzzle_id", how="left")


def average_ranks(values: list[float]) -> list[float]:
    sorted_pairs = sorted((value, index) for index, value in enumerate(values))
    ranks = [0.0] * len(values)
    position = 0
    while position < len(sorted_pairs):
        end = position + 1
        while end < len(sorted_pairs) and sorted_pairs[end][0] == sorted_pairs[position][0]:
            end += 1
        average_rank = (position + 1 + end) / 2
        for _, original_index in sorted_pairs[position:end]:
            ranks[original_index] = average_rank
        position = end
    return ranks


def pearson_correlation(x_values: list[float], y_values: list[float]) -> float:
    if len(x_values) < 2:
        return math.nan
    x_mean = sum(x_values) / len(x_values)
    y_mean = sum(y_values) / len(y_values)
    x_diffs = [value - x_mean for value in x_values]
    y_diffs = [value - y_mean for value in y_values]
    denominator = math.sqrt(sum(v * v for v in x_diffs) * sum(v * v for v in y_diffs))
    if denominator == 0:
        return math.nan
    return sum(x * y for x, y in zip(x_diffs, y_diffs)) / denominator


def spearman_correlation(x_values: list[float], y_values: list[float]) -> float:
    return pearson_correlation(average_ranks(x_values), average_ranks(y_values))


def kendall_tau_b(x_values: list[float], y_values: list[float]) -> float:
    concordant = 0
    discordant = 0
    ties_x = 0
    ties_y = 0
    for i, j in itertools.combinations(range(len(x_values)), 2):
        x_diff = (x_values[i] > x_values[j]) - (x_values[i] < x_values[j])
        y_diff = (y_values[i] > y_values[j]) - (y_values[i] < y_values[j])
        if x_diff == 0 and y_diff == 0:
            continue
        if x_diff == 0:
            ties_x += 1
        elif y_diff == 0:
            ties_y += 1
        elif x_diff == y_diff:
            concordant += 1
        else:
            discordant += 1
    denominator = math.sqrt((concordant + discordant + ties_x) * (concordant + discordant + ties_y))
    if denominator == 0:
        return math.nan
    return (concordant - discordant) / denominator


def exact_permutation_p_value(
    x_values: list[float],
    y_values: list[float],
    correlation_func: Any,
) -> tuple[float, float]:
    observed = correlation_func(x_values, y_values)
    if math.isnan(observed):
        return observed, math.nan
    total = 0
    at_least_as_extreme = 0
    for permuted_y in itertools.permutations(y_values):
        permuted = correlation_func(x_values, list(permuted_y))
        if math.isnan(permuted):
            continue
        total += 1
        if abs(permuted) >= abs(observed) - 1e-12:
            at_least_as_extreme += 1
    return observed, at_least_as_extreme / total if total else math.nan


def design_row(puzzle_id: int, order: int, columns: list[str]) -> np.ndarray:
    values = {column: 0.0 for column in columns}
    values["intercept"] = 1.0
    values["expertise_composite"] = 0.0
    puzzle_column = f"puzzle_{puzzle_id}"
    order_column = f"order_{order}"
    if puzzle_column in values:
        values[puzzle_column] = 1.0
    if order_column in values:
        values[order_column] = 1.0
    return np.array([values[column] for column in columns], dtype=float)


def fit_adjusted_difficulty_model(df: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    model_df = df[["participant_id", "puzzle_id", "order", "final_rating", "expertise_composite"]].dropna().copy()

    # Model: final_rating ~ C(puzzle_id) + expertise_composite + C(order)
    # Puzzle 0 and order 1 are reference categories.
    puzzle_dummies = pd.get_dummies(model_df["puzzle_id"].astype(int), prefix="puzzle", drop_first=True)
    order_dummies = pd.get_dummies(model_df["order"].astype(int), prefix="order", drop_first=True)
    x_df = pd.concat(
        [
            pd.Series(1.0, index=model_df.index, name="intercept"),
            puzzle_dummies.astype(float),
            model_df[["expertise_composite"]].astype(float),
            order_dummies.astype(float),
        ],
        axis=1,
    )
    y = model_df["final_rating"].astype(float).to_numpy()
    x = x_df.to_numpy(dtype=float)
    n_obs, n_terms = x.shape
    n_participants = model_df["participant_id"].nunique()

    xtx_inv = np.linalg.pinv(x.T @ x)
    beta = xtx_inv @ x.T @ y
    residuals = y - x @ beta

    # Participant-clustered covariance for adjusted predictions.
    meat = np.zeros((n_terms, n_terms))
    for _, group_index in model_df.groupby("participant_id").groups.items():
        positions = model_df.index.get_indexer(group_index)
        x_g = x[positions, :]
        u_g = residuals[positions].reshape(-1, 1)
        meat += x_g.T @ u_g @ u_g.T @ x_g
    covariance = xtx_inv @ meat @ xtx_inv
    if n_participants > 1 and n_obs > n_terms:
        covariance *= (n_participants / (n_participants - 1)) * ((n_obs - 1) / (n_obs - n_terms))

    return model_df.assign(_row_id=np.arange(len(model_df))), beta, covariance, list(x_df.columns)


def build_adjusted_puzzle_difficulty(df: pd.DataFrame) -> pd.DataFrame:
    model_df, beta, covariance, columns = fit_adjusted_difficulty_model(df)
    raw = (
        df.groupby("puzzle_id")
        .agg(
            raw_mean_final_rating=("final_rating", "mean"),
            n_final_ratings=("final_rating", "count"),
            n_participants=("participant_id", "nunique"),
        )
        .reset_index()
    )
    sat_stats = df.groupby("puzzle_id")[SAT_VARIABLES].first().reset_index()

    rows = []
    for puzzle_id in sorted(df["puzzle_id"].dropna().astype(int).unique()):
        # Marginal prediction at average expertise (composite=0) and balanced
        # order: average of predicted ratings at order 1, 2, and 3.
        prediction_rows = np.vstack([design_row(puzzle_id, order, columns) for order in [1, 2, 3]])
        contrast = prediction_rows.mean(axis=0)
        adjusted = float(contrast @ beta)
        adjusted_se = float(math.sqrt(max(contrast @ covariance @ contrast.T, 0)))
        rows.append(
            {
                "puzzle_id": puzzle_id,
                "adjusted_difficulty": adjusted,
                "adjusted_standard_error": adjusted_se,
                "notes": (
                    "Predicted from final_rating ~ C(puzzle_id) + expertise_composite + C(order), "
                    "holding expertise_composite=0 and averaging equally over order 1, 2, and 3; "
                    "participant-clustered covariance used for SE."
                ),
            }
        )

    adjusted_df = pd.DataFrame(rows).merge(raw, on="puzzle_id", how="left", validate="one_to_one")
    adjusted_df = adjusted_df.merge(sat_stats, on="puzzle_id", how="left", validate="one_to_one")
    adjusted_df = adjusted_df[
        [
            "puzzle_id",
            "raw_mean_final_rating",
            "adjusted_difficulty",
            "adjusted_standard_error",
            "n_final_ratings",
            "n_participants",
            "notes",
            *SAT_VARIABLES,
        ]
    ]
    adjusted_df.to_csv(OUTPUT_DIR / "experience_adjusted_puzzle_difficulty.csv", index=False)
    return adjusted_df


def save_adjusted_correlations(adjusted_df: pd.DataFrame) -> pd.DataFrame:
    methods = [
        ("spearman", spearman_correlation),
        ("kendall", kendall_tau_b),
        ("pearson", pearson_correlation),
    ]
    rows = []
    for sat_variable in SAT_VARIABLES:
        pair_df = adjusted_df[["adjusted_difficulty", sat_variable]].dropna()
        x_values = pair_df["adjusted_difficulty"].astype(float).tolist()
        y_values = pair_df[sat_variable].astype(float).tolist()
        for method, func in methods:
            if len(pair_df) < 2:
                correlation = math.nan
                p_value = math.nan
            else:
                correlation, p_value = exact_permutation_p_value(x_values, y_values, func)
            rows.append(
                {
                    "human_variable": "adjusted_difficulty",
                    "sat_variable": sat_variable,
                    "method": method,
                    "correlation": correlation,
                    "p_value": p_value,
                    "n_puzzles": len(pair_df),
                    "warning": "Exploratory: SAT variation is still only 6 puzzle-level observations.",
                }
            )
    results = pd.DataFrame(rows)
    results.to_csv(OUTPUT_DIR / "experience_adjusted_difficulty_sat_correlations.csv", index=False)
    return results


def save_raw_correlations(df: pd.DataFrame) -> pd.DataFrame:
    """Raw (unadjusted) mean_final_rating vs SAT correlations, for comparison
    against the expertise-adjusted correlations. Self-contained -- no longer
    depends on the deleted analyze-data/build_clean_participant_puzzle_data.py."""
    raw_means = df.groupby("puzzle_id").agg(
        mean_final_rating=("final_rating", "mean"),
    ).reset_index()
    sat_stats = df.groupby("puzzle_id")[SAT_VARIABLES].first().reset_index()
    merged = raw_means.merge(sat_stats, on="puzzle_id")

    methods = [
        ("spearman", spearman_correlation),
        ("kendall", kendall_tau_b),
        ("pearson", pearson_correlation),
    ]
    rows = []
    for sat_variable in SAT_VARIABLES:
        pair_df = merged[["mean_final_rating", sat_variable]].dropna()
        x_values = pair_df["mean_final_rating"].astype(float).tolist()
        y_values = pair_df[sat_variable].astype(float).tolist()
        for method, func in methods:
            if len(pair_df) < 2:
                correlation = math.nan
                p_value = math.nan
            else:
                correlation, p_value = exact_permutation_p_value(x_values, y_values, func)
            rows.append(
                {
                    "human_variable": "mean_final_rating",
                    "sat_variable": sat_variable,
                    "method": method,
                    "correlation": correlation,
                    "p_value": p_value,
                    "n_puzzles": len(pair_df),
                }
            )
    results = pd.DataFrame(rows)
    results.to_csv(OUTPUT_DIR / "correlation_mean_final_rating_vs_sat.csv", index=False)
    return results


def save_raw_vs_adjusted_comparison(raw_correlations: pd.DataFrame, adjusted_correlations: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for sat_variable in SAT_VARIABLES:
        raw_sub = raw_correlations[raw_correlations["sat_variable"] == sat_variable].set_index("method")
        adj_sub = adjusted_correlations[adjusted_correlations["sat_variable"] == sat_variable].set_index("method")
        rows.append(
            {
                "sat_variable": sat_variable,
                "raw_spearman": raw_sub.loc["spearman", "correlation"],
                "adjusted_spearman": adj_sub.loc["spearman", "correlation"],
                "change_in_spearman": adj_sub.loc["spearman", "correlation"] - raw_sub.loc["spearman", "correlation"],
                "raw_kendall": raw_sub.loc["kendall", "correlation"],
                "adjusted_kendall": adj_sub.loc["kendall", "correlation"],
                "raw_pearson": raw_sub.loc["pearson", "correlation"],
                "adjusted_pearson": adj_sub.loc["pearson", "correlation"],
            }
        )
    comparison = pd.DataFrame(rows)
    comparison.to_csv(OUTPUT_DIR / "raw_vs_experience_adjusted_correlation_comparison.csv", index=False)
    return comparison


def save_adjusted_plots(adjusted_df: pd.DataFrame, adjusted_correlations: pd.DataFrame) -> None:
    figure_dir = OUTPUT_DIR / "figures" / "experience_adjusted_difficulty"
    figure_dir.mkdir(parents=True, exist_ok=True)
    plot_specs = [
        ("conflicts", "SAT conflicts", "adjusted_difficulty_vs_conflicts.png"),
        ("decisions", "SAT decisions", "adjusted_difficulty_vs_decisions.png"),
        ("propagations", "SAT propagations", "adjusted_difficulty_vs_propagations.png"),
        ("sat_time_to_solve", "SAT time to solve (ms)", "adjusted_difficulty_vs_sat_time.png"),
        ("log_conflicts", "log(1 + SAT conflicts)", "adjusted_difficulty_vs_log_conflicts.png"),
        ("log_decisions", "log(1 + SAT decisions)", "adjusted_difficulty_vs_log_decisions.png"),
        ("log_propagations", "log(1 + SAT propagations)", "adjusted_difficulty_vs_log_propagations.png"),
    ]
    for sat_variable, x_label, filename in plot_specs:
        rho = adjusted_correlations[
            (adjusted_correlations["sat_variable"] == sat_variable)
            & (adjusted_correlations["method"] == "spearman")
        ]["correlation"].iloc[0]
        fig, ax = plt.subplots(figsize=(7, 5), dpi=160)
        ax.scatter(adjusted_df[sat_variable], adjusted_df["adjusted_difficulty"], color=NEUTRAL_COLOR, s=55)
        for row in adjusted_df.itertuples(index=False):
            ax.annotate(
                str(int(row.puzzle_id)),
                (getattr(row, sat_variable), row.adjusted_difficulty),
                textcoords="offset points",
                xytext=(6, 5),
                fontsize=9,
            )
        ax.set_xlabel(x_label)
        ax.set_ylabel("Experience-adjusted human difficulty")
        ax.text(
            0.97, 0.03, f"Spearman rho = {rho:.3f}\nn = 6 puzzles; exploratory",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=8,
            bbox=dict(boxstyle="round", facecolor="white", edgecolor="gray", alpha=0.8),
        )
        fig.tight_layout()
        fig.savefig(figure_dir / filename, bbox_inches="tight")
        plt.close(fig)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df = load_working_frame()
    adjusted_df = build_adjusted_puzzle_difficulty(df)
    adjusted_correlations = save_adjusted_correlations(adjusted_df)
    raw_correlations = save_raw_correlations(df)
    comparison = save_raw_vs_adjusted_comparison(raw_correlations, adjusted_correlations)
    save_adjusted_plots(adjusted_df, adjusted_correlations)

    spearman = adjusted_correlations[adjusted_correlations["method"] == "spearman"].copy()
    spearman["abs_correlation"] = spearman["correlation"].abs()
    strongest = spearman.sort_values("abs_correlation", ascending=False).iloc[0]

    print("Expertise-adjusted difficulty analysis complete.")
    print(f"Adjusted puzzle difficulty rows: {len(adjusted_df)}")
    print(f"Correlation result rows: {len(adjusted_correlations)}")
    print(
        f"Strongest adjusted-difficulty vs SAT correlation: {strongest.sat_variable} "
        f"(rho={strongest.correlation:.3f})"
    )


if __name__ == "__main__":
    main()
