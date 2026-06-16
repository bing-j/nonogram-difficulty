"""
Multi-linear regression of behavioral difficulty signals.

Regression 1 (per puzzle): behavioral features -> user-reported difficulty
  - Run separately for each puzzle_id (initial_difficulty and final_difficulty).
  - Output: per-puzzle coefficient tables + heatmap of B coefficients.

Regression 2 (pooled): behavioral features -> SAT solver decisions
  - Pool all (participant × puzzle) observations.
  - decisions is puzzle-level; it varies across the pooled dataset.
  - Output: one coefficient table + scatter grid.

Usage:
  python analyze-data/behavioral_regression.py
  python analyze-data/behavioral_regression.py --features_csv ... --solver_csv ... --out_dir ...
"""

import argparse
import os
import warnings
from typing import Dict

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm

BEHAVIORAL_FEATURES = [
    "pause_count",
    "pause_freq_per_min",
    "time_to_solve_sec",
    "error_count",
    "hint_count",
]

MIN_OBS = 5  # skip per-puzzle regression if fewer observations

PUZZLE_COLORS = plt.cm.tab10.colors[:6]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_features(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    for col in BEHAVIORAL_FEATURES + ["initial_difficulty", "final_difficulty"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    # -1 is a sentinel for unanswered survey questions  - treat as missing
    for col in ["initial_difficulty", "final_difficulty"]:
        if col in df.columns:
            df[col] = df[col].where(df[col] >= 1, np.nan)
    return df


def load_solver_stats(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, index_col=0)
    # The unnamed index is the experiment puzzle_id (0–5).
    # Drop the internal solver 'puzzle_id' column to avoid collision.
    if "puzzle_id" in df.columns:
        df = df.drop(columns=["puzzle_id"])
    df.index.name = "puzzle_id"
    df = df.reset_index()
    df["puzzle_id"] = df["puzzle_id"].astype(int)
    return df[["puzzle_id", "decisions", "propagations"]]


def ols_fit(df: pd.DataFrame, dv: str) -> sm.regression.linear_model.RegressionResultsWrapper:
    sub = df[BEHAVIORAL_FEATURES + [dv]].dropna()
    X = sm.add_constant(sub[BEHAVIORAL_FEATURES])
    y = sub[dv]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return sm.OLS(y, X).fit()


def print_model_table(result, label: str, n: int) -> None:
    print(f"\n{'-' * 60}")
    print(f"  {label}   N={n}   R2={result.rsquared:.3f}   adj-R2={result.rsquared_adj:.3f}")
    print(f"{'-' * 60}")
    print(f"  {'Predictor':<22}  {'B':>8}  {'SE':>8}  {'t':>7}  {'p':>7}")
    print(f"  {'-'*22}  {'-'*8}  {'-'*8}  {'-'*7}  {'-'*7}")
    for name, coef, se, tval, pval in zip(
        result.params.index,
        result.params.values,
        result.bse.values,
        result.tvalues.values,
        result.pvalues.values,
    ):
        sig = "*" if pval < 0.05 else " "
        print(f"  {name:<22}  {coef:>8.3f}  {se:>8.3f}  {tval:>7.3f}  {pval:>7.3f}{sig}")


# ---------------------------------------------------------------------------
# Regression 1: per puzzle, DV = difficulty
# ---------------------------------------------------------------------------

def run_regression1(df: pd.DataFrame, out_dir: str) -> None:
    print("\n" + "=" * 60)
    print("REGRESSION 1: behavioral features -> user difficulty")
    print("=" * 60)

    puzzle_ids = sorted(df["puzzle_id"].dropna().unique().astype(int))
    coef_init: Dict = {}
    coef_final: Dict = {}

    for pid in puzzle_ids:
        sub = df[df["puzzle_id"] == pid].copy()
        n_init = sub[BEHAVIORAL_FEATURES + ["initial_difficulty"]].dropna().shape[0]
        n_final = sub[BEHAVIORAL_FEATURES + ["final_difficulty"]].dropna().shape[0]

        for dv, coef_store, label in [
            ("initial_difficulty", coef_init, f"Puzzle {pid}  - initial difficulty"),
            ("final_difficulty", coef_final, f"Puzzle {pid}  - final difficulty"),
        ]:
            n = n_init if dv == "initial_difficulty" else n_final
            if n < MIN_OBS:
                print(f"\n  [Puzzle {pid} / {dv}] only {n} complete obs  - skipping (need {MIN_OBS})")
                continue
            result = ols_fit(sub, dv)
            print_model_table(result, label, n)
            coef_store[pid] = result.params[BEHAVIORAL_FEATURES].values

    _save_coef_heatmap(coef_init, puzzle_ids, "initial_difficulty", out_dir)
    _save_coef_heatmap(coef_final, puzzle_ids, "final_difficulty", out_dir)


def _save_coef_heatmap(
    coef_dict: dict,
    puzzle_ids: list,
    dv_label: str,
    out_dir: str,
) -> None:
    pids_with_data = [p for p in puzzle_ids if p in coef_dict]
    if not pids_with_data:
        return

    mat = np.array([coef_dict[p] for p in pids_with_data])
    fig, ax = plt.subplots(figsize=(9, max(3, len(pids_with_data) * 0.8)))
    vmax = np.abs(mat).max() or 1
    im = ax.imshow(mat, cmap="RdBu_r", vmin=-vmax, vmax=vmax, aspect="auto")
    ax.set_xticks(range(len(BEHAVIORAL_FEATURES)))
    ax.set_xticklabels(BEHAVIORAL_FEATURES, rotation=30, ha="right", fontsize=9)
    ax.set_yticks(range(len(pids_with_data)))
    ax.set_yticklabels([f"Puzzle {p}" for p in pids_with_data])
    ax.set_title(f"Reg 1 B coefficients  - DV: {dv_label}")
    plt.colorbar(im, ax=ax, label="B")
    fig.tight_layout()
    fname = f"behavioral_reg1_coef_heatmap_{dv_label}.png"
    fig.savefig(os.path.join(out_dir, fname), dpi=150)
    plt.close(fig)
    print(f"\nSaved: {fname}")


# ---------------------------------------------------------------------------
# Regression 1b: pooled across all puzzles, DV = user difficulty
# ---------------------------------------------------------------------------

def run_regression1_pooled(df: pd.DataFrame) -> None:
    print("\n" + "=" * 60)
    print("REGRESSION 1 (pooled): behavioral features -> user difficulty")
    print("=" * 60)

    for dv in ["initial_difficulty", "final_difficulty"]:
        complete = df[BEHAVIORAL_FEATURES + [dv]].dropna()
        n = len(complete)
        if n < MIN_OBS:
            print(f"\n  [{dv}] only {n} complete obs  - skipping.")
            continue
        result = ols_fit(complete, dv)
        print_model_table(result, f"All puzzles pooled  - {dv}", n)


# ---------------------------------------------------------------------------
# Regression 2: pooled, DV = decisions
# ---------------------------------------------------------------------------

def run_regression2(df: pd.DataFrame, solver_stats: pd.DataFrame, out_dir: str) -> None:
    print("\n" + "=" * 60)
    print("REGRESSION 2: behavioral features -> SAT decisions (pooled)")
    print("=" * 60)

    merged = df.merge(solver_stats[["puzzle_id", "decisions"]], on="puzzle_id", how="left")
    complete = merged[BEHAVIORAL_FEATURES + ["decisions", "puzzle_id"]].dropna()
    n = len(complete)

    if n < MIN_OBS:
        print(f"  Only {n} complete observations  - skipping regression.")
        return

    result = ols_fit(complete, "decisions")
    print_model_table(result, "All puzzles pooled  - decisions", n)

    _save_reg2_scatter(complete, out_dir)


def _save_reg2_scatter(df: pd.DataFrame, out_dir: str) -> None:
    puzzle_ids = sorted(df["puzzle_id"].dropna().unique().astype(int))
    color_map = {pid: PUZZLE_COLORS[i % len(PUZZLE_COLORS)] for i, pid in enumerate(puzzle_ids)}

    ncols = len(BEHAVIORAL_FEATURES)
    fig, axes = plt.subplots(1, ncols, figsize=(4 * ncols, 4), sharey=False)
    if ncols == 1:
        axes = [axes]

    for ax, feat in zip(axes, BEHAVIORAL_FEATURES):
        for pid in puzzle_ids:
            sub = df[df["puzzle_id"] == pid]
            ax.scatter(
                sub[feat], sub["decisions"],
                color=color_map[pid], label=f"Puzzle {pid}", alpha=0.7, s=40,
            )
        # OLS line across all points
        x_all = df[feat].dropna()
        y_all = df.loc[x_all.index, "decisions"].dropna()
        common = x_all.index.intersection(y_all.index)
        if len(common) >= 2:
            x_c = x_all[common].values
            y_c = y_all[common].values
            m, b = np.polyfit(x_c, y_c, 1)
            xline = np.linspace(x_c.min(), x_c.max(), 100)
            ax.plot(xline, m * xline + b, color="black", linewidth=1.2, linestyle="--")
        ax.set_xlabel(feat, fontsize=9)
        ax.set_ylabel("decisions")
        ax.set_title(feat, fontsize=9)

    # Shared legend
    handles = [
        plt.Line2D([0], [0], marker="o", color="w", markerfacecolor=color_map[p], markersize=8, label=f"Puzzle {p}")
        for p in puzzle_ids
    ]
    axes[-1].legend(handles=handles, loc="best", fontsize=8)
    fig.suptitle("Reg 2: behavioral features vs. SAT decisions (pooled)", fontsize=11)
    fig.tight_layout()
    fname = "behavioral_reg2_scatter_grid_decisions.png"
    fig.savefig(os.path.join(out_dir, fname), dpi=150)
    plt.close(fig)
    print(f"Saved: {fname}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="Behavioral feature regressions for nonogram difficulty.")
    ap.add_argument(
        "--features_csv",
        default=os.path.join(os.path.dirname(__file__), "out_features", "behavioral_features.csv"),
    )
    ap.add_argument(
        "--solver_csv",
        default=os.path.join(os.path.dirname(__file__), "..", "selected_six_nonogram_stats.csv"),
    )
    ap.add_argument(
        "--out_dir",
        default=os.path.join(os.path.dirname(__file__), "out_features"),
    )
    args = ap.parse_args()

    if not os.path.exists(args.features_csv):
        print(f"Features CSV not found: {args.features_csv}")
        print("Run extract_behavioral_features.py first.")
        return

    os.makedirs(args.out_dir, exist_ok=True)
    df = load_features(args.features_csv)
    solver = load_solver_stats(args.solver_csv)

    print(f"Loaded {len(df)} rows from {args.features_csv}")
    print(f"Puzzles: {sorted(df['puzzle_id'].dropna().unique().astype(int).tolist())}")

    run_regression1(df, args.out_dir)
    run_regression1_pooled(df)
    run_regression2(df, solver, args.out_dir)

    print("\nDone.")


if __name__ == "__main__":
    main()
