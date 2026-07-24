"""
expertise_diagnostics.py
=========================
Validates the naive z-mean expertise composite (expertise.py, baked into
behavioral_features.csv as `expertise_composite`) against a PCA of the same
six background dimensions.

The composite itself is NOT recomputed here -- expertise.py / Step 2 remain
the single source of truth for `expertise_composite`. This step only checks:
do the six dimensions hang together as one construct (Cronbach's alpha,
dimension correlations), and does an unsupervised PCA of them agree with the
z-mean composite (orientation-checked PC1, standardized, correlated against
the composite)?

Ported from an earlier standalone exploratory analysis's z-mean/PCA methods
(since removed from the repo). Factor Analysis (that analysis's third method)
is intentionally excluded.

Inputs
------
- analyze-data/out_features/behavioral_features.csv

Outputs
-------
- analyze-data/out_features/expertise_dimension_correlations.csv
- analyze-data/out_features/expertise_diagnostics.csv
- analyze-data/out_features/expertise_loadings.csv
- analyze-data/out_features/figures/expertise_dimension_correlations.png
- analyze-data/out_features/figures/expertise_pca_scree_loadings.png
- analyze-data/out_features/figures/expertise_composite_agreement.png

Usage
-----
  python analyze-data/expertise_diagnostics.py
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy.stats as stats
from sklearn.decomposition import PCA

sys.path.insert(0, str(Path(__file__).resolve().parent))
from expertise import EXPERTISE_DIMS  # noqa: E402
from plot_style import NEUTRAL_COLOR, apply_style  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FEATURES_CSV = REPO_ROOT / "analyze-data" / "out_features" / "behavioral_features.csv"
DEFAULT_OUT_DIR = REPO_ROOT / "analyze-data" / "out_features"

DIM_LABELS = {
    "skill_nonogram": "Nonogram skill (1-10)",
    "skill_puzzles": "Puzzle skill (1-10)",
    "played_before_ord": "Nonogram frequency",
    "puzzle_played_frequency_ord": "Puzzle frequency",
    "n_nonogram_sizes": "Nonogram size breadth",
    "n_logic_puzzles": "Logic-puzzle breadth",
}


def cronbach_alpha_standardized(z: pd.DataFrame) -> float:
    """Standardized Cronbach's alpha (items already z-scored)."""
    k = z.shape[1]
    item_var = z.var(axis=0, ddof=1).sum()
    total_var = z.sum(axis=1).var(ddof=1)
    if total_var == 0:
        return float("nan")
    return (k / (k - 1)) * (1 - item_var / total_var)


def load_participant_dims(features_csv: Path) -> pd.DataFrame:
    df = pd.read_csv(features_csv)
    part = df.groupby("participant_id")[EXPERTISE_DIMS + ["expertise_composite"]].first()
    for dim in EXPERTISE_DIMS:
        part[dim] = pd.to_numeric(part[dim], errors="coerce")
    return part


def main() -> None:
    ap = argparse.ArgumentParser(description="PCA validation of the expertise z-mean composite.")
    ap.add_argument("--features_csv", type=Path, default=DEFAULT_FEATURES_CSV)
    ap.add_argument("--out_dir", type=Path, default=DEFAULT_OUT_DIR)
    args = ap.parse_args()

    apply_style()

    if not args.features_csv.exists():
        print(f"Features CSV not found: {args.features_csv}")
        print("Run extract_behavioral_features.py first.")
        return

    fig_dir = args.out_dir / "figures"
    args.out_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    part = load_participant_dims(args.features_csv)
    n_participants = len(part)
    n_missing_any = int(part[EXPERTISE_DIMS].isna().any(axis=1).sum())

    means = part[EXPERTISE_DIMS].mean()
    sds = part[EXPERTISE_DIMS].std(ddof=0).replace(0, np.nan)
    z = (part[EXPERTISE_DIMS] - means) / sds
    z_filled = z.fillna(0.0)
    zmean_raw = z.mean(axis=1, skipna=True)  # unstandardized, for PCA orientation check only

    alpha = cronbach_alpha_standardized(z_filled)
    corr = z_filled.corr()

    # --- PCA ---
    X = z_filled.to_numpy()
    pca = PCA(n_components=len(EXPERTISE_DIMS))
    pc_scores = pca.fit_transform(X)
    pc1 = pc_scores[:, 0]
    if np.corrcoef(pc1, zmean_raw)[0, 1] < 0:
        pc1 = -pc1
        pca_loadings = -pca.components_[0]
    else:
        pca_loadings = pca.components_[0]
    expertise_pca = (pc1 - pc1.mean()) / pc1.std(ddof=0)
    var_explained = pca.explained_variance_ratio_

    # --- Agreement with the composite already in behavioral_features.csv ---
    rho, p = stats.spearmanr(part["expertise_composite"], expertise_pca)

    print("=" * 60)
    print("EXPERTISE COMPOSITE DIAGNOSTICS")
    print("=" * 60)
    print(f"Participants: {n_participants}  (missing >=1 dim: {n_missing_any})")
    print(f"Standardized Cronbach's alpha: {alpha:.3f}")
    print(f"PCA variance explained (PC1, PC2): {var_explained[0]:.3f}, {var_explained[1]:.3f}")
    print(f"Composite vs PCA-1 agreement: Spearman rho={rho:.3f}, p={p:.4f}")

    # --- Save tables ---
    corr.to_csv(args.out_dir / "expertise_dimension_correlations.csv")

    load_df = pd.DataFrame({
        "dimension": EXPERTISE_DIMS,
        "pca1_loading": pca_loadings,
        "corr_with_composite": [
            np.corrcoef(z_filled[d], part["expertise_composite"])[0, 1] for d in EXPERTISE_DIMS
        ],
    })
    load_df.to_csv(args.out_dir / "expertise_loadings.csv", index=False)

    pd.DataFrame({
        "metric": [
            "cronbach_alpha", "pca1_var_explained", "pca2_var_explained",
            "n_participants", "n_missing_any_dim",
            "composite_pca_spearman_rho", "composite_pca_spearman_p",
        ],
        "value": [
            alpha, var_explained[0], var_explained[1],
            n_participants, n_missing_any, rho, p,
        ],
    }).to_csv(args.out_dir / "expertise_diagnostics.csv", index=False)

    # --- Figures ---
    fig, ax = plt.subplots(figsize=(7.5, 6.5), dpi=160)
    im = ax.imshow(corr.to_numpy(), cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(EXPERTISE_DIMS)))
    ax.set_yticks(range(len(EXPERTISE_DIMS)))
    ax.set_xticklabels([DIM_LABELS[d] for d in EXPERTISE_DIMS], rotation=45, ha="right", fontsize=8)
    ax.set_yticklabels([DIM_LABELS[d] for d in EXPERTISE_DIMS], fontsize=8)
    for i in range(len(EXPERTISE_DIMS)):
        for j in range(len(EXPERTISE_DIMS)):
            ax.text(j, i, f"{corr.iloc[i, j]:.2f}", ha="center", va="center", fontsize=8, color="black")
    ax.set_title(f"Expertise dimensions: inter-correlations\nstandardized Cronbach alpha = {alpha:.2f}")
    fig.colorbar(im, ax=ax, label="Pearson r")
    fig.tight_layout()
    fig.savefig(fig_dir / "expertise_dimension_correlations.png", bbox_inches="tight")
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(13, 5), dpi=160)
    axes[0].plot(range(1, len(var_explained) + 1), var_explained, "o-", color=NEUTRAL_COLOR)
    axes[0].set_xlabel("Principal component")
    axes[0].set_ylabel("Variance explained")
    axes[0].set_title("PCA scree plot")
    axes[0].grid(alpha=0.25)
    order = np.argsort(pca_loadings)
    axes[1].barh(range(len(EXPERTISE_DIMS)), pca_loadings[order], color=NEUTRAL_COLOR)
    axes[1].set_yticks(range(len(EXPERTISE_DIMS)))
    axes[1].set_yticklabels([DIM_LABELS[EXPERTISE_DIMS[i]] for i in order])
    axes[1].set_xlabel("PC1 loading")
    axes[1].set_title(f"PC1 loadings ({var_explained[0] * 100:.0f}% variance)")
    axes[1].axvline(0, color="black", lw=0.8)
    fig.tight_layout()
    fig.savefig(fig_dir / "expertise_pca_scree_loadings.png", bbox_inches="tight")
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(13, 5), dpi=160)
    axes[0].scatter(part["expertise_composite"], expertise_pca, color=NEUTRAL_COLOR, alpha=0.6)
    lims = [-2.5, 2.5]
    axes[0].plot(lims, lims, "--", color="grey")
    axes[0].set_xlabel("z-mean composite (expertise_composite)")
    axes[0].set_ylabel("PCA-1 composite")
    axes[0].set_title(f"Composite vs PCA-1 agreement\nSpearman rho={rho:.3f}, p={p:.3f}")
    axes[0].grid(alpha=0.25)
    axes[1].hist(part["expertise_composite"], bins=12, color=NEUTRAL_COLOR, edgecolor="white")
    axes[1].set_xlabel("expertise_composite (z-mean, standardized)")
    axes[1].set_ylabel("Participants")
    axes[1].set_title("Distribution of composite expertise")
    fig.tight_layout()
    fig.savefig(fig_dir / "expertise_composite_agreement.png", bbox_inches="tight")
    plt.close(fig)

    print(f"\nWrote diagnostics tables and figures -> {args.out_dir}")
    print("\nDone.")


if __name__ == "__main__":
    main()
