"""
Experience interaction analysis for SAT-vs-human Nonogram difficulty.

Run from the repository root:
    python3 run_experience_interaction_analysis.py

This script is additive. It uses the existing cleaned participant-puzzle
dataset if available, runs the original pipeline only if needed, and writes
new experience-focused outputs under outputs/.
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
REPORT_BACKUP = OUTPUT_DIR / "sat_vs_human_difficulty_report_before_experience_interaction.md"
REPORT_WITH_EXPERIENCE = OUTPUT_DIR / "sat_vs_human_difficulty_report_with_experience_interaction.md"

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

Z_SAT_VARIABLES = {
    "conflicts": "z_conflicts",
    "decisions": "z_decisions",
    "propagations": "z_propagations",
    "sat_time_to_solve": "z_sat_time_to_solve",
    "log_conflicts": "z_log_conflicts",
    "log_decisions": "z_log_decisions",
    "log_propagations": "z_log_propagations",
    "log_sat_time": "z_log_sat_time",
}


def ensure_clean_data() -> None:
    # Reuse the existing reproducible pipeline only when the cleaned input is absent.
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
    n = len(x_values)
    if n < 2:
        return math.nan
    x_mean = sum(x_values) / n
    y_mean = sum(y_values) / n
    x_diffs = [value - x_mean for value in x_values]
    y_diffs = [value - y_mean for value in y_values]
    denominator = math.sqrt(sum(v * v for v in x_diffs) * sum(v * v for v in y_diffs))
    if denominator == 0:
        return math.nan
    return sum(x * y for x, y in zip(x_diffs, y_diffs)) / denominator


def spearman_correlation(x_values: list[float], y_values: list[float]) -> float:
    return pearson_correlation(average_ranks(x_values), average_ranks(y_values))


def exact_permutation_p_value(
    x_values: list[float],
    y_values: list[float],
) -> tuple[float, float]:
    observed = spearman_correlation(x_values, y_values)
    if math.isnan(observed):
        return observed, math.nan
    total = 0
    at_least_as_extreme = 0
    for permuted_y in itertools.permutations(y_values):
        permuted = spearman_correlation(x_values, list(permuted_y))
        if math.isnan(permuted):
            continue
        total += 1
        if abs(permuted) >= abs(observed) - 1e-12:
            at_least_as_extreme += 1
    return observed, at_least_as_extreme / total if total else math.nan


def two_sided_normal_p_value(test_statistic: float) -> float:
    if math.isnan(test_statistic):
        return math.nan
    return math.erfc(abs(test_statistic) / math.sqrt(2))


def assign_experience_group(value: float) -> str | None:
    if pd.isna(value):
        return None
    if value <= 3:
        return "beginner"
    if value <= 6:
        return "intermediate"
    return "experienced"


def prepare_experience_data(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["experience_level"] = pd.to_numeric(df["experience_level"], errors="coerce")
    df["experience_group"] = df["experience_level"].map(assign_experience_group)

    exp_mean = df["experience_level"].mean()
    exp_sd = df["experience_level"].std(ddof=0)
    df["z_experience"] = (df["experience_level"] - exp_mean) / exp_sd

    # Z-score SAT variables across participant-puzzle rows for interpretability.
    # These variables still only have six unique puzzle-level values.
    for source, target in Z_SAT_VARIABLES.items():
        mean = df[source].mean()
        sd = df[source].std(ddof=0)
        df[target] = (df[source] - mean) / sd if sd else 0.0
    return df


def save_experience_distribution(df: pd.DataFrame) -> pd.DataFrame:
    distribution = (
        df.groupby("experience_level", dropna=False)
        .agg(
            n_rows=("participant_id", "size"),
            n_participants=("participant_id", "nunique"),
        )
        .reset_index()
        .sort_values("experience_level", na_position="last")
    )
    distribution.to_csv(OUTPUT_DIR / "experience_distribution.csv", index=False)
    return distribution


def save_experience_coding_summary(df: pd.DataFrame) -> pd.DataFrame:
    rows_missing = int(df["experience_level"].isna().sum())
    participants_missing = int(df.groupby("participant_id")["experience_level"].first().isna().sum())
    grouped = (
        df.groupby("experience_group", dropna=False)
        .agg(n_rows=("participant_id", "size"), n_participants=("participant_id", "nunique"))
        .reset_index()
    )
    coding = pd.DataFrame(
        [
            {
                "original_experience_variable": "experience_level",
                "source_column": "skill_nonogram",
                "model_experience_variable": "z_experience",
                "grouped_experience_variable": "experience_group",
                "grouping_rule": "beginner=1-3, intermediate=4-6, experienced=7-10",
                "rows_missing_experience": rows_missing,
                "participants_missing_experience": participants_missing,
                "group": row.experience_group if pd.notna(row.experience_group) else "missing",
                "group_n_rows": int(row.n_rows),
                "group_n_participants": int(row.n_participants),
                "notes": (
                    "Numeric experience is preserved for interaction models; grouped "
                    "experience is used for summaries, correlations, and plots."
                ),
            }
            for row in grouped.itertuples(index=False)
        ]
    )
    coding.to_csv(OUTPUT_DIR / "experience_coding_summary.csv", index=False)
    return coding


def clustered_ols_interaction(df: pd.DataFrame, z_sat_variable: str, source_sat_variable: str) -> pd.DataFrame:
    model_df = df[
        ["participant_id", "puzzle_id", "final_rating", "order", "z_experience", z_sat_variable]
    ].dropna()
    model_df = model_df.copy()
    model_df["sat_x_experience"] = model_df[z_sat_variable] * model_df["z_experience"]

    order_dummies = pd.get_dummies(model_df["order"].astype(int), prefix="order", drop_first=True)
    x_df = pd.concat(
        [
            pd.Series(1.0, index=model_df.index, name="intercept"),
            model_df[[z_sat_variable, "z_experience", "sat_x_experience"]].astype(float),
            order_dummies.astype(float),
        ],
        axis=1,
    )
    y = model_df["final_rating"].astype(float).to_numpy()
    x = x_df.to_numpy(dtype=float)
    n_obs, n_terms = x.shape
    n_participants = model_df["participant_id"].nunique()
    n_puzzles = model_df["puzzle_id"].nunique()

    try:
        xtx_inv = np.linalg.pinv(x.T @ x)
        beta = xtx_inv @ x.T @ y
        residuals = y - x @ beta
        meat = np.zeros((n_terms, n_terms))
        for _, group_index in model_df.groupby("participant_id").groups.items():
            positions = model_df.index.get_indexer(group_index)
            x_g = x[positions, :]
            u_g = residuals[positions].reshape(-1, 1)
            meat += x_g.T @ u_g @ u_g.T @ x_g
        covariance = xtx_inv @ meat @ xtx_inv
        if n_participants > 1 and n_obs > n_terms:
            covariance *= (n_participants / (n_participants - 1)) * ((n_obs - 1) / (n_obs - n_terms))
        standard_errors = np.sqrt(np.maximum(np.diag(covariance), 0))
        status = "ok"
    except np.linalg.LinAlgError:
        beta = np.full(n_terms, math.nan)
        standard_errors = np.full(n_terms, math.nan)
        status = "failed"

    rows = []
    for term, estimate, standard_error in zip(x_df.columns, beta, standard_errors):
        test_statistic = estimate / standard_error if standard_error and not math.isnan(standard_error) else math.nan
        rows.append(
            {
                "model_name": f"final_rating ~ {z_sat_variable} * z_experience + C(order)",
                "sat_variable": source_sat_variable,
                "experience_variable_used": "z_experience",
                "term": term,
                "estimate": estimate,
                "standard_error": standard_error,
                "test_statistic": test_statistic,
                "p_value": two_sided_normal_p_value(test_statistic),
                "n_rows": n_obs,
                "n_participants": n_participants,
                "n_puzzles": n_puzzles,
                "model_type": "OLS_clustered_by_participant",
                "notes": (
                    f"Mixed-effects dependency unavailable; fallback clustered OLS. "
                    f"SAT variation remains puzzle-level with {n_puzzles} puzzles; no puzzle fixed effects included. "
                    f"Status={status}."
                ),
            }
        )
    return pd.DataFrame(rows)


def save_interaction_models(df: pd.DataFrame) -> pd.DataFrame:
    results = pd.concat(
        [
            clustered_ols_interaction(df, z_sat_variable, sat_variable)
            for sat_variable, z_sat_variable in Z_SAT_VARIABLES.items()
        ],
        ignore_index=True,
    )
    results.to_csv(OUTPUT_DIR / "experience_interaction_model_results.csv", index=False)
    return results


def save_puzzle_summary_by_experience(df: pd.DataFrame) -> pd.DataFrame:
    summary = (
        df.dropna(subset=["experience_group"])
        .groupby(["experience_group", "puzzle_id"])
        .agg(
            n_attempts=("participant_id", "size"),
            n_completed=("completed", "sum"),
            n_final_ratings_available=("final_rating", "count"),
            mean_final_rating=("final_rating", "mean"),
            median_final_rating=("final_rating", "median"),
            sd_final_rating=("final_rating", "std"),
            mean_initial_rating=("initial_rating", "mean"),
            mean_rating_change=("rating_change", "mean"),
        )
        .reset_index()
    )
    summary["completion_rate"] = summary["n_completed"] / summary["n_attempts"]
    columns = [
        "experience_group",
        "puzzle_id",
        "n_attempts",
        "n_completed",
        "n_final_ratings_available",
        "mean_final_rating",
        "median_final_rating",
        "sd_final_rating",
        "completion_rate",
        "mean_initial_rating",
        "mean_rating_change",
    ]
    summary = summary[columns].sort_values(["experience_group", "puzzle_id"])
    summary.to_csv(OUTPUT_DIR / "puzzle_human_difficulty_by_experience.csv", index=False)
    return summary


def save_group_correlations(df: pd.DataFrame, group_summary: pd.DataFrame) -> pd.DataFrame:
    sat_by_puzzle = df.groupby("puzzle_id")[SAT_VARIABLES].first().reset_index()
    rows: list[dict[str, Any]] = []
    for group, group_df in group_summary.groupby("experience_group"):
        merged = group_df.merge(sat_by_puzzle, on="puzzle_id", how="left")
        for sat_variable in SAT_VARIABLES:
            pair_df = merged[["mean_final_rating", sat_variable]].dropna()
            n_puzzles = len(pair_df)
            if n_puzzles >= 4:
                correlation, p_value = exact_permutation_p_value(
                    pair_df["mean_final_rating"].astype(float).tolist(),
                    pair_df[sat_variable].astype(float).tolist(),
                )
                warning = "Exploratory: only 4-6 puzzle-level observations in this group."
            else:
                correlation = math.nan
                p_value = math.nan
                warning = "Not computed: fewer than 4 puzzles with ratings."
            rows.append(
                {
                    "experience_group": group,
                    "human_variable": "mean_final_rating",
                    "sat_variable": sat_variable,
                    "method": "spearman",
                    "correlation": correlation,
                    "p_value": p_value,
                    "n_puzzles": n_puzzles,
                    "warning": warning,
                }
            )
    results = pd.DataFrame(rows)
    results.to_csv(OUTPUT_DIR / "experience_group_correlation_results.csv", index=False)
    return results


def fit_line(x_values: list[float], y_values: list[float]) -> tuple[list[float], list[float]] | None:
    if len(x_values) < 2 or len(set(x_values)) < 2:
        return None
    x_mean = sum(x_values) / len(x_values)
    y_mean = sum(y_values) / len(y_values)
    denom = sum((x - x_mean) ** 2 for x in x_values)
    if denom == 0:
        return None
    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, y_values)) / denom
    intercept = y_mean - slope * x_mean
    line_x = [min(x_values), max(x_values)]
    return line_x, [intercept + slope * x for x in line_x]


def save_interaction_plots(df: pd.DataFrame) -> None:
    figure_dir = OUTPUT_DIR / "figures" / "experience_interactions"
    figure_dir.mkdir(parents=True, exist_ok=True)
    plot_specs = [
        ("z_conflicts", "z-scored conflicts", "experience_interaction_conflicts.png"),
        ("z_decisions", "z-scored decisions", "experience_interaction_decisions.png"),
        ("z_propagations", "z-scored propagations", "experience_interaction_propagations.png"),
        ("z_log_propagations", "z-scored log(1 + propagations)", "experience_interaction_log_propagations.png"),
    ]
    colors = {"beginner": "#1f5a85", "intermediate": "#b66a00", "experienced": "#287c48"}
    plot_df = df.dropna(subset=["final_rating", "experience_group"]).copy()
    n_participants = plot_df["participant_id"].nunique()
    n_puzzles = plot_df["puzzle_id"].nunique()

    rng = np.random.default_rng(20260615)
    for z_variable, x_label, filename in plot_specs:
        fig, ax = plt.subplots(figsize=(7.5, 5.2), dpi=160)
        for group, group_df in plot_df.groupby("experience_group"):
            x = group_df[z_variable].astype(float).to_numpy()
            y = group_df["final_rating"].astype(float).to_numpy()
            jittered_x = x + rng.normal(0, 0.035, size=len(x))
            ax.scatter(
                jittered_x,
                y,
                s=28,
                alpha=0.55,
                color=colors.get(group, "#555555"),
                label=f"{group} (n={group_df['participant_id'].nunique()} participants)",
            )
            line = fit_line(x.tolist(), y.tolist())
            if line is not None:
                ax.plot(line[0], line[1], color=colors.get(group, "#555555"), linewidth=1.8)
        ax.set_xlabel(x_label)
        ax.set_ylabel("Final adjusted difficulty rating")
        ax.set_title(
            f"Experience interaction: final rating vs {x_label}\n"
            f"Exploratory; {n_participants} participants, {n_puzzles} puzzles"
        )
        ax.grid(True, alpha=0.25)
        ax.legend(frameon=False, fontsize=8)
        fig.tight_layout()
        fig.savefig(figure_dir / filename, bbox_inches="tight")
        plt.close(fig)


def format_float(value: float, digits: int = 3) -> str:
    if pd.isna(value):
        return "NA"
    return f"{value:.{digits}f}"


def append_report_section(
    df: pd.DataFrame,
    coding_summary: pd.DataFrame,
    model_results: pd.DataFrame,
    group_correlations: pd.DataFrame,
) -> None:
    if not BASE_REPORT.exists():
        runpy.run_path(str(ORIGINAL_PIPELINE), run_name="__main__")
    if not REPORT_BACKUP.exists():
        REPORT_BACKUP.write_text(BASE_REPORT.read_text(encoding="utf-8"), encoding="utf-8")

    interaction_terms = model_results[model_results["term"] == "sat_x_experience"].copy()
    interaction_terms["abs_estimate"] = interaction_terms["estimate"].abs()
    strongest_interactions = interaction_terms.sort_values("abs_estimate", ascending=False).head(4)
    strongest = strongest_interactions.iloc[0]

    group_corr = group_correlations.dropna(subset=["correlation"]).copy()
    group_corr["abs_correlation"] = group_corr["correlation"].abs()
    best_by_group = (
        group_corr.sort_values(["experience_group", "abs_correlation"], ascending=[True, False])
        .groupby("experience_group")
        .head(1)
    )

    model_lines = "\n".join(
        f"- {row.sat_variable}: interaction estimate = {format_float(row.estimate)}, SE = {format_float(row.standard_error)}, p = {format_float(row.p_value)}"
        for row in strongest_interactions.itertuples(index=False)
    )
    corr_lines = "\n".join(
        f"- {row.experience_group}: strongest Spearman with {row.sat_variable}, rho = {format_float(row.correlation)}, n_puzzles = {int(row.n_puzzles)}"
        for row in best_by_group.itertuples(index=False)
    )

    missing_rows = int(df["experience_level"].isna().sum())
    missing_participants = int(df.groupby("participant_id")["experience_level"].first().isna().sum())
    group_counts = coding_summary[["group", "group_n_rows", "group_n_participants"]].drop_duplicates()
    group_lines = "\n".join(
        f"- {row.group}: {int(row.group_n_participants)} participants, {int(row.group_n_rows)} rows"
        for row in group_counts.itertuples(index=False)
    )

    section = f"""

## 11. Participant Experience Interaction Analysis

This analysis was added to test whether SAT solver statistics align better or worse with human difficulty ratings depending on participant background experience.

Experience was encoded from `experience_level`, which comes from the pre-survey `skill_nonogram` response. The numeric 1-10 value was preserved and z-scored as `z_experience` for interaction models. For grouped summaries, correlations, and plots, experience was grouped as beginner = 1-3, intermediate = 4-6, and experienced = 7-10.

Experience availability:

- Missing participant-puzzle rows: {missing_rows}
- Participants with missing experience: {missing_participants}

Grouped experience counts:

{group_lines}

Separate models were fit for each SAT statistic:

`final_rating ~ z_SAT_stat * z_experience + C(order)`

Mixed-effects modeling was unavailable in this environment, so the analysis used OLS with participant-clustered standard errors. Puzzle fixed effects were not included because SAT statistics vary only by puzzle and would be collinear with puzzle indicators.

The strongest SAT-by-experience interaction by absolute estimate was for `{strongest.sat_variable}`:

{model_lines}

These interaction terms should not be overinterpreted. They are exploratory, and the effective SAT-level variation is still only 6 puzzles.

Group-specific Spearman correlations between group-level `mean_final_rating` and SAT statistics were:

{corr_lines}

Overall, there is some suggestion that alignment differs by experience group, but the pattern is not stable enough to change the main conclusion. The experience interaction analysis does not provide strong evidence that SAT statistics reliably track human difficulty for one experience group more than another.

Limitations:

- This is exploratory.
- SAT statistics still vary only across 6 puzzles.
- Experience groups have modest sample sizes.
- Participant ratings may be affected by order and by which other puzzles they saw.
- Interaction p-values should not be overinterpreted.
"""

    updated = BASE_REPORT.read_text(encoding="utf-8").rstrip() + section
    BASE_REPORT.write_text(updated + "\n", encoding="utf-8")
    REPORT_WITH_EXPERIENCE.write_text(updated + "\n", encoding="utf-8")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ensure_clean_data()

    df = pd.read_csv(CLEAN_DATA)
    df = prepare_experience_data(df)

    distribution = save_experience_distribution(df)
    coding_summary = save_experience_coding_summary(df)
    model_results = save_interaction_models(df)
    group_summary = save_puzzle_summary_by_experience(df)
    group_correlations = save_group_correlations(df, group_summary)
    save_interaction_plots(df)
    append_report_section(df, coding_summary, model_results, group_correlations)

    print("Experience interaction analysis complete.")
    print(f"Experience distribution rows: {len(distribution)}")
    print(f"Model result rows: {len(model_results)}")
    print(f"Group correlation rows: {len(group_correlations)}")
    print(f"Report backup: {REPORT_BACKUP}")
    print(f"Updated report copy: {REPORT_WITH_EXPERIENCE}")


if __name__ == "__main__":
    main()
