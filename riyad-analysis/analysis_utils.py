"""Shared statistics + plotting helpers for the riyad-analysis scripts (read-only)."""

from __future__ import annotations

import os
from pathlib import Path

_CACHE = Path(__file__).resolve().parent / ".mplcache"
_CACHE.mkdir(exist_ok=True)
os.environ["MPLCONFIGDIR"] = str(_CACHE)
os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np
import pandas as pd
from scipy import stats

HERE = Path(__file__).resolve().parent
DERIVED = HERE / "derived"
FIG_DIR = HERE / "figures"
DERIVED.mkdir(exist_ok=True)
FIG_DIR.mkdir(exist_ok=True)

# Consistent, colorblind-friendly palette.
PALETTE = ["#2c6e9c", "#b8531f", "#3f8a5a", "#8a5fa3", "#c0a02c", "#5a5a5a"]


def cohens_d(a: np.ndarray, b: np.ndarray) -> float:
    """Hedges-free Cohen's d for two independent groups (pooled SD)."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    if len(a) < 2 or len(b) < 2:
        return float("nan")
    na, nb = len(a), len(b)
    sp2 = ((na - 1) * a.var(ddof=1) + (nb - 1) * b.var(ddof=1)) / (na + nb - 2)
    if sp2 <= 0:
        return float("nan")
    return (a.mean() - b.mean()) / np.sqrt(sp2)


def rank_biserial_from_u(u: float, n1: int, n2: int) -> float:
    """Rank-biserial effect size from a Mann-Whitney U statistic."""
    if n1 == 0 or n2 == 0:
        return float("nan")
    return 1.0 - (2.0 * u) / (n1 * n2)


def group_compare(values: pd.Series, present: pd.Series) -> dict:
    """Compare a numeric outcome between code-present vs code-absent groups.

    Returns means, Mann-Whitney U test, point-biserial r, and Cohen's d.
    """
    df = pd.DataFrame({"y": pd.to_numeric(values, errors="coerce"),
                       "g": present.astype(int)}).dropna()
    a = df.loc[df["g"] == 1, "y"].to_numpy()
    b = df.loc[df["g"] == 0, "y"].to_numpy()
    out = {
        "n_present": int(len(a)),
        "n_absent": int(len(b)),
        "mean_present": float(a.mean()) if len(a) else float("nan"),
        "mean_absent": float(b.mean()) if len(b) else float("nan"),
        "median_present": float(np.median(a)) if len(a) else float("nan"),
        "median_absent": float(np.median(b)) if len(b) else float("nan"),
        "mannwhitney_u": float("nan"),
        "mannwhitney_p": float("nan"),
        "rank_biserial": float("nan"),
        "pointbiserial_r": float("nan"),
        "pointbiserial_p": float("nan"),
        "cohens_d": cohens_d(a, b),
    }
    if len(a) >= 2 and len(b) >= 2:
        u, p = stats.mannwhitneyu(a, b, alternative="two-sided")
        out["mannwhitney_u"] = float(u)
        out["mannwhitney_p"] = float(p)
        out["rank_biserial"] = rank_biserial_from_u(u, len(a), len(b))
        if df["g"].nunique() == 2 and df["y"].nunique() > 1:
            r, rp = stats.pointbiserialr(df["g"], df["y"])
            out["pointbiserial_r"] = float(r)
            out["pointbiserial_p"] = float(rp)
    return out


def benjamini_hochberg(pvalues: list[float]) -> list[float]:
    """BH-FDR adjusted p-values; NaNs preserved."""
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
