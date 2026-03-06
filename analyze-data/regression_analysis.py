"""
regression_analysis.py
======================
Linear regression analysis of nonogram difficulty ratings against SAT solver
metrics (decisions, propagations, conflicts).

Inputs
------
- backend/logs/p1-Michael.ndjson ... p7-Michael.ndjson
    NDJSON event streams recorded during participant sessions.
    Relevant events:
      * session_start_three  — queue field lists 3 puzzle IDs (integers 0–5)
      * survey_submit / survey_type in {puzzle_1, puzzle_2, puzzle_3}
          answers.difficulty  → in-the-moment (initial) difficulty rating
      * survey_submit / survey_type == "post"
          answers.puzzle_N_rate_again → final (retrospective) difficulty rating
- selected_six_nonogram_stats.csv
    SAT solver metrics for the 6 research puzzles.
    The unnamed index column (0–5) is the experiment puzzle_id.
    Columns used: conflicts, decisions, propagations.

Outputs
-------
- analyze-data/out_features/figures/regression_scatter_grid.png
    3×2 grid of scatter plots (predictor × rating type).
- analyze-data/out_features/figures/regression_per_puzzle_means.png
    Per-puzzle mean difficulty vs SAT predictor, with error bars.
- analyze-data/out_features/figures/regression_residuals.png
    Residual plot and Q-Q plot for the best single-variable regression.

Run from the repo root:
    python analyze-data/regression_analysis.py
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Any

# Force UTF-8 output on Windows so that Unicode characters (±, →, etc.)
# print correctly regardless of the console's default code page.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy.stats as stats
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = REPO_ROOT / "backend" / "logs"
STATS_CSV = REPO_ROOT / "selected_six_nonogram_stats.csv"
FIGURE_DIR = REPO_ROOT / "analyze-data" / "out_features" / "figures"

PREDICTORS: list[str] = ["decisions", "propagations", "conflicts"]
RATING_TYPES: list[str] = ["initial_difficulty", "final_difficulty"]

# Colorblind-friendly colors for 6 puzzle IDs (matplotlib tab10 first 6)
PUZZLE_COLORS: list[str] = [
    "#1f77b4",  # puzzle 0 — blue
    "#ff7f0e",  # puzzle 1 — orange
    "#2ca02c",  # puzzle 2 — green
    "#d62728",  # puzzle 3 — red
    "#9467bd",  # puzzle 4 — purple
    "#8c564b",  # puzzle 5 — brown
]

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def read_ndjson(path: Path) -> list[dict[str, Any]]:
    """Read a newline-delimited JSON file into a list of event dicts.

    Args:
        path: Absolute path to the .ndjson file.

    Returns:
        List of parsed JSON objects, in file order.

    Raises:
        FileNotFoundError: If path does not exist.
        ValueError: If a line contains invalid JSON.
    """
    if not path.exists():
        raise FileNotFoundError(f"Log file not found: {path}")
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, raw in enumerate(fh, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                events.append(json.loads(raw))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON in {path.name} at line {line_no}: {exc}"
                ) from exc
    return events


def extract_participant_ratings(
    participant_id: str, events: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Extract per-puzzle difficulty ratings for one participant.

    Maps the three position slots (puzzle_1 / puzzle_2 / puzzle_3) to actual
    puzzle IDs via the session's queue field, then collects:
      - initial_difficulty  from puzzle_N surveys
      - final_difficulty    from the post survey

    Args:
        participant_id: Human-readable label (e.g. "p1-Michael").
        events: Parsed event list from that participant's NDJSON log.

    Returns:
        List of dicts, each with keys:
          participant_id, puzzle_id, initial_difficulty, final_difficulty.
        Returns an empty list if the session_start_three event is missing.
    """
    # Locate the queue
    queue: list[int] | None = None
    for ev in events:
        if ev.get("type") == "session_start_three":
            queue = ev.get("queue")
            break

    if queue is None or len(queue) != 3:
        print(
            f"  WARNING: {participant_id} has no valid session_start_three queue; skipping.",
            file=sys.stderr,
        )
        return []

    # Collect initial difficulty ratings from per-puzzle surveys
    initial: dict[int, int | None] = {}  # position index → rating
    post_ratings: dict[int, int | None] = {}  # position index → rating

    for ev in events:
        if ev.get("type") != "survey_submit":
            continue
        survey_type = ev.get("survey_type", "")
        answers = ev.get("answers", {})

        # puzzle_N in-the-moment rating
        for pos_idx, label in enumerate(("puzzle_1", "puzzle_2", "puzzle_3")):
            if survey_type == label:
                diff = answers.get("difficulty")
                if diff is not None:
                    initial[pos_idx] = int(diff)

        # post-survey retrospective ratings
        if survey_type == "post":
            for pos_idx, key in enumerate(
                ("puzzle_1_rate_again", "puzzle_2_rate_again", "puzzle_3_rate_again")
            ):
                val = answers.get(key)
                if val is not None:
                    post_ratings[pos_idx] = int(val)

    records = []
    for pos_idx, puzzle_id in enumerate(queue):
        records.append(
            {
                "participant_id": participant_id,
                "puzzle_id": int(puzzle_id),
                "initial_difficulty": initial.get(pos_idx),
                "final_difficulty": post_ratings.get(pos_idx),
            }
        )
    return records


def load_all_ratings(log_dir: Path) -> pd.DataFrame:
    """Load ratings from all participant NDJSON logs in log_dir.

    Args:
        log_dir: Directory containing .ndjson files.

    Returns:
        DataFrame with columns:
          participant_id, puzzle_id, initial_difficulty, final_difficulty.
    """
    log_files = sorted(log_dir.glob("*.ndjson"))
    if not log_files:
        raise FileNotFoundError(f"No .ndjson files found in {log_dir}")

    all_records: list[dict[str, Any]] = []
    for path in log_files:
        participant_id = path.stem  # e.g. "p1-Michael"
        events = read_ndjson(path)
        records = extract_participant_ratings(participant_id, events)
        all_records.extend(records)
        print(f"  Loaded {len(records)} puzzle-ratings from {path.name}")

    df = pd.DataFrame(all_records)
    return df


def load_sat_stats(csv_path: Path) -> pd.DataFrame:
    """Load SAT solver metrics from CSV, using the unnamed row index as puzzle_id.

    The CSV has an unnamed integer index (0–5) that corresponds to the
    experiment puzzle IDs, and a separate 'puzzle_id' column that is an
    internal solver ID (not 0–5). We use the row index (0–5) as the
    experiment puzzle_id and drop the solver's internal puzzle_id column.

    Args:
        csv_path: Path to selected_six_nonogram_stats.csv.

    Returns:
        DataFrame with columns puzzle_id (int 0–5), conflicts, decisions,
        propagations (plus other SAT columns).

    Raises:
        FileNotFoundError: If csv_path does not exist.
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"Stats CSV not found: {csv_path}")
    df = pd.read_csv(csv_path, index_col=0)
    # The unnamed index is the experiment puzzle ID (0–5).
    # Drop the internal 'puzzle_id' column if it exists to avoid collision.
    if "puzzle_id" in df.columns:
        df = df.drop(columns=["puzzle_id"])
    df.index.name = "puzzle_id"
    df = df.reset_index()
    df["puzzle_id"] = df["puzzle_id"].astype(int)
    return df


# ---------------------------------------------------------------------------
# Merging
# ---------------------------------------------------------------------------


def merge_data(ratings: pd.DataFrame, sat_stats: pd.DataFrame) -> pd.DataFrame:
    """Merge participant ratings with SAT solver stats on puzzle_id.

    Args:
        ratings: Output of load_all_ratings().
        sat_stats: Output of load_sat_stats().

    Returns:
        Merged DataFrame; rows with NaN in all rating columns are dropped.
    """
    merged = ratings.merge(sat_stats, on="puzzle_id", how="left")
    # Drop rows where BOTH rating types are missing
    merged = merged.dropna(subset=["initial_difficulty", "final_difficulty"], how="all")
    merged["puzzle_id"] = merged["puzzle_id"].astype(int)
    return merged


# ---------------------------------------------------------------------------
# Summary statistics
# ---------------------------------------------------------------------------


def print_summary_table(df: pd.DataFrame) -> None:
    """Print a summary table of merged data, then per-puzzle statistics.

    Args:
        df: Merged DataFrame with rating + SAT columns.
    """
    print("\n" + "=" * 70)
    print("MERGED DATA SUMMARY")
    print("=" * 70)
    print(f"Total rows: {len(df)}")
    print(f"Participants: {df['participant_id'].nunique()}")
    print(f"Puzzles covered: {sorted(df['puzzle_id'].unique())}")
    null_initial = df["initial_difficulty"].isna().sum()
    null_final = df["final_difficulty"].isna().sum()
    print(f"Missing initial_difficulty: {null_initial}")
    print(f"Missing final_difficulty:   {null_final}")

    print("\nFull merged table:")
    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 120)
    cols_show = [
        "participant_id",
        "puzzle_id",
        "initial_difficulty",
        "final_difficulty",
        "decisions",
        "propagations",
        "conflicts",
    ]
    print(df[cols_show].to_string(index=False))

    print("\n" + "=" * 70)
    print("PER-PUZZLE STATISTICS")
    print("=" * 70)
    for pid in sorted(df["puzzle_id"].unique()):
        sub = df[df["puzzle_id"] == pid]
        dec = sub["decisions"].iloc[0]
        prop = sub["propagations"].iloc[0]
        conf = sub["conflicts"].iloc[0]
        init_mean = sub["initial_difficulty"].mean()
        init_std = sub["initial_difficulty"].std()
        fin_mean = sub["final_difficulty"].mean()
        fin_std = sub["final_difficulty"].std()
        n_init = sub["initial_difficulty"].notna().sum()
        n_fin = sub["final_difficulty"].notna().sum()
        print(
            f"  Puzzle {pid}: "
            f"decisions={dec:4d}  propagations={prop:5d}  conflicts={conf:3d}"
            f"  |  initial={init_mean:.2f}±{init_std:.2f} (n={n_init})"
            f"  final={fin_mean:.2f}±{fin_std:.2f} (n={n_fin})"
        )


# ---------------------------------------------------------------------------
# Regression helpers
# ---------------------------------------------------------------------------


def single_variable_regressions(
    df: pd.DataFrame,
) -> dict[tuple[str, str], dict]:
    """Run simple linear regressions for each predictor × rating combination.

    Uses scipy.stats.linregress.

    Args:
        df: Merged DataFrame.

    Returns:
        Dict keyed by (predictor, rating_type) → result dict with keys:
          slope, intercept, r_value, r_squared, p_value, std_err,
          x_vals (array), y_vals (array), fitted (array), residuals (array).
    """
    results: dict[tuple[str, str], dict] = {}
    for predictor in PREDICTORS:
        for rating in RATING_TYPES:
            sub = df[[predictor, rating]].dropna()
            if len(sub) < 3:
                print(
                    f"  WARNING: not enough data for {predictor} ~ {rating} "
                    f"(n={len(sub)}); skipping.",
                    file=sys.stderr,
                )
                continue
            x = sub[predictor].values.astype(float)
            y = sub[rating].values.astype(float)
            slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
            fitted = slope * x + intercept
            residuals = y - fitted
            results[(predictor, rating)] = {
                "slope": slope,
                "intercept": intercept,
                "r_value": r_value,
                "r_squared": r_value**2,
                "p_value": p_value,
                "std_err": std_err,
                "x_vals": x,
                "y_vals": y,
                "fitted": fitted,
                "residuals": residuals,
                "n": len(sub),
                "predictor": predictor,
                "rating_type": rating,
            }
    return results


def print_regression_results(
    results: dict[tuple[str, str], dict],
) -> tuple[str, str]:
    """Print single-variable regression results and return key of best model.

    Args:
        results: Output of single_variable_regressions().

    Returns:
        Tuple (predictor, rating_type) for the regression with highest R².
    """
    print("\n" + "=" * 70)
    print("SINGLE-VARIABLE LINEAR REGRESSIONS")
    print("=" * 70)
    best_key: tuple[str, str] | None = None
    best_r2 = -1.0
    for (predictor, rating), res in sorted(results.keys().__iter__() if False else results.items()):
        r2 = res["r_squared"]
        p = res["p_value"]
        slope = res["slope"]
        intercept = res["intercept"]
        n = res["n"]
        sig = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else "ns"
        print(
            f"  {rating:20s} ~ {predictor:14s} | "
            f"R²={r2:.4f}  p={p:.4f} {sig:3s}  "
            f"slope={slope:.5f}  intercept={intercept:.4f}  n={n}"
        )
        if r2 > best_r2:
            best_r2 = r2
            best_key = (predictor, rating)
    if best_key:
        print(
            f"\n  Best model: {best_key[1]} ~ {best_key[0]} "
            f"(R²={best_r2:.4f})"
        )
    return best_key  # type: ignore[return-value]


def multiple_regression(df: pd.DataFrame) -> None:
    """Fit and print multiple regression of initial_difficulty on all predictors.

    Uses sklearn.linear_model.LinearRegression.

    Args:
        df: Merged DataFrame.
    """
    print("\n" + "=" * 70)
    print("MULTIPLE REGRESSION: initial_difficulty ~ decisions + propagations + conflicts")
    print("=" * 70)
    sub = df[PREDICTORS + ["initial_difficulty"]].dropna()
    if len(sub) < len(PREDICTORS) + 2:
        print("  Not enough complete cases for multiple regression.")
        return

    X = sub[PREDICTORS].values.astype(float)
    y = sub["initial_difficulty"].values.astype(float)

    model = LinearRegression()
    model.fit(X, y)
    r2 = model.score(X, y)

    print(f"  n = {len(sub)}")
    print(f"  R² = {r2:.4f}")
    print(f"  Intercept: {model.intercept_:.4f}")
    for name, coef in zip(PREDICTORS, model.coef_):
        print(f"  Coefficient [{name:14s}]: {coef:.6f}")

    # Also report standardized coefficients for comparability
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    model_std = LinearRegression()
    model_std.fit(X_scaled, y)
    print("\n  Standardized coefficients (comparable across predictors):")
    for name, coef in zip(PREDICTORS, model_std.coef_):
        print(f"  Beta [{name:14s}]: {coef:.4f}")


# ---------------------------------------------------------------------------
# Plotting helpers
# ---------------------------------------------------------------------------


def _regression_line(
    ax: plt.Axes,
    x: np.ndarray,
    fitted: np.ndarray,
) -> None:
    """Draw the regression line on ax by connecting min/max fitted values.

    Args:
        ax: Target matplotlib Axes.
        x: Predictor values.
        fitted: Fitted (predicted) values from the regression.
    """
    sort_idx = np.argsort(x)
    ax.plot(x[sort_idx], fitted[sort_idx], color="black", linewidth=1.5, zorder=3)


def plot_scatter_grid(
    df: pd.DataFrame,
    results: dict[tuple[str, str], dict],
    output_path: Path,
) -> None:
    """Create a 3×2 scatter grid (predictors × rating types) with regression lines.

    Rows: decisions, propagations, conflicts.
    Columns: initial_difficulty, final_difficulty.
    Points are colored by puzzle_id. One subplot carries the puzzle legend.

    Args:
        df: Merged DataFrame (used for per-point puzzle_id color lookup).
        results: Output of single_variable_regressions().
        output_path: File path to save the figure.
    """
    fig, axes = plt.subplots(3, 2, figsize=(12, 13))
    fig.suptitle(
        "SAT Solver Metrics vs. Difficulty Ratings\n(Linear Regression)",
        fontsize=14,
        fontweight="bold",
        y=0.99,
    )

    for row_idx, predictor in enumerate(PREDICTORS):
        for col_idx, rating in enumerate(RATING_TYPES):
            ax = axes[row_idx][col_idx]
            key = (predictor, rating)

            if key not in results:
                ax.text(0.5, 0.5, "Insufficient data", ha="center", va="center",
                        transform=ax.transAxes)
                ax.set_xlabel(predictor)
                ax.set_ylabel(rating)
                continue

            res = results[key]
            sub = df[[predictor, rating, "puzzle_id"]].dropna(subset=[predictor, rating])

            # Scatter colored by puzzle_id
            for pid in sorted(sub["puzzle_id"].unique()):
                mask = sub["puzzle_id"] == pid
                ax.scatter(
                    sub.loc[mask, predictor],
                    sub.loc[mask, rating],
                    color=PUZZLE_COLORS[int(pid)],
                    s=60,
                    zorder=4,
                    alpha=0.85,
                    label=f"Puzzle {pid}",
                )

            # Regression line
            _regression_line(ax, res["x_vals"], res["fitted"])

            r2 = res["r_squared"]
            p = res["p_value"]
            sig = "***" if p < 0.001 else "**" if p < 0.01 else "*" if p < 0.05 else "ns"
            title = (
                f"{rating.replace('_', ' ').title()} ~ {predictor}\n"
                f"R²={r2:.3f}  p={p:.3f} {sig}"
            )
            ax.set_title(title, fontsize=10)
            ax.set_xlabel(predictor, fontsize=9)
            ax.set_ylabel("Difficulty rating (1–5)", fontsize=9)
            ax.tick_params(labelsize=8)
            ax.set_ylim(0.5, 5.5)
            ax.yaxis.set_major_locator(plt.MultipleLocator(1))
            ax.grid(True, linestyle="--", alpha=0.4)

    # Puzzle legend in bottom-right subplot
    legend_ax = axes[2][1]
    handles = [
        plt.Line2D(
            [0], [0],
            marker="o",
            color="w",
            markerfacecolor=PUZZLE_COLORS[i],
            markersize=8,
            label=f"Puzzle {i}",
        )
        for i in range(6)
    ]
    legend_ax.legend(handles=handles, title="Puzzle ID", fontsize=8, title_fontsize=9,
                     loc="lower right")

    fig.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {output_path}")


def plot_per_puzzle_means(
    df: pd.DataFrame,
    output_path: Path,
) -> None:
    """Plot mean initial and final difficulty vs SAT predictor per puzzle.

    3 subplots, one per predictor. Each shows two lines (initial/final) with
    error bars (±1 std) and per-puzzle labels.

    Args:
        df: Merged DataFrame.
        output_path: File path to save the figure.
    """
    # Compute per-puzzle means and stds
    grouped = (
        df.groupby("puzzle_id")[PREDICTORS + ["initial_difficulty", "final_difficulty"]]
        .agg(["mean", "std"])
    )

    fig, axes = plt.subplots(1, 3, figsize=(16, 5), sharey=False)
    fig.suptitle(
        "Mean Difficulty vs. SAT Predictor by Puzzle\n(error bars = ±1 SD)",
        fontsize=13,
        fontweight="bold",
    )

    for ax, predictor in zip(axes, PREDICTORS):
        puzzle_ids = sorted(df["puzzle_id"].unique())
        x_vals = np.array(
            [grouped.loc[pid, (predictor, "mean")] for pid in puzzle_ids]
        )

        for rating, color, marker, label in [
            ("initial_difficulty", "#1f77b4", "o", "Initial difficulty"),
            ("final_difficulty", "#ff7f0e", "s", "Final difficulty"),
        ]:
            y_means = np.array(
                [grouped.loc[pid, (rating, "mean")] for pid in puzzle_ids]
            )
            y_stds = np.array(
                [grouped.loc[pid, (rating, "std")] for pid in puzzle_ids]
            )
            # Replace NaN stds (n=1 puzzles) with 0
            y_stds = np.nan_to_num(y_stds, nan=0.0)

            # Sort by SAT predictor for connected line
            sort_idx = np.argsort(x_vals)
            ax.errorbar(
                x_vals[sort_idx],
                y_means[sort_idx],
                yerr=y_stds[sort_idx],
                color=color,
                marker=marker,
                markersize=8,
                linewidth=1.5,
                capsize=5,
                label=label,
                zorder=3,
            )
            # Annotate puzzle IDs next to each point
            for i, pid in enumerate(np.array(puzzle_ids)[sort_idx]):
                ax.annotate(
                    f"P{pid}",
                    (x_vals[sort_idx][i], y_means[sort_idx][i]),
                    textcoords="offset points",
                    xytext=(5, 4),
                    fontsize=8,
                    color=color,
                )

        ax.set_xlabel(predictor, fontsize=10)
        ax.set_ylabel("Mean difficulty rating (1–5)", fontsize=10)
        ax.set_title(f"Difficulty vs. {predictor}", fontsize=11)
        ax.set_ylim(0.5, 5.5)
        ax.yaxis.set_major_locator(plt.MultipleLocator(1))
        ax.legend(fontsize=9)
        ax.grid(True, linestyle="--", alpha=0.4)

    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {output_path}")


def plot_residuals(
    results: dict[tuple[str, str], dict],
    best_key: tuple[str, str],
    output_path: Path,
) -> None:
    """Plot residuals vs fitted values and a Q-Q plot for the best regression.

    Args:
        results: Output of single_variable_regressions().
        best_key: (predictor, rating_type) key of the best-R² model.
        output_path: File path to save the figure.
    """
    if best_key not in results:
        print(
            f"  WARNING: best_key {best_key} not in results; skipping residual plot.",
            file=sys.stderr,
        )
        return

    res = results[best_key]
    fitted = res["fitted"]
    residuals = res["residuals"]
    predictor, rating = best_key

    fig, (ax_resid, ax_qq) = plt.subplots(1, 2, figsize=(11, 5))
    fig.suptitle(
        f"Residual Diagnostics — Best Model: {rating} ~ {predictor}\n"
        f"(R²={res['r_squared']:.4f}, n={res['n']})",
        fontsize=12,
        fontweight="bold",
    )

    # --- Residuals vs. fitted ---
    ax_resid.scatter(fitted, residuals, color="#2ca02c", s=55, alpha=0.8, zorder=3)
    ax_resid.axhline(0, color="black", linewidth=1.2, linestyle="--")
    ax_resid.set_xlabel("Fitted values", fontsize=10)
    ax_resid.set_ylabel("Residuals", fontsize=10)
    ax_resid.set_title("Residuals vs. Fitted", fontsize=11)
    ax_resid.grid(True, linestyle="--", alpha=0.4)

    # --- Normal Q-Q plot ---
    (osm, osr), (slope, intercept, r) = stats.probplot(residuals, dist="norm")
    ax_qq.scatter(osm, osr, color="#9467bd", s=55, alpha=0.8, zorder=3)
    # Reference line
    x_line = np.array([osm[0], osm[-1]])
    ax_qq.plot(x_line, slope * x_line + intercept, color="red",
               linewidth=1.5, linestyle="--", label="Normal reference")
    ax_qq.set_xlabel("Theoretical quantiles", fontsize=10)
    ax_qq.set_ylabel("Sample quantiles", fontsize=10)
    ax_qq.set_title("Normal Q-Q Plot of Residuals", fontsize=11)
    ax_qq.legend(fontsize=9)
    ax_qq.grid(True, linestyle="--", alpha=0.4)

    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {output_path}")


# ---------------------------------------------------------------------------
# Findings commentary
# ---------------------------------------------------------------------------


def print_findings(
    results: dict[tuple[str, str], dict],
    best_key: tuple[str, str],
    df: pd.DataFrame,
) -> None:
    """Print analytic commentary on regression results and per-puzzle patterns.

    Args:
        results: Output of single_variable_regressions().
        best_key: Key of the best single-variable model.
        df: Merged DataFrame.
    """
    print("\n" + "=" * 70)
    print("FINDINGS & OBSERVATIONS")
    print("=" * 70)

    # Best predictor
    best_pred, best_rating = best_key
    best_r2 = results[best_key]["r_squared"]
    best_p = results[best_key]["p_value"]
    print(
        f"\n1. Best single predictor of difficulty:\n"
        f"   '{best_pred}' predicting '{best_rating}' achieves the highest R²={best_r2:.4f} "
        f"(p={best_p:.4f}).\n"
        f"   This means ~{best_r2*100:.1f}% of variance in {best_rating} is "
        f"explained by the {best_pred} count."
    )

    # Compare initial vs final across predictors
    print("\n2. Initial vs. final difficulty ratings — predictability comparison:")
    for pred in PREDICTORS:
        r2_init = results.get((pred, "initial_difficulty"), {}).get("r_squared", float("nan"))
        r2_fin = results.get((pred, "final_difficulty"), {}).get("r_squared", float("nan"))
        better = (
            "initial" if r2_init > r2_fin
            else "final" if r2_fin > r2_init
            else "equal"
        )
        print(
            f"   {pred:14s}: initial R²={r2_init:.4f}  final R²={r2_fin:.4f}  "
            f"→ {better} ratings better predicted"
        )

    # Overall comparison
    init_r2s = [
        v["r_squared"]
        for (pred, rat), v in results.items()
        if rat == "initial_difficulty"
    ]
    fin_r2s = [
        v["r_squared"]
        for (pred, rat), v in results.items()
        if rat == "final_difficulty"
    ]
    avg_init = np.mean(init_r2s) if init_r2s else float("nan")
    avg_fin = np.mean(fin_r2s) if fin_r2s else float("nan")
    print(
        f"\n   Average R² across predictors — initial: {avg_init:.4f}, "
        f"final: {avg_fin:.4f}"
    )
    if avg_init > avg_fin:
        print(
            "   In-the-moment ratings are (slightly) better predicted by SAT metrics "
            "than retrospective ratings."
        )
    elif avg_fin > avg_init:
        print(
            "   Retrospective (final) ratings are better predicted by SAT metrics "
            "than in-the-moment ratings."
        )
    else:
        print("   Both rating types are equally predicted by SAT metrics.")

    # Per-puzzle patterns
    print("\n3. Notable per-puzzle patterns:")
    for pid in sorted(df["puzzle_id"].unique()):
        sub = df[df["puzzle_id"] == pid]
        init_vals = sub["initial_difficulty"].dropna().tolist()
        fin_vals = sub["final_difficulty"].dropna().tolist()
        dec = int(sub["decisions"].iloc[0])
        prop = int(sub["propagations"].iloc[0])
        conf = int(sub["conflicts"].iloc[0])
        init_mean = np.mean(init_vals) if init_vals else float("nan")
        fin_mean = np.mean(fin_vals) if fin_vals else float("nan")
        shift = fin_mean - init_mean
        direction = "harder" if shift > 0 else "easier" if shift < 0 else "unchanged"
        print(
            f"   Puzzle {pid} (decisions={dec}, propagations={prop}, conflicts={conf}): "
            f"initial={init_mean:.2f}, final={fin_mean:.2f} "
            f"(retrospective shift: {shift:+.2f} → {direction})"
        )

    # Significance summary
    print("\n4. Statistical significance (α=0.05):")
    for (pred, rating), res in sorted(results.items()):
        sig = "SIGNIFICANT" if res["p_value"] < 0.05 else "not significant"
        print(
            f"   {rating:20s} ~ {pred:14s}: p={res['p_value']:.4f} → {sig}"
        )

    print(
        "\n5. Caveats:\n"
        "   - Sample size is small (n=7 participants, 21 puzzle-ratings).\n"
        "   - Only 6 distinct SAT-metric values are available, so scatter plots\n"
        "     show many ties on the x-axis. Results should be interpreted cautiously.\n"
        "   - Ordinal difficulty ratings are treated as continuous; this is a\n"
        "     common simplification but violates strict OLS assumptions."
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the full regression analysis pipeline."""
    print("=" * 70)
    print("NONOGRAM DIFFICULTY — REGRESSION ANALYSIS")
    print("=" * 70)

    # Ensure output directory exists
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Load data
    print("\n[1/5] Loading participant ratings from logs...")
    ratings_df = load_all_ratings(LOG_DIR)

    print("\n[2/5] Loading SAT solver stats...")
    sat_df = load_sat_stats(STATS_CSV)
    print(sat_df[["puzzle_id"] + PREDICTORS].to_string(index=False))

    # 3. Merge
    df = merge_data(ratings_df, sat_df)

    # 4. Summary
    print_summary_table(df)

    # 5. Regressions
    print("\n[3/5] Running single-variable regressions...")
    sv_results = single_variable_regressions(df)
    best_key = print_regression_results(sv_results)

    print("\n[4/5] Running multiple regression...")
    multiple_regression(df)

    # 6. Plots
    print("\n[5/5] Generating figures...")
    plot_scatter_grid(df, sv_results, FIGURE_DIR / "regression_scatter_grid.png")
    plot_per_puzzle_means(df, FIGURE_DIR / "regression_per_puzzle_means.png")
    plot_residuals(sv_results, best_key, FIGURE_DIR / "regression_residuals.png")

    # 7. Findings
    print_findings(sv_results, best_key, df)

    print("\n" + "=" * 70)
    print("Analysis complete.")
    print("=" * 70)


if __name__ == "__main__":
    main()
