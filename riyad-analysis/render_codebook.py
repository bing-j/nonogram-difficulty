"""Render riyad-analysis/derived/codebook.md as a table image.

Reads the two markdown tables (difficulty themes, strategy taxonomy) and
draws them as styled matplotlib tables, stacked in one PNG. Read-only
w.r.t. the repository except for the output figure.
"""

from __future__ import annotations

import re
import textwrap
from pathlib import Path

from analysis_utils import FIG_DIR, PALETTE  # sets MPLCONFIGDIR before mpl

import matplotlib.pyplot as plt

CODEBOOK_MD = Path(__file__).resolve().parent / "derived" / "codebook.md"

HEADER_BG = PALETTE[0]
CODE_COLOR = PALETTE[1]
ROW_BG_ALT = "#f2f2f2"
ROW_BG = "#ffffff"


def parse_markdown_table(lines: list[str]) -> list[tuple[str, str, str]]:
    rows = []
    for line in lines:
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip().strip("`") for c in line.strip("|").split("|")]
        if len(cells) != 3:
            continue
        if cells[0] in ("Code",) or set(cells[0]) <= {"-"}:
            continue
        rows.append((cells[0], cells[1], cells[2]))
    return rows


def load_codebook_tables() -> tuple[list[tuple[str, str, str]], list[tuple[str, str, str]]]:
    text = CODEBOOK_MD.read_text(encoding="utf-8")
    sections = re.split(r"^## ", text, flags=re.MULTILINE)[1:]
    tables: dict[str, list[tuple[str, str, str]]] = {}
    for section in sections:
        header, _, body = section.partition("\n")
        tables[header.strip()] = parse_markdown_table(body.splitlines())
    diff = next(v for k, v in tables.items() if k.startswith("Difficulty themes"))
    strat = next(v for k, v in tables.items() if k.startswith("Strategy taxonomy"))
    return diff, strat


def draw_table(
    ax, rows: list[tuple[str, str, str]], col2_label: str,
    theme_wrap_width: int, def_wrap_width: int,
) -> None:
    ax.axis("off")

    wrapped_themes = [textwrap.wrap(t, width=theme_wrap_width) or [""] for _, t, _ in rows]
    wrapped_defs = [textwrap.wrap(d, width=def_wrap_width) or [""] for _, _, d in rows]
    line_counts = [max(len(t), len(d)) for t, d in zip(wrapped_themes, wrapped_defs)]

    cell_text = [
        [code, "\n".join(wrapped_theme), "\n".join(wrapped_def)]
        for (code, _, _), wrapped_theme, wrapped_def in zip(rows, wrapped_themes, wrapped_defs)
    ]

    table = ax.table(
        cellText=cell_text,
        colLabels=["Code", col2_label, "Definition"],
        colWidths=[0.12, 0.22, 0.66],
        cellLoc="left",
        loc="upper left",
        bbox=[0, 0, 1, 1],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)

    header_weight = 1.3
    row_weights = [max(n, 1) * 1.15 for n in line_counts]
    total_weight = header_weight + sum(row_weights)

    for j in range(3):
        cell = table[0, j]
        cell.set_facecolor(HEADER_BG)
        cell.get_text().set_color("white")
        cell.get_text().set_fontweight("bold")
        cell.set_height(header_weight / total_weight)
        cell.PAD = 0.01

    for i, weight in enumerate(row_weights, start=1):
        bg = ROW_BG_ALT if i % 2 == 0 else ROW_BG
        h = weight / total_weight
        for j in range(3):
            cell = table[i, j]
            cell.set_facecolor(bg)
            cell.set_height(h)
            cell.PAD = 0.01
            cell.get_text().set_va("center")
        table[i, 0].get_text().set_fontweight("bold")
        table[i, 0].get_text().set_color(CODE_COLOR)


def main() -> None:
    diff_rows, strat_rows = load_codebook_tables()

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(11, 15), dpi=150,
        gridspec_kw={"height_ratios": [len(diff_rows), len(strat_rows) * 0.85]},
    )

    draw_table(ax1, diff_rows, "Theme", theme_wrap_width=22, def_wrap_width=60)
    draw_table(ax2, strat_rows, "Strategy", theme_wrap_width=22, def_wrap_width=60)

    fig.tight_layout(h_pad=2.0)
    out_path = FIG_DIR / "codebook.png"
    fig.savefig(out_path, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
