"""
Shared matplotlib style and color palette for every figure-producing script
in this repo (analyze-data/*.py and the root-level expertise scripts).
"""

import matplotlib.pyplot as plt

# Single-series marks/lines that aren't doing identity-coding work. Puzzle
# identity is carried by direct labels, axis ticks, or facet position
# instead of color, so this is the only mark color most figures need.
NEUTRAL_COLOR = "#4D4D4D"

# Lighter grayscale shades for ramps (e.g. tercile/group splits) that stay
# within the grayscale budget rather than spending one of the two accents.
GRAY_LIGHT = "#D8D8D8"
GRAY_MID = "#8F8F8F"

# The only two non-grayscale colors used anywhere in this repo's figures.
# Reserve them for cases plain gray can't carry: highlighting a subset
# (ACCENT_COLOR) or distinguishing a second simultaneous series from a first
# (ACCENT_COLOR_2). Continuous data-encoding colormaps (correlation heatmaps,
# frequency heatmaps) are a separate visual language and are exempt from
# this two-color budget.
ACCENT_COLOR = "#B8531F"
ACCENT_COLOR_2 = "#3B6E8F"

# 3-shade light/base/dark tints of each accent, for the rare case of a
# categorical series (e.g. low/mean/high expertise) that wants visibility
# beyond plain gray but must stay internally distinguishable -- not a third
# and fourth identity color, just tints of the two above.
ACCENT_TINT_LIGHT = "#E3A377"
ACCENT_TINT_DARK = "#7A3712"
ACCENT_COLOR_2_LIGHT = "#8FB6C9"
ACCENT_COLOR_2_DARK = "#204759"


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
