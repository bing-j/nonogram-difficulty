import argparse
import json
import glob
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import pandas as pd
from dateutil import parser as dtparser

from plot_style import ACCENT_COLOR, ACCENT_COLOR_2, NEUTRAL_COLOR, apply_style


EXCLUDE_SESSION_TYPES = {"survey_submit", "session_start_three", "session_end"}

# For "time used", we treat these as interactions (everything except session/survey markers).
def is_interaction_event(ev_type: str) -> bool:
    return ev_type not in EXCLUDE_SESSION_TYPES


def read_ndjson(path: str) -> List[Dict[str, Any]]:
    events = []
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"Bad JSON in {path} on line {line_no}: {e}") from e
    # Sort by timestamp just in case
    events.sort(key=lambda e: dtparser.isoparse(e["t"]))
    return events


def first_event_of_type(events: List[Dict[str, Any]], ev_type: str) -> Optional[Dict[str, Any]]:
    for e in events:
        if e.get("type") == ev_type:
            return e
    return None


def find_survey(events: List[Dict[str, Any]], survey_type: str) -> Optional[Dict[str, Any]]:
    for e in events:
        if e.get("type") == "survey_submit" and e.get("survey_type") == survey_type:
            return e
    return None


def parse_time(ts: str) -> datetime:
    return dtparser.isoparse(ts)


def slice_events_by_time(
    events: List[Dict[str, Any]],
    start_t: datetime,
    end_t: datetime,
) -> List[Dict[str, Any]]:
    out = []
    for e in events:
        t = parse_time(e["t"])
        if start_t <= t < end_t:
            out.append(e)
    return out


def event_type_distribution(events: List[Dict[str, Any]]) -> Dict[str, int]:
    dist: Dict[str, int] = {}
    for e in events:
        ev_type = e.get("type", "")
        if ev_type in EXCLUDE_SESSION_TYPES:
            continue
        dist[ev_type] = dist.get(ev_type, 0) + 1
    return dist


def puzzle_interaction_duration_seconds(puzzle_events: List[Dict[str, Any]]) -> Optional[float]:
    interaction_times = [parse_time(e["t"]) for e in puzzle_events if is_interaction_event(e.get("type", ""))]
    if not interaction_times:
        return None
    return (max(interaction_times) - min(interaction_times)).total_seconds()


def safe_get(d: Dict[str, Any], key: str, default=None):
    return d.get(key, default) if isinstance(d, dict) else default


@dataclass
class ParticipantSummary:
    participant_id: str
    source_file: str
    queue: List[int]

    # Order-indexed by puzzle_idx 0..2 (not puzzle_id)
    puzzle_ids: List[int]
    initial_difficulty: List[Optional[int]]
    final_difficulty: List[Optional[int]]

    # Flags by puzzle_idx 0..2
    solved_flags: List[Optional[bool]]
    skipped_flags: List[Optional[bool]]

    # Per puzzle_idx distributions & duration
    event_dist_by_idx: List[Dict[str, int]]
    duration_sec_by_idx: List[Optional[float]]

    # Surveys (raw)
    pre_answers: Dict[str, Any]
    puzzle_answers: List[Dict[str, Any]]  # puzzle_1..3
    post_answers: Dict[str, Any]


def build_ratings_table(participants: List[ParticipantSummary]) -> pd.DataFrame:
    """
    One row per participant x puzzle_idx (3 per participant).
    Columns: puzzle_id, initial_difficulty, final_difficulty, solved_flag, skipped_flag, duration_sec
    """
    rows = []
    for ps in participants:
        for idx in range(3):
            rows.append({
                "participant_id": ps.participant_id,
                "puzzle_idx": idx + 1,  # 1..3
                "puzzle_id": ps.puzzle_ids[idx],
                "initial_difficulty": ps.initial_difficulty[idx],
                "final_difficulty": ps.final_difficulty[idx],
                "solved_flag": ps.solved_flags[idx],
                "skipped_flag": ps.skipped_flags[idx],
                "duration_sec": ps.duration_sec_by_idx[idx],
            })
    return pd.DataFrame(rows)


def save_puzzle_rating_figures(ratings_df: pd.DataFrame, out_dir: str, puzzle_ids: List[int]) -> None:
    """
    Saves an overview figure (boxplots by puzzle) into out_dir.
    """
    os.makedirs(out_dir, exist_ok=True)

    # --- Overview figure: boxplots by puzzle ---
    # Build lists in puzzle order
    fin_lists = []
    labels = []
    for pid in puzzle_ids:
        sub = ratings_df[ratings_df["puzzle_id"] == pid]
        fin_vals = pd.to_numeric(sub["final_difficulty"], errors="coerce").dropna().tolist()
        fin_lists.append(fin_vals)
        labels.append(str(pid))

    fig = plt.figure(figsize=(12, 4))

    ax1 = fig.add_subplot(1, 1, 1)
    bp1 = ax1.boxplot(
        fin_lists, tick_labels=labels, showmeans=True,
        boxprops=dict(color=NEUTRAL_COLOR),
        whiskerprops=dict(color=NEUTRAL_COLOR),
        capprops=dict(color=NEUTRAL_COLOR),
        flierprops=dict(markeredgecolor=NEUTRAL_COLOR),
        medianprops=dict(color=ACCENT_COLOR, linewidth=2),
        meanprops=dict(marker='^', markerfacecolor=ACCENT_COLOR_2, markeredgecolor=ACCENT_COLOR_2),
    )
    ax1.set_xlabel("Puzzle ID")
    ax1.set_ylabel("Final rating")
    ax1.set_ylim(0.5, 5.5)

    # ----- Legend -----
    legend_elements = [
        Line2D([0], [0], color=ACCENT_COLOR, lw=2, label='Median'),
        Line2D([0], [0], marker='^', color=ACCENT_COLOR_2, linestyle='None', label='Mean'),
    ]

    ax1.legend(handles=legend_elements, loc='upper right')

    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "ratings_overview_all_puzzles.png"), dpi=200)
    plt.close(fig)


def infer_participant_id(path: str) -> str:
    # e.g., "p4-Michael.ndjson" -> "p4-Michael"
    base = os.path.basename(path)
    return base.replace(".ndjson", "")


def get_completion_flags(events: List[Dict[str, Any]]) -> Tuple[List[Optional[bool]], List[Optional[bool]]]:
    """
    Returns (solved_flags, skipped_flags) for puzzle_idx 0..2.

    - If completed_all_three exists: solved=[True,True,True], skipped=[False,False,False]
    - Else if ended_without_full_completion exists: read solved_flags/skipped_flags from it
    - Else: fall back to None (unknown)
    """
    if first_event_of_type(events, "completed_all_three") is not None:
        return [True, True, True], [False, False, False]

    end_ev = first_event_of_type(events, "ended_without_full_completion")
    if end_ev is not None:
        solved = safe_get(end_ev, "solved_flags", [None, None, None])
        skipped = safe_get(end_ev, "skipped_flags", [None, None, None])
        # Ensure length 3
        solved = (solved + [None, None, None])[:3]
        skipped = (skipped + [None, None, None])[:3]
        return solved, skipped

    return [None, None, None], [None, None, None]


def segment_puzzles(events: List[Dict[str, Any]]) -> List[Tuple[datetime, datetime]]:
    """
    Returns 3 time windows for puzzle_idx 0..2 based on survey_submit timestamps:
      [pre -> puzzle_1], [puzzle_1 -> puzzle_2], [puzzle_2 -> puzzle_3]

    If anything is missing, raises a clear error (you can relax later if needed).
    """
    pre = find_survey(events, "pre")
    p1 = find_survey(events, "puzzle_1")
    p2 = find_survey(events, "puzzle_2")
    p3 = find_survey(events, "puzzle_3")

    if not pre or not p1 or not p2 or not p3:
        missing = []
        if not pre: missing.append("pre")
        if not p1: missing.append("puzzle_1")
        if not p2: missing.append("puzzle_2")
        if not p3: missing.append("puzzle_3")
        raise ValueError(f"Missing required surveys for segmentation: {missing}")

    t_pre = parse_time(pre["t"])
    t_p1 = parse_time(p1["t"])
    t_p2 = parse_time(p2["t"])
    t_p3 = parse_time(p3["t"])

    return [(t_pre, t_p1), (t_p1, t_p2), (t_p2, t_p3)]


def extract_participant(path: str) -> ParticipantSummary:
    events = read_ndjson(path)
    pid = infer_participant_id(path)

    ss = first_event_of_type(events, "session_start_three")
    if not ss or "queue" not in ss:
        raise ValueError(f"{path}: missing session_start_three with queue")
    queue = ss["queue"]
    if not isinstance(queue, list) or len(queue) != 3:
        raise ValueError(f"{path}: queue should be a list of length 3, got: {queue}")

    solved_flags, skipped_flags = get_completion_flags(events)

    # Surveys
    pre = find_survey(events, "pre") or {}
    post = find_survey(events, "post") or {}
    puzzle_surveys = [find_survey(events, f"puzzle_{i}") or {} for i in (1, 2, 3)]

    # Initial difficulties (immediately after puzzle)
    initial_diff = []
    for i, ps in enumerate(puzzle_surveys, start=1):
        diff = safe_get(safe_get(ps, "answers", {}), "difficulty", None)
        initial_diff.append(diff)

    # Final difficulties (post)
    final_diff = []
    post_answers = safe_get(post, "answers", {})
    for i in (1, 2, 3):
        final_diff.append(post_answers.get(f"puzzle_{i}_rate_again"))

    # Segment into puzzle windows and compute per-puzzle distributions/durations
    windows = segment_puzzles(events)
    dists = []
    durations = []
    for (start_t, end_t) in windows:
        chunk = slice_events_by_time(events, start_t, end_t)
        dists.append(event_type_distribution(chunk))
        durations.append(puzzle_interaction_duration_seconds(chunk))

    return ParticipantSummary(
        participant_id=pid,
        source_file=os.path.basename(path),
        queue=queue,
        puzzle_ids=queue[:],
        initial_difficulty=initial_diff,
        final_difficulty=final_diff,
        solved_flags=solved_flags,
        skipped_flags=skipped_flags,
        event_dist_by_idx=dists,
        duration_sec_by_idx=durations,
        pre_answers=safe_get(pre, "answers", {}),
        puzzle_answers=[safe_get(ps, "answers", {}) for ps in puzzle_surveys],
        post_answers=safe_get(post, "answers", {}),
    )


def flatten_for_csv(ps: ParticipantSummary) -> Dict[str, Any]:
    row: Dict[str, Any] = {
        "participant_id": ps.participant_id,
        "source_file": ps.source_file,
        "queue": ",".join(map(str, ps.queue)),
    }

    # Per puzzle_idx columns
    for idx in range(3):
        pid = ps.puzzle_ids[idx]
        row[f"p{idx+1}_puzzle_id"] = pid
        row[f"p{idx+1}_initial_difficulty"] = ps.initial_difficulty[idx]
        row[f"p{idx+1}_final_difficulty"] = ps.final_difficulty[idx]
        row[f"p{idx+1}_solved_flag"] = ps.solved_flags[idx]
        row[f"p{idx+1}_skipped_flag"] = ps.skipped_flags[idx]
        row[f"p{idx+1}_duration_sec"] = ps.duration_sec_by_idx[idx]

        # Event distribution: put as compact JSON string (easy to eyeball, can parse later)
        row[f"p{idx+1}_event_dist_json"] = json.dumps(ps.event_dist_by_idx[idx], sort_keys=True)

    # A few survey fields that are often useful to eyeball
    # (Keep minimal; you can add more later.)
    row["pre_skill_nonogram"] = ps.pre_answers.get("skill_nonogram")
    row["pre_skill_puzzles"] = ps.pre_answers.get("skill_puzzles")
    row["post_strategy"] = ps.post_answers.get("strategy")
    row["post_comments"] = ps.post_answers.get("comments")
    return row


def build_puzzle_rating_lists(participants: List[ParticipantSummary]) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Returns:
      - initial_ratings_df: columns [puzzle_id, participant_id, puzzle_idx, initial_difficulty]
      - final_ratings_df:   columns [puzzle_id, participant_id, puzzle_idx, final_difficulty]
    """
    init_rows = []
    final_rows = []

    for ps in participants:
        for idx in range(3):
            puzzle_id = ps.puzzle_ids[idx]
            init_rows.append({
                "puzzle_id": puzzle_id,
                "participant_id": ps.participant_id,
                "puzzle_idx": idx,
                "initial_difficulty": ps.initial_difficulty[idx],
                "solved_flag": ps.solved_flags[idx],
                "skipped_flag": ps.skipped_flags[idx],
            })
            final_rows.append({
                "puzzle_id": puzzle_id,
                "participant_id": ps.participant_id,
                "puzzle_idx": idx,
                "final_difficulty": ps.final_difficulty[idx],
                "solved_flag": ps.solved_flags[idx],
                "skipped_flag": ps.skipped_flags[idx],
            })

    return pd.DataFrame(init_rows), pd.DataFrame(final_rows)


def write_survey_dump(out_dir: str, ps: ParticipantSummary) -> None:
    os.makedirs(out_dir, exist_ok=True)
    dump = {
        "participant_id": ps.participant_id,
        "source_file": ps.source_file,
        "queue": ps.queue,
        "pre": ps.pre_answers,
        "puzzle_1": ps.puzzle_answers[0],
        "puzzle_2": ps.puzzle_answers[1],
        "puzzle_3": ps.puzzle_answers[2],
        "post": ps.post_answers,
    }
    out_path = os.path.join(out_dir, f"{ps.participant_id}_surveys.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(dump, f, indent=2, ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input_glob", type=str, required=True,
                    help='Glob for ndjson logs, e.g. "data/*.ndjson"')
    ap.add_argument("--out_dir", type=str, default="out_features",
                    help="Output directory for CSV and JSON dumps")
    args = ap.parse_args()

    apply_style()

    paths = sorted(glob.glob(args.input_glob))
    if not paths:
        raise SystemExit(f"No files matched: {args.input_glob}")

    participants: List[ParticipantSummary] = []
    for p in paths:
        try:
            participants.append(extract_participant(p))
        except ValueError as exc:
            print(f"  SKIP {os.path.basename(p)}: {exc}", file=__import__("sys").stderr)

    os.makedirs(args.out_dir, exist_ok=True)

    # 1) Visualizations for puzzle ratings
    ratings_df = build_ratings_table(participants)
    fig_dir = os.path.join(args.out_dir, "figures")
    save_puzzle_rating_figures(ratings_df, fig_dir, puzzle_ids=list(range(6)))

    # 3) Human-readable survey dumps (one JSON per participant)
    survey_dir = os.path.join(args.out_dir, "survey_dumps")
    for ps in participants:
        write_survey_dump(survey_dir, ps)

    print(f"Wrote outputs to: {args.out_dir}")
    print(" - survey_dumps/*.json")
    print(" - figures/ratings_overview_all_puzzles.png")


if __name__ == "__main__":
    main()