"""
Plot the distribution of inter-event gaps within puzzle windows to inform
a data-driven pause threshold for extract_behavioral_features.py.

Collects every consecutive gap between interaction events (moves, hints,
checks, etc.) within each puzzle window across all participants. Gaps at
puzzle boundaries are excluded.

Output:
  analyze-data/out_features/gap_distribution.png     — original four-panel plot
  analyze-data/out_features/gap_log_intervals.png    — log-interval + GMM fit
  analyze-data/out_features/pause_sensitivity.png    — sensitivity analysis

Run:
  python analyze-data/plot_gap_distribution.py

After running, copy the printed --pause_threshold value and pass it to
extract_behavioral_features.py.
"""

import argparse
import glob
import os
import sys

import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import minimize_scalar
from scipy.stats import median_abs_deviation
from sklearn.mixture import GaussianMixture

sys.path.insert(0, os.path.dirname(__file__))
from extract_features import (
    is_interaction_event,
    parse_time,
    read_ndjson,
    segment_puzzles,
    slice_events_by_time,
)


# ---------------------------------------------------------------------------
# Gap collection
# ---------------------------------------------------------------------------

def collect_gaps_from_file(path: str):
    """Return (flat_gaps, per_window_gaps) for all puzzle windows in one file."""
    try:
        events = read_ndjson(path)
        windows = segment_puzzles(events)
    except ValueError as exc:
        print(f"  SKIP {os.path.basename(path)}: {exc}")
        return [], []

    flat_gaps = []
    per_window_gaps = []
    for start_t, end_t in windows:
        chunk = slice_events_by_time(events, start_t, end_t)
        times = sorted(
            parse_time(e["t"])
            for e in chunk
            if is_interaction_event(e.get("type", ""))
        )
        window_gaps = [
            (times[i + 1] - times[i]).total_seconds()
            for i in range(len(times) - 1)
        ]
        flat_gaps.extend(window_gaps)
        per_window_gaps.append(window_gaps)
    return flat_gaps, per_window_gaps


# ---------------------------------------------------------------------------
# Descriptive stats
# ---------------------------------------------------------------------------

def print_stats(gaps: np.ndarray) -> None:
    print(f"\nTotal gaps: {len(gaps)}")
    print(f"  min={gaps.min():.3f}s  max={gaps.max():.1f}s  "
          f"mean={gaps.mean():.2f}s  median={np.median(gaps):.2f}s")
    print("\nPercentiles:")
    for pct in [50, 75, 90, 95, 99]:
        print(f"  {pct}th: {np.percentile(gaps, pct):.2f}s")
    print("\nGaps above threshold:")
    for thresh in [3, 5, 10, 20, 30]:
        n = (gaps >= thresh).sum()
        print(f"  >= {thresh:2d}s: {n:4d}  ({100 * n / len(gaps):.1f}%)")


# ---------------------------------------------------------------------------
# Original four-panel plot (unchanged)
# ---------------------------------------------------------------------------

def plot(gaps: np.ndarray, out_path: str) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    fig.suptitle("Inter-event gap distribution (within-puzzle, interaction events only)", fontsize=12)

    ax = axes[0, 0]
    bins = np.arange(0, 30.5, 0.5)
    ax.hist(gaps[gaps <= 30], bins=bins, color="steelblue", edgecolor="none")
    ax.set_xlabel("Gap (s)")
    ax.set_ylabel("Count")
    ax.set_title("Linear scale, 0–30 s (0.5 s bins)")

    ax = axes[0, 1]
    log_bins = np.logspace(np.log10(max(gaps.min(), 0.01)), np.log10(gaps.max()), 60)
    ax.hist(gaps, bins=log_bins, color="steelblue", edgecolor="none")
    ax.set_xscale("log")
    ax.set_xlabel("Gap (s, log scale)")
    ax.set_ylabel("Count")
    ax.set_title("Log scale, full range")

    ax = axes[1, 0]
    sorted_gaps = np.sort(gaps)
    ecdf = np.arange(1, len(sorted_gaps) + 1) / len(sorted_gaps)
    ax.plot(sorted_gaps, ecdf, lw=1.2, color="steelblue")
    ax.set_xscale("log")
    ax.set_xlabel("Gap (s, log scale)")
    ax.set_ylabel("Cumulative fraction")
    ax.set_title("ECDF (log x-axis)")
    ax.axhline(0.90, color="gray", lw=0.8, linestyle="--", label="90th pct")
    ax.axhline(0.95, color="gray", lw=0.8, linestyle=":",  label="95th pct")
    ax.legend(fontsize=8)
    ax.grid(True, which="both", alpha=0.3)

    ax = axes[1, 1]
    bins60 = np.arange(0, 61, 1)
    ax.hist(gaps[gaps <= 60], bins=bins60, color="steelblue", edgecolor="none")
    for thresh, col in [(3, "orange"), (5, "red"), (10, "purple"), (20, "green")]:
        ax.axvline(thresh, color=col, lw=1.2, linestyle="--", label=f"{thresh}s")
    ax.set_xlabel("Gap (s)")
    ax.set_ylabel("Count")
    ax.set_title("Zoomed 0–60 s (1 s bins) with candidate thresholds")
    ax.legend(fontsize=8)

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"\nSaved: {out_path}")


# ---------------------------------------------------------------------------
# GMM bimodality analysis
# ---------------------------------------------------------------------------

def _sort_gmm_components(gmm: GaussianMixture) -> None:
    """Sort GMM components in-place by ascending mean."""
    order = np.argsort(gmm.means_.ravel())
    gmm.means_ = gmm.means_[order]
    gmm.covariances_ = gmm.covariances_[order]
    gmm.weights_ = gmm.weights_[order]
    gmm.precisions_ = gmm.precisions_[order]
    gmm.precisions_cholesky_ = gmm.precisions_cholesky_[order]


def fit_gmm_on_log_gaps(gaps: np.ndarray) -> dict:
    """Fit 1-, 2-, and 3-component GMMs on log(gap); compare BICs.

    The 3-component model is the primary fit:
      Component 0 — UI artifact  (rapid drag/multi-cell selections)
      Component 1 — normal interaction gaps
      Component 2 — cognitive pauses
    The pause threshold is the crossover between components 1 and 2.
    """
    log_gaps = np.log(gaps[gaps > 0]).reshape(-1, 1)

    gmm1 = GaussianMixture(n_components=1, covariance_type="full", random_state=42)
    gmm1.fit(log_gaps)

    gmm2 = GaussianMixture(n_components=2, covariance_type="full", n_init=10, random_state=42)
    gmm2.fit(log_gaps)

    gmm3 = GaussianMixture(n_components=3, covariance_type="full", n_init=10, random_state=42)
    gmm3.fit(log_gaps)

    bic1 = gmm1.bic(log_gaps)
    bic2 = gmm2.bic(log_gaps)
    bic3 = gmm3.bic(log_gaps)

    for gmm in (gmm2, gmm3):
        _sort_gmm_components(gmm)

    # Primary comparison: 3-component vs 1-component
    delta_bic_3v1 = bic1 - bic3
    delta_bic_2v1 = bic1 - bic2
    best_n = int(np.argmin([bic1, bic2, bic3])) + 1

    return {
        "gmm1": gmm1,
        "gmm2": gmm2,
        "gmm3": gmm3,
        "bic1": bic1,
        "bic2": bic2,
        "bic3": bic3,
        "delta_bic_3v1": delta_bic_3v1,
        "delta_bic_2v1": delta_bic_2v1,
        "best_n": best_n,
        "log_gaps": log_gaps,
    }


def find_gmm_crossover(gmm: GaussianMixture, comp_a: int, comp_b: int) -> float:
    """Find the equal-posterior crossover between components comp_a and comp_b.

    Solves w_a * N(x; mu_a, sigma_a) = w_b * N(x; mu_b, sigma_b) in log-space,
    using Brent's method on the interval [mu_a, mu_b].

    This is the point where the posterior probability of belonging to comp_b
    first exceeds that of comp_a, i.e., P(comp_b | x) = 0.5.
    Returns the crossover in seconds.
    """
    import scipy.stats as stats
    from scipy.optimize import brentq

    mus = gmm.means_.ravel()
    sigmas = np.sqrt(gmm.covariances_[:, 0, 0])
    weights = gmm.weights_

    def density_diff(x):
        da = weights[comp_a] * stats.norm.pdf(x, mus[comp_a], sigmas[comp_a])
        db = weights[comp_b] * stats.norm.pdf(x, mus[comp_b], sigmas[comp_b])
        return da - db

    lo, hi = mus[comp_a], mus[comp_b]
    # If no sign change the components don't cross; fall back to midpoint
    if density_diff(lo) * density_diff(hi) > 0:
        return float(np.exp((lo + hi) / 2))

    root = brentq(density_diff, lo, hi)
    return float(np.exp(root))


# ---------------------------------------------------------------------------
# Per-participant fallback threshold
# ---------------------------------------------------------------------------

def compute_fallback_threshold(gaps_by_participant: dict) -> dict:
    """Compute per-participant (median + 3·MAD) thresholds; return global median."""
    per_participant = []
    skipped = []
    for pid, participant_gaps in gaps_by_participant.items():
        arr = np.array([g for g in participant_gaps if g > 0])
        if len(arr) < 2:
            skipped.append(pid)
            continue
        med = np.median(arr)
        mad = median_abs_deviation(arr, scale=1)
        per_participant.append(med + 3 * mad)

    global_threshold = float(np.median(per_participant)) if per_participant else 5.0
    return {
        "per_participant_thresholds": per_participant,
        "global_threshold": global_threshold,
        "n_participants": len(per_participant),
        "n_skipped": len(skipped),
    }


# ---------------------------------------------------------------------------
# Threshold selection
# ---------------------------------------------------------------------------

def select_threshold(gmm_result: dict, gaps_by_participant: dict) -> dict:
    """Choose threshold from 3-component GMM (components 1->2 crossover) or fallback.

    Component 0 is treated as the UI-artifact (rapid drag/multi-cell) component
    and is excluded from the threshold calculation.  The pause threshold is the
    full-mixture density minimum between the means of components 1 and 2.

    Falls back to per-participant (median + 3*MAD) if the 3-component model does
    not beat the 1-component baseline by at least 10 BIC points.
    """
    gmm3 = gmm_result["gmm3"]
    delta_bic = gmm_result["delta_bic_3v1"]
    best_n = gmm_result["best_n"]
    use_gmm = delta_bic >= 10

    if use_gmm:
        threshold = find_gmm_crossover(gmm3, comp_a=1, comp_b=2)
        mus = gmm3.means_.ravel()
        sigmas = np.sqrt(gmm3.covariances_[:, 0, 0])
        ws = gmm3.weights_
        crossover_log = np.log(threshold)

        justification = (
            f"\n{'=' * 45}\n"
            f"  PAUSE THRESHOLD SELECTION\n"
            f"{'=' * 45}\n"
            f"  Method    : 3-component GMM crossover on log(gap_s)\n"
            f"  dBIC (3 vs 1 component): {delta_bic:.1f} (>= 10 -> structured)\n"
            f"  Best BIC model: {best_n} components\n"
            f"  Comp 0 (UI artifact): mean = {np.exp(mus[0]):.3f}s  "
            f"(log mu={mus[0]:.3f}, sd={sigmas[0]:.3f}, w={ws[0]:.3f})\n"
            f"  Comp 1 (interaction): mean = {np.exp(mus[1]):.3f}s  "
            f"(log mu={mus[1]:.3f}, sd={sigmas[1]:.3f}, w={ws[1]:.3f})\n"
            f"  Comp 2 (pause)      : mean = {np.exp(mus[2]):.3f}s  "
            f"(log mu={mus[2]:.3f}, sd={sigmas[2]:.3f}, w={ws[2]:.3f})\n"
            f"  Equal-posterior crossover (1->2, log-space): {crossover_log:.3f}  ->  {threshold:.2f}s\n"
            f"  Chosen threshold : {threshold:.2f}s\n"
            f"  Reproduce with   : python analyze-data/extract_behavioral_features.py "
            f"--pause_threshold {threshold:.2f}\n"
            f"{'=' * 45}"
        )
        fallback_result = None
    else:
        fallback_result = compute_fallback_threshold(gaps_by_participant)
        threshold = fallback_result["global_threshold"]
        pts = fallback_result["per_participant_thresholds"]
        justification = (
            f"\n{'=' * 45}\n"
            f"  PAUSE THRESHOLD SELECTION\n"
            f"{'=' * 45}\n"
            f"  Method    : Per-participant fallback (median + 3*MAD)\n"
            f"  dBIC (3 vs 1 component): {delta_bic:.1f} (< 10 -> no clear structure)\n"
            f"  Per-participant thresholds (n={fallback_result['n_participants']}):\n"
            f"    min={min(pts):.2f}s  median={np.median(pts):.2f}s  max={max(pts):.2f}s\n"
            f"  Global threshold = median of per-participant thresholds\n"
            f"  Chosen threshold : {threshold:.2f}s\n"
            f"  Reproduce with   : python analyze-data/extract_behavioral_features.py "
            f"--pause_threshold {threshold:.2f}\n"
            f"{'=' * 45}"
        )

    return {
        "threshold": threshold,
        "justification": justification,
        "gmm_result": gmm_result,
        "fallback_result": fallback_result,
    }


# ---------------------------------------------------------------------------
# New plot: log-interval histogram + GMM
# ---------------------------------------------------------------------------

def plot_log_intervals(gmm_result: dict, threshold: float, out_path: str) -> None:
    import scipy.stats as stats

    log_gaps = gmm_result["log_gaps"].ravel()
    gmm3 = gmm_result["gmm3"]
    delta_bic = gmm_result["delta_bic_3v1"]
    best_n = gmm_result["best_n"]
    use_gmm = delta_bic >= 10

    mus = gmm3.means_.ravel()
    sigmas = np.sqrt(gmm3.covariances_[:, 0, 0])
    ws = gmm3.weights_

    comp_colors = ["steelblue", "darkorange", "purple"]
    comp_labels = [
        f"Comp 0 UI artifact (mean={np.exp(mus[0]):.2f}s)",
        f"Comp 1 interaction  (mean={np.exp(mus[1]):.2f}s)",
        f"Comp 2 pause        (mean={np.exp(mus[2]):.2f}s)",
    ]

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # --- Left panel: log(gap) histogram + 3-component GMM overlay ---
    ax = axes[0]
    ax.hist(log_gaps, bins=60, density=True, color="lightsteelblue",
            edgecolor="none", alpha=0.7, label="Observed")

    x_plot = np.linspace(log_gaps.min(), log_gaps.max(), 500)

    mixture = sum(ws[k] * stats.norm.pdf(x_plot, mus[k], sigmas[k]) for k in range(3))
    ax.plot(x_plot, mixture, color="red", lw=2, label="GMM mixture (3 comp)")

    for k in range(3):
        ax.plot(x_plot, ws[k] * stats.norm.pdf(x_plot, mus[k], sigmas[k]),
                color=comp_colors[k], lw=1.3, linestyle="--", label=comp_labels[k])

    ax.axvline(np.log(threshold), color="orange", lw=1.8, linestyle="-",
               label=f"Equal-posterior threshold: {threshold:.2f}s")
    ax.text(0.97, 0.97,
            f"dBIC (3v1) = {delta_bic:.1f}\nbest n = {best_n}",
            transform=ax.transAxes, ha="right", va="top", fontsize=8,
            bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow", edgecolor="gray"))
    ax.set_xlabel("log(gap_seconds)")
    ax.set_ylabel("Density")
    ax.set_title("Log-interval distribution with 3-component GMM")
    ax.legend(fontsize=7.5)

    # --- Right panel: component means on seconds scale ---
    ax = axes[1]
    x_sec = np.linspace(0, min(np.exp(mus[2]) * 4, 150), 600)
    # plot mixture PDF in seconds space for visual reference
    log_x = np.log(np.maximum(x_sec, 1e-6))
    # Jacobian: p(x) = p(log x) / x
    mixture_sec = sum(
        ws[k] * stats.norm.pdf(log_x, mus[k], sigmas[k])
        for k in range(3)
    ) / np.maximum(x_sec, 1e-6)
    ax.plot(x_sec, mixture_sec, color="red", lw=1.5, alpha=0.6, label="Mixture PDF")

    for k in range(3):
        comp_sec = ws[k] * stats.norm.pdf(log_x, mus[k], sigmas[k]) / np.maximum(x_sec, 1e-6)
        ax.plot(x_sec, comp_sec, color=comp_colors[k], lw=1.3,
                linestyle="--", label=comp_labels[k])
        ax.axvline(np.exp(mus[k]), color=comp_colors[k], lw=0.8, linestyle=":")

    ax.axvline(threshold, color="orange", lw=2, linestyle="-",
               label=f"Threshold: {threshold:.2f}s")
    ax.set_xlim(0, min(np.exp(mus[2]) * 4, 150))
    ax.set_xlabel("Gap (seconds)")
    ax.set_ylabel("Density")
    ax.set_title("Component means - seconds scale")
    ax.legend(fontsize=7.5)

    fig.suptitle(
        f"3-component GMM log-interval analysis  |  dBIC(3v1)={delta_bic:.1f}  |  "
        f"pause threshold = {threshold:.2f}s",
        fontsize=10,
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"Saved: {out_path}")


# ---------------------------------------------------------------------------
# New plot: sensitivity analysis
# ---------------------------------------------------------------------------

def plot_sensitivity(
    per_window_gaps: list,
    chosen_threshold: float,
    out_path: str,
) -> None:
    thresholds = np.logspace(np.log10(2), np.log10(30), 20)

    means = []
    sds = []
    for t in thresholds:
        counts = [sum(1 for g in window if g >= t) for window in per_window_gaps]
        means.append(np.mean(counts))
        sds.append(np.std(counts))

    means = np.array(means)
    sds = np.array(sds)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(thresholds, means, color="steelblue", lw=2, label="Mean pause count")
    ax.fill_between(thresholds, means - sds, np.maximum(means - sds, 0),
                    alpha=0.2, color="steelblue")
    ax.fill_between(thresholds, means, means + sds, alpha=0.2, color="steelblue",
                    label="±1 SD")
    ax.axvline(chosen_threshold, color="orange", lw=1.8, linestyle="--",
               label=f"Chosen: {chosen_threshold:.2f}s")
    ax.text(chosen_threshold * 1.05, ax.get_ylim()[1] * 0.95,
            f"{chosen_threshold:.2f}s", color="orange", fontsize=9, va="top")
    ax.set_xscale("log")
    ax.set_xlabel("Threshold (s, log scale)")
    ax.set_ylabel("Mean pause count per observation")
    ax.set_title("Pause count sensitivity to threshold (2s - 30s band)")
    ax.legend(fontsize=9)
    ax.grid(True, which="both", alpha=0.25)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"Saved: {out_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Plot gap distributions and select a data-driven pause threshold."
    )
    ap.add_argument(
        "--input_glob",
        default=os.path.join(os.path.dirname(__file__), "..", "backend", "logs", "*.ndjson"),
    )
    ap.add_argument(
        "--out_dir",
        default=os.path.join(os.path.dirname(__file__), "out_features"),
    )
    args = ap.parse_args()

    paths = sorted(glob.glob(args.input_glob))
    if not paths:
        print(f"No files matched: {args.input_glob}")
        return

    all_gaps = []
    per_window_gaps = []
    gaps_by_participant = {}

    for path in paths:
        flat, windows = collect_gaps_from_file(path)
        all_gaps.extend(flat)
        per_window_gaps.extend(windows)
        pid = os.path.basename(path).replace(".ndjson", "")
        if flat:
            gaps_by_participant.setdefault(pid, []).extend(flat)

    if not all_gaps:
        print("No gaps collected.")
        return

    gaps = np.array(all_gaps)
    print_stats(gaps)

    os.makedirs(args.out_dir, exist_ok=True)

    # Existing four-panel plot
    plot(gaps, os.path.join(args.out_dir, "gap_distribution.png"))

    # GMM bimodality analysis + threshold selection
    gmm_result = fit_gmm_on_log_gaps(gaps)
    selection = select_threshold(gmm_result, gaps_by_participant)

    print(selection["justification"])

    # Log-interval + GMM plot
    plot_log_intervals(
        gmm_result,
        selection["threshold"],
        os.path.join(args.out_dir, "gap_log_intervals.png"),
    )

    # Sensitivity analysis plot
    plot_sensitivity(
        per_window_gaps,
        selection["threshold"],
        os.path.join(args.out_dir, "pause_sensitivity.png"),
    )


if __name__ == "__main__":
    main()
