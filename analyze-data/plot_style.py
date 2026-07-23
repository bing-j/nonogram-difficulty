"""
Shared matplotlib style and color palette for every figure-producing script
in this repo (analyze-data/*.py and the root-level expertise scripts).

Colors follow Okabe & Ito (2002), a colorblind-safe qualitative palette --
the standard choice for scientific figures. Black and yellow are reserved
(black for OLS/reference lines, yellow skipped for poor contrast on white),
leaving exactly six colors for the six research puzzles.
"""

import matplotlib.pyplot as plt

PUZZLE_COLORS = [
    "#0072B2",  # P0 - blue
    "#E69F00",  # P1 - orange
    "#009E73",  # P2 - green
    "#D55E00",  # P3 - vermillion
    "#56B4E9",  # P4 - sky blue
    "#CC79A7",  # P5 - pink
]

# Single-series marks/lines that aren't doing identity-coding work.
NEUTRAL_COLOR = "#4D4D4D"


def apply_style() -> None:
    """Call once near the start of a script's entry point."""
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.size": 10,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.color": "#cccccc",
        "grid.linewidth": 0.6,
        "grid.linestyle": "-",
        "axes.axisbelow": True,
        "savefig.dpi": 150,
        "figure.dpi": 100,
    })
