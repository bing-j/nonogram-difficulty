"""
Step 05 - How should reported & behavioural difficulty be adjusted for the
participant's reported expertise so comparisons are fair?

We motivate the problem (expertise predicts ratings & behaviour) and then
implement and COMPARE five adjustment strategies, reporting numbers + figures:

  M0. Raw                      no adjustment (baseline)
  M1. Within-participant       centre each participant's 3 ratings/behaviours
  M2. Residualization          regress outcome ~ expertise (+order); use residual
  M3. Covariate model          mixed model outcome ~ C(puzzle)+expertise+C(order)
                               with a participant random intercept; report the
                               expertise coefficient and expertise-adjusted
                               (marginal) puzzle difficulty
  M4. Stratification           difficulty estimated within expertise tiers
  M5. Expertise x SAT          does expertise moderate the conflicts->difficulty
                               relationship?

Adjustments are applied both to the subjective rating and to behavioural
"difficulty" proxies (solve time, hints). Read-only w.r.t. the repository.
"""

from __future__ import annotations

from analysis_utils import DERIVED, FIG_DIR, PALETTE  # sets MPLCONFIGDIR before mpl

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats

from nono_data import load_participant_puzzle_df, load_solver_stats

ADJ_FIG = FIG_DIR / "expertise_adjustment"
ADJ_FIG.mkdir(parents=True, exist_ok=True)

EXPERTISE = "exp_zmean_z"   # primary composite (robust; matches PCA/FA)


# --------------------------------------------------------------------------- #
def load_modeling_frame() -> pd.DataFrame:
    base = load_participant_puzzle_df()
    exp = pd.read_csv(DERIVED / "participant_expertise.csv")
    df = base.merge(exp[["participant_id", "exp_zmean_z", "exp_pca", "exp_fa", "expertise_tier"]],
                    on="participant_id", how="left")

    sat = load_solver_stats()
    mini = sat[sat["solver"] == "MiniSat22"][["puzzle_id", "conflicts", "decisions", "propagations"]]
    mini = mini.rename(columns={"conflicts": "mini_conflicts", "decisions": "mini_decisions",
                                "propagations": "mini_propagations"})
    glu = sat[sat["solver"] == "Glucose42"][["puzzle_id", "conflicts"]].rename(
        columns={"conflicts": "glu_conflicts"})
    df = df.merge(mini, on="puzzle_id", how="left").merge(glu, on="puzzle_id", how="left")
    df["log_mini_conflicts"] = np.log1p(df["mini_conflicts"])
    return df


def spearman(x: pd.Series, y: pd.Series) -> tuple[float, float, int]:
    d = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(d) < 3 or d["x"].nunique() < 2 or d["y"].nunique() < 2:
        return float("nan"), float("nan"), len(d)
    rho, p = stats.spearmanr(d["x"], d["y"])
    return float(rho), float(p), len(d)


# --------------------------------------------------------------------------- #
def motivation(df: pd.DataFrame) -> pd.DataFrame:
    """Does expertise predict difficulty/behaviour? (justifies adjustment)"""
    perf = df.groupby("participant_id").agg(
        expertise=(EXPERTISE, "first"),
        mean_difficulty=("final_difficulty", "mean"),
        mean_time=("time_to_solve", "mean"),
        mean_hints=("n_hints", "mean"),
        mean_incorrect=("n_incorrect_submissions", "mean"),
        solve_rate=("solved", "mean"),
        mean_rating_change=("rating_change", "mean"),
        mean_actions=("n_actions", "mean"),
        mean_pause_count=("pause_count", "mean"),
        mean_pause_freq=("pause_freq_per_min", "mean"),
    ).reset_index()

    rows = []
    specs = [("mean_difficulty", "Mean difficulty rating"), ("mean_time", "Mean solve time (s)"),
             ("mean_hints", "Mean hints used"), ("mean_incorrect", "Mean incorrect subs"),
             ("solve_rate", "Solve rate"), ("mean_rating_change", "Mean rating change"),
             ("mean_actions", "Mean actions"),
             ("mean_pause_count", "Mean pause count"),
             ("mean_pause_freq", "Mean pause freq/min")]
    for col, lbl in specs:
        rho, p, n = spearman(perf["expertise"], perf[col])
        r = perf[["expertise", col]].dropna()
        pr = stats.pearsonr(r["expertise"], r[col]) if len(r) > 2 else (np.nan, np.nan)
        rows.append({"outcome": lbl, "column": col, "spearman_rho": rho, "spearman_p": p,
                     "pearson_r": float(pr[0]), "pearson_p": float(pr[1]), "n": n})
    stat = pd.DataFrame(rows)
    stat.to_csv(DERIVED / "stats_expertise_vs_outcomes.csv", index=False)

    plot_specs = [(col, lbl) for col, lbl in specs
                  if col not in ("mean_incorrect", "mean_rating_change", "mean_actions")]

    fig, axes = plt.subplots(2, 3, figsize=(15, 9), dpi=150)
    for ax, (col, lbl) in zip(axes.ravel(), plot_specs):
        d = perf[["expertise", col]].dropna()
        ax.scatter(d["expertise"], d[col], color=PALETTE[0], alpha=0.6)
        if len(d) > 3 and d["expertise"].nunique() > 1:
            m, b = np.polyfit(d["expertise"], d[col], 1)
            xs = np.array([d["expertise"].min(), d["expertise"].max()])
            ax.plot(xs, m * xs + b, "--", color="#b8531f")
            rho, p, _ = spearman(d["expertise"], d[col])
            ax.set_title(f"{lbl}\nSpearman rho={rho:.2f}, p={p:.3f}", fontsize=10)
        ax.set_xlabel("Composite expertise (z)")
        ax.set_ylabel(lbl)
        ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(ADJ_FIG / "01_expertise_vs_outcomes.png", bbox_inches="tight")
    plt.close(fig)
    return stat


# --------------------------------------------------------------------------- #
def puzzle_difficulty_methods(df: pd.DataFrame) -> pd.DataFrame:
    """Estimate per-puzzle difficulty under M0/M1/M2/M3 and correlate with SAT."""
    work = df.dropna(subset=["final_difficulty"]).copy()

    # M0 raw mean
    m0 = work.groupby("puzzle_id")["final_difficulty"].mean().rename("M0_raw")

    # M1 within-participant centred (then add grand mean back for interpretability)
    grand = work["final_difficulty"].mean()
    work["wp_centered"] = work.groupby("participant_id")["final_difficulty"].transform(
        lambda s: s - s.mean()) + grand
    m1 = work.groupby("puzzle_id")["wp_centered"].mean().rename("M1_within_participant")

    # M2 residualization: difficulty ~ expertise + C(order); puzzle mean of residual + grand mean
    res_df = work.dropna(subset=[EXPERTISE]).copy()
    ols = smf.ols(f"final_difficulty ~ {EXPERTISE} + C(order)", data=res_df).fit()
    res_df["resid_adj"] = ols.resid + grand
    m2 = res_df.groupby("puzzle_id")["resid_adj"].mean().rename("M2_residualized")

    # M3 mixed model marginal means at mean expertise (=0), averaged over order
    mm = smf.mixedlm(f"final_difficulty ~ C(puzzle_id) + {EXPERTISE} + C(order)",
                     data=res_df, groups=res_df["participant_id"]).fit()
    puzzles = sorted(res_df["puzzle_id"].unique())
    grid = pd.DataFrame([(p, o) for p in puzzles for o in [1, 2, 3]], columns=["puzzle_id", "order"])
    grid[EXPERTISE] = 0.0
    grid_pred = mm.predict(grid)
    grid["pred"] = grid_pred.values
    m3 = grid.groupby("puzzle_id")["pred"].mean().rename("M3_mixed_emm")

    out = pd.concat([m0, m1, m2, m3], axis=1).reset_index()
    sat = df.groupby("puzzle_id")[["mini_conflicts", "log_mini_conflicts", "glu_conflicts",
                                   "mini_decisions", "mini_propagations"]].first().reset_index()
    out = out.merge(sat, on="puzzle_id", how="left")
    out.to_csv(DERIVED / "puzzle_difficulty_by_method.csv", index=False)

    # Correlate each method's difficulty with SAT conflicts (primary proxy)
    rows = []
    for method in ["M0_raw", "M1_within_participant", "M2_residualized", "M3_mixed_emm"]:
        for sat_col, sat_lbl in [("mini_conflicts", "MiniSat conflicts"),
                                 ("log_mini_conflicts", "log MiniSat conflicts"),
                                 ("glu_conflicts", "Glucose conflicts")]:
            rho, p, n = spearman(out[method], out[sat_col])
            rows.append({"difficulty_method": method, "sat_metric": sat_lbl,
                         "spearman_rho": rho, "spearman_p": p, "n_puzzles": n})
    corr = pd.DataFrame(rows)
    corr.to_csv(DERIVED / "stats_difficulty_method_vs_sat.csv", index=False)

    # Figure: puzzle difficulty under each method + ranking stability
    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5), dpi=150)
    methods = ["M0_raw", "M1_within_participant", "M2_residualized", "M3_mixed_emm"]
    width = 0.2
    xpos = np.arange(len(out))
    for i, m in enumerate(methods):
        axes[0].bar(xpos + i * width, out[m], width, label=m, color=PALETTE[i])
    axes[0].set_xticks(xpos + 1.5 * width)
    axes[0].set_xticklabels([f"P{int(p)}" for p in out["puzzle_id"]])
    axes[0].set_ylabel("Estimated puzzle difficulty (1-5 scale)")
    axes[0].set_xlabel("Puzzle")
    axes[0].set_title("Per-puzzle difficulty under four adjustment methods")
    axes[0].set_ylim(out[methods].min().min() - 0.3, out[methods].max().max() + 0.3)
    axes[0].legend(fontsize=8)
    axes[0].grid(axis="y", alpha=0.25)

    # right: difficulty vs conflicts, M0 vs M3
    axes[1].scatter(out["mini_conflicts"], out["M0_raw"], color=PALETTE[0], s=60, label="M0 raw")
    axes[1].scatter(out["mini_conflicts"], out["M3_mixed_emm"], color=PALETTE[3], s=60, label="M3 adjusted")
    for _, r in out.iterrows():
        axes[1].annotate(f"P{int(r['puzzle_id'])}", (r["mini_conflicts"], r["M0_raw"]),
                         textcoords="offset points", xytext=(5, 3), fontsize=8)
    axes[1].set_xlabel("MiniSat conflicts")
    axes[1].set_ylabel("Puzzle difficulty")
    axes[1].set_title("Difficulty vs SAT conflicts (raw vs expertise-adjusted)")
    axes[1].legend(); axes[1].grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(ADJ_FIG / "02_puzzle_difficulty_methods.png", bbox_inches="tight")
    plt.close(fig)

    # report mixed-model fixed effects
    mm_summary = pd.DataFrame({
        "term": mm.params.index, "coef": mm.params.values,
        "se": mm.bse.values, "p_value": mm.pvalues.values,
    })
    mm_summary.to_csv(DERIVED / "mixed_model_difficulty_params.csv", index=False)
    return out, corr, mm, mm_summary


# --------------------------------------------------------------------------- #
def stratified_difficulty(df: pd.DataFrame) -> pd.DataFrame:
    work = df.dropna(subset=["final_difficulty", "expertise_tier"]).copy()
    tab = work.groupby(["puzzle_id", "expertise_tier"], observed=True)["final_difficulty"].mean().unstack()
    tab.to_csv(DERIVED / "stratified_puzzle_difficulty_by_tier.csv")

    sat = df.groupby("puzzle_id")["mini_conflicts"].first()
    fig, ax = plt.subplots(figsize=(9, 5.5), dpi=160)
    order_by_conflict = sat.sort_values().index.tolist()
    for i, tier in enumerate(["novice", "intermediate", "expert"]):
        if tier in tab.columns:
            ax.plot([f"P{int(p)}" for p in order_by_conflict],
                    [tab.loc[p, tier] if p in tab.index else np.nan for p in order_by_conflict],
                    "o-", color=PALETTE[i], label=tier)
    ax.set_xlabel("Puzzle (ordered by increasing SAT conflicts ->)")
    ax.set_ylabel("Mean difficulty rating")
    ax.set_title("Expertise-stratified puzzle difficulty")
    ax.legend(); ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(ADJ_FIG / "03_stratified_difficulty.png", bbox_inches="tight")
    plt.close(fig)

    # within-tier Spearman(difficulty, conflicts)
    rows = []
    for tier in ["novice", "intermediate", "expert"]:
        if tier in tab.columns:
            merged = pd.DataFrame({"diff": tab[tier], "conf": sat}).dropna()
            rho, p, n = spearman(merged["diff"], merged["conf"])
            rows.append({"tier": tier, "spearman_rho_diff_vs_conflicts": rho, "p_value": p, "n_puzzles": n})
    pd.DataFrame(rows).to_csv(DERIVED / "stats_stratified_difficulty_vs_sat.csv", index=False)
    return tab


# --------------------------------------------------------------------------- #
def interaction_model(df: pd.DataFrame) -> pd.DataFrame:
    work = df.dropna(subset=["final_difficulty", EXPERTISE, "log_mini_conflicts"]).copy()
    work["conflicts_z"] = (work["log_mini_conflicts"] - work["log_mini_conflicts"].mean()) / \
        work["log_mini_conflicts"].std(ddof=0)
    # OLS with participant-clustered SE
    model = smf.ols(f"final_difficulty ~ conflicts_z * {EXPERTISE} + C(order)", data=work).fit(
        cov_type="cluster", cov_kwds={"groups": work["participant_id"]})
    summ = pd.DataFrame({"term": model.params.index, "coef": model.params.values,
                         "se": model.bse.values, "p_value": model.pvalues.values})
    summ.to_csv(DERIVED / "stats_expertise_sat_interaction.csv", index=False)

    # figure: difficulty vs conflicts by tier with slopes
    fig, ax = plt.subplots(figsize=(9, 5.5), dpi=160)
    for i, tier in enumerate(["novice", "intermediate", "expert"]):
        sub = work[work["expertise_tier"] == tier]
        if len(sub) < 3:
            continue
        jit = sub["mini_conflicts"] + np.random.uniform(-0.4, 0.4, len(sub))
        ax.scatter(jit, sub["final_difficulty"] + np.random.uniform(-0.1, 0.1, len(sub)),
                   color=PALETTE[i], alpha=0.5, label=tier)
        m, b = np.polyfit(sub["mini_conflicts"], sub["final_difficulty"], 1)
        xs = np.array([work["mini_conflicts"].min(), work["mini_conflicts"].max()])
        ax.plot(xs, m * xs + b, "-", color=PALETTE[i], lw=2)
    ax.set_xlabel("MiniSat conflicts (puzzle)")
    ax.set_ylabel("Difficulty rating")
    ax.set_title("Does expertise moderate the conflicts->difficulty link?")
    ax.legend(); ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(ADJ_FIG / "04_expertise_sat_interaction.png", bbox_inches="tight")
    plt.close(fig)
    return summ


# --------------------------------------------------------------------------- #
def behavioural_adjustment(df: pd.DataFrame) -> pd.DataFrame:
    """Apply residualization to behavioural difficulty proxies and compare to raw."""
    work = df.dropna(subset=[EXPERTISE]).copy()
    rows = []
    for col in ["time_to_solve", "n_hints", "n_incorrect_submissions", "n_actions"]:
        sub = work.dropna(subset=[col]).copy()
        # raw puzzle means vs conflicts
        raw = sub.groupby("puzzle_id")[col].mean()
        # expertise-residualized
        ols = smf.ols(f"{col} ~ {EXPERTISE} + C(order)", data=sub).fit()
        sub["resid"] = ols.resid
        adj = sub.groupby("puzzle_id")["resid"].mean()
        conf = df.groupby("puzzle_id")["mini_conflicts"].first()
        rho_raw, p_raw, n = spearman(raw, conf)
        rho_adj, p_adj, _ = spearman(adj, conf)
        rows.append({"behaviour": col,
                     "expertise_coef": ols.params.get(EXPERTISE, np.nan),
                     "expertise_p": ols.pvalues.get(EXPERTISE, np.nan),
                     "raw_spearman_vs_conflicts": rho_raw, "raw_p": p_raw,
                     "adjusted_spearman_vs_conflicts": rho_adj, "adjusted_p": p_adj,
                     "n_puzzles": n})
    out = pd.DataFrame(rows)
    out.to_csv(DERIVED / "stats_behavioural_adjustment.csv", index=False)
    return out


# --------------------------------------------------------------------------- #
def main() -> None:
    np.random.seed(0)
    df = load_modeling_frame()

    print("=== EXPERTISE ADJUSTMENT ===\n")
    mot = motivation(df)
    print("Expertise vs outcomes:\n", mot.to_string(index=False))

    out, corr, mm, mm_summary = puzzle_difficulty_methods(df)
    print("\nPuzzle difficulty by method:\n", out[["puzzle_id", "M0_raw", "M1_within_participant",
                                                   "M2_residualized", "M3_mixed_emm",
                                                   "mini_conflicts"]].to_string(index=False))
    print("\nDifficulty-method vs SAT correlations:\n", corr.to_string(index=False))
    print("\nMixed-model expertise coefficient:")
    print(mm_summary[mm_summary["term"].str.contains("exp_")].to_string(index=False))

    tab = stratified_difficulty(df)
    print("\nStratified difficulty by tier:\n", tab.to_string())

    inter = interaction_model(df)
    print("\nExpertise x SAT interaction:\n", inter.to_string(index=False))

    beh = behavioural_adjustment(df)
    print("\nBehavioural adjustment (raw vs expertise-adjusted vs conflicts):\n",
          beh.to_string(index=False))

    print(f"\nFigures -> {ADJ_FIG}")


if __name__ == "__main__":
    main()
