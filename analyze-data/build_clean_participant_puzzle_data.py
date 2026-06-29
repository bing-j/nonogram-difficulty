"""
Build a clean participant-puzzle-level dataset for the Nonogram study.

Inputs, read-only:
  - backend/logs/*.ndjson and backend/logs/*.json
  - solver_statistics.txt

Output:
  - outputs/clean_participant_puzzle_data.csv

Run from the repository root:
  python3 analyze-data/build_clean_participant_puzzle_data.py
"""

from __future__ import annotations

import argparse
import ast
import itertools
import json
import math
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/nonogram-difficulty-matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/private/tmp/nonogram-difficulty-cache")
os.environ.setdefault("MPLBACKEND", "Agg")
import matplotlib.pyplot as plt
import numpy as np


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOG_DIR = REPO_ROOT / "backend" / "logs"
DEFAULT_SOLVER_STATS = REPO_ROOT / "solver_statistics.txt"
DEFAULT_OUTPUT_CSV = REPO_ROOT / "outputs" / "clean_participant_puzzle_data.csv"

LOG_EXTENSIONS = {".ndjson", ".json"}
INTERACTION_EVENT_TYPES = {
    "move",
    "drag",
    "hint",
    "hint_none",
    "undo",
    "reset",
    "check_bank",
}


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def natural_log_sort_key(path: Path) -> tuple[str, int, str]:
    match = re.match(r"^(?P<host>.+)-p(?P<num>\d+)$", path.stem)
    if not match:
        return (path.stem, 0, path.suffix)
    return (match.group("host"), int(match.group("num")), path.suffix)


def source_metadata(path: Path) -> tuple[str | None, str | None]:
    match = re.match(r"^(?P<host>.+)-(?P<label>p\d+)$", path.stem)
    if not match:
        return None, None
    return match.group("host"), match.group("label")


def read_event_log(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON in {path} line {line_number}: {exc}") from exc
    return events


def coerce_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def extract_participant_rows(
    participant_id: str,
    source_file: str,
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    start_event = next((event for event in events if event.get("type") == "session_start_three"), None)
    queue = start_event.get("queue") if start_event else None
    if not isinstance(queue, list) or len(queue) == 0:
        return []

    host, host_participant_label = source_metadata(Path(source_file))
    n_slots = min(3, len(queue))

    initial_ratings: dict[int, int | None] = {}
    final_ratings: dict[int, int | None] = {}
    pre_answers: dict[str, Any] = {}
    first_interaction_at: dict[int, datetime] = {}
    completed_at: dict[int, datetime] = {}
    skipped: dict[int, bool] = {}
    completed: dict[int, bool] = {}

    current_order_idx = 0

    for event in events:
        event_type = event.get("type")
        event_time = parse_time(event.get("t"))

        if event_type in INTERACTION_EVENT_TYPES and current_order_idx < n_slots and event_time:
            first_interaction_at.setdefault(current_order_idx, event_time)

        if event_type == "survey_submit":
            survey_type = event.get("survey_type")
            answers = event.get("answers") or {}

            if survey_type == "pre" and isinstance(answers, dict):
                pre_answers = answers

            if survey_type in {"puzzle_1", "puzzle_2", "puzzle_3"}:
                order_idx = int(survey_type.split("_")[1]) - 1
                if isinstance(answers, dict):
                    initial_ratings[order_idx] = coerce_int(answers.get("difficulty"))

            if survey_type == "post" and isinstance(answers, dict):
                for order_idx in range(3):
                    key = f"puzzle_{order_idx + 1}_rate_again"
                    final_ratings[order_idx] = coerce_int(answers.get(key))

        if event_type == "check_bank" and current_order_idx < n_slots:
            if event.get("solved") is True:
                completed[current_order_idx] = True
                if event_time:
                    completed_at[current_order_idx] = event_time
                current_order_idx += 1

        if event_type == "skip_puzzle":
            order_idx = coerce_int(event.get("idx"))
            if order_idx is None:
                order_idx = current_order_idx
            if 0 <= order_idx < n_slots:
                skipped[order_idx] = True
                completed.setdefault(order_idx, False)
            current_order_idx = max(current_order_idx, order_idx + 1)

    rows: list[dict[str, Any]] = []
    for order_idx in range(n_slots):
        solved = bool(completed.get(order_idx, False))
        start_time = first_interaction_at.get(order_idx)
        end_time = completed_at.get(order_idx)
        human_time_to_solve = None
        if solved and start_time and end_time:
            human_time_to_solve = (end_time - start_time).total_seconds()

        initial_rating = initial_ratings.get(order_idx)
        final_rating = final_ratings.get(order_idx)
        rating_change = None
        if initial_rating is not None and final_rating is not None:
            rating_change = final_rating - initial_rating

        rows.append(
            {
                "participant_id": participant_id,
                "source_file": source_file,
                "host": host,
                "host_participant_label": host_participant_label,
                "puzzle_id": coerce_int(queue[order_idx]),
                "order": order_idx + 1,
                "completed": solved,
                "skipped": bool(skipped.get(order_idx, False)),
                "initial_rating": initial_rating,
                "final_rating": final_rating,
                "rating_change": rating_change,
                "experience_level": coerce_int(pre_answers.get("skill_nonogram")),
                "played_before": pre_answers.get("played_before"),
                "skill_nonogram": coerce_int(pre_answers.get("skill_nonogram")),
                "skill_puzzles": coerce_int(pre_answers.get("skill_puzzles")),
                "nonogram_size_experience": json.dumps(
                    pre_answers.get("nonogram_size_experience"), ensure_ascii=True
                )
                if "nonogram_size_experience" in pre_answers
                else None,
                "logic_experience": json.dumps(
                    pre_answers.get("logic_experience"), ensure_ascii=True
                )
                if "logic_experience" in pre_answers
                else None,
                "puzzle_played_frequency": pre_answers.get("puzzle_played_frequency"),
                "human_time_to_solve": human_time_to_solve,
            }
        )

    return rows


def load_human_data(log_dir: Path) -> pd.DataFrame:
    log_files = sorted(
        [path for path in log_dir.iterdir() if path.is_file() and path.suffix in LOG_EXTENSIONS],
        key=natural_log_sort_key,
    )
    if not log_files:
        raise FileNotFoundError(f"No participant log files found in {log_dir}")

    rows: list[dict[str, Any]] = []
    for index, path in enumerate(log_files, start=1):
        participant_id = f"P{index:03d}"
        events = read_event_log(path)
        rows.extend(extract_participant_rows(participant_id, path.name, events))

    return pd.DataFrame(rows)


def load_minisat_stats(stats_path: Path) -> pd.DataFrame:
    if not stats_path.exists():
        raise FileNotFoundError(f"Solver statistics file not found: {stats_path}")

    rows: list[dict[str, Any]] = []
    current_puzzle_id: int | None = None
    current_solver: str | None = None

    for raw_line in stats_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("puzzle id:"):
            current_puzzle_id = int(line.split(":", 1)[1].strip())
            current_solver = None
            continue
        if line.startswith("Solver:"):
            current_solver = line.split(":", 1)[1].strip()
            continue
        if line.startswith("{"):
            stats = ast.literal_eval(line)
            solver_name = current_solver or stats.get("backend")
            if solver_name == "MiniSat22" or stats.get("backend") == "Minisat22":
                rows.append(
                    {
                        "puzzle_id": current_puzzle_id,
                        "conflicts": stats.get("conflicts"),
                        "decisions": stats.get("decisions"),
                        "propagations": stats.get("propagations"),
                        "sat_time_to_solve": stats.get("time_ms"),
                    }
                )

    if not rows:
        raise ValueError(f"No MiniSat22 statistics found in {stats_path}")

    sat_df = pd.DataFrame(rows)
    for column in ["conflicts", "decisions", "propagations", "sat_time_to_solve"]:
        sat_df[column] = pd.to_numeric(sat_df[column], errors="coerce")

    sat_df["log_conflicts"] = sat_df["conflicts"].map(lambda value: math.log1p(value))
    sat_df["log_decisions"] = sat_df["decisions"].map(lambda value: math.log1p(value))
    sat_df["log_propagations"] = sat_df["propagations"].map(lambda value: math.log1p(value))
    sat_df["log_sat_time"] = sat_df["sat_time_to_solve"].map(lambda value: math.log1p(value))
    return sat_df


def validate_dataset(df: pd.DataFrame) -> None:
    print("\nValidation summary")
    print("==================")
    print(f"Rows: {len(df)}")
    print(f"Unique participants: {df['participant_id'].nunique()}")
    print(f"Unique puzzles: {df['puzzle_id'].nunique()}")

    print("\nAttempts per puzzle:")
    print(df.groupby("puzzle_id").size().rename("attempts").to_string())

    print("\nCompleted/incomplete attempts per puzzle:")
    completion_summary = (
        df.assign(incomplete=~df["completed"].astype(bool))
        .groupby("puzzle_id")
        .agg(completed=("completed", "sum"), incomplete=("incomplete", "sum"))
    )
    print(completion_summary.to_string())

    print("\nMissing rating values:")
    print(df[["initial_rating", "final_rating", "rating_change"]].isna().sum().to_string())

    attempts_per_participant = df.groupby("participant_id").size()
    print("\nAttempts per participant:")
    print(attempts_per_participant.value_counts().sort_index().rename("participants").to_string())
    print(f"Every participant has at most 3 attempts: {bool((attempts_per_participant <= 3).all())}")
    print(f"Every participant has exactly 3 attempts: {bool((attempts_per_participant == 3).all())}")

    missing_sat = df[["conflicts", "decisions", "propagations", "sat_time_to_solve"]].isna().sum()
    print("\nMissing SAT values after merge:")
    print(missing_sat.to_string())


def build_assignment_balance_tables(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    assignment_counts = (
        df.groupby("puzzle_id")
        .size()
        .rename("assigned_count")
        .reset_index()
        .sort_values("puzzle_id")
    )

    order_counts = (
        df.pivot_table(
            index="puzzle_id",
            columns="order",
            values="participant_id",
            aggfunc="count",
            fill_value=0,
        )
        .rename(columns={1: "order_1_count", 2: "order_2_count", 3: "order_3_count"})
        .reset_index()
    )

    expected_order_columns = ["order_1_count", "order_2_count", "order_3_count"]
    for column in expected_order_columns:
        if column not in order_counts.columns:
            order_counts[column] = 0
    order_counts = order_counts[["puzzle_id", *expected_order_columns]].sort_values("puzzle_id")

    pair_rows: list[dict[str, int]] = []
    for participant_id, participant_rows in df.groupby("participant_id"):
        puzzle_ids = sorted(set(participant_rows["puzzle_id"].dropna().astype(int)))
        for puzzle_a, puzzle_b in itertools.combinations(puzzle_ids, 2):
            pair_rows.append(
                {
                    "puzzle_a": puzzle_a,
                    "puzzle_b": puzzle_b,
                    "participant_id": participant_id,
                }
            )

    if pair_rows:
        pair_counts = (
            pd.DataFrame(pair_rows)
            .groupby(["puzzle_a", "puzzle_b"])
            .size()
            .rename("pair_count")
            .reset_index()
            .sort_values(["puzzle_a", "puzzle_b"])
        )
    else:
        pair_counts = pd.DataFrame(columns=["puzzle_a", "puzzle_b", "pair_count"])

    return assignment_counts, order_counts, pair_counts


def describe_balance_range(values: pd.Series) -> str:
    min_value = int(values.min())
    max_value = int(values.max())
    spread = max_value - min_value
    mean_value = float(values.mean())
    pct_spread = (spread / mean_value * 100) if mean_value else 0.0
    return f"range {min_value}-{max_value}, spread {spread} ({pct_spread:.1f}% of mean)"


def save_assignment_balance_outputs(df: pd.DataFrame, output_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    assignment_counts, order_counts, pair_counts = build_assignment_balance_tables(df)

    assignment_counts.to_csv(output_dir / "puzzle_assignment_counts.csv", index=False)
    order_counts.to_csv(output_dir / "puzzle_order_counts.csv", index=False)
    pair_counts.to_csv(output_dir / "puzzle_pair_counts.csv", index=False)

    print("\nAssignment balance")
    print("==================")
    print("\nPuzzle assignment counts:")
    print(assignment_counts.to_string(index=False))

    print("\nPuzzle order counts:")
    print(order_counts.to_string(index=False))

    print("\nPuzzle pair counts:")
    print(pair_counts.to_string(index=False))

    assigned = assignment_counts["assigned_count"]
    print("\nInterpretation:")
    print(f"- Puzzle representation: {describe_balance_range(assigned)}.")

    order_long = order_counts.melt(
        id_vars="puzzle_id",
        value_vars=["order_1_count", "order_2_count", "order_3_count"],
        var_name="order_position",
        value_name="count",
    )
    order_min = int(order_long["count"].min())
    order_max = int(order_long["count"].max())
    high_order_rows = order_long[order_long["count"] == order_max]
    high_order_labels = ", ".join(
        f"puzzle {int(row.puzzle_id)} in {row.order_position.replace('_count', '').replace('_', ' ')}"
        for row in high_order_rows.itertuples(index=False)
    )
    print(
        "- Order representation: "
        f"cell counts range {order_min}-{order_max}; highest cell(s): {high_order_labels}."
    )

    if pair_counts.empty:
        print("- Puzzle pairs: no pair counts available.")
    else:
        pair_min = int(pair_counts["pair_count"].min())
        pair_max = int(pair_counts["pair_count"].max())
        high_pairs = pair_counts[pair_counts["pair_count"] == pair_max]
        high_pair_labels = ", ".join(
            f"({int(row.puzzle_a)}, {int(row.puzzle_b)})"
            for row in high_pairs.itertuples(index=False)
        )
        print(
            "- Puzzle pairs: "
            f"counts range {pair_min}-{pair_max}; most common pair(s): {high_pair_labels}."
        )
    return assignment_counts, order_counts, pair_counts


def add_participant_centered_final_rating(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    participant_mean = df.groupby("participant_id")["final_rating"].transform("mean")
    df["centered_final_rating"] = df["final_rating"] - participant_mean
    return df


def build_puzzle_human_difficulty_summary(df: pd.DataFrame) -> pd.DataFrame:
    summary = (
        df.groupby("puzzle_id")
        .agg(
            n_assigned=("participant_id", "size"),
            n_completed=("completed", "sum"),
            n_final_ratings_available=("final_rating", "count"),
            mean_final_rating=("final_rating", "mean"),
            median_final_rating=("final_rating", "median"),
            sd_final_rating=("final_rating", "std"),
            mean_initial_rating=("initial_rating", "mean"),
            median_initial_rating=("initial_rating", "median"),
            mean_rating_change=("rating_change", "mean"),
            mean_human_time_to_solve=("human_time_to_solve", "mean"),
            mean_centered_final_rating=("centered_final_rating", "mean"),
            median_centered_final_rating=("centered_final_rating", "median"),
        )
        .reset_index()
        .sort_values("puzzle_id")
    )

    summary["se_final_rating"] = (
        summary["sd_final_rating"] / summary["n_final_ratings_available"].pow(0.5)
    )
    summary["completion_rate"] = summary["n_completed"] / summary["n_assigned"]

    column_order = [
        "puzzle_id",
        "n_assigned",
        "n_completed",
        "n_final_ratings_available",
        "mean_final_rating",
        "median_final_rating",
        "sd_final_rating",
        "se_final_rating",
        "mean_initial_rating",
        "median_initial_rating",
        "mean_rating_change",
        "completion_rate",
        "mean_human_time_to_solve",
        "mean_centered_final_rating",
        "median_centered_final_rating",
    ]
    return summary[column_order]


def save_puzzle_human_difficulty_summary(df: pd.DataFrame, output_dir: Path) -> None:
    summary = build_puzzle_human_difficulty_summary(df)
    output_path = output_dir / "puzzle_human_difficulty_summary.csv"
    summary.to_csv(output_path, index=False)

    print("\nPuzzle-level human difficulty summary")
    print("=====================================")
    print(summary.to_string(index=False))
    print(f"\nWrote puzzle-level summary to {output_path}")


def build_puzzle_level_difficulty_vs_sat(
    human_summary: pd.DataFrame,
    sat_df: pd.DataFrame,
) -> pd.DataFrame:
    human_columns = [
        "puzzle_id",
        "mean_final_rating",
        "median_final_rating",
        "mean_centered_final_rating",
        "completion_rate",
        "mean_initial_rating",
        "mean_rating_change",
        "mean_human_time_to_solve",
    ]
    sat_columns = [
        "puzzle_id",
        "conflicts",
        "decisions",
        "propagations",
        "sat_time_to_solve",
        "log_conflicts",
        "log_decisions",
        "log_propagations",
        "log_sat_time",
    ]
    merged = human_summary[human_columns].merge(
        sat_df[sat_columns],
        on="puzzle_id",
        how="inner",
        validate="one_to_one",
    )
    merged = merged.sort_values("puzzle_id").reset_index(drop=True)

    if len(merged) != 6:
        raise ValueError(f"Expected 6 puzzle-level rows, found {len(merged)}")
    if merged["puzzle_id"].nunique() != len(merged):
        raise ValueError("Puzzle-level dataset does not have exactly one row per puzzle_id")

    return merged


def save_puzzle_level_difficulty_vs_sat(
    human_df: pd.DataFrame,
    sat_df: pd.DataFrame,
    output_dir: Path,
) -> None:
    human_summary = build_puzzle_human_difficulty_summary(human_df)
    final_df = build_puzzle_level_difficulty_vs_sat(human_summary, sat_df)
    output_path = output_dir / "puzzle_level_difficulty_vs_sat.csv"
    final_df.to_csv(output_path, index=False)

    print("\nPuzzle-level difficulty vs SAT dataset")
    print("======================================")
    print(final_df.to_string(index=False))
    print(f"\nWrote puzzle-level difficulty vs SAT dataset to {output_path}")


def pearson_correlation(x_values: list[float], y_values: list[float]) -> float:
    n = len(x_values)
    if n < 2:
        return math.nan
    x_mean = sum(x_values) / n
    y_mean = sum(y_values) / n
    x_diffs = [value - x_mean for value in x_values]
    y_diffs = [value - y_mean for value in y_values]
    numerator = sum(x_diff * y_diff for x_diff, y_diff in zip(x_diffs, y_diffs))
    x_ss = sum(x_diff * x_diff for x_diff in x_diffs)
    y_ss = sum(y_diff * y_diff for y_diff in y_diffs)
    denominator = math.sqrt(x_ss * y_ss)
    if denominator == 0:
        return math.nan
    return numerator / denominator


def average_ranks(values: list[float]) -> list[float]:
    sorted_pairs = sorted((value, index) for index, value in enumerate(values))
    ranks = [0.0] * len(values)
    position = 0
    while position < len(sorted_pairs):
        end = position + 1
        while end < len(sorted_pairs) and sorted_pairs[end][0] == sorted_pairs[position][0]:
            end += 1
        average_rank = (position + 1 + end) / 2
        for _, original_index in sorted_pairs[position:end]:
            ranks[original_index] = average_rank
        position = end
    return ranks


def spearman_correlation(x_values: list[float], y_values: list[float]) -> float:
    return pearson_correlation(average_ranks(x_values), average_ranks(y_values))


def kendall_tau_b(x_values: list[float], y_values: list[float]) -> float:
    concordant = 0
    discordant = 0
    ties_x = 0
    ties_y = 0

    for i, j in itertools.combinations(range(len(x_values)), 2):
        x_diff = (x_values[i] > x_values[j]) - (x_values[i] < x_values[j])
        y_diff = (y_values[i] > y_values[j]) - (y_values[i] < y_values[j])

        if x_diff == 0 and y_diff == 0:
            continue
        if x_diff == 0:
            ties_x += 1
        elif y_diff == 0:
            ties_y += 1
        elif x_diff == y_diff:
            concordant += 1
        else:
            discordant += 1

    denominator = math.sqrt((concordant + discordant + ties_x) * (concordant + discordant + ties_y))
    if denominator == 0:
        return math.nan
    return (concordant - discordant) / denominator


def exact_permutation_p_value(
    x_values: list[float],
    y_values: list[float],
    correlation_func: Any,
) -> tuple[float, float]:
    observed = correlation_func(x_values, y_values)
    if math.isnan(observed):
        return observed, math.nan

    total = 0
    at_least_as_extreme = 0
    for permuted_y in itertools.permutations(y_values):
        permuted = correlation_func(x_values, list(permuted_y))
        if math.isnan(permuted):
            continue
        total += 1
        if abs(permuted) >= abs(observed) - 1e-12:
            at_least_as_extreme += 1

    if total == 0:
        return observed, math.nan
    return observed, at_least_as_extreme / total


def compute_correlation_rows(
    puzzle_level_df: pd.DataFrame,
    human_variable: str = "mean_final_rating",
) -> pd.DataFrame:
    sat_variables = [
        "conflicts",
        "decisions",
        "propagations",
        "sat_time_to_solve",
        "log_conflicts",
        "log_decisions",
        "log_propagations",
        "log_sat_time",
    ]
    methods = [
        ("spearman", spearman_correlation),
        ("kendall", kendall_tau_b),
        ("pearson", pearson_correlation),
    ]

    rows: list[dict[str, Any]] = []
    for sat_variable in sat_variables:
        pair_df = puzzle_level_df[[human_variable, sat_variable]].dropna()
        n_puzzles = len(pair_df)
        x_values = pair_df[human_variable].astype(float).tolist()
        y_values = pair_df[sat_variable].astype(float).tolist()
        for method_name, method_func in methods:
            if n_puzzles < 2:
                correlation = math.nan
                p_value = math.nan
            else:
                correlation, p_value = exact_permutation_p_value(x_values, y_values, method_func)
            rows.append(
                {
                    "human_variable": human_variable,
                    "sat_variable": sat_variable,
                    "method": method_name,
                    "correlation": correlation,
                    "p_value": p_value,
                    "n_puzzles": n_puzzles,
                }
            )

    return pd.DataFrame(rows)


def save_correlation_analysis(puzzle_level_df: pd.DataFrame, output_dir: Path) -> pd.DataFrame:
    correlations = compute_correlation_rows(puzzle_level_df)
    output_path = output_dir / "correlation_mean_final_rating_vs_sat.csv"
    correlations.to_csv(output_path, index=False)

    print("\nExploratory puzzle-level correlation analysis")
    print("============================================")
    print(
        "Because the SAT statistics vary only at the puzzle level, the effective "
        "sample size for this analysis is 6 puzzles, not the number of participant ratings."
    )
    print("Treat these correlations as exploratory and do not overclaim statistical significance.")
    print(correlations.to_string(index=False))
    print(f"\nWrote correlation results to {output_path}")
    return correlations


def add_difficulty_ranks(puzzle_level_df: pd.DataFrame) -> pd.DataFrame:
    rankings = puzzle_level_df[["puzzle_id"]].copy()

    # Rank 1 means easiest, rank 6 means hardest. Ties receive average ranks.
    rankings["human_difficulty_rank"] = puzzle_level_df["mean_final_rating"].rank(
        method="average",
        ascending=True,
    )
    rankings["median_final_rating_rank"] = puzzle_level_df["median_final_rating"].rank(
        method="average",
        ascending=True,
    )
    rankings["mean_centered_final_rating_rank"] = puzzle_level_df[
        "mean_centered_final_rating"
    ].rank(method="average", ascending=True)
    rankings["completion_rate_rank"] = puzzle_level_df["completion_rate"].rank(
        method="average",
        ascending=False,
    )

    sat_rank_columns = {
        "conflicts": "conflicts_rank",
        "decisions": "decisions_rank",
        "propagations": "propagations_rank",
        "sat_time_to_solve": "sat_time_rank",
        "log_conflicts": "log_conflicts_rank",
        "log_decisions": "log_decisions_rank",
        "log_propagations": "log_propagations_rank",
        "log_sat_time": "log_sat_time_rank",
    }
    for source_column, rank_column in sat_rank_columns.items():
        rankings[rank_column] = puzzle_level_df[source_column].rank(
            method="average",
            ascending=True,
        )

    return rankings.sort_values("human_difficulty_rank").reset_index(drop=True)


def build_rank_correlation_results(rankings: pd.DataFrame) -> pd.DataFrame:
    sat_rank_columns = [
        "conflicts_rank",
        "decisions_rank",
        "propagations_rank",
        "sat_time_rank",
        "log_conflicts_rank",
        "log_decisions_rank",
        "log_propagations_rank",
        "log_sat_time_rank",
    ]

    rows: list[dict[str, Any]] = []
    human_ranks = rankings["human_difficulty_rank"].astype(float).tolist()
    for sat_rank_column in sat_rank_columns:
        sat_ranks = rankings[sat_rank_column].astype(float).tolist()
        correlation, p_value = exact_permutation_p_value(
            human_ranks,
            sat_ranks,
            spearman_correlation,
        )
        rows.append(
            {
                "human_rank_variable": "human_difficulty_rank",
                "sat_rank_variable": sat_rank_column,
                "method": "spearman",
                "correlation": correlation,
                "p_value": p_value,
                "n_puzzles": len(rankings),
            }
        )

    return pd.DataFrame(rows)


def save_ranking_analysis(puzzle_level_df: pd.DataFrame, output_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    rankings = add_difficulty_ranks(puzzle_level_df)
    rank_correlations = build_rank_correlation_results(rankings)

    rankings_path = output_dir / "puzzle_difficulty_rankings.csv"
    rank_correlations_path = output_dir / "rank_correlation_results.csv"
    rankings.to_csv(rankings_path, index=False)
    rank_correlations.to_csv(rank_correlations_path, index=False)

    print("\nPuzzle difficulty rankings")
    print("==========================")
    print("Rank 1 is easiest and rank 6 is hardest. Human difficulty rank uses mean_final_rating.")
    print(rankings.to_string(index=False))

    print("\nRank correlations")
    print("=================")
    print(
        "These Spearman correlations compare the primary human difficulty ranking "
        "with each SAT-based ranking across 6 puzzles."
    )
    print(rank_correlations.to_string(index=False))
    print(f"\nWrote puzzle rankings to {rankings_path}")
    print(f"Wrote rank correlation results to {rank_correlations_path}")
    return rankings, rank_correlations


def fitted_line_points(x_values: list[float], y_values: list[float]) -> tuple[list[float], list[float]] | None:
    if len(set(x_values)) < 2 or len(set(y_values)) < 2:
        return None

    x_mean = sum(x_values) / len(x_values)
    y_mean = sum(y_values) / len(y_values)
    x_var = sum((value - x_mean) ** 2 for value in x_values)
    if x_var == 0:
        return None

    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, y_values)) / x_var
    intercept = y_mean - slope * x_mean
    line_x = [min(x_values), max(x_values)]
    line_y = [intercept + slope * value for value in line_x]
    return line_x, line_y


def save_scatterplots(puzzle_level_df: pd.DataFrame, output_dir: Path) -> None:
    figure_dir = output_dir / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)

    plot_specs = [
        ("conflicts", "SAT conflicts", "mean_final_rating_vs_conflicts.png"),
        ("decisions", "SAT decisions", "mean_final_rating_vs_decisions.png"),
        ("propagations", "SAT propagations", "mean_final_rating_vs_propagations.png"),
        ("sat_time_to_solve", "SAT time to solve (ms)", "mean_final_rating_vs_sat_time.png"),
        ("log_conflicts", "log(1 + SAT conflicts)", "mean_final_rating_vs_log_conflicts.png"),
        ("log_decisions", "log(1 + SAT decisions)", "mean_final_rating_vs_log_decisions.png"),
        ("log_propagations", "log(1 + SAT propagations)", "mean_final_rating_vs_log_propagations.png"),
    ]

    print("\nScatterplots")
    print("============")
    for sat_variable, x_label, filename in plot_specs:
        plot_df = puzzle_level_df[["puzzle_id", "mean_final_rating", sat_variable]].dropna()
        x_values = plot_df[sat_variable].astype(float).tolist()
        y_values = plot_df["mean_final_rating"].astype(float).tolist()
        rho = spearman_correlation(y_values, x_values)

        fig, ax = plt.subplots(figsize=(7, 5), dpi=160)
        ax.scatter(x_values, y_values, color="#1f5a85", s=55, zorder=3)

        for row in plot_df.itertuples(index=False):
            ax.annotate(
                str(int(row.puzzle_id)),
                (getattr(row, sat_variable), row.mean_final_rating),
                textcoords="offset points",
                xytext=(6, 5),
                fontsize=9,
            )

        line = fitted_line_points(x_values, y_values)
        if line is not None:
            ax.plot(line[0], line[1], color="#b23a48", linestyle="--", linewidth=1.4, label="Linear fit")
            ax.legend(frameon=False, loc="best")

        ax.set_xlabel(x_label)
        ax.set_ylabel("Mean final human difficulty rating")
        ax.set_title(f"Mean final rating vs {x_label}\nSpearman rho = {rho:.3f}, n = {len(plot_df)} puzzles")
        ax.grid(True, alpha=0.25)
        fig.text(
            0.02,
            0.01,
            "Exploratory puzzle-level comparison; SAT statistics vary at the puzzle level only.",
            fontsize=8,
            color="#555555",
        )
        fig.tight_layout(rect=(0, 0.04, 1, 1))

        output_path = figure_dir / filename
        fig.savefig(output_path, bbox_inches="tight")
        plt.close(fig)
        print(f"Wrote {output_path}")


def normal_approx_two_sided_p_value(t_stat: float) -> float:
    if math.isnan(t_stat):
        return math.nan
    return math.erfc(abs(t_stat) / math.sqrt(2))


def fit_clustered_ols(
    df: pd.DataFrame,
    sat_variable: str,
) -> pd.DataFrame:
    model_df = df[
        ["participant_id", "final_rating", sat_variable, "order", "experience_level"]
    ].dropna()
    model_df = model_df.copy()

    # Keep SAT coefficients on a comparable scale for numerical stability.
    sat_mean = float(model_df[sat_variable].mean())
    sat_sd = float(model_df[sat_variable].std(ddof=0))
    sat_scaled = f"{sat_variable}_z"
    if sat_sd == 0 or math.isnan(sat_sd):
        model_df[sat_scaled] = 0.0
    else:
        model_df[sat_scaled] = (model_df[sat_variable] - sat_mean) / sat_sd

    order_dummies = pd.get_dummies(model_df["order"].astype(int), prefix="order", drop_first=True)
    x_df = pd.concat(
        [
            pd.Series(1.0, index=model_df.index, name="intercept"),
            model_df[[sat_scaled, "experience_level"]].astype(float),
            order_dummies.astype(float),
        ],
        axis=1,
    )
    y = model_df["final_rating"].astype(float).to_numpy()
    x = x_df.to_numpy(dtype=float)
    n_obs, n_terms = x.shape
    n_participants = model_df["participant_id"].nunique()

    status = "ok"
    try:
        xtx_inv = np.linalg.pinv(x.T @ x)
        beta = xtx_inv @ x.T @ y
        residuals = y - x @ beta

        meat = np.zeros((n_terms, n_terms))
        for _, group_index in model_df.groupby("participant_id").groups.items():
            positions = model_df.index.get_indexer(group_index)
            x_g = x[positions, :]
            u_g = residuals[positions].reshape(-1, 1)
            meat += x_g.T @ u_g @ u_g.T @ x_g

        covariance = xtx_inv @ meat @ xtx_inv
        if n_participants > 1 and n_obs > n_terms:
            correction = (n_participants / (n_participants - 1)) * ((n_obs - 1) / (n_obs - n_terms))
            covariance *= correction
        standard_errors = np.sqrt(np.maximum(np.diag(covariance), 0))
    except np.linalg.LinAlgError:
        status = "failed"
        beta = np.full(n_terms, math.nan)
        standard_errors = np.full(n_terms, math.nan)

    rows: list[dict[str, Any]] = []
    for term, coefficient, standard_error in zip(x_df.columns, beta, standard_errors):
        t_stat = coefficient / standard_error if standard_error and not math.isnan(standard_error) else math.nan
        rows.append(
            {
                "sat_variable": sat_variable,
                "model_type": "ols_clustered_by_participant",
                "model_role": "secondary_robustness_check",
                "formula": f"final_rating ~ {sat_variable} + order + experience_level",
                "term": term,
                "coefficient": coefficient,
                "std_error": standard_error,
                "t_stat": t_stat,
                "p_value_normal_approx": normal_approx_two_sided_p_value(t_stat),
                "n_observations": n_obs,
                "n_participants": n_participants,
                "covariance": "participant-clustered",
                "sat_mean": sat_mean,
                "sat_sd": sat_sd,
                "status": status,
                "note": (
                    "Fallback OLS used because mixed-effects modeling dependency is unavailable; "
                    "SAT statistics vary across only 6 puzzles."
                ),
            }
        )

    return pd.DataFrame(rows)


def save_participant_level_robustness_models(df: pd.DataFrame, output_dir: Path) -> pd.DataFrame:
    sat_variables = [
        "conflicts",
        "decisions",
        "propagations",
        "sat_time_to_solve",
        "log_conflicts",
        "log_decisions",
        "log_propagations",
        "log_sat_time",
    ]

    model_results = pd.concat(
        [fit_clustered_ols(df, sat_variable) for sat_variable in sat_variables],
        ignore_index=True,
    )
    output_path = output_dir / "participant_level_model_results.csv"
    model_results.to_csv(output_path, index=False)

    print("\nSecondary participant-level robustness models")
    print("=============================================")
    print(
        "This is a secondary robustness check, not the main analysis. "
        "SAT statistics vary only across 6 puzzles, so participant-level rows do not "
        "increase the effective SAT-statistic sample size."
    )
    print(
        "Mixed-effects modeling is unavailable in this environment, so the script uses "
        "fallback OLS models with participant-clustered standard errors."
    )
    sat_terms = model_results[model_results["term"].str.endswith("_z")].copy()
    print(sat_terms[[
        "sat_variable",
        "term",
        "coefficient",
        "std_error",
        "t_stat",
        "p_value_normal_approx",
        "n_observations",
        "n_participants",
    ]].to_string(index=False))
    print(f"\nWrote participant-level model results to {output_path}")
    return model_results


def compute_sensitivity_correlation_results(
    df: pd.DataFrame,
    puzzle_level_df: pd.DataFrame,
) -> pd.DataFrame:
    sat_variables = [
        "conflicts",
        "decisions",
        "propagations",
        "sat_time_to_solve",
        "log_conflicts",
        "log_decisions",
        "log_propagations",
        "log_sat_time",
    ]
    sensitivity_df = puzzle_level_df.copy()

    # Treat incomplete attempts as maximum difficulty to test whether missing final
    # ratings from incomplete sessions could change the puzzle-level conclusion.
    incomplete_max = df.copy()
    incomplete_max["final_rating_max_incomplete"] = incomplete_max["final_rating"]
    incomplete_max.loc[~incomplete_max["completed"].astype(bool), "final_rating_max_incomplete"] = 5
    max_summary = (
        incomplete_max.groupby("puzzle_id")["final_rating_max_incomplete"]
        .mean()
        .reset_index(name="mean_final_rating_max_incomplete")
    )
    sensitivity_df = sensitivity_df.merge(max_summary, on="puzzle_id", how="left", validate="one_to_one")
    sensitivity_df["completion_rate_harder_low"] = -sensitivity_df["completion_rate"]

    human_variables = [
        ("mean_initial_rating", "Initial ratings before final adjustment"),
        ("mean_centered_final_rating", "Participant-centered final ratings"),
        ("completion_rate_harder_low", "Negative completion rate; larger means harder"),
        ("mean_human_time_to_solve", "Mean solve time among completed attempts"),
        ("mean_final_rating_max_incomplete", "Incomplete attempts treated as maximum difficulty"),
    ]
    methods = [
        ("spearman", spearman_correlation),
        ("kendall", kendall_tau_b),
    ]

    rows: list[dict[str, Any]] = []
    for human_variable, note in human_variables:
        for sat_variable in sat_variables:
            pair_df = sensitivity_df[[human_variable, sat_variable]].dropna()
            x_values = pair_df[human_variable].astype(float).tolist()
            y_values = pair_df[sat_variable].astype(float).tolist()
            for method_name, method_func in methods:
                if len(pair_df) < 2:
                    correlation = math.nan
                    p_value = math.nan
                else:
                    correlation, p_value = exact_permutation_p_value(x_values, y_values, method_func)
                rows.append(
                    {
                        "human_variable": human_variable,
                        "sat_variable": sat_variable,
                        "method": method_name,
                        "correlation": correlation,
                        "p_value": p_value,
                        "n_puzzles": len(pair_df),
                        "note": note,
                    }
                )

    return pd.DataFrame(rows)


def save_sensitivity_correlation_results(
    df: pd.DataFrame,
    puzzle_level_df: pd.DataFrame,
    output_dir: Path,
) -> pd.DataFrame:
    sensitivity_results = compute_sensitivity_correlation_results(df, puzzle_level_df)
    output_path = output_dir / "sensitivity_correlation_results.csv"
    sensitivity_results.to_csv(output_path, index=False)

    print("\nSensitivity correlation results")
    print("===============================")
    print(
        "These secondary checks repeat rank correlations with alternate human "
        "difficulty summaries and incomplete-attempt handling."
    )
    strongest = (
        sensitivity_results[sensitivity_results["method"] == "spearman"]
        .assign(abs_correlation=lambda table: table["correlation"].abs())
        .sort_values(["human_variable", "abs_correlation"], ascending=[True, False])
        .groupby("human_variable")
        .head(1)
        [["human_variable", "sat_variable", "correlation", "p_value", "n_puzzles"]]
    )
    print(strongest.to_string(index=False))
    print(f"\nWrote sensitivity correlation results to {output_path}")
    return sensitivity_results


def format_float(value: float, digits: int = 3) -> str:
    if pd.isna(value):
        return "NA"
    return f"{value:.{digits}f}"


def strongest_by_abs(table: pd.DataFrame, method: str) -> pd.Series:
    sub = table[table["method"] == method].copy()
    sub["abs_correlation"] = sub["correlation"].abs()
    return sub.sort_values("abs_correlation", ascending=False).iloc[0]


def generate_markdown_report(
    df: pd.DataFrame,
    assignment_counts: pd.DataFrame,
    order_counts: pd.DataFrame,
    pair_counts: pd.DataFrame,
    correlations: pd.DataFrame,
    rank_correlations: pd.DataFrame,
    sensitivity_results: pd.DataFrame,
    model_results: pd.DataFrame,
    output_dir: Path,
) -> None:
    report_path = output_dir / "sat_vs_human_difficulty_report.md"

    n_participants = df["participant_id"].nunique()
    n_puzzles = df["puzzle_id"].nunique()
    n_attempts = len(df)
    n_completed = int(df["completed"].sum())
    n_incomplete = int((~df["completed"].astype(bool)).sum())
    missing_initial = int(df["initial_rating"].isna().sum())
    missing_final = int(df["final_rating"].isna().sum())
    missing_change = int(df["rating_change"].isna().sum())

    assignment_min = int(assignment_counts["assigned_count"].min())
    assignment_max = int(assignment_counts["assigned_count"].max())
    order_cells = order_counts[["order_1_count", "order_2_count", "order_3_count"]]
    order_min = int(order_cells.min().min())
    order_max = int(order_cells.max().max())
    pair_min = int(pair_counts["pair_count"].min())
    pair_max = int(pair_counts["pair_count"].max())

    strongest_spearman = strongest_by_abs(correlations, "spearman")
    strongest_kendall = strongest_by_abs(correlations, "kendall")
    strongest_pearson = strongest_by_abs(correlations, "pearson")

    rank_summary = rank_correlations[["sat_rank_variable", "correlation"]].copy()
    rank_summary["line"] = rank_summary.apply(
        lambda row: f"- {row.sat_rank_variable}: rho = {format_float(row.correlation)}",
        axis=1,
    )

    sens_spearman = sensitivity_results[sensitivity_results["method"] == "spearman"].copy()
    sens_spearman["abs_correlation"] = sens_spearman["correlation"].abs()
    sens_best = sens_spearman.sort_values(
        ["human_variable", "abs_correlation"], ascending=[True, False]
    ).groupby("human_variable").head(1)

    model_terms = model_results[model_results["term"].str.endswith("_z")].copy()
    model_terms["abs_coefficient"] = model_terms["coefficient"].abs()
    top_model = model_terms.sort_values("abs_coefficient", ascending=False).iloc[0]
    top_model_lines = "\n".join(
        f"- {row.sat_variable}: beta = {format_float(row.coefficient)}, SE = {format_float(row.std_error)}, p = {format_float(row.p_value_normal_approx)}"
        for row in model_terms.sort_values("abs_coefficient", ascending=False).head(4).itertuples(index=False)
    )

    sensitivity_lines = "\n".join(
        f"- {row.human_variable}: strongest Spearman with {row.sat_variable}, rho = {format_float(row.correlation)}"
        for row in sens_best.itertuples(index=False)
    )

    report = f"""# SAT Solver Statistics vs Human-Evaluated Nonogram Difficulty

## 1. Research Question

How do SAT solver statistics correlate with human-evaluated puzzle difficulty?

## 2. Data Summary

The cleaned participant-puzzle dataset contains:

- Participants: {n_participants}
- Puzzles: {n_puzzles}
- Participant-puzzle attempts: {n_attempts}
- Completed attempts: {n_completed}
- Incomplete attempts: {n_incomplete}
- Missing initial ratings: {missing_initial}
- Missing final adjusted ratings: {missing_final}
- Missing rating-change values: {missing_change}

Puzzle assignment was not perfectly balanced. Puzzle assignment counts ranged from {assignment_min} to {assignment_max} attempts per puzzle. Order-position counts ranged from {order_min} to {order_max} within puzzle-by-order cells, and puzzle-pair counts ranged from {pair_min} to {pair_max}. This is acceptable for exploratory analysis, but assignment imbalance should be kept in mind when interpreting human ratings.

## 3. Human Difficulty Measure

The primary human difficulty measure is `mean_final_rating`, based on participants' final adjusted difficulty ratings. This is preferred over the initial rating because participants rated each puzzle again after seeing all 3 puzzles in their session, giving them a chance to recalibrate difficulty judgments against the other puzzles they solved.

## 4. Main Method

The main analysis is puzzle-level. SAT solver statistics vary only by puzzle, not by participant-puzzle attempt, so the effective sample size for SAT-vs-human comparisons is {n_puzzles} puzzles, not {n_attempts} participant-puzzle rows.

For this reason, the main analysis compares each SAT statistic separately against `mean_final_rating` using Spearman rank correlation, Kendall tau, and Pearson correlation as a secondary descriptive check. A multiple regression using conflicts, decisions, propagations, and SAT time together is not appropriate here because there are only {n_puzzles} puzzle-level observations and the SAT statistics are likely correlated.

## 5. Main Results

The strongest Spearman association with `mean_final_rating` was for `{strongest_spearman.sat_variable}` with rho = {format_float(strongest_spearman.correlation)}. This is a very small association.

The strongest Kendall association by absolute value was for `{strongest_kendall.sat_variable}` with tau = {format_float(strongest_kendall.correlation)}. This is also very small.

Pearson correlations were somewhat larger descriptively, with `{strongest_pearson.sat_variable}` highest at r = {format_float(strongest_pearson.correlation)}, but Pearson is secondary here and unstable with only {n_puzzles} observations.

Overall, the main puzzle-level evidence does not show a strong monotonic relationship between MiniSat22 statistics and mean final human difficulty ratings.

## 6. Ranking Comparison

Human difficulty ranking used `mean_final_rating`, with rank 1 as easiest and rank 6 as hardest.

Spearman correlations between the primary human ranking and SAT-based rankings were small:

{chr(10).join(rank_summary["line"].tolist())}

This suggests that the SAT statistics do not rank the 6 puzzles in a similar easiest-to-hardest order as the human final ratings.

## 7. Sensitivity Checks

Sensitivity checks gave mixed but still exploratory results:

{sensitivity_lines}

Initial ratings, participant-centered final ratings, completion rate, and human solve time do not produce a stable conclusion that SAT statistics strongly reproduce human difficulty. Completion-rate sensitivity is especially inconsistent with the primary rating-based ordering.

## 8. Incomplete Data

The main rating analysis uses available final adjusted ratings. Incomplete attempts remain in assignment and completion-rate summaries, but they do not contribute a final rating when no final adjusted rating was submitted.

As a sensitivity check, incomplete attempts without usable final ratings were treated as maximum difficulty. Under that approach, the SAT correlations did not become stronger in a way that changes the conclusion. The main finding remains that SAT statistics do not clearly align with human-evaluated difficulty in this 6-puzzle dataset.

## 9. Robustness Model

A secondary participant-level robustness check was also run. This is not the main analysis because SAT statistics vary only across 6 puzzles; expanding to participant-level rows does not increase the effective sample size for SAT statistics.

Mixed-effects modeling was unavailable in the current environment, so the script used fallback OLS models with participant-clustered standard errors:

`final_rating ~ SAT_stat + order + experience_level`

Each SAT statistic was modeled separately. The largest standardized fallback-model coefficient was for `{top_model.sat_variable}` at beta = {format_float(top_model.coefficient)}.

{top_model_lines}

These participant-level models should be interpreted only as robustness checks. They partly support a positive association for some SAT statistics, but they do not override the weaker puzzle-level rank correlations.

## 10. Conclusion

Among the SAT solver statistics, `{top_model.sat_variable}` appears most aligned with human-evaluated difficulty in some secondary summaries. However, the primary rank-based puzzle-level analysis shows only very weak associations, with `{strongest_spearman.sat_variable}` having the largest Spearman rho at only {format_float(strongest_spearman.correlation)}.

The safest conclusion is that MiniSat22 statistics show at most weak exploratory alignment with human-evaluated difficulty in this dataset. No SAT statistic clearly reproduces the human easiest-to-hardest ordering.

Key limitations:

- There are only 6 puzzles, so puzzle-level analyses have an effective sample size of 6.
- SAT time varies over a very small range, making it especially hard to interpret.
- Human ratings may depend on participant experience, puzzle order, and which other puzzles were shown in the same session.
- Puzzle assignment was not perfectly balanced.
- Results should be treated as exploratory rather than confirmatory.
"""

    report_path.write_text(report, encoding="utf-8")
    print(f"\nWrote Markdown report to {report_path}")


def build_dataset(log_dir: Path, solver_stats: Path, output_csv: Path) -> pd.DataFrame:
    # Step 1: Parse raw event logs and MiniSat22 statistics into analysis-ready tables.
    human_df = load_human_data(log_dir)
    sat_df = load_minisat_stats(solver_stats)

    # Step 2: Build the participant-puzzle dataset used by downstream summaries.
    merged = human_df.merge(sat_df, on="puzzle_id", how="left", validate="many_to_one")
    merged = add_participant_centered_final_rating(merged)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(output_csv, index=False)

    # Step 3: Check whether puzzle assignment, order, and pair exposure were balanced.
    assignment_counts, order_counts, pair_counts = save_assignment_balance_outputs(merged, output_csv.parent)

    # Step 4: Summarize human difficulty at the puzzle level using final adjusted ratings.
    save_puzzle_human_difficulty_summary(merged, output_csv.parent)

    # Step 5: Merge puzzle-level human difficulty with puzzle-level SAT statistics.
    save_puzzle_level_difficulty_vs_sat(merged, sat_df, output_csv.parent)
    puzzle_level_df = build_puzzle_level_difficulty_vs_sat(
        build_puzzle_human_difficulty_summary(merged),
        sat_df,
    )

    # Step 6: Main analysis: one SAT statistic at a time against mean final rating.
    correlations = save_correlation_analysis(puzzle_level_df, output_csv.parent)

    # Step 7: Ranking analysis: compare SAT-based easiest-to-hardest orderings to humans.
    _, rank_correlations = save_ranking_analysis(puzzle_level_df, output_csv.parent)

    # Step 8: Sensitivity checks using alternate human difficulty summaries.
    sensitivity_results = save_sensitivity_correlation_results(merged, puzzle_level_df, output_csv.parent)

    # Step 9: Visualize the main puzzle-level comparisons.
    save_scatterplots(puzzle_level_df, output_csv.parent)

    # Step 10: Secondary participant-level robustness models, one SAT statistic per model.
    model_results = save_participant_level_robustness_models(merged, output_csv.parent)

    # Step 11: Write a short Markdown report from the generated tables.
    generate_markdown_report(
        merged,
        assignment_counts,
        order_counts,
        pair_counts,
        correlations,
        rank_correlations,
        sensitivity_results,
        model_results,
        output_csv.parent,
    )
    return merged


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build clean participant-puzzle data merged with MiniSat22 statistics."
    )
    parser.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR)
    parser.add_argument("--solver-stats", type=Path, default=DEFAULT_SOLVER_STATS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_CSV)
    args = parser.parse_args()

    df = build_dataset(args.log_dir, args.solver_stats, args.output)
    print(f"Wrote cleaned dataset to {args.output}")
    validate_dataset(df)


if __name__ == "__main__":
    main()
