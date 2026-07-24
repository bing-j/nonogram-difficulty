"""
Shared matplotlib style and color palette for every figure-producing script
in this repo (analyze-data/*.py and the root-level expertise scripts).
"""

import matplotlib.pyplot as plt

# Single-series marks/lines that aren't doing identity-coding work. Puzzle
# identity is carried by direct labels, axis ticks, or facet position
# instead of color, so this is the only mark color most figures need.
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
