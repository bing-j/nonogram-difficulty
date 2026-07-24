"""
expertise_adjustment.py
========================
Two things: (1) does expertise predict behavior/difficulty? and (2) an
expertise-adjusted per-puzzle difficulty estimate via residualization,
correlated against SAT solver metrics.

Ported from an earlier standalone exploratory analysis's motivation() and
M2 residualization method (since removed from the repo). M0 (raw) is kept only as a side-by-side reference
column, not as an alternative adjustment method. M1 (within-participant),
M3 (mixed model), M4 (stratification -- would reintroduce discrete expertise
tiers, which this pipeline does not use anywhere), and M5 (expertise x SAT
interaction) are intentionally excluded.

Inputs
------
- analyze-data/out_features/behavioral_features.csv
- selected_six_nonogram_stats.csv

Outputs
-------
- analyze-data/out_features/expertise_vs_outcomes.csv
- analyze-data/out_features/figures/expertise_vs_outcomes.png
- analyze-data/out_features/expertise_adjusted_puzzle_difficulty.csv
- analyze-data/out_features/expertise_adjustment_model_params.csv
- analyze-data/out_features/stats_expertise_adjusted_difficulty_vs_sat.csv
- analyze-data/out_features/figures/expertise_adjusted_difficulty_vs_sat.png

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
import statsmodels.formula.api as smf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plot_style import NEUTRAL_COLOR, apply_style  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FEATURES_CSV = REPO_ROOT / "analyze-data" / "out_features" / "behavioral_features.csv"
DEFAULT_SOLVER_CSV = REPO_ROOT / "selected_six_nonogram_stats.csv"
DEFAULT_OUT_DIR = REPO_ROOT / "analyze-data" / "out_features"

# Same behavioral signals as behavioral_regression.py's BEHAVIORAL_FEATURES.
BEHAVIORAL_FEATURES = ["time_to_solve_sec", "pause_count", "pause_freq_per_min", "error_count", "hint_count"]
OUTCOME_LABELS = {
    "time_to_solve_sec": "Mean time to solve (s)",
    "pause_count": "Mean pause count",
    "pause_freq_per_min": "Mean pause freq/min",
    "error_count": "Mean error count",
    "hint_count": "Mean hints used",
    "final_difficulty": "Mean final difficulty",
}
SAT_PREDICTORS = ["decisions", "propagations", "conflicts"]


def load_solver_stats(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, index_col=0)
    if "puzzle_id" in df.columns:
        df = df.drop(columns=["puzzle_id"])
    df.index.name = "puzzle_id"
    df = df.reset_index()
    df["puzzle_id"] = df["puzzle_id"].astype(int)
    return df[["puzzle_id"] + SAT_PREDICTORS]


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
        pause_freq_per_min=("pause_freq_per_min", "mean"),
        error_count=("error_count", "mean"),
        hint_count=("hint_count", "mean"),
        final_difficulty=("final_difficulty", "mean"),
    ).reset_index()

    rows = []
    for col in outcome_cols:
        rho, p, n = spearman(perf["expertise"], perf[col])
        rows.append({"outcome": OUTCOME_LABELS[col], "column": col, "spearman_rho": rho, "spearman_p": p, "n": n})
    stat = pd.DataFrame(rows)
    stat.to_csv(out_dir / "expertise_vs_outcomes.csv", index=False)

    fig, axes = plt.subplots(2, 3, figsize=(15, 9), dpi=150)
    for ax, col in zip(axes.ravel(), outcome_cols):
        d = perf[["expertise", col]].dropna()
        ax.scatter(d["expertise"], d[col], color=NEUTRAL_COLOR, alpha=0.6)
        if len(d) > 3 and d["expertise"].nunique() > 1:
            m, b = np.polyfit(d["expertise"], d[col], 1)
            xs = np.array([d["expertise"].min(), d["expertise"].max()])
            ax.plot(xs, m * xs + b, "--", color="black")
            rho, p, _ = spearman(d["expertise"], d[col])
            ax.set_title(f"{OUTCOME_LABELS[col]}\nSpearman rho={rho:.2f}, p={p:.3f}", fontsize=10)
        ax.set_xlabel("Composite expertise (z)")
        ax.set_ylabel(OUTCOME_LABELS[col])
        ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(fig_dir / "expertise_vs_outcomes.png", bbox_inches="tight")
    plt.close(fig)
    return stat


# ---------------------------------------------------------------------------
# Part 2: residualization-adjusted difficulty (M2 only)
# ---------------------------------------------------------------------------

def run_residualized_difficulty(df: pd.DataFrame, sat_df: pd.DataFrame, out_dir: Path) -> pd.DataFrame:
    work = df.dropna(subset=["final_difficulty"]).copy()
    grand = work["final_difficulty"].mean()

    m0 = work.groupby("puzzle_id")["final_difficulty"].agg(raw_mean_difficulty="mean", n_ratings="count")

    res_df = work.dropna(subset=["expertise_composite", "order"]).copy()
    model = smf.ols("final_difficulty ~ expertise_composite + C(order)", data=res_df).fit()
    res_df["resid_adj"] = model.resid + grand
    m2 = res_df.groupby("puzzle_id")["resid_adj"].mean().rename("adjusted_difficulty")

    out = m0.join(m2).reset_index()
    out = out.merge(sat_df, on="puzzle_id", how="left")
    out.to_csv(out_dir / "expertise_adjusted_puzzle_difficulty.csv", index=False)

    params = pd.DataFrame({
        "term": model.params.index,
        "coef": model.params.values,
        "se": model.bse.values,
        "p_value": model.pvalues.values,
    })
    params.to_csv(out_dir / "expertise_adjustment_model_params.csv", index=False)

    return out


# ---------------------------------------------------------------------------
# Part 3: adjusted difficulty vs. SAT metrics
# ---------------------------------------------------------------------------

def run_adjusted_vs_sat(adjusted_df: pd.DataFrame, out_dir: Path, fig_dir: Path) -> pd.DataFrame:
    rows = []
    for predictor in SAT_PREDICTORS:
        raw_rho, raw_p, n = spearman(adjusted_df["raw_mean_difficulty"], adjusted_df[predictor])
        adj_rho, adj_p, _ = spearman(adjusted_df["adjusted_difficulty"], adjusted_df[predictor])
        rows.append({
            "sat_metric": predictor,
            "raw_spearman_rho": raw_rho, "raw_spearman_p": raw_p,
            "adjusted_spearman_rho": adj_rho, "adjusted_spearman_p": adj_p,
            "n_puzzles": n,
        })
    result = pd.DataFrame(rows)
    result.to_csv(out_dir / "stats_expertise_adjusted_difficulty_vs_sat.csv", index=False)

    fig, axes = plt.subplots(1, 3, figsize=(16, 5), dpi=150)
    for ax, predictor in zip(axes, SAT_PREDICTORS):
        ax.scatter(adjusted_df[predictor], adjusted_df["adjusted_difficulty"], color=NEUTRAL_COLOR, s=55)
        for row in adjusted_df.itertuples(index=False):
            ax.annotate(
                str(int(row.puzzle_id)),
                (getattr(row, predictor), row.adjusted_difficulty),
                textcoords="offset points", xytext=(6, 5), fontsize=9,
            )
        rho_row = result[result["sat_metric"] == predictor].iloc[0]
        ax.set_xlabel(predictor)
        ax.set_ylabel("Expertise-adjusted difficulty")
        ax.set_title(f"Adjusted difficulty vs {predictor}\nSpearman rho={rho_row['adjusted_spearman_rho']:.3f}")
        ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(fig_dir / "expertise_adjusted_difficulty_vs_sat.png", bbox_inches="tight")
    plt.close(fig)
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Expertise vs. behavior/difficulty, and residualization-adjusted puzzle difficulty."
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

    fig_dir = args.out_dir / "figures"
    args.out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    df = load_features(args.features_csv)
    sat_df = load_solver_stats(args.solver_csv)

    print("=" * 60)
    print("EXPERTISE vs. BEHAVIOR AND DIFFICULTY")
    print("=" * 60)
    outcomes = run_expertise_vs_outcomes(df, args.out_dir, fig_dir)
    print(outcomes.to_string(index=False))

    print("\n" + "=" * 60)
    print("EXPERTISE-ADJUSTED DIFFICULTY (residualization only)")
    print("=" * 60)
    adjusted = run_residualized_difficulty(df, sat_df, args.out_dir)
    print(adjusted.to_string(index=False))

    print("\n" + "=" * 60)
    print("EXPERTISE-ADJUSTED DIFFICULTY vs SAT METRICS")
    print("=" * 60)
    sat_corr = run_adjusted_vs_sat(adjusted, args.out_dir, fig_dir)
    print(sat_corr.to_string(index=False))

    print("\nDone.")


if __name__ == "__main__":
    main()
