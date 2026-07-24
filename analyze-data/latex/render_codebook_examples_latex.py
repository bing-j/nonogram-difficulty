"""Render the survey text-coding codebook (analyze-data/codes.py) as LaTeX tables with examples.

Lives in analyze-data/latex/ (a sibling of codes.py, not a nested step
script) since it's LaTeX-output tooling for the paper rather than part of
the text-coding analysis pipeline (Steps 10-12 in PIPELINE.md) itself.

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
    table (opposite of figure captions).
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
  - ALL 21 codes are one single `table*` with a leading "Category" column
    (Difficulty/Strategy, via `\\multirow` spanning each group) instead of
    two separate tables. Two prior approaches were tried and rejected:
    (1) one combined `longtable` -- works, but `\\caption` inside `longtable`
    is a special internal redefinition (`\\LT@c@ption`) that can only be
    used once, in the `firsthead` block, forcing the caption above the
    table (AAAI requires below) -- confirmed via real pdflatex compile;
    (2) two separate `table*` floats + `\\FloatBarrier` -- satisfies AAAI's
    caption-below rule, but LaTeX's float algorithm still places the two
    floats on separate pages (verified: landed on consecutive but distinct
    pages), which wasn't good enough. A single `table*` avoids both
    problems, since it's one float that can't be split by the placement
    algorithm and has no `longtable`-style caption restriction.
  - A single `table*` can't paginate, so all 21 rows (with wrapped
    multi-line Example quotes) must fit within one AAAI page's height.
    Verified via real pdflatex compile: at \\arraystretch{1.2} (used by the
    prior two-table version) it was too tall by 58pt; dropping to
    \\arraystretch{1.0} got it to within 9.66pt; the remaining gap was
    closed by capping MAX_QUOTE_CHARS at 180 instead of 220 (the only quote
    long enough to be affected is S_HINT, at 213 raw chars -- everything
    else is already under 180, so this doesn't touch other codes' quotes).
  - The output file's first line is a LaTeX comment reminding you to add
    \\usepackage{array}, \\usepackage{booktabs}, and \\usepackage{multirow}
    to your preamble -- remove that comment line once you've done so.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from codes import CODING, DIFFICULTY_THEMES, STRATEGY_TAXONOMY  # noqa: E402

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
    return "".join(LATEX_SPECIAL.get(ch, ch) for ch in text)


MAX_QUOTE_CHARS = 180

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
        pd.read_csv(OUT_FEATURES / "text_coding" / "text_responses.csv")
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
    truncated = text[:MAX_QUOTE_CHARS].rsplit(" ", 1)[0]
    return truncated.rstrip(",;:. ") + "…"


ROW_SPACING = "3pt"


def _data_rows(
    theme_dict: dict[str, dict[str, str]], examples: dict[str, str], category: str
) -> list[str]:
    rows = []
    for i, (code, info) in enumerate(theme_dict.items()):
        quote = truncate_quote(examples[code])
        category_cell = (
            rf"\multirow{{{len(theme_dict)}}}{{*}}{{\textbf{{{category}}}}}" if i == 0 else ""
        )
        rows.append(
            rf"{category_cell} & \texttt{{{escape_latex(code)}}} & "
            rf"{escape_latex(info['name'])} & ``{escape_latex(quote)}'' "
            rf"\\[{ROW_SPACING}]"
        )
    return rows


def build_table(
    diff_dict: dict[str, dict[str, str]],
    strat_dict: dict[str, dict[str, str]],
    examples: dict[str, str],
    caption: str,
    label: str,
) -> str:
    # Column widths sum to ~12.6cm (m{} widths) + ~1.8cm auto Category column
    # + ~1.3cm auto Code column + ~1.1cm tabcolsep padding (4 cols x 2 x 4pt)
    # = ~16.8cm, leaving ~0.9cm of margin under AAAI's ~17.7cm two-column
    # (table*) width. The Name column must wrap (not a bare `l`) since
    # several theme names alone run to ~7-8cm unwrapped (e.g. "Combinatorial
    # ambiguity / overlap reasoning"), which would overflow the width alone.
    #
    # A single table* can't paginate, so all 21 rows must fit within one
    # AAAI page's height (verified via real pdflatex compile). At
    # \tabcolsep=6pt / Example=9.5cm there was ~0 slack -- \arraystretch
    # couldn't be raised even slightly, and per-row extra space topped out
    # at an imperceptible ~0.4pt. Tightening tabcolsep to 4pt and widening
    # Example to 10.0cm (both content-neutral -- no quote truncation
    # needed) freed enough room for ROW_SPACING="3pt" of real, visible
    # extra space between entries via `\\[3pt]` on each data row (verified:
    # up to 4pt fits, 5pt overflows by ~1pt, so 3pt keeps a safety margin).
    lines = [
        r"\begin{table*}[t]",
        r"\centering",
        r"{\small",
        r"\renewcommand{\arraystretch}{1.0}",
        r"\setlength{\tabcolsep}{4pt}",
        r"\begin{tabular}{llm{2.6cm}m{10.0cm}}",
        r"\toprule",
        r"\textbf{Category} & \textbf{Code} & \textbf{Theme / Strategy} & \textbf{Example} \\",
        r"\midrule",
        *_data_rows(diff_dict, examples, "Difficulty"),
        r"\midrule",
        *_data_rows(strat_dict, examples, "Strategy"),
        r"\bottomrule",
        r"\end{tabular}",
        r"}",
        rf"\caption{{{caption}}}",
        rf"\label{{{label}}}",
        r"\end{table*}",
    ]
    return "\n".join(lines)


def main() -> None:
    examples = build_examples()

    missing = [
        code
        for code in {**DIFFICULTY_THEMES, **STRATEGY_TAXONOMY}
        if code not in examples
    ]
    if missing:
        raise RuntimeError(f"No example response found for codes: {missing}")

    table_tex = build_table(
        DIFFICULTY_THEMES, STRATEGY_TAXONOMY, examples,
        # Shortened from a version that also named which survey fields each
        # half applies to ("applied to rating_reason + comments" / "applied
        # to strategy") -- that detail didn't fit alongside ROW_SPACING once
        # the caption's own wrapped height was accounted for (verified via
        # real pdflatex compile). State it in the surrounding prose instead
        # if it needs to appear somewhere.
        caption="Difficulty themes and strategy taxonomy, with example responses",
        label="tab:codebook-examples",
    )

    preamble_note = (
        "% Requires \\usepackage{array}, \\usepackage{booktabs}, and "
        "\\usepackage{multirow} in your preamble (for the m{} column type, "
        "\\toprule/\\midrule/\\bottomrule, and the Category column's "
        "\\multirow below) -- remove this comment once added.\n"
    )

    out_path = FIG_DIR / "codebook_examples_latex.txt"
    out_path.write_text(preamble_note + "\n" + table_tex + "\n", encoding="utf-8")
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
