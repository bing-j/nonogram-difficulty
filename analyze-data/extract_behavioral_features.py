"""
Extract per-participant, per-puzzle behavioral difficulty signals from NDJSON logs.

Signals extracted:
  pause_count       — number of inter-event gaps >= PAUSE_THRESHOLD_SEC
  pause_freq_per_min — pause_count / (duration_min), or 0 if duration is zero
  time_to_solve_sec — seconds from first interaction to first successful check_bank;
                      falls back to full interaction duration if puzzle never solved
  error_count       — number of move events where value==1 (fill black) but
                      solution[r][c]==0 (should be white). Only move events are
                      checked; drag events do not log individual cell coordinates.
  hint_count        — number of hint events (excludes hint_none, which is rate-limited)

Output: analyze-data/out_features/behavioral_features.csv
"""

import argparse
import glob
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from extract_features import (
    find_survey,
    is_interaction_event,
    parse_time,
    puzzle_interaction_duration_seconds,
    read_ndjson,
    safe_get,
    segment_puzzles,
    slice_events_by_time,
    infer_participant_id,
    first_event_of_type,
    get_completion_flags,
)

PAUSE_THRESHOLD_SEC = 2.40


def detect_pauses(
    puzzle_events: List[Dict[str, Any]],
    threshold_sec: float = PAUSE_THRESHOLD_SEC,
) -> Tuple[int, float]:
    interaction_times = sorted(
        parse_time(e["t"])
        for e in puzzle_events
        if is_interaction_event(e.get("type", ""))
    )
    if len(interaction_times) < 2:
        return 0, 0.0

    duration_sec = (interaction_times[-1] - interaction_times[0]).total_seconds()
    gaps = [
        (interaction_times[i + 1] - interaction_times[i]).total_seconds()
        for i in range(len(interaction_times) - 1)
    ]
    count = sum(1 for g in gaps if g >= threshold_sec)
    freq = count / (duration_sec / 60.0) if duration_sec > 0 else 0.0
    return count, freq


def count_hints(puzzle_events: List[Dict[str, Any]]) -> int:
    return sum(1 for e in puzzle_events if e.get("type") == "hint")


def load_solutions(puzzles_path: str) -> Dict[int, List[List[int]]]:
    with open(puzzles_path, encoding="utf-8") as f:
        puzzles = json.load(f)
    return {p["id"]: p["solution"] for p in puzzles}


def count_solution_errors(
    puzzle_events: List[Dict[str, Any]],
    solution: List[List[int]],
) -> int:
    """Count move events where the user filled a cell black (value=1)
    but the solution has that cell as white (0)."""
    count = 0
    for e in puzzle_events:
        if e.get("type") == "move" and e.get("value") == 1:
            r, c = e.get("r"), e.get("c")
            if r is not None and c is not None:
                if solution[r][c] == 0:
                    count += 1
    return count


def time_to_first_solve(puzzle_events: List[Dict[str, Any]]) -> Optional[float]:
    interaction_times = sorted(
        parse_time(e["t"])
        for e in puzzle_events
        if is_interaction_event(e.get("type", ""))
    )
    if not interaction_times:
        return None
    first_t = interaction_times[0]

    for e in sorted(puzzle_events, key=lambda x: parse_time(x["t"])):
        if e.get("type") == "check_bank" and e.get("solved") is True:
            return (parse_time(e["t"]) - first_t).total_seconds()

    # Never solved — fall back to full interaction duration
    return (interaction_times[-1] - first_t).total_seconds() if len(interaction_times) >= 2 else None


def extract_behavioral_row(
    participant_id: str,
    puzzle_id: int,
    puzzle_events: List[Dict[str, Any]],
    solution: List[List[int]],
    initial_diff: Optional[Any],
    final_diff: Optional[Any],
    solved_flag: Optional[bool],
    pause_threshold: float = PAUSE_THRESHOLD_SEC,
) -> Dict[str, Any]:
    pause_count, pause_freq = detect_pauses(puzzle_events, threshold_sec=pause_threshold)
    return {
        "participant_id": participant_id,
        "puzzle_id": puzzle_id,
        "pause_count": pause_count,
        "pause_freq_per_min": round(pause_freq, 4),
        "time_to_solve_sec": time_to_first_solve(puzzle_events),
        "error_count": count_solution_errors(puzzle_events, solution),
        "hint_count": count_hints(puzzle_events),
        "initial_difficulty": initial_diff,
        "final_difficulty": final_diff,
        "solved_flag": solved_flag,
    }


def process_file(
    path: str,
    solutions: Dict[int, List[List[int]]],
    pause_threshold: float = PAUSE_THRESHOLD_SEC,
) -> List[Dict[str, Any]]:
    events = read_ndjson(path)
    pid = infer_participant_id(path)

    ss = first_event_of_type(events, "session_start_three")
    if not ss or "queue" not in ss:
        raise ValueError(f"missing session_start_three with queue")
    queue = ss["queue"]

    solved_flags, _ = get_completion_flags(events)

    puzzle_surveys = [find_survey(events, f"puzzle_{i}") or {} for i in (1, 2, 3)]
    initial_diffs = [
        safe_get(safe_get(ps, "answers", {}), "difficulty", None)
        for ps in puzzle_surveys
    ]
    post = find_survey(events, "post") or {}
    post_answers = safe_get(post, "answers", {})
    final_diffs = [post_answers.get(f"puzzle_{i}_rate_again") for i in (1, 2, 3)]

    windows = segment_puzzles(events)
    rows = []
    for idx, (start_t, end_t) in enumerate(windows):
        chunk = slice_events_by_time(events, start_t, end_t)
        puzzle_id = queue[idx]
        rows.append(
            extract_behavioral_row(
                participant_id=pid,
                puzzle_id=puzzle_id,
                puzzle_events=chunk,
                solution=solutions[puzzle_id],
                initial_diff=initial_diffs[idx],
                final_diff=final_diffs[idx],
                solved_flag=solved_flags[idx],
                pause_threshold=pause_threshold,
            )
        )
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Extract behavioral difficulty signals from NDJSON logs.")
    ap.add_argument(
        "--input_glob",
        default=os.path.join(os.path.dirname(__file__), "..", "backend", "logs", "*.ndjson"),
        help="Glob pattern for NDJSON log files",
    )
    ap.add_argument(
        "--puzzles_json",
        default=os.path.join(os.path.dirname(__file__), "..", "nonograms_6.json"),
        help="Path to nonograms_6.json (contains solution grids)",
    )
    ap.add_argument(
        "--out_dir",
        default=os.path.join(os.path.dirname(__file__), "out_features"),
        help="Output directory",
    )
    ap.add_argument(
        "--pause_threshold",
        type=float,
        default=None,
        help=(
            "Pause threshold in seconds (overrides PAUSE_THRESHOLD_SEC). "
            "Use the value recommended by plot_gap_distribution.py."
        ),
    )
    args = ap.parse_args()

    effective_threshold = args.pause_threshold if args.pause_threshold is not None else PAUSE_THRESHOLD_SEC
    if args.pause_threshold is not None:
        print(f"Pause threshold: {effective_threshold}s (overrides default {PAUSE_THRESHOLD_SEC}s)")
    else:
        print(f"Pause threshold: {effective_threshold}s (default)")

    solutions = load_solutions(args.puzzles_json)

    paths = sorted(glob.glob(args.input_glob))
    if not paths:
        print(f"No files matched: {args.input_glob}")
        return

    all_rows: List[Dict[str, Any]] = []
    for path in paths:
        try:
            rows = process_file(path, solutions, pause_threshold=effective_threshold)
            all_rows.extend(rows)
            print(f"  OK  {os.path.basename(path)} ({len(rows)} rows)")
        except ValueError as exc:
            print(f"  SKIP {os.path.basename(path)}: {exc}")

    if not all_rows:
        print("No data extracted.")
        return

    os.makedirs(args.out_dir, exist_ok=True)
    out_path = os.path.join(args.out_dir, "behavioral_features.csv")
    df = pd.DataFrame(all_rows)
    df.to_csv(out_path, index=False)
    print(f"\nWrote {len(df)} rows to {out_path}")
    print(df.describe().to_string())


if __name__ == "__main__":
    main()
