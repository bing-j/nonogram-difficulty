"""
Expertise interaction analysis for SAT-vs-human Nonogram difficulty.

Run from the repository root:
    python3 run_experience_interaction_analysis.py

Reads analyze-data/out_features/behavioral_features.csv (participant-puzzle
ratings + the continuous expertise_composite score -- see analyze-data/
expertise.py) merged with selected_six_nonogram_stats.csv, and writes
expertise-focused outputs under outputs/. No discrete experience groups are
used anywhere in this script -- expertise enters only as a continuous
covariate (expertise_composite).
"""

from __future__ import annotations

import math
import os
from pathlib import Path

import numpy as np
import pandas as pd

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/nonogram-difficulty-matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/private/tmp/nonogram-difficulty-cache")
os.environ.setdefault("MPLBACKEND", "Agg")
import matplotlib.pyplot as plt

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
    behavioral_features.csv (participant_id, puzzle_id, order,
    expertise_composite, final_difficulty) merged with SAT solver stats.

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


def two_sided_normal_p_value(test_statistic: float) -> float:
    if math.isnan(test_statistic):
        return math.nan
    return math.erfc(abs(test_statistic) / math.sqrt(2))


def prepare_expertise_data(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # Z-score SAT variables across participant-puzzle rows for interpretability.
    # These variables still only have six unique puzzle-level values.
    for source, target in Z_SAT_VARIABLES.items():
        mean = df[source].mean()
        sd = df[source].std(ddof=0)
        df[target] = (df[source] - mean) / sd if sd else 0.0
    return df


def clustered_ols_interaction(df: pd.DataFrame, z_sat_variable: str, source_sat_variable: str) -> pd.DataFrame:
    model_df = df[
        ["participant_id", "puzzle_id", "final_rating", "order", "expertise_composite", z_sat_variable]
    ].dropna()
    model_df = model_df.copy()
    model_df["sat_x_expertise"] = model_df[z_sat_variable] * model_df["expertise_composite"]

    order_dummies = pd.get_dummies(model_df["order"].astype(int), prefix="order", drop_first=True)
    x_df = pd.concat(
        [
            pd.Series(1.0, index=model_df.index, name="intercept"),
            model_df[[z_sat_variable, "expertise_composite", "sat_x_expertise"]].astype(float),
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
                "model_name": f"final_rating ~ {z_sat_variable} * expertise_composite + C(order)",
                "sat_variable": source_sat_variable,
                "expertise_variable_used": "expertise_composite",
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


def save_interaction_plots(df: pd.DataFrame) -> None:
    figure_dir = OUTPUT_DIR / "figures" / "experience_interactions"
    figure_dir.mkdir(parents=True, exist_ok=True)
    plot_specs = [
        ("z_conflicts", "z-scored conflicts", "experience_interaction_conflicts.png"),
        ("z_decisions", "z-scored decisions", "experience_interaction_decisions.png"),
        ("z_propagations", "z-scored propagations", "experience_interaction_propagations.png"),
        ("z_log_propagations", "z-scored log(1 + propagations)", "experience_interaction_log_propagations.png"),
    ]
    plot_df = df.dropna(subset=["final_rating", "expertise_composite"]).copy()
    n_participants = plot_df["participant_id"].nunique()
    n_puzzles = plot_df["puzzle_id"].nunique()

    rng = np.random.default_rng(20260615)
    for z_variable, x_label, filename in plot_specs:
        fig, ax = plt.subplots(figsize=(7.5, 5.2), dpi=160)
        x = plot_df[z_variable].astype(float).to_numpy()
        y = plot_df["final_rating"].astype(float).to_numpy()
        jittered_x = x + rng.normal(0, 0.035, size=len(x))
        scatter = ax.scatter(
            jittered_x,
            y,
            s=28,
            alpha=0.65,
            c=plot_df["expertise_composite"].astype(float),
            cmap="viridis",
        )
        fig.colorbar(scatter, ax=ax, label="Expertise composite (z)")
        line = fit_line(x.tolist(), y.tolist())
        if line is not None:
            ax.plot(line[0], line[1], color="#333333", linewidth=1.8)
        ax.set_xlabel(x_label)
        ax.set_ylabel("Final adjusted difficulty rating")
        ax.text(
            0.03, 0.97, f"Exploratory\n{n_participants} participants, {n_puzzles} puzzles",
            transform=ax.transAxes, ha="left", va="top", fontsize=8,
            bbox=dict(boxstyle="round", facecolor="white", edgecolor="gray", alpha=0.8),
        )
        fig.tight_layout()
        fig.savefig(figure_dir / filename, bbox_inches="tight")
        plt.close(fig)


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


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df = load_working_frame()
    df = prepare_expertise_data(df)

    model_results = save_interaction_models(df)
    save_interaction_plots(df)

    interaction_terms = model_results[model_results["term"] == "sat_x_expertise"].copy()
    interaction_terms["abs_estimate"] = interaction_terms["estimate"].abs()
    strongest = interaction_terms.sort_values("abs_estimate", ascending=False).iloc[0]

    print("Expertise interaction analysis complete.")
    print(f"Model result rows: {len(model_results)}")
    print(
        f"Strongest SAT-by-expertise interaction: {strongest.sat_variable} "
        f"(estimate={strongest.estimate:.3f}, p={strongest.p_value:.3f})"
    )


if __name__ == "__main__":
    main()
