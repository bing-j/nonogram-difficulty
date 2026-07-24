"""
text_coding_analysis.py
=========================
Step 12 - Prevalence and rank-biserial correlation analysis of the thematically
coded open-text survey responses.

Two things only (narrowed from an earlier standalone exploratory analysis's
fuller scope, since removed from the repo): (1) how prevalent is each
difficulty theme / strategy among coded responses, and (2) does a theme's
presence track a higher/lower value of a behavioural or subjective outcome
(rank-biserial effect size + Mann-Whitney U, via group_compare/theme_vs_outcome).
Co-occurrence (Jaccard) heatmaps and the strategy-breadth-vs-outcomes Spearman
correlations are intentionally excluded -- neither is prevalence nor rank-biserial.

Ported from that earlier analysis's text-analysis script (prevalence_plot,
group_compare, rank_biserial_from_u, cohens_d, benjamini_hochberg,
theme_vs_outcome, outcome_effect_plot) and its shared stats-utils module
(the same helpers, originally shared -- kept local here per this repo's
convention of self-contained analysis scripts, e.g. spearman_ranking.py).

Inputs
------
- analyze-data/out_features/text_coding/coded_responses.csv (Step 11)
- backend/logs/*.ndjson, *.json (via text_response_loader.py, for behavioural outcomes)

Outputs
-------
- analyze-data/out_features/text_coding/stats_difficulty_theme_prevalence.csv
- analyze-data/out_features/text_coding/stats_strategy_prevalence.csv
- analyze-data/out_features/text_coding/stats_theme_vs_difficulty.csv
- analyze-data/out_features/text_coding/stats_theme_vs_behaviour.csv
- analyze-data/out_features/text_coding/stats_theme_vs_guessfreq.csv
- analyze-data/out_features/text_coding/stats_convergent_validity.csv
- analyze-data/out_features/text_coding/stats_strategy_vs_outcomes.csv
- analyze-data/out_features/figures/text_coding/01_difficulty_theme_prevalence.png
- analyze-data/out_features/figures/text_coding/02_strategy_prevalence.png
- analyze-data/out_features/figures/text_coding/03_theme_vs_difficulty.png
- analyze-data/out_features/figures/text_coding/04_convergent_validity.png

Usage
-----
  python analyze-data/text_coding_analysis.py
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
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
from codes import ALL_DIFFICULTY_CODES, ALL_STRATEGY_CODES, DIFFICULTY_THEMES, STRATEGY_TAXONOMY  # noqa: E402
from plot_style import NEUTRAL_COLOR, apply_style  # noqa: E402
from text_response_loader import load_participant_puzzle_df  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TEXT_CODING_DIR = REPO_ROOT / "analyze-data" / "out_features" / "text_coding"
DEFAULT_OUT_DIR = REPO_ROOT / "analyze-data" / "out_features"

ACCENT_COLOR = "#b8531f"  # highlights p < .05 bars against NEUTRAL_COLOR


def label(code: str) -> str:
    if code in DIFFICULTY_THEMES:
        return DIFFICULTY_THEMES[code]["name"]
    return STRATEGY_TAXONOMY[code]["name"]


# --------------------------------------------------------------------------- #
# Rank-biserial stats helpers (ported from that earlier analysis's shared stats-utils module)
# --------------------------------------------------------------------------- #
def cohens_d(a: np.ndarray, b: np.ndarray) -> float:
    """Hedges-free Cohen's d for two independent groups (pooled SD)."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    if len(a) < 2 or len(b) < 2:
        return float("nan")
    na, nb = len(a), len(b)
    sp2 = ((na - 1) * a.var(ddof=1) + (nb - 1) * b.var(ddof=1)) / (na + nb - 2)
    if sp2 <= 0:
        return float("nan")
    return (a.mean() - b.mean()) / np.sqrt(sp2)


def rank_biserial_from_u(u: float, n1: int, n2: int) -> float:
    """Rank-biserial effect size from a Mann-Whitney U statistic."""
    if n1 == 0 or n2 == 0:
        return float("nan")
    return 1.0 - (2.0 * u) / (n1 * n2)


def group_compare(values: pd.Series, present: pd.Series) -> dict:
    """Compare a numeric outcome between code-present vs code-absent groups.

    Returns means, Mann-Whitney U test, point-biserial r, rank-biserial
    effect size, and Cohen's d.
    """
    df = pd.DataFrame({"y": pd.to_numeric(values, errors="coerce"),
                       "g": present.astype(int)}).dropna()
    a = df.loc[df["g"] == 1, "y"].to_numpy()
    b = df.loc[df["g"] == 0, "y"].to_numpy()
    out = {
        "n_present": int(len(a)),
        "n_absent": int(len(b)),
        "mean_present": float(a.mean()) if len(a) else float("nan"),
        "mean_absent": float(b.mean()) if len(b) else float("nan"),
        "median_present": float(np.median(a)) if len(a) else float("nan"),
        "median_absent": float(np.median(b)) if len(b) else float("nan"),
        "mannwhitney_u": float("nan"),
        "mannwhitney_p": float("nan"),
        "rank_biserial": float("nan"),
        "pointbiserial_r": float("nan"),
        "pointbiserial_p": float("nan"),
        "cohens_d": cohens_d(a, b),
    }
    if len(a) >= 2 and len(b) >= 2:
        u, p = stats.mannwhitneyu(a, b, alternative="two-sided")
        out["mannwhitney_u"] = float(u)
        out["mannwhitney_p"] = float(p)
        out["rank_biserial"] = rank_biserial_from_u(u, len(a), len(b))
        if df["g"].nunique() == 2 and df["y"].nunique() > 1:
            r, rp = stats.pointbiserialr(df["g"], df["y"])
            out["pointbiserial_r"] = float(r)
            out["pointbiserial_p"] = float(rp)
    return out


def benjamini_hochberg(pvalues: list[float]) -> list[float]:
    """BH-FDR adjusted p-values; NaNs preserved."""
    p = np.asarray(pvalues, dtype=float)
    mask = ~np.isnan(p)
    adj = np.full_like(p, np.nan)
    pv = p[mask]
    m = len(pv)
    if m == 0:
        return adj.tolist()
    order = np.argsort(pv)
    ranked = pv[order]
    bh = ranked * m / (np.arange(1, m + 1))
    bh = np.minimum.accumulate(bh[::-1])[::-1]
    bh = np.clip(bh, 0, 1)
    out = np.empty(m)
    out[order] = bh
    adj[mask] = out
    return adj.tolist()


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


# --------------------------------------------------------------------------- #
# Part 1: prevalence
# --------------------------------------------------------------------------- #
def prevalence_plot(coded: pd.DataFrame, code_cols: list[str], title: str, fig_path: Path) -> pd.DataFrame:
    n = len(coded)
    counts = {c: int(coded[f"code_{c}"].sum()) for c in code_cols}
    rows = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    labels = [f"{label(c)}" for c, _ in rows]
    vals = [v for _, v in rows]
    pct = [100.0 * v / n for v in vals]

    fig, ax = plt.subplots(figsize=(9, 5.5), dpi=160)
    ax.barh(range(len(rows)), pct, color=NEUTRAL_COLOR)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels(labels)
    ax.invert_yaxis()
    ax.set_xlabel(f"% of coded responses mentioning theme (n = {n})")
    ax.set_title(title)
    for i, (v, p) in enumerate(zip(vals, pct)):
        ax.text(p + 0.5, i, f"{v} ({p:.0f}%)", va="center", fontsize=8)
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(fig_path, bbox_inches="tight")
    plt.close(fig)

    return pd.DataFrame({"code": [c for c, _ in rows], "theme": labels,
                         "count": vals, "pct_of_coded": pct})


# --------------------------------------------------------------------------- #
# Part 2: rank-biserial figures
# --------------------------------------------------------------------------- #
def outcome_effect_plot(stat_df: pd.DataFrame, outcome_label: str, fig_path: Path) -> None:
    if stat_df.empty:
        return
    d = stat_df.sort_values("rank_biserial")
    colors = [ACCENT_COLOR if p < 0.05 else NEUTRAL_COLOR for p in d["mannwhitney_p"]]
    fig, ax = plt.subplots(figsize=(8.5, 5.5), dpi=160)
    ax.barh(range(len(d)), d["rank_biserial"], color=colors)
    ax.axvline(0, color="black", lw=0.8)
    ax.set_yticks(range(len(d)))
    ax.set_yticklabels(d["theme"])
    ax.set_xlabel(f"Rank-biserial effect (theme-present vs absent) on {outcome_label}\n"
                  f"{ACCENT_COLOR} = Mann-Whitney p < .05")
    ax.set_title(f"Which difficulty themes track higher {outcome_label}?")
    for i, (rb, mp) in enumerate(zip(d["rank_biserial"], d["mannwhitney_p"])):
        ax.text(rb + (0.01 if rb >= 0 else -0.01), i, f"p={mp:.3f}",
                va="center", ha="left" if rb >= 0 else "right", fontsize=7)
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(fig_path, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Prevalence + rank-biserial correlation analysis of coded open-text responses."
    )
    ap.add_argument("--coded_responses_csv", type=Path, default=DEFAULT_TEXT_CODING_DIR / "coded_responses.csv")
    ap.add_argument("--out_dir", type=Path, default=DEFAULT_TEXT_CODING_DIR)
    ap.add_argument("--fig_dir", type=Path, default=DEFAULT_OUT_DIR / "figures" / "text_coding")
    args = ap.parse_args()

    apply_style()

    if not args.coded_responses_csv.exists():
        print(f"Coded responses CSV not found: {args.coded_responses_csv}")
        print("Run build_coded_dataset.py first.")
        return

    args.out_dir.mkdir(parents=True, exist_ok=True)
    args.fig_dir.mkdir(parents=True, exist_ok=True)

    coded = pd.read_csv(args.coded_responses_csv)
    base = load_participant_puzzle_df()

    # ---- 1. Prevalence ----------------------------------------------------- #
    diff_coded = coded[(coded["response_kind"].isin(["rating_reason", "comments"]))
                       & (coded["n_codes"] > 0)].copy()
    strat_coded = coded[(coded["response_kind"] == "strategy") & (coded["n_codes"] > 0)].copy()

    print("=" * 60)
    print("PREVALENCE")
    print("=" * 60)
    diff_prev = prevalence_plot(diff_coded, ALL_DIFFICULTY_CODES,
                                "Difficulty themes across all open-text difficulty explanations",
                                args.fig_dir / "01_difficulty_theme_prevalence.png")
    strat_prev = prevalence_plot(strat_coded, ALL_STRATEGY_CODES,
                                 "Solving strategies described by participants",
                                 args.fig_dir / "02_strategy_prevalence.png")
    diff_prev.to_csv(args.out_dir / "stats_difficulty_theme_prevalence.csv", index=False)
    strat_prev.to_csv(args.out_dir / "stats_strategy_prevalence.csv", index=False)
    print("\nTop difficulty themes:\n", diff_prev.head(6).to_string(index=False))
    print("\nTop strategies:\n", strat_prev.head(6).to_string(index=False))

    # ---- 2. Theme vs difficulty & behaviour (attempt level) ---------------- #
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

    print("\n" + "=" * 60)
    print("THEME vs. DIFFICULTY (rank-biserial)")
    print("=" * 60)
    diff_stat = theme_vs_outcome(attempts, "final_difficulty", ALL_DIFFICULTY_CODES, "final difficulty (1-5)")
    diff_stat.to_csv(args.out_dir / "stats_theme_vs_difficulty.csv", index=False)
    outcome_effect_plot(diff_stat, "subjective difficulty", args.fig_dir / "03_theme_vs_difficulty.png")
    sig = diff_stat[diff_stat["mannwhitney_p"] < 0.05][
        ["theme", "mean_present", "mean_absent", "rank_biserial", "mannwhitney_p", "mw_p_fdr"]]
    print(sig.to_string(index=False) if not sig.empty else "  (none significant at p<.05)")

    behav_frames = []
    for col, lbl in [("time_to_solve", "solve time"), ("n_hints", "hints used"),
                     ("n_incorrect_submissions", "incorrect submissions"), ("n_actions", "actions")]:
        s_raw = theme_vs_outcome(attempts, col, ALL_DIFFICULTY_CODES, f"{lbl} (raw)")
        s_pc = theme_vs_outcome(attempts, f"{col}_pc", ALL_DIFFICULTY_CODES, f"{lbl} (within-participant)")
        behav_frames += [s_raw, s_pc]
    behav_stat = pd.concat(behav_frames, ignore_index=True)
    behav_stat.to_csv(args.out_dir / "stats_theme_vs_behaviour.csv", index=False)

    # Convergent-validity: HINT theme -> hints; GUESS -> hints+incorrect; ERR -> cell errors.
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
                ha="center", va="top", fontsize=8, color=ACCENT_COLOR)
    fig.suptitle("Convergent validity: do qualitative codes match logged behaviour?", fontsize=12)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(args.fig_dir / "04_convergent_validity.png", bbox_inches="tight")
    plt.close(fig)
    pd.DataFrame(val_rows).to_csv(args.out_dir / "stats_convergent_validity.csv", index=False)
    print("\nConvergent validity:")
    print(pd.DataFrame(val_rows)[["code", "outcome", "mean_present", "mean_absent",
                                  "mannwhitney_p", "rank_biserial"]].to_string(index=False))

    # ---- 3. Theme vs self-reported guessing --------------------------------- #
    guess_stat = theme_vs_outcome(
        attempts.assign(guess=attempts["immediate_guess_ord"]),
        "guess", ALL_DIFFICULTY_CODES, "self-reported guessing (0-3)")
    guess_stat.to_csv(args.out_dir / "stats_theme_vs_guessfreq.csv", index=False)

    # ---- 4. Strategy vs expertise & performance ----------------------------- #
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
    strat_outcome.to_csv(args.out_dir / "stats_strategy_vs_outcomes.csv", index=False)

    print(f"\nWrote stats tables -> {args.out_dir}")
    print(f"Wrote figures -> {args.fig_dir}")
    print("\nDone.")


if __name__ == "__main__":
    main()
