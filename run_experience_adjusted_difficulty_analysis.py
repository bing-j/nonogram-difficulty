"""
Experience-adjusted puzzle difficulty analysis.

Run from the repository root:
    python3 run_experience_adjusted_difficulty_analysis.py

This script is additive. It uses outputs/clean_participant_puzzle_data.csv,
estimates puzzle difficulty adjusted for participant experience and order, and
writes new outputs without modifying raw data.
"""

from __future__ import annotations

import itertools
import math
import os
import runpy
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/nonogram-difficulty-matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/private/tmp/nonogram-difficulty-cache")
os.environ.setdefault("MPLBACKEND", "Agg")
import matplotlib.pyplot as plt


REPO_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = REPO_ROOT / "outputs"
CLEAN_DATA = OUTPUT_DIR / "clean_participant_puzzle_data.csv"
ORIGINAL_PIPELINE = REPO_ROOT / "run_sat_human_difficulty_analysis.py"
BASE_REPORT = OUTPUT_DIR / "sat_vs_human_difficulty_report.md"
REPORT_BACKUP = OUTPUT_DIR / "sat_vs_human_difficulty_report_before_experience_adjusted_difficulty.md"
REPORT_WITH_ADJUSTED = OUTPUT_DIR / "sat_vs_human_difficulty_report_with_experience_adjusted_difficulty.md"

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


def ensure_inputs() -> None:
    # The adjusted analysis depends on the existing cleaned analysis dataset.
    if not CLEAN_DATA.exists():
        runpy.run_path(str(ORIGINAL_PIPELINE), run_name="__main__")


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


def prepare_data(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["experience_level"] = pd.to_numeric(df["experience_level"], errors="coerce")
    exp_mean = df["experience_level"].mean()
    exp_sd = df["experience_level"].std(ddof=0)
    df["z_experience"] = (df["experience_level"] - exp_mean) / exp_sd
    return df


def design_row(puzzle_id: int, order: int, columns: list[str]) -> np.ndarray:
    values = {column: 0.0 for column in columns}
    values["intercept"] = 1.0
    values["z_experience"] = 0.0
    puzzle_column = f"puzzle_{puzzle_id}"
    order_column = f"order_{order}"
    if puzzle_column in values:
        values[puzzle_column] = 1.0
    if order_column in values:
        values[order_column] = 1.0
    return np.array([values[column] for column in columns], dtype=float)


def fit_adjusted_difficulty_model(df: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    model_df = df[["participant_id", "puzzle_id", "order", "final_rating", "z_experience"]].dropna().copy()

    # Model: final_rating ~ C(puzzle_id) + z_experience + C(order)
    # Puzzle 0 and order 1 are reference categories.
    puzzle_dummies = pd.get_dummies(model_df["puzzle_id"].astype(int), prefix="puzzle", drop_first=True)
    order_dummies = pd.get_dummies(model_df["order"].astype(int), prefix="order", drop_first=True)
    x_df = pd.concat(
        [
            pd.Series(1.0, index=model_df.index, name="intercept"),
            puzzle_dummies.astype(float),
            model_df[["z_experience"]].astype(float),
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
        # Marginal prediction at average experience (z=0) and balanced order:
        # average of predicted ratings at order 1, 2, and 3.
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
                    "Predicted from final_rating ~ C(puzzle_id) + z_experience + C(order), "
                    "holding z_experience=0 and averaging equally over order 1, 2, and 3; "
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


def save_raw_vs_adjusted_comparison(adjusted_correlations: pd.DataFrame) -> pd.DataFrame:
    raw_path = OUTPUT_DIR / "correlation_mean_final_rating_vs_sat.csv"
    if not raw_path.exists():
        runpy.run_path(str(ORIGINAL_PIPELINE), run_name="__main__")
    raw = pd.read_csv(raw_path)

    rows = []
    for sat_variable in SAT_VARIABLES:
        raw_sub = raw[raw["sat_variable"] == sat_variable].set_index("method")
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
        ax.scatter(adjusted_df[sat_variable], adjusted_df["adjusted_difficulty"], color="#245c7c", s=55)
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
        ax.set_title(
            f"Adjusted difficulty vs {x_label}\n"
            f"Spearman rho = {rho:.3f}; n = 6 puzzles; exploratory"
        )
        ax.grid(True, alpha=0.25)
        fig.tight_layout()
        fig.savefig(figure_dir / filename, bbox_inches="tight")
        plt.close(fig)


def format_float(value: float, digits: int = 3) -> str:
    if pd.isna(value):
        return "NA"
    return f"{value:.{digits}f}"


def update_report(adjusted_df: pd.DataFrame, adjusted_correlations: pd.DataFrame, comparison: pd.DataFrame) -> None:
    if not BASE_REPORT.exists():
        runpy.run_path(str(ORIGINAL_PIPELINE), run_name="__main__")
    REPORT_BACKUP.write_text(BASE_REPORT.read_text(encoding="utf-8"), encoding="utf-8")

    spearman = adjusted_correlations[adjusted_correlations["method"] == "spearman"].copy()
    spearman["abs_correlation"] = spearman["correlation"].abs()
    strongest = spearman.sort_values("abs_correlation", ascending=False).iloc[0]

    comparison_spearman = comparison.copy()
    comparison_spearman["abs_change"] = comparison_spearman["change_in_spearman"].abs()
    largest_change = comparison_spearman.sort_values("abs_change", ascending=False).iloc[0]

    ranking = adjusted_df.sort_values("adjusted_difficulty")[["puzzle_id", "adjusted_difficulty"]]
    ranking_lines = "\n".join(
        f"- Puzzle {int(row.puzzle_id)}: adjusted difficulty = {format_float(row.adjusted_difficulty)}"
        for row in ranking.itertuples(index=False)
    )

    section = f"""

## 12. Experience-Adjusted Puzzle Difficulty

Raw ratings may not mean the same thing for participants with different Nonogram experience. To address this, we estimated puzzle difficulty after controlling for participant experience and puzzle order.

The adjustment model was:

`final_rating ~ C(puzzle_id) + z_experience + C(order)`

The model used participant-clustered standard errors. It does not test SAT statistics directly; it estimates adjusted human difficulty for each puzzle. Adjusted difficulty was extracted by predicting each puzzle's final rating at average experience (`z_experience = 0`) and averaging equally over order positions 1, 2, and 3.

Adjusted easiest-to-hardest puzzle order:

{ranking_lines}

The strongest Spearman correlation between adjusted difficulty and SAT statistics was for `{strongest.sat_variable}`, rho = {format_float(strongest.correlation)}. The largest change from the raw `mean_final_rating` Spearman result was for `{largest_change.sat_variable}`, changing by {format_float(largest_change.change_in_spearman)}.

Overall, adjusting for experience and order does not materially change the original conclusion. SAT statistics still show weak and exploratory alignment with human-evaluated difficulty, and no SAT statistic clearly reproduces the human easiest-to-hardest ordering.

Limitations:

- This is still based on only 6 puzzles.
- Adjustment can control for average experience differences, but it cannot solve the small puzzle-level sample size.
- Experience is self-reported.
- Ratings may still be affected by individual rating-scale behavior and by which other puzzles each participant saw.
- Results remain exploratory.
"""

    base_text = BASE_REPORT.read_text(encoding="utf-8").rstrip()
    if "## 12. Experience-Adjusted Puzzle Difficulty" not in base_text:
        updated = base_text + section
        BASE_REPORT.write_text(updated + "\n", encoding="utf-8")
    else:
        updated = base_text
    REPORT_WITH_ADJUSTED.write_text(updated + "\n", encoding="utf-8")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ensure_inputs()

    df = pd.read_csv(CLEAN_DATA)
    df = prepare_data(df)
    adjusted_df = build_adjusted_puzzle_difficulty(df)
    adjusted_correlations = save_adjusted_correlations(adjusted_df)
    comparison = save_raw_vs_adjusted_comparison(adjusted_correlations)
    save_adjusted_plots(adjusted_df, adjusted_correlations)
    update_report(adjusted_df, adjusted_correlations, comparison)

    print("Experience-adjusted difficulty analysis complete.")
    print(f"Adjusted puzzle difficulty rows: {len(adjusted_df)}")
    print(f"Correlation result rows: {len(adjusted_correlations)}")
    print(f"Report backup: {REPORT_BACKUP}")
    print(f"Updated report copy: {REPORT_WITH_ADJUSTED}")


if __name__ == "__main__":
    main()
