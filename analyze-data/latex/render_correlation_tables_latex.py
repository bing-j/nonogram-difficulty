"""Render four correlation/regression result tables as AAAI-compliant LaTeX.

Lives in analyze-data/latex/ alongside render_codebook_examples_latex.py,
following the same AAAI Press style conventions established there (see that
file's docstring for the full rationale, verified via local pdflatex
compiles): booktabs rules instead of \\hline, caption below the tabular via a
plain \\caption (AAAI requires table captions below, opposite of figures), no
\\resizebox (explicitly disallowed by AAAI), and \\small (9pt) body text (the
smallest AAAI permits for table content).

Unlike the codebook table, these four tables are narrow and numeric (a
handful of rows, short labels plus a few numeric columns), so each fits
comfortably inside AAAI's single-column width (~3.3in/8.4cm) as a plain
`table` -- no `table*`, `m{}` wrapping, or `multirow` needed here.

Reads four CSVs produced by the analyze-data/ pipeline:
  - out_features/stats_bt_vs_sat.csv                            (spearman_ranking.py)
  - out_features/stats_behavioral_vs_difficulty_pooled.csv       (behavioral_regression.py)
  - out_features/stats_behavioral_vs_conflicts.csv                (behavioral_regression.py)
  - out_features/expertise_vs_outcomes.csv                        (expertise_adjustment.py)

The first three are exported specifically for this renderer (added alongside
this script); the last already existed. A fifth table
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


PREDICTOR_LABELS = {
    "const": "Intercept",
    "pause_count": "Pause count",
    "pause_freq_per_min": "Pause freq. (/min)",
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
    df = df[df["predictor_type"] == "sat_metric"]
    raw = df[df["rating_col"] == "final_difficulty"].set_index("predictor")
    adj = df[df["rating_col"] == "final_difficulty_order_adjusted"].set_index("predictor")
    n = int(raw["n"].iloc[0])
    rows = []
    for predictor in raw.index:
        r_raw, r_adj = raw.loc[predictor], adj.loc[predictor]
        rows.append([
            METRIC_LABELS.get(predictor, predictor),
            fmt_rho(r_raw["bt_rho"], r_raw["bt_p"]),
            fmt_p(r_raw["bt_p"]),
            fmt_rho(r_adj["bt_rho"], r_adj["bt_p"]),
            fmt_p(r_adj["bt_p"]),
        ])
    return build_table(
        ["SAT metric", r"Raw $\rho$", "$p$", r"Order-adj. $\rho$", "$p$"],
        "lrrrr",
        rows,
        caption=(
            "Spearman correlation between Bradley-Terry puzzle difficulty "
            "ranking and SAT solver metrics, raw ratings vs. order-adjusted "
            f"ratings ($n={n}$ puzzles). " + SIG_NOTE
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


def table_behavioral_vs_conflicts() -> str:
    return _coef_table(
        "stats_behavioral_vs_conflicts.csv",
        "Behavioral predictors of SAT solver conflicts, at full per-response "
        "granularity (not pooled to per-puzzle means).",
        "tab:behavioral-vs-conflicts",
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


def main() -> None:
    tables = [
        table_bt_vs_sat(),
        table_behavioral_vs_difficulty(),
        table_behavioral_vs_conflicts(),
        table_expertise_vs_outcomes(),
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
