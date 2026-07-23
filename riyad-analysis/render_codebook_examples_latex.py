"""Render riyad-analysis codebook (codes.py) as LaTeX tables with examples.

Renders a Code/Name/Example table from codes.py: the code, its theme/strategy
name, and a real example quote pulled from derived/text_responses.csv for
each code (via codes.py's CODING map). The full prose definition from
codes.py isn't rendered here -- a 4-column Code/Name/Description/Example
table was tried first but the Description column made the table too busy;
the Name column plus a concrete example already conveys the theme. Read-only
w.r.t. the repository except for the output file.

Output is formatted to fit the AAAI Press LaTeX style ("AAAI Press Formatting
Instructions for Authors Using LaTeX", arXiv:2405.18554):
  - AAAI's two-column layout is 3.3in (~8.4cm) per column with a 0.375in
    gutter, i.e. ~6.975in (~17.7cm) available if a table spans both columns.
    With 3 columns (Code/Name/Example) this table still doesn't fit a single
    AAAI column, so it uses `table*` (spans both columns) rather than
    `table`, per AAAI's instruction to reformat across both columns.
  - Table body text is set in \\small (9pt in AAAI's 10pt document class) --
    the smallest size AAAI permits for table content -- while the caption
    stays at the normal 10pt roman AAAI requires (not smaller/bold/italic).
  - The caption is placed below the tabular (a plain `\\caption`, no special
    handling needed), per AAAI's rule that table captions go beneath the
    table (opposite of figure captions). A `longtable`-based single-table
    version was tried first to keep the two groups glued together, but
    `\\caption` inside `longtable` is a special internal redefinition
    (`\\LT@c@ption`) that can only be used once as part of the `firsthead`
    block -- both putting it in `\\endlastfoot` and wrapping it in
    `\\multicolumn` throw "Misplaced \\noalign" (confirmed against a real
    pdflatex compile), forcing the caption above the table, which AAAI
    disallows. Reverted to two plain `table*` floats instead, where
    `\\caption` has no such restriction.
  - No \\resizebox or other whole-table scaling is used (explicitly
    disallowed by AAAI); column widths are fixed cm values sized to fit.
  - No vertical rules and no boxed outer border (booktabs-style \\toprule/
    \\midrule/\\bottomrule instead of \\hline on every row) for a cleaner,
    less cramped look -- this only requires the `booktabs` package, which
    doesn't affect AAAI's required margins/fonts.
  - Cell text is vertically centered via the `array` package's `m{width}`
    column type (plain `p{width}` top-aligns, which looks cramped/misaligned
    next to the short single-line Code cell), plus \\arraystretch for extra
    row padding.
  - Difficulty themes and the strategy taxonomy are two separate `table*`
    floats (not one combined table), each internally labeled via a
    `\\multicolumn` section-header row ("Difficulty Themes" /
    "Strategy Themes") -- but only ONE `\\caption`/`\\label`, on the second
    (Strategy) table, describing both, so there's a single caption for the
    pair as requested. Two independent floats normally get placed by
    LaTeX's algorithm independently and can drift apart onto non-adjacent
    pages, which was the original complaint; a `\\FloatBarrier` (from the
    `placeins` package) is inserted between them so the second table can't
    be placed before the first is flushed, keeping them consecutive
    (verified: they land on directly-consecutive pages in a real compile,
    even with several pages of filler text before them).
  - The output file's first line is a LaTeX comment reminding you to add
    \\usepackage{array}, \\usepackage{booktabs}, and \\usepackage{placeins}
    to your preamble -- remove that comment line once you've done so.
"""

from __future__ import annotations

import pandas as pd

from analysis_utils import DERIVED, FIG_DIR
from codes import CODING, DIFFICULTY_THEMES, STRATEGY_TAXONOMY

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
    return "".join(LATEX_SPECIAL.get(ch, ch) for ch in text)


MAX_QUOTE_CHARS = 220

# The "shortest single-code response" heuristic occasionally picks a quote
# that's technically pure but too terse to be informative (e.g. VIS -> "make
# it 15x15", AFF -> "hell"). Override those specific codes with a manually
# chosen response_id that still carries only that one code but better
# illustrates the theme in the paper.
MANUAL_EXAMPLE_OVERRIDES = {
    "VIS": "R0232",
    "AFF": "R0036",
}


def build_examples() -> dict[str, str]:
    """Map each code -> one representative example quote (raw, untruncated)."""
    text_by_id = (
        pd.read_csv(DERIVED / "text_responses.csv")
        .set_index("response_id")["text"]
        .to_dict()
    )

    candidates: dict[str, list[tuple[int, int, str, str]]] = {}
    for response_id, codes in CODING.items():
        text = text_by_id.get(response_id)
        if text is None:
            continue
        for code in codes:
            candidates.setdefault(code, []).append(
                (0 if len(codes) == 1 else 1, len(text), response_id, text)
            )

    examples: dict[str, str] = {}
    for code, rows in candidates.items():
        rows.sort(key=lambda r: (r[0], r[1], r[2]))
        examples[code] = rows[0][3]

    for code, response_id in MANUAL_EXAMPLE_OVERRIDES.items():
        assert response_id in CODING and CODING[response_id] == [code], (
            f"Override {response_id!r} for {code!r} no longer matches CODING"
        )
        examples[code] = text_by_id[response_id]

    return examples


def truncate_quote(text: str) -> str:
    text = " ".join(text.split())
    if len(text) <= MAX_QUOTE_CHARS:
        return text
    return text[:MAX_QUOTE_CHARS].rstrip() + "…"


def _data_rows(theme_dict: dict[str, dict[str, str]], examples: dict[str, str]) -> list[str]:
    rows = []
    for code, info in theme_dict.items():
        quote = truncate_quote(examples[code])
        rows.append(
            rf"\texttt{{{escape_latex(code)}}} & {escape_latex(info['name'])} & "
            rf"``{escape_latex(quote)}'' \\"
        )
    return rows


def _section_table(
    theme_dict: dict[str, dict[str, str]],
    examples: dict[str, str],
    section_title: str,
    trailer_lines: list[str],
) -> str:
    # Column widths sum to ~13.6cm (m{} widths) + ~1.3cm auto Code column +
    # ~1.3cm tabcolsep padding (6 x 6pt) = ~16.2cm, leaving ~1.5cm of margin
    # under AAAI's ~17.7cm two-column (table*) width. The Name column must
    # wrap (not a bare `l`) since several theme names alone run to ~7-8cm
    # unwrapped (e.g. "Combinatorial ambiguity / overlap reasoning"), which
    # would overflow the width on its own.
    lines = [
        r"\begin{table*}[t]",
        r"\centering",
        r"{\small",
        r"\renewcommand{\arraystretch}{1.2}",
        r"\setlength{\tabcolsep}{6pt}",
        r"\begin{tabular}{lm{3.2cm}m{10.4cm}}",
        r"\toprule",
        rf"\multicolumn{{3}}{{l}}{{\textbf{{{section_title}}}}} \\",
        r"\midrule",
        r"\textbf{Code} & \textbf{Theme / Strategy} & \textbf{Example} \\",
        r"\midrule",
        *_data_rows(theme_dict, examples),
        r"\bottomrule",
        r"\end{tabular}",
        r"}",
        *trailer_lines,
        r"\end{table*}",
    ]
    return "\n".join(lines)


def build_tables(
    diff_dict: dict[str, dict[str, str]],
    strat_dict: dict[str, dict[str, str]],
    examples: dict[str, str],
    caption: str,
    label: str,
) -> str:
    diff_tex = _section_table(diff_dict, examples, "Difficulty Themes", trailer_lines=[])
    strat_tex = _section_table(
        strat_dict, examples, "Strategy Themes",
        trailer_lines=[rf"\caption{{{caption}}}", rf"\label{{{label}}}"],
    )
    # `\FloatBarrier` (placeins) forces the difficulty table to be placed
    # before the strategy table is even considered, so LaTeX's float
    # algorithm can't scatter them onto non-adjacent pages -- verified
    # against a real pdflatex compile (they land on consecutive pages even
    # with several pages of filler text pushing them down).
    return "\n\n".join([diff_tex, r"\FloatBarrier", strat_tex])


def main() -> None:
    examples = build_examples()

    missing = [
        code
        for code in {**DIFFICULTY_THEMES, **STRATEGY_TAXONOMY}
        if code not in examples
    ]
    if missing:
        raise RuntimeError(f"No example response found for codes: {missing}")

    tables_tex = build_tables(
        DIFFICULTY_THEMES, STRATEGY_TAXONOMY, examples,
        caption=(
            "Difficulty themes (applied to \\texttt{rating\\_reason} + "
            "\\texttt{comments}) and strategy taxonomy (applied to "
            "\\texttt{strategy}), with example responses"
        ),
        label="tab:codebook-examples",
    )

    preamble_note = (
        "% Requires \\usepackage{array}, \\usepackage{booktabs}, and "
        "\\usepackage{placeins} in your preamble (for the m{} column type, "
        "\\toprule/\\midrule/\\bottomrule, and \\FloatBarrier below) -- "
        "remove this comment once added.\n"
    )

    out_path = FIG_DIR / "codebook_examples_latex.txt"
    out_path.write_text(preamble_note + "\n" + tables_tex + "\n", encoding="utf-8")
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
