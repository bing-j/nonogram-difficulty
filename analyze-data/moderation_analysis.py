"""
Moderation analysis: does participant expertise change *how strongly* SAT
solver metrics predict perceived puzzle difficulty?

A prior version of this script tested mediation (does expertise *explain*
the SAT-metric -> difficulty relationship?) and found none: expertise is a
participant trait fixed before a participant ever sees a puzzle, and puzzles
are assigned independent of expertise (round-robin schedule), so a
puzzle-level SAT metric structurally cannot cause expertise -- mediation
doesn't apply here. Moderation is the right frame instead: does the *slope*
relating SAT hardness to reported difficulty differ by expertise level, even
though expertise isn't caused by the metric?

Method: crossed-random-effects linear mixed model
---------------------------------------------------
final_difficulty ~ SAT_metric * expertise_composite, with CROSSED random
intercepts for participant_id and puzzle_id -- the standard specification
for "participant crossed with item" designs (Baayen, Davidson & Bates 2008,
J. Memory & Language), matching this study's structure exactly: every
participant rates 3 of 6 puzzles, and every puzzle is rated by many
participants, so participant and puzzle are crossed, non-nested sources of
non-independence. A single-participant-cluster bootstrap (this script's
previous approach) only corrects for the first; it silently ignores that the
SAT metric only takes 6 distinct values (one per puzzle) and is therefore
*also* clustered. The crossed-effects LMM here corrects for both at once and
reports the puzzle-level variance component explicitly rather than leaving
it unaddressed.

statsmodels' MixedLM has no native `(1|a) + (1|b)` crossed-random-effects
syntax (unlike R's lme4); the standard workaround is a constant dummy
`groups` column (re_formula="0", so it contributes no random effect of its
own) plus `vc_formula` supplying the two real (crossed) variance components,
one per grouping factor.

Simple slopes (Aiken & West 1991) replace a tercile split of expertise for
visualizing the interaction: dichotomizing a continuous moderator throws
away information and is a well-documented discouraged practice. Because
`expertise_composite` is already a population z-score (mean~=0, sd~=1 by
construction -- see expertise.py), "representative" expertise levels are
just z = -1, 0, +1 (no separate mean/SD computation needed). The slope of
SAT metric on difficulty at each level, and its delta-method CI from the
model's fixed-effect covariance matrix, replace the old per-tercile Spearman
rho.

Three limitations, disclosed rather than "fixed" (relevant for the paper):
  1. With only 6 puzzles, the puzzle-level variance component -- and any
     fixed effect involving the SAT metric -- has an irreducible small-sample
     bound. No statistical method removes this; the crossed-effects model
     just reports it honestly (as `var_puzzle` below) instead of hiding it
     behind participant-only clustering.
  2. statsmodels' MixedLM Wald inference is asymptotic (z-based), not
     Satterthwaite/Kenward-Roger small-sample-corrected like R's lmerTest.
     Worth a sensitivity cross-check in R if reviewers push on it; not
     implemented here to avoid a new R/rpy2 dependency.
  3. The same crossed-effects LMM is also fit against five behavioral
     outcomes (see "Behavioral outcomes" below) to check whether expertise
     moderates SAT-metric effects on behavior the way it does on reported
     difficulty. The model assumes Gaussian residuals; `final_difficulty` is
     an ~ordinal 1-5 rating it was designed for, but `pause_count`,
     `error_count`, and `hint_count` are non-negative counts and
     `time_to_solve_sec` is a right-skewed duration. Following this repo's
     existing convention (behavioral_regression.py's OLS, expertise_
     adjustment.py's Spearman correlations) of using these as raw
     untransformed continuous variables for consistency, rather than a
     script-specific log/Poisson/negative-binomial transform -- treat the
     behavioral-outcome p-values/CIs as approximate; a transformed or GLMM
     sensitivity check would be a natural follow-up if reviewers push on it.

Behavioral outcomes
--------------------
Same crossed-effects-LMM + simple-slopes test as above, run against the five
canonical behavioral signals (BEHAVIORAL_FEATURES, matching
behavioral_regression.py / expertise_adjustment.py) instead of
final_difficulty, so a reader can check whether expertise moderates SAT
metrics' effect on behavior the same way it moderates their effect on
reported difficulty. Combined with the final_difficulty results into one
comparison table/figure. This does not change the final_difficulty-only
outputs below, which stay exactly as they were (still feeding
analyze-data/latex/render_correlation_tables_latex.py).

Inputs
------
- analyze-data/out_features/behavioral_features.csv
- selected_six_nonogram_stats.csv

Outputs
-------
- analyze-data/out_features/stats_moderation_expertise.csv — one row per SAT metric
  (final_difficulty only)
- analyze-data/out_features/figures/moderation_expertise.png — interaction coefficient CI +
  simple-slopes plots (one per SAT metric, final_difficulty only)
- analyze-data/out_features/stats_moderation_behavioral.csv — one row per
  (outcome x SAT metric), final_difficulty + the 5 behavioral outcomes
- analyze-data/out_features/figures/moderation_behavioral_heatmap.png — interaction
  z-statistic heatmap comparing all 6 outcomes across the 3 SAT metrics

Usage
-----
  python analyze-data/moderation_analysis.py
  python analyze-data/moderation_analysis.py --features_csv ... --solver_csv ... --out_dir ...
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy.stats as stats
import statsmodels.formula.api as smf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from plot_style import (  # noqa: E402
    ACCENT_COLOR,
    ACCENT_TINT_DARK,
    ACCENT_TINT_LIGHT,
    NEUTRAL_COLOR,
    apply_style,
)

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FEATURES_CSV = REPO_ROOT / "analyze-data" / "out_features" / "behavioral_features.csv"
DEFAULT_SOLVER_CSV = REPO_ROOT / "selected_six_nonogram_stats.csv"
DEFAULT_OUT_DIR = REPO_ROOT / "analyze-data" / "out_features"

SAT_METRICS = ["decisions", "propagations", "conflicts"]
METRIC_LABELS = {
    "decisions": "Decisions",
    "propagations": "Propagations",
    "conflicts": "Conflicts",
}
M_COL = "expertise_composite"
Y_COL = "final_difficulty"
Z_LEVELS = {"low": -1.0, "mean": 0.0, "high": 1.0}
Z_SHADES = {"low": ACCENT_TINT_LIGHT, "mean": ACCENT_COLOR, "high": ACCENT_TINT_DARK}

# Same canonical list as behavioral_regression.py / expertise_adjustment.py.
BEHAVIORAL_FEATURES = ["pause_count", "time_to_solve_sec", "error_count", "hint_count"]
OUTCOME_LABELS = {
    "final_difficulty": "Final difficulty",
    "pause_count": "Pause count",
    "time_to_solve_sec": "Time to solve (s)",
    "error_count": "Error count",
    "hint_count": "Hint count",
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_features(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    for col in [Y_COL, M_COL] + BEHAVIORAL_FEATURES:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    # -1/0 is a missing-answer sentinel on the 1-5 Likert difficulty scale only;
    # 0 is legitimate real data for the behavioral count/duration outcomes.
    df[Y_COL] = df[Y_COL].where(df[Y_COL] >= 1, np.nan)
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
# Crossed-random-effects model
# ---------------------------------------------------------------------------

def fit_crossed_lmm(df: pd.DataFrame, x_col: str, y_col: str = Y_COL):
    """Fit y_col ~ x_col * expertise_composite with crossed random
    intercepts for participant_id and puzzle_id."""
    sub = df[[x_col, M_COL, y_col, "participant_id", "puzzle_id"]].dropna().copy()
    sub["participant_id"] = sub["participant_id"].astype(str)
    sub["puzzle_id"] = sub["puzzle_id"].astype(str)
    sub["_group"] = "1"  # dummy single group; real (crossed) REs come from vc_formula

    vc_formula = {
        "participant": "0 + C(participant_id)",
        "puzzle": "0 + C(puzzle_id)",
    }
    model = smf.mixedlm(
        f"{y_col} ~ {x_col} * {M_COL}",
        data=sub,
        groups="_group",
        re_formula="0",
        vc_formula=vc_formula,
    )
    result = model.fit(reml=True)
    return result, sub


def _fixed_effect(result, name: str) -> tuple[float, float, float, float, float]:
    coef = float(result.params[name])
    se = float(result.bse[name])
    p = float(result.pvalues[name])
    ci = result.conf_int().loc[name]
    return coef, se, p, float(ci[0]), float(ci[1])


def compute_simple_slopes(result, x_col: str) -> dict:
    """Simple slope of x_col at expertise z-levels, via the delta method on
    the model's fixed-effect covariance matrix (Aiken & West 1991)."""
    inter_name = f"{x_col}:{M_COL}"
    b1 = float(result.params[x_col])
    b3 = float(result.params[inter_name])
    cov = result.cov_params()
    var_b1 = float(cov.loc[x_col, x_col])
    var_b3 = float(cov.loc[inter_name, inter_name])
    cov_b1b3 = float(cov.loc[x_col, inter_name])

    slopes = {}
    for label, z in Z_LEVELS.items():
        slope = b1 + z * b3
        var_slope = var_b1 + (z ** 2) * var_b3 + 2 * z * cov_b1b3
        se_slope = np.sqrt(max(var_slope, 0.0))
        z_stat = slope / se_slope if se_slope > 0 else np.nan
        p = 2 * (1 - stats.norm.cdf(abs(z_stat))) if not np.isnan(z_stat) else np.nan
        slopes[label] = {
            "slope": slope, "se": se_slope, "p": float(p) if not np.isnan(p) else np.nan,
            "ci_lower": slope - 1.96 * se_slope, "ci_upper": slope + 1.96 * se_slope,
        }
    return slopes


def predicted_curve(result, x_col: str, x_vals: np.ndarray, z: float) -> tuple[np.ndarray, np.ndarray]:
    """Predicted difficulty ± SE (delta method) across x_vals, at a fixed
    expertise z-level, from the model's fixed effects."""
    names = ["Intercept", x_col, M_COL, f"{x_col}:{M_COL}"]
    b = result.params[names].values.astype(float)
    cov = result.cov_params().loc[names, names].values.astype(float)

    preds = np.empty(len(x_vals))
    ses = np.empty(len(x_vals))
    for i, xv in enumerate(x_vals):
        c = np.array([1.0, xv, z, xv * z])
        preds[i] = c @ b
        ses[i] = np.sqrt(max(c @ cov @ c, 0.0))
    return preds, ses


def fit_moderation(df: pd.DataFrame, x_col: str, y_col: str = Y_COL) -> dict:
    result, sub = fit_crossed_lmm(df, x_col, y_col=y_col)

    coef_metric, se_metric, p_metric, ci_lo_metric, ci_hi_metric = _fixed_effect(result, x_col)
    coef_expertise, se_expertise, p_expertise, ci_lo_expertise, ci_hi_expertise = _fixed_effect(result, M_COL)
    interaction, se_interaction, p_interaction, ci_lo_interaction, ci_hi_interaction = _fixed_effect(
        result, f"{x_col}:{M_COL}"
    )

    var_participant = float(result.vcomp[0])
    var_puzzle = float(result.vcomp[1])
    var_residual = float(result.scale)

    row = {
        "predictor": x_col,
        "coef_metric": coef_metric, "se_metric": se_metric, "p_metric": p_metric,
        "ci_lower_metric": ci_lo_metric, "ci_upper_metric": ci_hi_metric,
        "coef_expertise": coef_expertise, "se_expertise": se_expertise, "p_expertise": p_expertise,
        "ci_lower_expertise": ci_lo_expertise, "ci_upper_expertise": ci_hi_expertise,
        "interaction": interaction, "se_interaction": se_interaction, "p_interaction": p_interaction,
        "ci_lower_interaction": ci_lo_interaction, "ci_upper_interaction": ci_hi_interaction,
        "var_participant": var_participant, "var_puzzle": var_puzzle, "var_residual": var_residual,
        "n": len(sub), "n_participants": sub["participant_id"].nunique(),
        "n_puzzles": sub["puzzle_id"].nunique(),
    }

    slopes = compute_simple_slopes(result, x_col)
    for label, s in slopes.items():
        row[f"slope_{label}"] = s["slope"]
        row[f"se_slope_{label}"] = s["se"]
        row[f"p_slope_{label}"] = s["p"]
        row[f"ci_lower_slope_{label}"] = s["ci_lower"]
        row[f"ci_upper_slope_{label}"] = s["ci_upper"]

    return row, result, sub


# ---------------------------------------------------------------------------
# Summary table
# ---------------------------------------------------------------------------

def _sig_stars(p: float) -> str:
    if p is None or np.isnan(p):
        return ""
    if p < 0.001:
        return "***"
    if p < 0.01:
        return "**"
    if p < 0.05:
        return "*"
    return "ns"


def print_moderation_summary(row: dict, result, y_col: str = Y_COL) -> None:
    outcome_label = OUTCOME_LABELS.get(y_col, y_col)
    print(f"\n{'='*72}")
    print(f"MODERATION (crossed-effects LMM): {row['predictor']} x expertise -> {outcome_label}")
    print(f"{'='*72}")
    print(f"  N={row['n']}  participants={row['n_participants']}  puzzles={row['n_puzzles']}")
    print(f"  Metric coef:       {row['coef_metric']:>+10.6f}  SE={row['se_metric']:.6f}  p={row['p_metric']:.4f} {_sig_stars(row['p_metric'])}"
          f"  95% CI [{row['ci_lower_metric']:+.6f}, {row['ci_upper_metric']:+.6f}]")
    print(f"  Expertise coef:    {row['coef_expertise']:>+10.6f}  SE={row['se_expertise']:.6f}  p={row['p_expertise']:.4f} {_sig_stars(row['p_expertise'])}"
          f"  95% CI [{row['ci_lower_expertise']:+.6f}, {row['ci_upper_expertise']:+.6f}]")
    print(f"  Interaction coef:  {row['interaction']:>+10.6f}  SE={row['se_interaction']:.6f}  p={row['p_interaction']:.4f} {_sig_stars(row['p_interaction'])}"
          f"  95% CI [{row['ci_lower_interaction']:+.6f}, {row['ci_upper_interaction']:+.6f}]")
    print(f"  Variance components: participant={row['var_participant']:.4f}  puzzle={row['var_puzzle']:.4f}  residual={row['var_residual']:.4f}")
    print(f"  Simple slopes (metric -> {outcome_label}) at expertise z-levels:")
    for label in Z_LEVELS:
        print(
            f"    z={Z_LEVELS[label]:+.0f} ({label:>4}): slope={row[f'slope_{label}']:>+10.6f}"
            f"  SE={row[f'se_slope_{label}']:.6f}  p={row[f'p_slope_{label}']:.4f} {_sig_stars(row[f'p_slope_{label}'])}"
            f"  95% CI [{row[f'ci_lower_slope_{label}']:+.6f}, {row[f'ci_upper_slope_{label}']:+.6f}]"
        )
    print("\n  Full model summary:")
    print(result.summary())


def run_moderation(df: pd.DataFrame, out_dir: Path) -> tuple[pd.DataFrame, dict, dict]:
    rows = []
    fitted = {}
    data = {}
    for metric in SAT_METRICS:
        row, result, sub = fit_moderation(df, metric)
        print_moderation_summary(row, result)
        rows.append(row)
        fitted[metric] = result
        data[metric] = sub

    result_df = pd.DataFrame(rows)
    out_path = out_dir / "stats_moderation_expertise.csv"
    result_df.to_csv(out_path, index=False)
    print(f"\n  Saved: {out_path}")
    return result_df, fitted, data


def run_behavioral_moderation(
    df: pd.DataFrame, out_dir: Path, difficulty_result_df: pd.DataFrame
) -> pd.DataFrame:
    """Run the same crossed-effects-LMM moderation test against the five
    behavioral outcomes, combined with the already-computed final_difficulty
    rows so the two are directly comparable in one table."""
    rows = [{"outcome": Y_COL, **r} for r in difficulty_result_df.to_dict(orient="records")]

    for outcome in BEHAVIORAL_FEATURES:
        for metric in SAT_METRICS:
            row, result, _ = fit_moderation(df, metric, y_col=outcome)
            print_moderation_summary(row, result, y_col=outcome)
            rows.append({"outcome": outcome, **row})

    combined_df = pd.DataFrame(rows)
    out_path = out_dir / "stats_moderation_behavioral.csv"
    combined_df.to_csv(out_path, index=False)
    print(f"\n  Saved: {out_path}")
    return combined_df


def print_behavioral_comparison(combined_df: pd.DataFrame) -> None:
    """Quick textual answer to 'does the moderation pattern for behavioral
    outcomes look similar to the one for final_difficulty?'"""
    print(f"\n{'=' * 72}")
    print("BEHAVIORAL vs. DIFFICULTY: interaction sign/significance comparison")
    print(f"{'=' * 72}")
    diff_by_metric = {
        r["predictor"]: r
        for r in combined_df[combined_df["outcome"] == Y_COL].to_dict(orient="records")
    }
    for outcome in BEHAVIORAL_FEATURES:
        print(f"\n  {OUTCOME_LABELS[outcome]}:")
        for metric in SAT_METRICS:
            row = combined_df[(combined_df["outcome"] == outcome) & (combined_df["predictor"] == metric)].iloc[0]
            diff_row = diff_by_metric[metric]
            same_sign = np.sign(row["interaction"]) == np.sign(diff_row["interaction"])
            flag = "same direction as difficulty" if same_sign else "OPPOSITE direction from difficulty"
            print(
                f"    {METRIC_LABELS[metric]:<13} interaction={row['interaction']:>+9.5f}"
                f"  p={row['p_interaction']:.4f} {_sig_stars(row['p_interaction']):<3}  ({flag})"
            )


# ---------------------------------------------------------------------------
# Visualisation
# ---------------------------------------------------------------------------

def plot_moderation(result_df: pd.DataFrame, fitted: dict, data: dict, fig_dir: Path) -> None:
    fig, axes = plt.subplots(1, 1 + len(SAT_METRICS), figsize=(4.5 * (1 + len(SAT_METRICS)), 4.5))
    ax_interaction = axes[0]

    labels = [METRIC_LABELS.get(p, p) for p in result_df["predictor"]]
    x_pos = np.arange(len(result_df))
    yerr = np.vstack([
        result_df["interaction"] - result_df["ci_lower_interaction"],
        result_df["ci_upper_interaction"] - result_df["interaction"],
    ])
    ax_interaction.errorbar(
        x_pos, result_df["interaction"], yerr=yerr,
        fmt="o", color=NEUTRAL_COLOR, ecolor=NEUTRAL_COLOR,
        capsize=4, markersize=7,
    )
    ax_interaction.axhline(0.0, color="black", linewidth=0.8, linestyle="--", alpha=0.6)
    ax_interaction.set_xticks(x_pos)
    ax_interaction.set_xticklabels(labels)
    ax_interaction.set_ylabel("Interaction coef. (metric × expertise) ± 95% CI")
    ax_interaction.set_title("Crossed-effects LMM\ninteraction estimate")

    for ax, metric in zip(axes[1:], SAT_METRICS):
        result = fitted[metric]
        sub = data[metric]
        ax.scatter(sub[metric], sub[Y_COL], color=NEUTRAL_COLOR, alpha=0.15, s=25, zorder=1)

        x_vals = np.linspace(sub[metric].min(), sub[metric].max(), 50)
        for label, z in Z_LEVELS.items():
            preds, ses = predicted_curve(result, metric, x_vals, z)
            ax.plot(x_vals, preds, color=Z_SHADES[label], linewidth=2, label=f"expertise z={z:+.0f}", zorder=3)
            ax.fill_between(x_vals, preds - 1.96 * ses, preds + 1.96 * ses, color=Z_SHADES[label], alpha=0.15, zorder=2)

        ax.set_xlabel(METRIC_LABELS.get(metric, metric), fontsize=9)
        ax.set_ylabel("Predicted final_difficulty", fontsize=9)
        ax.set_title(f"Simple slopes: {METRIC_LABELS.get(metric, metric)}", fontsize=10)
        ax.legend(fontsize=7, loc="best")

    fig.tight_layout()
    out_path = fig_dir / "moderation_expertise.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {out_path}")


def plot_moderation_heatmap(combined_df: pd.DataFrame, fig_dir: Path) -> None:
    """Interaction-coefficient comparison across all 6 outcomes x 3 SAT metrics.

    Outcomes span incompatible units (Likert points, seconds, raw counts), so
    coloring by the raw interaction coefficient would just be dominated by
    time_to_solve_sec. Color by the Wald z-statistic (interaction / SE)
    instead -- unit-free, still centered at 0, magnitude already reflects
    significance -- and annotate each cell with the outcome's own raw beta
    (native units) + significance stars so exact effect sizes stay visible.
    """
    outcomes = [Y_COL] + BEHAVIORAL_FEATURES
    z_mat = np.full((len(outcomes), len(SAT_METRICS)), np.nan)
    annot = np.empty((len(outcomes), len(SAT_METRICS)), dtype=object)

    for i, outcome in enumerate(outcomes):
        for j, metric in enumerate(SAT_METRICS):
            row = combined_df[(combined_df["outcome"] == outcome) & (combined_df["predictor"] == metric)]
            if row.empty:
                annot[i, j] = ""
                continue
            r = row.iloc[0]
            z_mat[i, j] = r["interaction"] / r["se_interaction"] if r["se_interaction"] > 0 else np.nan
            annot[i, j] = f"{r['interaction']:.3f}{_sig_stars(r['p_interaction'])}\n(p={r['p_interaction']:.3f})"

    fig, ax = plt.subplots(figsize=(7, max(3, len(outcomes) * 0.9)))
    vmax = np.nanmax(np.abs(z_mat)) or 1
    im = ax.imshow(z_mat, cmap="RdBu_r", vmin=-vmax, vmax=vmax, aspect="auto")
    ax.grid(which="major", visible=False)  # apply_style's major grid would bisect cells at their centers
    ax.set_xticks(range(len(SAT_METRICS)))
    ax.set_xticklabels([METRIC_LABELS[m] for m in SAT_METRICS])
    ax.set_yticks(range(len(outcomes)))
    ax.set_yticklabels([OUTCOME_LABELS[o] for o in outcomes])

    for i in range(len(outcomes)):
        for j in range(len(SAT_METRICS)):
            if annot[i, j] == "":
                continue
            text_color = "white" if abs(z_mat[i, j]) > vmax * 0.5 else "black"
            ax.text(j, i, annot[i, j], ha="center", va="center", fontsize=7.5, color=text_color)

    fig.colorbar(im, ax=ax, label="Interaction z-statistic (beta / SE)")
    fig.text(0.01, -0.02, "* p<.05   ** p<.01   *** p<.001   cell text: raw beta, native units", fontsize=8, ha="left")
    fig.tight_layout()
    out_path = fig_dir / "moderation_behavioral_heatmap.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {out_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Moderation analysis: does expertise change the SAT metric -> difficulty slope?"
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

    print("=" * 60)
    print("NONOGRAM DIFFICULTY — MODERATION: EXPERTISE x SAT METRIC")
    print("=" * 60)

    features_df = load_features(args.features_csv)
    solver_df = load_solver_stats(args.solver_csv)
    merged = features_df.merge(solver_df, on="puzzle_id", how="left")

    print(f"\nLoaded {len(merged)} rows, "
          f"{merged['participant_id'].nunique()} participants, "
          f"puzzles {sorted(merged['puzzle_id'].unique().tolist())}")
    print(f"expertise_composite: mean={merged[M_COL].mean():.3f}  sd={merged[M_COL].std():.3f} "
          "(should be ~0/~1 by construction; z-levels below assume this)")

    result_df, fitted, data = run_moderation(merged, args.out_dir)

    print("\nGenerating figure...")
    plot_moderation(result_df, fitted, data, fig_dir)

    print("\n" + "=" * 60)
    print("BEHAVIORAL OUTCOMES: same moderation test, 5 behavioral signals")
    print("=" * 60)
    combined_df = run_behavioral_moderation(merged, args.out_dir, result_df)
    print_behavioral_comparison(combined_df)

    print("\nGenerating comparison heatmap...")
    plot_moderation_heatmap(combined_df, fig_dir)

    print("\nDone.")


if __name__ == "__main__":
    main()
