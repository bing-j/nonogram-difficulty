"""
Step 04 - Construct a composite EXPERTISE score from the multi-dimensional
self-reported background, and compare three construction methods.

Expertise dimensions (all oriented so higher = more expert):
  * skill_nonogram             self-rated Nonogram skill (1-10)
  * skill_puzzles              self-rated general logic-puzzle skill (1-10)
  * played_before_ord          Nonogram play frequency (0-3)
  * puzzle_played_frequency_ord general logic-puzzle frequency (0-3)
  * n_nonogram_sizes           breadth of Nonogram sizes solved (0-4)
  * n_logic_puzzles            breadth of other logic puzzles known (0-5)

Composite methods:
  A. z-mean        equal-weighted mean of standardized dimensions
  B. PCA-1         first principal component score
  C. FA-1          single common-factor score (regression scores)

Outputs: participant_expertise.csv (+ tiers), diagnostic figures & tables.
Read-only with respect to the repository.
"""

from __future__ import annotations

from analysis_utils import DERIVED, FIG_DIR, PALETTE  # sets MPLCONFIGDIR before mpl

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.decomposition import PCA, FactorAnalysis

from nono_data import load_participant_puzzle_df

EXP_FIG = FIG_DIR / "expertise"
EXP_FIG.mkdir(parents=True, exist_ok=True)

DIMS = ["skill_nonogram", "skill_puzzles", "played_before_ord",
        "puzzle_played_frequency_ord", "n_nonogram_sizes", "n_logic_puzzles"]
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


def main() -> None:
    base = load_participant_puzzle_df()
    part = base.groupby("participant_id").agg({d: "first" for d in DIMS}).reset_index()
    for d in DIMS:
        part[d] = pd.to_numeric(part[d], errors="coerce")

    n_missing_any = int(part[DIMS].isna().any(axis=1).sum())

    # Standardize each dimension; mean-impute missing standardized values to 0.
    means = part[DIMS].mean()
    sds = part[DIMS].std(ddof=0).replace(0, np.nan)
    z = (part[DIMS] - means) / sds
    z_filled = z.fillna(0.0)
    z_cols = [f"z_{d}" for d in DIMS]
    for d, zc in zip(DIMS, z_cols):
        part[zc] = z_filled[d]

    # --- A. z-mean (use only available dims per participant) --------------- #
    part["exp_zmean"] = z.mean(axis=1, skipna=True)
    part["exp_zmean"] = part["exp_zmean"].fillna(0.0)

    # --- B. PCA-1 ---------------------------------------------------------- #
    X = z_filled.to_numpy()
    pca = PCA(n_components=len(DIMS))
    pc_scores = pca.fit_transform(X)
    # Orient PC1 so it positively correlates with z-mean.
    pc1 = pc_scores[:, 0]
    if np.corrcoef(pc1, part["exp_zmean"])[0, 1] < 0:
        pc1 = -pc1
        pca_loadings = -pca.components_[0]
    else:
        pca_loadings = pca.components_[0]
    part["exp_pca"] = (pc1 - pc1.mean()) / pc1.std(ddof=0)

    # --- C. FA-1 ----------------------------------------------------------- #
    fa = FactorAnalysis(n_components=1, random_state=0)
    fa_scores = fa.fit_transform(X).ravel()
    fa_load = fa.components_[0]
    if np.corrcoef(fa_scores, part["exp_zmean"])[0, 1] < 0:
        fa_scores = -fa_scores
        fa_load = -fa_load
    part["exp_fa"] = (fa_scores - fa_scores.mean()) / fa_scores.std(ddof=0)

    # Standardize z-mean too for comparability.
    part["exp_zmean_z"] = (part["exp_zmean"] - part["exp_zmean"].mean()) / part["exp_zmean"].std(ddof=0)

    # Tiers from the z-mean (primary), tertiles.
    part["expertise_tier"] = pd.qcut(part["exp_zmean_z"], 3, labels=["novice", "intermediate", "expert"])

    # ---- Diagnostics ------------------------------------------------------ #
    alpha = cronbach_alpha_standardized(z_filled)
    corr = z_filled.corr()
    var_explained = pca.explained_variance_ratio_

    # composite agreement
    comp_corr = part[["exp_zmean_z", "exp_pca", "exp_fa"]].corr(method="spearman")

    # save table
    out_cols = (["participant_id"] + DIMS + z_cols
                + ["exp_zmean", "exp_zmean_z", "exp_pca", "exp_fa", "expertise_tier"])
    part[out_cols].to_csv(DERIVED / "participant_expertise.csv", index=False)

    # diagnostics tables
    load_df = pd.DataFrame({
        "dimension": DIMS,
        "pca1_loading": pca_loadings,
        "fa1_loading": fa_load,
        "corr_with_zmean": [np.corrcoef(z_filled[d], part["exp_zmean_z"])[0, 1] for d in DIMS],
    })
    load_df.to_csv(DERIVED / "expertise_loadings.csv", index=False)
    corr.to_csv(DERIVED / "expertise_dimension_correlations.csv")
    pd.DataFrame({
        "metric": ["cronbach_alpha_standardized", "pca1_var_explained", "pca2_var_explained",
                   "n_participants", "n_missing_any_dim"],
        "value": [alpha, var_explained[0], var_explained[1], len(part), n_missing_any],
    }).to_csv(DERIVED / "expertise_diagnostics.csv", index=False)

    # ---- Figures ---------------------------------------------------------- #
    # 1. dimension correlation heatmap
    fig, ax = plt.subplots(figsize=(7.5, 6.5), dpi=160)
    im = ax.imshow(corr.to_numpy(), cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(len(DIMS))); ax.set_yticks(range(len(DIMS)))
    ax.set_xticklabels([DIM_LABELS[d] for d in DIMS], rotation=45, ha="right", fontsize=8)
    ax.set_yticklabels([DIM_LABELS[d] for d in DIMS], fontsize=8)
    for i in range(len(DIMS)):
        for j in range(len(DIMS)):
            ax.text(j, i, f"{corr.iloc[i, j]:.2f}", ha="center", va="center", fontsize=8,
                    color="black")
    ax.set_title(f"Expertise dimensions: inter-correlations\nstandardized Cronbach alpha = {alpha:.2f}")
    fig.colorbar(im, ax=ax, label="Pearson r")
    fig.tight_layout()
    fig.savefig(EXP_FIG / "01_dimension_correlations.png", bbox_inches="tight")
    plt.close(fig)

    # 2. PCA scree + PC1 loadings
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), dpi=160)
    axes[0].plot(range(1, len(var_explained) + 1), var_explained, "o-", color=PALETTE[0])
    axes[0].set_xlabel("Principal component"); axes[0].set_ylabel("Variance explained")
    axes[0].set_title("PCA scree plot")
    axes[0].grid(alpha=0.25)
    order = np.argsort(pca_loadings)
    axes[1].barh(range(len(DIMS)), pca_loadings[order], color=PALETTE[1])
    axes[1].set_yticks(range(len(DIMS)))
    axes[1].set_yticklabels([DIM_LABELS[DIMS[i]] for i in order])
    axes[1].set_xlabel("PC1 loading")
    axes[1].set_title(f"PC1 loadings ({var_explained[0]*100:.0f}% variance)")
    axes[1].axvline(0, color="black", lw=0.8)
    fig.tight_layout()
    fig.savefig(EXP_FIG / "02_pca_scree_loadings.png", bbox_inches="tight")
    plt.close(fig)

    # 3. agreement among composites + distribution
    fig, axes = plt.subplots(1, 2, figsize=(13, 5), dpi=160)
    axes[0].scatter(part["exp_zmean_z"], part["exp_pca"], color=PALETTE[0], label="PCA-1", alpha=0.6)
    axes[0].scatter(part["exp_zmean_z"], part["exp_fa"], color=PALETTE[2], label="FA-1", alpha=0.6)
    lims = [-2.5, 2.5]
    axes[0].plot(lims, lims, "--", color="grey")
    axes[0].set_xlabel("z-mean composite"); axes[0].set_ylabel("PCA-1 / FA-1 composite")
    axes[0].set_title("Composite methods agree closely")
    axes[0].legend(); axes[0].grid(alpha=0.25)
    axes[1].hist(part["exp_zmean_z"], bins=12, color=PALETTE[0], edgecolor="white")
    axes[1].set_xlabel("Composite expertise (z-mean, standardized)")
    axes[1].set_ylabel("Participants")
    axes[1].set_title("Distribution of composite expertise")
    fig.tight_layout()
    fig.savefig(EXP_FIG / "03_composite_agreement.png", bbox_inches="tight")
    plt.close(fig)

    # ---- console ---------------------------------------------------------- #
    print("=== EXPERTISE SCORE CONSTRUCTION ===")
    print(f"participants: {len(part)}, missing>=1 dim: {n_missing_any}")
    print(f"standardized Cronbach alpha: {alpha:.3f}")
    print(f"PCA variance explained (PC1..): {np.round(var_explained, 3).tolist()}")
    print("\nLoadings:\n", load_df.to_string(index=False))
    print("\nComposite Spearman agreement:\n", comp_corr.to_string())
    print("\nTier counts:\n", part["expertise_tier"].value_counts().to_string())
    print(f"\nWrote participant_expertise.csv and figures -> {EXP_FIG}")


if __name__ == "__main__":
    main()
