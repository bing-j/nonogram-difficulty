"""
Shared statistical helpers for every analyze-data/ script that needs
multiple-comparisons correction. Previously duplicated inside
text_coding_analysis.py; centralized here once behavioral_regression.py,
spearman_ranking.py, and expertise_adjustment.py all needed the same
Benjamini-Hochberg FDR correction and had none.
"""

from __future__ import annotations

import numpy as np


def benjamini_hochberg(pvalues) -> list[float]:
    """BH-FDR adjusted p-values; NaNs preserved, order matches input."""
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
