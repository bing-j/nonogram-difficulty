"""
Step 03 - Analyse the thematically coded open-text responses.

Produces figures (riyad-analysis/figures/) and statistics tables
(riyad-analysis/derived/) covering:

  1. Difficulty-theme prevalence + strategy prevalence.
  2. Code co-occurrence heatmaps (difficulty themes, strategies).
  3. Theme presence vs subjective difficulty rating (point-biserial + Mann-Whitney).
  4. Theme presence vs logged behaviour (convergent validity of self-report).
  5. Theme presence vs self-reported guessing frequency.
  6. Strategy use vs expertise & performance; strategy-repertoire breadth.

All inputs are read-only; nothing in the repo is modified.
"""

from __future__ import annotations

from pathlib import Path

from analysis_utils import DERIVED, FIG_DIR, PALETTE, benjamini_hochberg, group_compare  # sets MPLCONFIGDIR

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from codes import ALL_DIFFICULTY_CODES, ALL_STRATEGY_CODES, DIFFICULTY_THEMES, STRATEGY_TAXONOMY
from nono_data import load_participant_puzzle_df

TXT_FIG = FIG_DIR / "text"
TXT_FIG.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------- #
def label(code: str) -> str:
    if code in DIFFICULTY_THEMES:
        return DIFFICULTY_THEMES[code]["name"]
    return STRATEGY_TAXONOMY[code]["name"]


def prevalence_plot(coded: pd.DataFrame, code_cols: list[str], title: str, fname: str,
                    color: str) -> pd.DataFrame:
    n = len(coded)
    counts = {c: int(coded[f"code_{c}"].sum()) for c in code_cols}
    rows = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    labels = [f"{label(c)}" for c, _ in rows]
    vals = [v for _, v in rows]
    pct = [100.0 * v / n for v in vals]

    fig, ax = plt.subplots(figsize=(9, 5.5), dpi=160)
    ax.barh(range(len(rows)), pct, color=color)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlabel(f"% of coded responses mentioning theme (n = {n})")
    ax.set_title(title)
    for i, (v, p) in enumerate(zip(vals, pct)):
        ax.text(p + 0.5, i, f"{v} ({p:.0f}%)", va="center", fontsize=8)
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(TXT_FIG / fname, bbox_inches="tight")
    plt.close(fig)

    return pd.DataFrame({"code": [c for c, _ in rows], "theme": labels,
                         "count": vals, "pct_of_coded": pct})


def cooccurrence_plot(coded: pd.DataFrame, code_cols: list[str], title: str, fname: str) -> None:
    mat = coded[[f"code_{c}" for c in code_cols]].to_numpy()
    k = len(code_cols)
    # Jaccard similarity between codes.
    jac = np.zeros((k, k))
    for i in range(k):
        for j in range(k):
            a = mat[:, i].astype(bool)
            b = mat[:, j].astype(bool)
            union = (a | b).sum()
            jac[i, j] = (a & b).sum() / union if union else 0.0
    fig, ax = plt.subplots(figsize=(8, 7), dpi=160)
    im = ax.imshow(jac, cmap="viridis", vmin=0, vmax=1)
    ax.set_xticks(range(k))
    ax.set_yticks(range(k))
    ax.set_xticklabels(code_cols, rotation=45, ha="right", fontsize=8)
    ax.set_yticklabels([label(c) for c in code_cols], fontsize=8)
    for i in range(k):
        for j in range(k):
            if jac[i, j] >= 0.05:
                ax.text(j, i, f"{jac[i, j]:.2f}", ha="center", va="center",
                        color="white" if jac[i, j] < 0.6 else "black", fontsize=7)
    ax.set_title(title)
    fig.colorbar(im, ax=ax, label="Jaccard overlap")
    fig.tight_layout()
    fig.savefig(TXT_FIG / fname, bbox_inches="tight")
    plt.close(fig)


def theme_vs_outcome(attempts: pd.DataFrame, outcome: str, code_cols: list[str],
                     outcome_label: str) -> pd.DataFrame:
    """Compare an attempt-level outcome between theme-present vs absent."""
    rows = []
    for c in code_cols:
        present = attempts[f"code_{c}"] == 1
        if present.sum() < 3 or (~present).sum() < 3:
            continue
        res = group_compare(attempts[outcome], present)
        res.update({"code": c, "theme": label(c), "outcome": outcome_label})
        rows.append(res)
    df = pd.DataFrame(rows)
    if not df.empty:
        df["mw_p_fdr"] = benjamini_hochberg(df["mannwhitney_p"].tolist())
    return df


def outcome_effect_plot(stat_df: pd.DataFrame, outcome_label: str, fname: str) -> None:
    if stat_df.empty:
        return
    d = stat_df.sort_values("rank_biserial")
    colors = ["#b8531f" if p < 0.05 else "#9bb7c9" for p in d["mannwhitney_p"]]
    fig, ax = plt.subplots(figsize=(8.5, 5.5), dpi=160)
    ax.barh(range(len(d)), d["rank_biserial"], color=colors)
    ax.axvline(0, color="black", lw=0.8)
    ax.set_yticks(range(len(d)))
    ax.set_yticklabels(d["theme"])
    ax.set_xlabel(f"Rank-biserial effect (theme-present vs absent) on {outcome_label}\n"
                  "orange = Mann-Whitney p < .05")
    ax.set_title(f"Which difficulty themes track higher {outcome_label}?")
    for i, (rb, mp) in enumerate(zip(d["rank_biserial"], d["mannwhitney_p"])):
        ax.text(rb + (0.01 if rb >= 0 else -0.01), i, f"p={mp:.3f}",
                va="center", ha="left" if rb >= 0 else "right", fontsize=7)
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(TXT_FIG / fname, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    coded = pd.read_csv(DERIVED / "coded_responses.csv")
    base = load_participant_puzzle_df()

    # ---- 1. Prevalence ----------------------------------------------------- #
    diff_coded = coded[(coded["response_kind"].isin(["rating_reason", "comments"]))
                       & (coded["n_codes"] > 0)].copy()
    strat_coded = coded[(coded["response_kind"] == "strategy") & (coded["n_codes"] > 0)].copy()

    diff_prev = prevalence_plot(diff_coded, ALL_DIFFICULTY_CODES,
                                "Difficulty themes across all open-text difficulty explanations",
                                "01_difficulty_theme_prevalence.png", PALETTE[0])
    strat_prev = prevalence_plot(strat_coded, ALL_STRATEGY_CODES,
                                 "Solving strategies described by participants",
                                 "02_strategy_prevalence.png", PALETTE[2])
    diff_prev.to_csv(DERIVED / "stats_difficulty_theme_prevalence.csv", index=False)
    strat_prev.to_csv(DERIVED / "stats_strategy_prevalence.csv", index=False)

    # ---- 2. Co-occurrence -------------------------------------------------- #
    cooccurrence_plot(diff_coded, ALL_DIFFICULTY_CODES,
                      "Difficulty-theme co-occurrence (Jaccard)", "03_difficulty_cooccurrence.png")
    cooccurrence_plot(strat_coded, ALL_STRATEGY_CODES,
                      "Strategy co-occurrence (Jaccard)", "04_strategy_cooccurrence.png")

    # ---- 3+4. Theme vs difficulty & behaviour (attempt level) -------------- #
    # rating_reason is attempt-linked (participant_id + order). Merge behaviour.
    rr = coded[coded["response_kind"] == "rating_reason"].copy()
    rr["order"] = rr["order"].astype("Int64")
    attempts = base.merge(
        rr[["participant_id", "order", "n_codes"] + [f"code_{c}" for c in ALL_DIFFICULTY_CODES]],
        on=["participant_id", "order"], how="inner",
    )
    attempts = attempts[attempts["n_codes"] > 0].copy()

    # Within-participant centring of behaviour (preferred for this design).
    for col in ["time_to_solve", "n_actions", "n_hints", "n_incorrect_submissions", "final_difficulty"]:
        attempts[f"{col}_pc"] = attempts.groupby("participant_id")[col].transform(
            lambda s: s - s.mean())

    # difficulty rating
    diff_stat = theme_vs_outcome(attempts, "final_difficulty", ALL_DIFFICULTY_CODES, "final difficulty (1-5)")
    diff_stat.to_csv(DERIVED / "stats_theme_vs_difficulty.csv", index=False)
    outcome_effect_plot(diff_stat, "subjective difficulty", "05_theme_vs_difficulty.png")

    # behaviour (raw + participant-centred)
    behav_frames = []
    for col, lbl in [("time_to_solve", "solve time"), ("n_hints", "hints used"),
                     ("n_incorrect_submissions", "incorrect submissions"), ("n_actions", "actions")]:
        s_raw = theme_vs_outcome(attempts, col, ALL_DIFFICULTY_CODES, f"{lbl} (raw)")
        s_pc = theme_vs_outcome(attempts, f"{col}_pc", ALL_DIFFICULTY_CODES, f"{lbl} (within-participant)")
        behav_frames += [s_raw, s_pc]
    behav_stat = pd.concat(behav_frames, ignore_index=True)
    behav_stat.to_csv(DERIVED / "stats_theme_vs_behaviour.csv", index=False)

    # Convergent-validity figure: HINT theme -> hints; GUESS -> hints+incorrect; ERR -> cell errors.
    validity_pairs = [("HINT", "n_hints", "hints used"), ("GUESS", "n_hints", "hints used"),
                      ("GUESS", "n_incorrect_submissions", "incorrect subs"),
                      ("ERR", "n_cell_errors", "cell errors"),
                      ("AMBIG", "time_to_solve", "solve time"),
                      ("FOOT", "time_to_solve", "solve time")]
    fig, axes = plt.subplots(2, 3, figsize=(14, 8), dpi=150)
    val_rows = []
    for ax, (code, col, lbl) in zip(axes.ravel(), validity_pairs):
        present = attempts[f"code_{code}"] == 1
        a = pd.to_numeric(attempts.loc[present, col], errors="coerce").dropna()
        b = pd.to_numeric(attempts.loc[~present, col], errors="coerce").dropna()
        ax.boxplot([b, a], tick_labels=[f"no {code}\n(n={len(b)})", f"{code}\n(n={len(a)})"],
                   showmeans=True)
        ax.set_title(f"{label(code)}  vs  {lbl}", fontsize=9)
        ax.set_ylabel(lbl)
        res = group_compare(attempts[col], present)
        res.update({"code": code, "outcome": col})
        val_rows.append(res)
        ax.text(0.5, 0.95, f"MW p={res['mannwhitney_p']:.3f}", transform=ax.transAxes,
                ha="center", va="top", fontsize=8, color="#b8531f")
    fig.suptitle("Convergent validity: do qualitative codes match logged behaviour?", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(TXT_FIG / "06_convergent_validity.png", bbox_inches="tight")
    plt.close(fig)
    pd.DataFrame(val_rows).to_csv(DERIVED / "stats_convergent_validity.csv", index=False)

    # ---- 5. Theme vs self-reported guessing -------------------------------- #
    guess_stat = theme_vs_outcome(
        attempts.assign(guess=attempts["immediate_guess_ord"]),
        "guess", ALL_DIFFICULTY_CODES, "self-reported guessing (0-3)")
    guess_stat.to_csv(DERIVED / "stats_theme_vs_guessfreq.csv", index=False)

    # ---- 6. Strategy vs expertise & performance ---------------------------- #
    # participant-level performance summary
    perf = base.groupby("participant_id").agg(
        skill_nonogram=("skill_nonogram", "first"),
        skill_puzzles=("skill_puzzles", "first"),
        mean_time=("time_to_solve", "mean"),
        mean_difficulty=("final_difficulty", "mean"),
        solve_rate=("solved", "mean"),
        mean_hints=("n_hints", "mean"),
    ).reset_index()

    strat_part = coded[coded["response_kind"] == "strategy"].copy()
    strat_part = strat_part.drop(columns=[c for c in ["skill_nonogram"] if c in strat_part.columns])
    strat_part = strat_part.merge(perf, on="participant_id", how="left")
    strat_part["n_strategies"] = strat_part[[f"code_{c}" for c in ALL_STRATEGY_CODES]].sum(axis=1)

    # 6a. strategy presence vs skill & performance
    strat_rows = []
    for c in ALL_STRATEGY_CODES:
        present = strat_part[f"code_{c}"] == 1
        if present.sum() < 3 or (~present).sum() < 3:
            continue
        for outcome, lbl in [("skill_nonogram", "self-rated skill"),
                             ("mean_time", "mean solve time"),
                             ("mean_difficulty", "mean difficulty rating"),
                             ("solve_rate", "solve rate")]:
            res = group_compare(strat_part[outcome], present)
            res.update({"code": c, "strategy": label(c), "outcome": lbl})
            strat_rows.append(res)
    strat_outcome = pd.DataFrame(strat_rows)
    strat_outcome.to_csv(DERIVED / "stats_strategy_vs_outcomes.csv", index=False)

    # 6b. strategy repertoire breadth vs skill / performance (scatter + Spearman)
    from scipy import stats as sps
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5), dpi=150)
    for ax, (col, lbl) in zip(axes, [("skill_nonogram", "Self-rated Nonogram skill"),
                                      ("mean_time", "Mean solve time (s)"),
                                      ("mean_difficulty", "Mean difficulty rating")]):
        d = strat_part[["n_strategies", col]].dropna()
        ax.scatter(d["n_strategies"], d[col], color=PALETTE[2], alpha=0.6)
        if len(d) > 3 and d["n_strategies"].nunique() > 1:
            rho, p = sps.spearmanr(d["n_strategies"], d[col])
            m, b0 = np.polyfit(d["n_strategies"], d[col], 1)
            xs = np.array([d["n_strategies"].min(), d["n_strategies"].max()])
            ax.plot(xs, m * xs + b0, "--", color="#b8531f")
            ax.set_title(f"{lbl}\nSpearman rho={rho:.2f}, p={p:.3f}", fontsize=9)
        ax.set_xlabel("# distinct strategies described")
        ax.set_ylabel(lbl)
        ax.grid(alpha=0.25)
    fig.suptitle("Strategy-repertoire breadth vs expertise and performance", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(TXT_FIG / "07_strategy_breadth.png", bbox_inches="tight")
    plt.close(fig)

    # 6c. spearman table for breadth
    breadth_rows = []
    for col, lbl in [("skill_nonogram", "self-rated skill"), ("skill_puzzles", "self-rated puzzle skill"),
                     ("mean_time", "mean solve time"), ("mean_difficulty", "mean difficulty"),
                     ("solve_rate", "solve rate"), ("mean_hints", "mean hints")]:
        d = strat_part[["n_strategies", col]].dropna()
        if len(d) > 3 and d["n_strategies"].nunique() > 1:
            rho, p = sps.spearmanr(d["n_strategies"], d[col])
            breadth_rows.append({"outcome": lbl, "spearman_rho": rho, "p_value": p, "n": len(d)})
    pd.DataFrame(breadth_rows).to_csv(DERIVED / "stats_strategy_breadth_correlations.csv", index=False)

    # ---- console summary ---------------------------------------------------- #
    print("=== TEXT ANALYSIS SUMMARY ===")
    print("\nTop difficulty themes:\n", diff_prev.head(6).to_string(index=False))
    print("\nTop strategies:\n", strat_prev.head(6).to_string(index=False))
    print("\nTheme vs difficulty (sig at MW p<.05):")
    sig = diff_stat[diff_stat["mannwhitney_p"] < 0.05][
        ["theme", "mean_present", "mean_absent", "rank_biserial", "mannwhitney_p", "mw_p_fdr"]]
    print(sig.to_string(index=False) if not sig.empty else "  (none)")
    print("\nConvergent validity:")
    print(pd.DataFrame(val_rows)[["code", "outcome", "mean_present", "mean_absent",
                                  "mannwhitney_p", "rank_biserial"]].to_string(index=False))
    print("\nStrategy breadth correlations:\n",
          pd.DataFrame(breadth_rows).to_string(index=False))
    print(f"\nFigures -> {TXT_FIG}")


if __name__ == "__main__":
    main()
