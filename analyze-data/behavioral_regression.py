"""
Multi-linear regression of behavioral difficulty signals.

Regression 1 (per puzzle): behavioral features -> user-reported difficulty
  - Run separately for each puzzle_id, using final_difficulty (retrospective rating).
  - Output: per-puzzle coefficient tables + heatmap of B coefficients.

Regression 2: SAT solver metric -> behavioral signal (crossed-random-effects
LMM, one model per behavioral-signal x SAT-metric pair, 12 total).

This used to be fit backwards -- SAT_metric ~ behavioral_features, pooled
OLS -- which has two real problems. (1) Causal direction: a puzzle's SAT
metric is a fixed, exogenous property set before any participant touches
it; it cannot be "explained by" participant behavior, so the natural
direction is behavior ~ metric, not metric ~ behavior. (2) Pseudoreplication:
the old pooled OLS treated ~197-201 participant x puzzle rows as
independent, but the SAT metric only has 6 truly distinct values (one per
puzzle), each repeated ~30-40 times -- overstating precision on anything
involving the puzzle-level variable.

Both are fixed the same way moderation_analysis.py fixes the structurally
identical SAT-metric<->difficulty problem: a crossed-random-effects linear
mixed model (behavioral_signal ~ SAT_metric, with CROSSED random intercepts
for participant_id and puzzle_id -- the standard "participant crossed with
item" specification, Baayen, Davidson & Bates 2008). statsmodels' MixedLM
has no native `(1|a)+(1|b)` syntax, hence the same dummy `groups` +
`vc_formula` workaround used there.

Three disclosed limitations (same situation as moderation_analysis.py,
worded for this simpler one-fixed-predictor model):
  1. With only 6 puzzles, one fixed slope, and a puzzle-level random
     intercept all competing for the same between-puzzle variation, the
     puzzle-level variance component (and the metric's own coefficient) has
     an irreducible small-sample bound -- expect it to sometimes sit near
     the REML boundary (0) or carry a wide CI. No statistical method removes
     this; it's reported honestly via `var_puzzle` rather than hidden.
  2. MixedLM's Wald inference is asymptotic (z-based), not
     Satterthwaite/Kenward-Roger small-sample-corrected like R's lmerTest.
  3. The model assumes Gaussian residuals; `pause_count`/`error_count`/
     `hint_count` are non-negative counts and `time_to_solve_sec` is a
     right-skewed duration, not the continuous scale the model expects.
     Following this repo's existing convention (Reg 1's OLS, expertise_
     adjustment.py's Spearman correlations) of raw untransformed continuous
     variables for consistency -- treat p-values/CIs as approximate.

Note: Reg 2's coefficient table reports a Wald **z**-statistic (`z` column,
MixedLM), while Reg 1's tables report a **t**-statistic (`t` column, OLS) --
different columns, different statistics, despite living in the same file.

  - Output: one combined coefficient table (12 rows) + one comparison
    heatmap (color = z-statistic, since behavioral signals and SAT metrics
    both span incompatible units; cell text = raw beta, native units).

Diagnostics (CSV/console only -- not added to any figure): every saved
coefficient table gets a Benjamini-Hochberg FDR-corrected p-value (`p_fdr`,
corrected within that table's own family of predictor tests), an
`underpowered` flag (N < 15, since 4 predictors + intercept needs far more
than the MIN_OBS=5 floor to be reliably identified), and per-model
Breusch-Pagan (heteroscedasticity), Shapiro-Wilk (residual normality, N<3
guarded), and max Cook's distance (leverage/influence) diagnostics -- none of
this was checked previously; OLS was fit and reported with no assumption
checking. A one-time VIF (variance inflation factor) table across the 4
predictors is also saved, since time_to_solve_sec mechanically bounds
pause/error opportunity -- collinearity among predictors was never
previously diagnosed.

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
import statsmodels.formula.api as smf
from scipy.stats import shapiro
from statsmodels.stats.diagnostic import het_breuschpagan
from statsmodels.stats.outliers_influence import OLSInfluence, variance_inflation_factor

from plot_style import ACCENT_COLOR, NEUTRAL_COLOR, apply_style
from stats_utils import benjamini_hochberg

BEHAVIORAL_FEATURES = [
    "pause_count",
    "time_to_solve_sec",
    "error_count",
    "hint_count",
]

# Same three metrics used throughout the pipeline (moderation_analysis.py,
# spearman_ranking.py, regression_analysis.py).
SAT_METRICS = ["decisions", "propagations", "conflicts"]
METRIC_LABELS = {
    "decisions": "Decisions",
    "propagations": "Propagations",
    "conflicts": "Conflicts",
}

MIN_OBS = 5  # skip per-puzzle regression if fewer observations
UNDERPOWERED_N = 15  # rule-of-thumb ~10-15 obs/predictor for 5 predictors + intercept


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
    return df[["puzzle_id", "decisions", "propagations", "conflicts"]]


def ols_fit(df: pd.DataFrame, dv: str) -> sm.regression.linear_model.RegressionResultsWrapper:
    sub = df[BEHAVIORAL_FEATURES + [dv]].dropna()
    X = sm.add_constant(sub[BEHAVIORAL_FEATURES])
    y = sub[dv]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return sm.OLS(y, X).fit()


def _sig_stars(pval: float) -> str:
    if pval < 0.001:
        return "***"
    if pval < 0.01:
        return "**"
    if pval < 0.05:
        return "*"
    return ""


def ols_diagnostics(result) -> dict:
    """Assumption checks that raw R2/coefficient tables don't surface on
    their own: heteroscedasticity (Breusch-Pagan), residual normality
    (Shapiro-Wilk, unreliable below N=3 so guarded), and leverage/influence
    (max Cook's distance)."""
    resid = result.resid
    exog = result.model.exog
    _, bp_p, _, _ = het_breuschpagan(resid, exog)
    shapiro_p = float(shapiro(resid)[1]) if len(resid) >= 3 else float("nan")
    cooks_d, _ = OLSInfluence(result).cooks_distance
    max_cooks_d = float(np.max(cooks_d)) if len(cooks_d) else float("nan")
    return {"breusch_pagan_p": float(bp_p), "shapiro_p": shapiro_p, "max_cooks_d": max_cooks_d}


def compute_vif(df: pd.DataFrame, features: list) -> pd.DataFrame:
    """Variance inflation factor per predictor, on the pooled complete-case
    data -- a collinearity diagnostic never previously computed here."""
    sub = df[features].dropna()
    X = sm.add_constant(sub)
    cols = list(X.columns)
    vifs = [variance_inflation_factor(X.values, cols.index(feat)) for feat in features]
    return pd.DataFrame({"predictor": features, "vif": vifs, "n": len(sub)})


def print_model_table(result, label: str, n: int) -> None:
    diag = ols_diagnostics(result)
    print(f"\n{'-' * 60}")
    print(f"  {label}   N={n}   R2={result.rsquared:.3f}   adj-R2={result.rsquared_adj:.3f}")
    if n < UNDERPOWERED_N:
        print(f"  WARNING: N={n} is below the ~{UNDERPOWERED_N} obs/predictor "
              f"rule of thumb for {len(BEHAVIORAL_FEATURES)} predictors -- underpowered.")
    print(f"  Diagnostics: Breusch-Pagan p={diag['breusch_pagan_p']:.3f}  "
          f"Shapiro-Wilk p={diag['shapiro_p']:.3f}  max Cook's D={diag['max_cooks_d']:.3f}")
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
    coef_final: Dict = {}
    pval_final: Dict = {}
    per_puzzle_rows = []

    for pid in puzzle_ids:
        sub = df[df["puzzle_id"] == pid].copy()
        n_final = sub[BEHAVIORAL_FEATURES + ["final_difficulty"]].dropna().shape[0]

        dv = "final_difficulty"
        label = f"Puzzle {pid}  - final difficulty"
        if n_final < MIN_OBS:
            print(f"\n  [Puzzle {pid} / {dv}] only {n_final} complete obs  - skipping (need {MIN_OBS})")
            continue
        result = ols_fit(sub, dv)
        print_model_table(result, label, n_final)
        coef_final[pid] = result.params[BEHAVIORAL_FEATURES].values
        pval_final[pid] = result.pvalues[BEHAVIORAL_FEATURES].values

        diag = ols_diagnostics(result)
        for feat in BEHAVIORAL_FEATURES:
            per_puzzle_rows.append({
                "puzzle_id": pid, "predictor": feat,
                "coef": result.params[feat], "se": result.bse[feat],
                "t": result.tvalues[feat], "p_value": result.pvalues[feat],
                "n": n_final, "r_squared": result.rsquared, "adj_r_squared": result.rsquared_adj,
                "underpowered": n_final < UNDERPOWERED_N, **diag,
            })

    _save_coef_heatmap(coef_final, pval_final, puzzle_ids, "final_difficulty", out_dir)

    if per_puzzle_rows:
        # One FDR family across ALL puzzles x predictors together -- this heatmap's
        # figure is unchanged (raw p, as before); this CSV is the corrected reference.
        per_puzzle_df = pd.DataFrame(per_puzzle_rows)
        per_puzzle_df["p_fdr"] = benjamini_hochberg(per_puzzle_df["p_value"].tolist())
        out_path = os.path.join(out_dir, "stats_behavioral_vs_difficulty_per_puzzle.csv")
        per_puzzle_df.to_csv(out_path, index=False)
        print(f"Saved: {out_path}")


def _save_coef_heatmap(
    coef_dict: dict,
    pval_dict: dict,
    puzzle_ids: list,
    dv_label: str,
    out_dir: str,
) -> None:
    pids_with_data = [p for p in puzzle_ids if p in coef_dict]
    if not pids_with_data:
        return

    mat = np.array([coef_dict[p] for p in pids_with_data])
    pmat = np.array([pval_dict[p] for p in pids_with_data])
    fig, ax = plt.subplots(figsize=(9, max(3, len(pids_with_data) * 0.8)))
    vmax = np.abs(mat).max() or 1
    im = ax.imshow(mat, cmap="RdBu_r", vmin=-vmax, vmax=vmax, aspect="auto")
    ax.grid(which="major", visible=False)  # apply_style's major grid would bisect cells at their centers
    ax.set_xticks(range(len(BEHAVIORAL_FEATURES)))
    ax.set_xticklabels(BEHAVIORAL_FEATURES, rotation=30, ha="right", fontsize=9)
    ax.set_yticks(range(len(pids_with_data)))
    ax.set_yticklabels([f"Puzzle {p}" for p in pids_with_data])

    for i in range(mat.shape[0]):
        for j in range(mat.shape[1]):
            stars = _sig_stars(pmat[i, j])
            text_color = "white" if abs(mat[i, j]) > vmax * 0.5 else "black"
            ax.text(
                j, i, f"{mat[i, j]:.2f}{stars}\n(p={pmat[i, j]:.3f})",
                ha="center", va="center", fontsize=7.5, color=text_color,
            )

    plt.colorbar(im, ax=ax, label="B")
    fig.text(0.01, -0.02, "* p<.05   ** p<.01   *** p<.001", fontsize=8, ha="left")
    fig.tight_layout()
    fname = f"behavioral_reg1_coef_heatmap_{dv_label}.png"
    fig.savefig(os.path.join(out_dir, fname), dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"\nSaved: {fname}")


# ---------------------------------------------------------------------------
# Regression 1b: pooled across all puzzles, DV = user difficulty
# ---------------------------------------------------------------------------

def run_regression1_pooled(df: pd.DataFrame, out_dir: str) -> None:
    print("\n" + "=" * 60)
    print("REGRESSION 1 (pooled): behavioral features -> user difficulty")
    print("=" * 60)

    for dv in ["final_difficulty"]:
        complete = df[BEHAVIORAL_FEATURES + [dv]].dropna()
        n = len(complete)
        if n < MIN_OBS:
            print(f"\n  [{dv}] only {n} complete obs  - skipping.")
            continue
        result = ols_fit(complete, dv)
        print_model_table(result, f"All puzzles pooled  - {dv}", n)
        _save_coef_table(
            result, n, os.path.join(out_dir, "stats_behavioral_vs_difficulty_pooled.csv")
        )


def _save_coef_table(result, n: int, out_path: str) -> None:
    """Save a pooled OLS coefficient table (predictor, B, SE, t, p) plus model
    fit stats (N, R2, adj-R2) as extra rows with predictor='(model)'.

    Also adds an FDR-corrected p-value (BH, across this table's own
    behavioral-feature predictors -- excluding the intercept, which isn't a
    test of interest here) and diagnostic columns (underpowered flag,
    Breusch-Pagan/Shapiro-Wilk/max-Cook's-D) -- reference columns for the
    paper's methods/limitations text, not surfaced in any figure."""
    diag = ols_diagnostics(result)
    rows = pd.DataFrame({
        "predictor": result.params.index,
        "coef": result.params.values,
        "se": result.bse.values,
        "t": result.tvalues.values,
        "p_value": result.pvalues.values,
    })
    rows["p_fdr"] = np.nan
    is_predictor = rows["predictor"] != "const"
    rows.loc[is_predictor, "p_fdr"] = benjamini_hochberg(rows.loc[is_predictor, "p_value"].tolist())

    fit = pd.DataFrame([{
        "predictor": "(model)",
        "coef": float("nan"), "se": float("nan"), "t": float("nan"), "p_value": float("nan"),
        "p_fdr": float("nan"),
        "n": n, "r_squared": result.rsquared, "adj_r_squared": result.rsquared_adj,
        "underpowered": n < UNDERPOWERED_N, **diag,
    }])
    rows["n"] = n
    rows["r_squared"] = result.rsquared
    rows["adj_r_squared"] = result.rsquared_adj
    rows["underpowered"] = n < UNDERPOWERED_N
    for key, val in diag.items():
        rows[key] = val
    out = pd.concat([rows, fit], ignore_index=True)
    out.to_csv(out_path, index=False)
    print(f"Saved: {out_path}")


# ---------------------------------------------------------------------------
# Regression 2: SAT metric -> behavioral signal (crossed-random-effects LMM)
# ---------------------------------------------------------------------------

def _fixed_effect(result, name: str) -> tuple:
    """Duplicated from moderation_analysis.py's identical helper -- this
    repo's scripts are self-contained (see text_coding_analysis.py's
    docstring), no cross-file imports of analysis logic."""
    coef = float(result.params[name])
    se = float(result.bse[name])
    p = float(result.pvalues[name])
    ci = result.conf_int().loc[name]
    return coef, se, p, float(ci[0]), float(ci[1])


def fit_crossed_lmm(df: pd.DataFrame, x_col: str, y_col: str):
    """y_col ~ x_col, with crossed random intercepts for participant_id and
    puzzle_id. Same machinery as moderation_analysis.py's fit_crossed_lmm,
    minus the expertise interaction term -- a main-effects-only test, not a
    moderation test."""
    sub = df[[x_col, y_col, "participant_id", "puzzle_id"]].dropna().copy()
    sub["participant_id"] = sub["participant_id"].astype(str)
    sub["puzzle_id"] = sub["puzzle_id"].astype(str)
    sub["_group"] = "1"  # dummy single group; real (crossed) REs come from vc_formula

    vc_formula = {
        "participant": "0 + C(participant_id)",
        "puzzle": "0 + C(puzzle_id)",
    }
    model = smf.mixedlm(
        f"{y_col} ~ {x_col}", data=sub, groups="_group", re_formula="0", vc_formula=vc_formula,
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = model.fit(reml=True)
        converged_with_warning = any("onverg" in str(w.message) for w in caught)
    return result, sub, converged_with_warning


def fit_behavior_vs_metric(df: pd.DataFrame, outcome: str, metric: str) -> tuple:
    result, sub, conv_warn = fit_crossed_lmm(df, x_col=metric, y_col=outcome)
    coef, se, p, ci_lo, ci_hi = _fixed_effect(result, metric)
    row = {
        "outcome": outcome, "predictor": metric,
        "coef": coef, "se": se, "z": coef / se if se else float("nan"), "p": p,
        "ci_lower": ci_lo, "ci_upper": ci_hi,
        "var_participant": float(result.vcomp[0]), "var_puzzle": float(result.vcomp[1]),
        "var_residual": float(result.scale),
        "n": len(sub), "n_participants": sub["participant_id"].nunique(),
        "n_puzzles": sub["puzzle_id"].nunique(),
        "converged": bool(result.converged), "convergence_warning": conv_warn,
    }
    return row, result, sub


def print_crossed_lmm_summary(row: dict) -> None:
    print(f"\n{'-' * 60}")
    print(f"  {row['outcome']} ~ {row['predictor']}   N={row['n']}  "
          f"participants={row['n_participants']}  puzzles={row['n_puzzles']}")
    if row["convergence_warning"]:
        print("  WARNING: optimizer fell back (ConvergenceWarning during fit).")
    sig = _sig_stars(row["p"])
    print(f"  coef={row['coef']:+.5f}{sig}  SE={row['se']:.5f}  z={row['z']:.3f}  p={row['p']:.4f}"
          f"  95% CI [{row['ci_lower']:+.5f}, {row['ci_upper']:+.5f}]")
    print(f"  Variance components: participant={row['var_participant']:.4f}  "
          f"puzzle={row['var_puzzle']:.4f}  residual={row['var_residual']:.4f}")


def run_regression2(merged: pd.DataFrame, out_dir: str) -> pd.DataFrame:
    print("\n" + "=" * 60)
    print("REGRESSION 2: SAT metric -> behavioral signal (crossed-effects LMM)")
    print("=" * 60)

    rows = []
    for outcome in BEHAVIORAL_FEATURES:
        for metric in SAT_METRICS:
            row, result, _ = fit_behavior_vs_metric(merged, outcome, metric)
            print_crossed_lmm_summary(row)
            rows.append(row)

    result_df = pd.DataFrame(rows)
    result_df["p_fdr"] = benjamini_hochberg(result_df["p"].tolist())
    out_path = os.path.join(out_dir, "stats_behavioral_vs_sat_metrics.csv")
    result_df.to_csv(out_path, index=False)
    print(f"\nSaved: {out_path}")

    _save_reg2_heatmap(result_df, out_dir)
    return result_df


def _save_reg2_heatmap(result_df: pd.DataFrame, out_dir: str) -> None:
    """Same visual pattern as moderation_analysis.py's plot_moderation_heatmap
    (rows=outcome, cols=SAT metric, color=Wald z-statistic since units are
    incompatible across both axes, cell text=raw beta+stars) -- reimplemented
    locally per this repo's no-cross-import convention, not imported."""
    outcomes = BEHAVIORAL_FEATURES
    z_mat = np.full((len(outcomes), len(SAT_METRICS)), np.nan)
    annot = np.empty((len(outcomes), len(SAT_METRICS)), dtype=object)

    for i, outcome in enumerate(outcomes):
        for j, metric in enumerate(SAT_METRICS):
            row = result_df[(result_df["outcome"] == outcome) & (result_df["predictor"] == metric)]
            if row.empty:
                annot[i, j] = ""
                continue
            r = row.iloc[0]
            z_mat[i, j] = r["z"]
            annot[i, j] = f"{r['coef']:.3f}{_sig_stars(r['p'])}\n(p={r['p']:.3f})"

    fig, ax = plt.subplots(figsize=(7, max(3, len(outcomes) * 0.9)))
    vmax = np.nanmax(np.abs(z_mat)) or 1
    im = ax.imshow(z_mat, cmap="RdBu_r", vmin=-vmax, vmax=vmax, aspect="auto")
    ax.grid(which="major", visible=False)  # apply_style's major grid would bisect cells at their centers
    ax.set_xticks(range(len(SAT_METRICS)))
    ax.set_xticklabels([METRIC_LABELS[m] for m in SAT_METRICS])
    ax.set_yticks(range(len(outcomes)))
    ax.set_yticklabels(outcomes)

    for i in range(len(outcomes)):
        for j in range(len(SAT_METRICS)):
            if annot[i, j] == "":
                continue
            text_color = "white" if abs(z_mat[i, j]) > vmax * 0.5 else "black"
            ax.text(j, i, annot[i, j], ha="center", va="center", fontsize=7.5, color=text_color)

    fig.colorbar(im, ax=ax, label="z-statistic (coef / SE)")
    fig.tight_layout()
    fname = "behavioral_reg2_heatmap.png"
    fig.savefig(os.path.join(out_dir, fname), dpi=150, bbox_inches="tight")
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

    apply_style()

    if not os.path.exists(args.features_csv):
        print(f"Features CSV not found: {args.features_csv}")
        print("Run extract_behavioral_features.py first.")
        return

    os.makedirs(args.out_dir, exist_ok=True)
    df = load_features(args.features_csv)
    solver = load_solver_stats(args.solver_csv)

    print(f"Loaded {len(df)} rows from {args.features_csv}")
    print(f"Puzzles: {sorted(df['puzzle_id'].dropna().unique().astype(int).tolist())}")

    vif_df = compute_vif(df, BEHAVIORAL_FEATURES)
    print("\nVariance inflation factors (predictor collinearity, pooled complete-case data):")
    print(vif_df.to_string(index=False))
    vif_path = os.path.join(args.out_dir, "stats_behavioral_predictor_vif.csv")
    vif_df.to_csv(vif_path, index=False)
    print(f"Saved: {vif_path}")

    run_regression1(df, args.out_dir)
    run_regression1_pooled(df, args.out_dir)

    merged = df.merge(solver, on="puzzle_id", how="left")
    run_regression2(merged, args.out_dir)

    print("\nDone.")


if __name__ == "__main__":
    main()
