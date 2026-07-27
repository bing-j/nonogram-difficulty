"""Render six correlation/regression result tables as AAAI-compliant LaTeX.

Lives in analyze-data/latex/ alongside render_codebook_examples_latex.py,
following the same AAAI Press style conventions established there (see that
file's docstring for the full rationale, verified via local pdflatex
compiles): booktabs rules instead of \\hline, caption below the tabular via a
plain \\caption (AAAI requires table captions below, opposite of figures), no
\\resizebox (explicitly disallowed by AAAI), and \\small (9pt) body text (the
smallest AAAI permits for table content).

Unlike the codebook table, these six tables are narrow and numeric (a
handful of rows, short labels plus a few numeric columns), so each fits
comfortably inside AAAI's single-column width (~3.3in/8.4cm) as a plain
`table` -- no `table*`, `m{}` wrapping, or `multirow` needed here.

Reads six CSVs produced by the analyze-data/ pipeline:
  - out_features/stats_bt_vs_sat.csv                            (spearman_ranking.py)
  - out_features/stats_behavioral_vs_difficulty_pooled.csv       (behavioral_regression.py)
  - out_features/stats_behavioral_vs_sat_metrics.csv               (behavioral_regression.py)
  - out_features/expertise_vs_outcomes.csv                        (expertise_adjustment.py)
  - out_features/stats_moderation_expertise.csv                    (moderation_analysis.py, two tables)

The first three are exported specifically for this renderer (added alongside
this script); the fourth already existed. A table
(tab:expertise-adjusted-vs-sat, reading stats_expertise_adjusted_difficulty_vs_sat.csv)
was removed along with expertise_adjustment.py's residualization-based
per-puzzle difficulty estimate -- see that script's docstring for why. Renders
one `table` per analysis into a single output file,
analyze-data/latex/figures/correlation_tables_latex.txt.

Usage
-----
  python analyze-data/latex/render_correlation_tables_latex.py
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

OUT_FEATURES = Path(__file__).resolve().parents[1] / "out_features"
FIG_DIR = Path(__file__).resolve().parent / "figures"
FIG_DIR.mkdir(exist_ok=True)

LATEX_SPECIAL = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def escape_latex(text: str) -> str:
    return "".join(LATEX_SPECIAL.get(ch, ch) for ch in str(text))


SIG_NOTE = r"* $p<.05$, ** $p<.01$, *** $p<.001$."


def sig_stars(p: float) -> str:
    if pd.isna(p):
        return ""
    if p < 0.001:
        return "***"
    if p < 0.01:
        return "**"
    if p < 0.05:
        return "*"
    return ""


def fmt_p(p: float) -> str:
    if pd.isna(p):
        return "--"
    if p < 0.001:
        return "$<$.001"
    return f"{p:.3f}"


def fmt_rho(rho: float, p: float) -> str:
    if pd.isna(rho):
        return "--"
    return f"{rho:+.3f}{sig_stars(p)}"


def fmt_coef(coef: float, p: float) -> str:
    if pd.isna(coef):
        return "--"
    return f"{coef:.3f}{sig_stars(p)}"


def fmt_coef_ci(coef: float, p: float, lo: float, hi: float) -> str:
    if pd.isna(coef):
        return "--"
    return f"{coef:+.4f}{sig_stars(p)} [{lo:+.4f}, {hi:+.4f}]"


PREDICTOR_LABELS = {
    "const": "Intercept",
    "pause_count": "Pause count",
    "time_to_solve_sec": "Time to solve (s)",
    "error_count": "Error count",
    "hint_count": "Hints used",
}

METRIC_LABELS = {
    "decisions": "Decisions",
    "propagations": "Propagations",
    "conflicts": "Conflicts",
}


def build_table(
    headers: list[str], col_spec: str, rows: list[list[str]], caption: str, label: str
) -> str:
    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\small",
        r"\setlength{\tabcolsep}{4pt}",
        rf"\begin{{tabular}}{{{col_spec}}}",
        r"\toprule",
        " & ".join(rf"\textbf{{{h}}}" for h in headers) + r" \\",
        r"\midrule",
    ]
    for row in rows:
        lines.append(" & ".join(row) + r" \\")
    lines += [
        r"\bottomrule",
        r"\end{tabular}",
        rf"\caption{{{caption}}}",
        rf"\label{{{label}}}",
        r"\end{table}",
    ]
    return "\n".join(lines)


def table_bt_vs_sat() -> str:
    df = pd.read_csv(OUT_FEATURES / "stats_bt_vs_sat.csv")
    df = df[(df["predictor_type"] == "sat_metric") & (df["rating_col"] == "final_difficulty")]
    n = int(df["n"].iloc[0])
    rows = []
    for _, r in df.iterrows():
        rows.append([
            METRIC_LABELS.get(r["predictor"], r["predictor"]),
            fmt_rho(r["bt_rho"], r["bt_p"]),
            fmt_p(r["bt_p"]),
            fmt_rho(r["raw_rho"], r["raw_p"]),
            fmt_p(r["raw_p"]),
        ])
    return build_table(
        ["SAT metric", r"BT $\rho$", "$p$", r"Raw $\rho$", "$p$"],
        "lrrrr",
        rows,
        caption=(
            "Spearman correlation between Bradley-Terry-adjusted puzzle "
            "difficulty ranking and SAT solver metrics, compared against "
            f"raw per-puzzle mean difficulty ranking ($n={n}$ puzzles). " + SIG_NOTE
        ),
        label="tab:bt-vs-sat",
    )


def _coef_table(csv_name: str, caption_prefix: str, label: str) -> str:
    df = pd.read_csv(OUT_FEATURES / csv_name)
    model_row = df[df["predictor"] == "(model)"].iloc[0]
    data = df[df["predictor"] != "(model)"]
    rows = []
    for _, r in data.iterrows():
        rows.append([
            PREDICTOR_LABELS.get(r["predictor"], r["predictor"]),
            fmt_coef(r["coef"], r["p_value"]),
            fmt_p(r["p_value"]),
        ])
    n = int(model_row["n"])
    caption = (
        f"{caption_prefix} Pooled OLS across all participant--puzzle "
        f"observations ($N={n}$). " + SIG_NOTE
    )
    return build_table(
        ["Predictor", "$B$", "$p$"],
        "lrr",
        rows,
        caption=caption,
        label=label,
    )


def table_behavioral_vs_difficulty() -> str:
    return _coef_table(
        "stats_behavioral_vs_difficulty_pooled.csv",
        "Behavioral predictors of retrospective difficulty rating, at full "
        "per-response granularity (not pooled to per-puzzle means).",
        "tab:behavioral-vs-difficulty",
    )


def table_behavioral_vs_sat_metrics() -> str:
    df = pd.read_csv(OUT_FEATURES / "stats_behavioral_vs_sat_metrics.csv")
    rows = []
    for _, r in df.iterrows():
        rows.append([
            PREDICTOR_LABELS.get(r["outcome"], r["outcome"]),
            METRIC_LABELS.get(r["predictor"], r["predictor"]),
            fmt_coef_ci(r["coef"], r["p"], r["ci_lower"], r["ci_upper"]),
            str(int(r["n"])),
        ])
    return build_table(
        ["Behavioral signal", "SAT metric", r"$\beta$ [95\% CI]", "$N$"],
        "llcr",
        rows,
        caption=(
            "SAT-metric fixed effects on behavioral difficulty signals: "
            "crossed-random-effects linear mixed model (behavioral signal "
            "$\\sim$ SAT metric, with crossed random intercepts for "
            "participant and puzzle -- Baayen, Davidson \\& Bates 2008), "
            "Wald 95\\% CIs, one row per behavioral-signal $\\times$ "
            "SAT-metric pair. " + SIG_NOTE
        ),
        label="tab:behavioral-vs-sat-metrics",
    )


def table_expertise_vs_outcomes() -> str:
    df = pd.read_csv(OUT_FEATURES / "expertise_vs_outcomes.csv")
    rows = []
    for _, r in df.iterrows():
        rows.append([
            escape_latex(r["outcome"]),
            fmt_rho(r["spearman_rho"], r["spearman_p"]),
            fmt_p(r["spearman_p"]),
        ])
    return build_table(
        ["Outcome", r"$\rho$", "$p$"],
        "lrr",
        rows,
        caption=(
            "Spearman correlation between participant expertise (composite "
            "score) and behavioral outcomes / retrospective difficulty "
            "rating, aggregated to participant-level means. " + SIG_NOTE
        ),
        label="tab:expertise-vs-outcomes",
    )


def table_moderation_interaction() -> str:
    df = pd.read_csv(OUT_FEATURES / "stats_moderation_expertise.csv")
    n = int(df["n"].iloc[0])
    n_participants = int(df["n_participants"].iloc[0])
    n_puzzles = int(df["n_puzzles"].iloc[0])
    rows = []
    for _, r in df.iterrows():
        rows.append([
            METRIC_LABELS.get(r["predictor"], r["predictor"]),
            fmt_coef_ci(r["coef_metric"], r["p_metric"], r["ci_lower_metric"], r["ci_upper_metric"]),
            fmt_coef_ci(r["coef_expertise"], r["p_expertise"], r["ci_lower_expertise"], r["ci_upper_expertise"]),
            fmt_coef_ci(r["interaction"], r["p_interaction"], r["ci_lower_interaction"], r["ci_upper_interaction"]),
        ])
    return build_table(
        ["SAT metric", "Metric $\\beta$ [95\\% CI]", "Expertise $\\beta$ [95\\% CI]", "Interaction $\\beta$ [95\\% CI]"],
        "lccc",
        rows,
        caption=(
            "Moderation of the SAT-metric $\\to$ difficulty relationship by "
            "participant expertise: fixed effects from a crossed-random-"
            "effects linear mixed model (\\texttt{final\\_difficulty} $\\sim$ "
            "metric $\\times$ expertise, with crossed random intercepts for "
            "participant and puzzle -- Baayen, Davidson \\& Bates 2008), Wald "
            f"95\\% CIs ($N={n}$ observations, {n_participants} participants, "
            f"{n_puzzles} puzzles). " + SIG_NOTE
        ),
        label="tab:moderation-interaction",
    )


def table_moderation_simple_slopes() -> str:
    df = pd.read_csv(OUT_FEATURES / "stats_moderation_expertise.csv")
    rows = []
    for _, r in df.iterrows():
        rows.append([
            METRIC_LABELS.get(r["predictor"], r["predictor"]),
            fmt_coef_ci(r["slope_low"], r["p_slope_low"], r["ci_lower_slope_low"], r["ci_upper_slope_low"]),
            fmt_coef_ci(r["slope_mean"], r["p_slope_mean"], r["ci_lower_slope_mean"], r["ci_upper_slope_mean"]),
            fmt_coef_ci(r["slope_high"], r["p_slope_high"], r["ci_lower_slope_high"], r["ci_upper_slope_high"]),
        ])
    return build_table(
        ["SAT metric", "Slope @ $z{=}{-}1$", "Slope @ $z{=}0$", "Slope @ $z{=}{+}1$"],
        "lccc",
        rows,
        caption=(
            "Simple slopes (Aiken \\& West 1991) of SAT metric on "
            "\\texttt{final\\_difficulty} at representative expertise levels "
            "-- \\texttt{expertise\\_composite} is a population $z$-score "
            "by construction, so $z{=}{-}1/0/{+}1$ correspond to low/average/"
            "high expertise. Delta-method 95\\% CIs from the crossed-effects "
            "model in Table~\\ref{tab:moderation-interaction}. " + SIG_NOTE
        ),
        label="tab:moderation-simple-slopes",
    )


def main() -> None:
    tables = [
        table_bt_vs_sat(),
        table_behavioral_vs_difficulty(),
        table_behavioral_vs_sat_metrics(),
        table_expertise_vs_outcomes(),
        table_moderation_interaction(),
        table_moderation_simple_slopes(),
    ]
    preamble_note = (
        "% Requires \\usepackage{booktabs} in your preamble (for "
        "\\toprule/\\midrule/\\bottomrule) -- remove this comment once added.\n"
    )
    out_path = FIG_DIR / "correlation_tables_latex.txt"
    out_path.write_text(preamble_note + "\n\n".join(tables) + "\n", encoding="utf-8")
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
