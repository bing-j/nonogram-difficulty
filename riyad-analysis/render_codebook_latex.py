"""Render riyad-analysis/derived/codebook.md as LaTeX tables.

Reads the two markdown tables (difficulty themes, strategy taxonomy) and
writes equivalent LaTeX `table`/`tabular` environments to a .txt file.
Read-only w.r.t. the repository except for the output file.
"""

from __future__ import annotations

from pathlib import Path

from analysis_utils import FIG_DIR
from render_codebook import load_codebook_tables

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
    out = []
    for ch in text:
        out.append(LATEX_SPECIAL.get(ch, ch))
    return "".join(out)


def build_table(
    rows: list[tuple[str, str, str]],
    col2_label: str,
    caption: str,
    label: str,
) -> str:
    lines = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\begin{tabular}{|l|l|p{8.5cm}|}",
        r"\hline",
        rf"\textbf{{Code}} & \textbf{{{col2_label}}} & \textbf{{Definition}} \\",
        r"\hline",
    ]
    for code, col2, definition in rows:
        lines.append(
            rf"\texttt{{{escape_latex(code)}}} & {escape_latex(col2)} & "
            rf"{escape_latex(definition)} \\"
        )
        lines.append(r"\hline")
    lines += [
        r"\end{tabular}",
        rf"\caption{{{caption}}}",
        rf"\label{{{label}}}",
        r"\end{table}",
    ]
    return "\n".join(lines)


def main() -> None:
    diff_rows, strat_rows = load_codebook_tables()

    diff_tex = build_table(
        diff_rows, "Theme",
        caption="Difficulty themes (applied to \\texttt{rating\\_reason} + \\texttt{comments})",
        label="tab:difficulty-themes",
    )
    strat_tex = build_table(
        strat_rows, "Strategy",
        caption="Strategy taxonomy (applied to \\texttt{strategy})",
        label="tab:strategy-taxonomy",
    )

    out_path = FIG_DIR / "codebook_latex.txt"
    out_path.write_text(diff_tex + "\n\n\n" + strat_tex + "\n", encoding="utf-8")
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
