"""
Shared, READ-ONLY data loader for the Nonogram study.

This module parses the raw participant event logs in ``backend/logs`` and builds
analysis-ready tables. It never writes to or modifies any existing repo file.

It exposes three building blocks used by the rest of ``riyad-analysis``:

  * ``load_participant_puzzle_df()`` -> one row per (participant, puzzle slot)
        behavioural measures, subjective ratings, background, and text fields.
  * ``load_text_responses()``       -> long table of every free-text response.
  * ``load_solver_stats()``         -> per-puzzle SAT solver metrics
                                       (MiniSat primary, Glucose secondary).

Run directly to print a quick sanity summary:

    riyad-analysis/.venv/bin/python riyad-analysis/nono_data.py
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = REPO_ROOT / "backend" / "logs"
SOLVER_STATS_TXT = REPO_ROOT / "solver_statistics.txt"

LOG_EXTENSIONS = {".ndjson", ".json"}

# Cell-changing user actions for the behavioural "number of actions" measure.
ACTION_EVENT_TYPES = {"move", "drag"}
# Anything that is not a session/survey marker counts as "engaged with the puzzle".
NON_INTERACTION_TYPES = {
    "session_start_three",
    "session_end",
    "survey_submit",
    "completed_all_three",
    "ended_without_full_completion",
}

# Ordinal encodings for self-reported frequency questions.
FREQUENCY_ORDER = {"never": 0, "few": 1, "many": 2, "regular": 3}
# Free-text guessing frequency answers -> ordinal scale (N/A stays missing).
GUESS_ORDER = {"never": 0, "few": 1, "many": 2, "all": 3}


# --------------------------------------------------------------------------- #
# Low-level parsing helpers
# --------------------------------------------------------------------------- #
def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def coerce_int(value: Any) -> int | None:
    if value is None or value == "" or (isinstance(value, str) and value.strip().lower() in {"n/a", "na", "none"}):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def host_and_label(stem: str) -> tuple[str | None, str | None]:
    match = re.match(r"^(?P<host>.+)-(?P<label>p\d+)$", stem)
    if not match:
        return None, None
    return match.group("host"), match.group("label")


def natural_sort_key(path: Path) -> tuple[str, int, str]:
    match = re.match(r"^(?P<host>.+)-p(?P<num>\d+)$", path.stem)
    if not match:
        return (path.stem, 0, path.suffix)
    return (match.group("host"), int(match.group("num")), path.suffix)


def read_event_log(path: Path) -> list[dict[str, Any]]:
    """Read a log file. Files are line-delimited JSON regardless of extension."""
    events: list[dict[str, Any]] = []
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return events
    # Some .json files may be a single JSON array; handle that defensively.
    if text[0] == "[":
        try:
            arr = json.loads(text)
            if isinstance(arr, list):
                return [e for e in arr if isinstance(e, dict)]
        except json.JSONDecodeError:
            pass
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {path} line {line_number}: {exc}") from exc
    return events


def list_log_files() -> list[Path]:
    files = [p for p in LOG_DIR.iterdir() if p.is_file() and p.suffix in LOG_EXTENSIONS]
    return sorted(files, key=natural_sort_key)


# --------------------------------------------------------------------------- #
# Per-participant extraction
# --------------------------------------------------------------------------- #
@dataclass
class SlotAccumulator:
    n_moves: int = 0
    n_drags: int = 0
    n_cell_changes: int = 0
    n_hints: int = 0
    n_incorrect_submissions: int = 0
    first_interaction: datetime | None = None
    last_interaction: datetime | None = None
    solved_time: datetime | None = None
    solved: bool = False
    skipped: bool = False
    puzzle_id_seen: int | None = None  # puzzle id from check_bank/skip events


def _new_slots(n: int) -> list[SlotAccumulator]:
    return [SlotAccumulator() for _ in range(n)]


def extract_participant_rows(participant_id: str, source_file: str,
                             events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    start = next((e for e in events if e.get("type") == "session_start_three"), None)
    queue = start.get("queue") if start else None
    if not isinstance(queue, list) or not queue:
        return []
    n_slots = min(3, len(queue))
    host, label = host_and_label(Path(source_file).stem)

    pre: dict[str, Any] = {}
    post: dict[str, Any] = {}
    immediate: dict[int, dict[str, Any]] = {}
    slots = _new_slots(n_slots)
    idx = 0  # current puzzle slot pointer

    for ev in events:
        et = ev.get("type")
        t = parse_time(ev.get("t"))

        if et in ACTION_EVENT_TYPES and idx < n_slots:
            s = slots[idx]
            if et == "move":
                s.n_moves += 1
                s.n_cell_changes += 1
            else:  # drag
                s.n_drags += 1
                s.n_cell_changes += int(ev.get("changed_cells") or 1)

        if et not in NON_INTERACTION_TYPES and idx < n_slots and t is not None:
            s = slots[idx]
            if s.first_interaction is None:
                s.first_interaction = t
            s.last_interaction = t

        if et == "hint" and idx < n_slots:
            slots[idx].n_hints += 1

        if et == "survey_submit":
            stype = ev.get("survey_type")
            answers = ev.get("answers") or {}
            if stype == "pre" and isinstance(answers, dict):
                pre = answers
            elif stype == "post" and isinstance(answers, dict):
                post = answers
            elif stype in {"puzzle_1", "puzzle_2", "puzzle_3"} and isinstance(answers, dict):
                immediate[int(stype.split("_")[1]) - 1] = answers

        if et == "check_bank" and idx < n_slots:
            slots[idx].puzzle_id_seen = coerce_int(ev.get("puzzle_id"))
            if ev.get("solved") is True:
                slots[idx].solved = True
                slots[idx].solved_time = t
                idx += 1
            else:
                slots[idx].n_incorrect_submissions += 1

        if et == "skip_puzzle":
            sidx = coerce_int(ev.get("idx"))
            if sidx is None:
                sidx = idx
            if 0 <= sidx < n_slots:
                slots[sidx].skipped = True
                slots[sidx].puzzle_id_seen = coerce_int(ev.get("puzzle_id"))
            idx = max(idx, sidx + 1)

    # Completion flags from terminal markers (more reliable when present).
    completed_all = any(e.get("type") == "completed_all_three" for e in events)
    ended_partial = next((e for e in events if e.get("type") == "ended_without_full_completion"), None)
    solved_flags = None
    skipped_flags = None
    if completed_all:
        solved_flags = [True] * n_slots
        skipped_flags = [False] * n_slots
    elif ended_partial is not None:
        sf = (ended_partial.get("solved_flags") or []) + [None, None, None]
        kf = (ended_partial.get("skipped_flags") or []) + [None, None, None]
        solved_flags = sf[:n_slots]
        skipped_flags = kf[:n_slots]

    rows: list[dict[str, Any]] = []
    for i in range(n_slots):
        s = slots[i]
        solved = bool(solved_flags[i]) if solved_flags else s.solved
        skipped = bool(skipped_flags[i]) if skipped_flags else s.skipped

        time_to_solve = None
        if solved and s.first_interaction and s.solved_time:
            time_to_solve = (s.solved_time - s.first_interaction).total_seconds()
        time_on_puzzle = None
        if s.first_interaction and s.last_interaction:
            time_on_puzzle = (s.last_interaction - s.first_interaction).total_seconds()

        imm = immediate.get(i, {})
        immediate_diff = coerce_int(imm.get("difficulty"))
        immediate_guess = imm.get(f"puzzle_{i + 1}_guesses")
        revised_diff = coerce_int(post.get(f"puzzle_{i + 1}_rate_again"))
        revised_guess = post.get(f"puzzle_{i + 1}_guesses")

        rating_change = None
        if immediate_diff is not None and revised_diff is not None:
            rating_change = revised_diff - immediate_diff

        rows.append({
            "participant_id": participant_id,
            "source_file": source_file,
            "host": host,
            "host_label": label,
            "order": i + 1,
            "puzzle_id": coerce_int(queue[i]),
            "puzzle_id_seen": s.puzzle_id_seen,
            "solved": solved,
            "skipped": skipped,
            # Behavioural
            "n_actions": s.n_moves + s.n_drags,
            "n_moves": s.n_moves,
            "n_drags": s.n_drags,
            "n_cell_changes": s.n_cell_changes,
            "n_hints": s.n_hints,
            "n_incorrect_submissions": s.n_incorrect_submissions,
            "time_to_solve": time_to_solve,
            "time_on_puzzle": time_on_puzzle,
            # Subjective
            "immediate_difficulty": immediate_diff,
            "revised_difficulty": revised_diff,
            "final_difficulty": revised_diff if revised_diff is not None else immediate_diff,
            "rating_change": rating_change,
            "immediate_guess": immediate_guess,
            "revised_guess": revised_guess,
            "immediate_guess_ord": GUESS_ORDER.get(str(immediate_guess).lower()) if immediate_guess else None,
            "revised_guess_ord": GUESS_ORDER.get(str(revised_guess).lower()) if revised_guess else None,
            # Background (repeated per row; one participant -> same values)
            "played_before": pre.get("played_before"),
            "played_before_ord": FREQUENCY_ORDER.get(str(pre.get("played_before")).lower()),
            "skill_nonogram": coerce_int(pre.get("skill_nonogram")),
            "skill_puzzles": coerce_int(pre.get("skill_puzzles")),
            "puzzle_played_frequency": pre.get("puzzle_played_frequency"),
            "puzzle_played_frequency_ord": FREQUENCY_ORDER.get(str(pre.get("puzzle_played_frequency")).lower()),
            "n_nonogram_sizes": _list_len(pre.get("nonogram_size_experience")),
            "n_logic_puzzles": _list_len(pre.get("logic_experience")),
            "nonogram_size_experience": json.dumps(pre.get("nonogram_size_experience")) if pre.get("nonogram_size_experience") is not None else None,
            "logic_experience": json.dumps(pre.get("logic_experience")) if pre.get("logic_experience") is not None else None,
            # Text (per-puzzle and shared)
            "rating_reason": post.get(f"puzzle_{i + 1}_rating_reason"),
            "strategy_text": post.get("strategy"),
            "comments_text": post.get("comments"),
            "size_experience_other": pre.get("nonogram_size_experience_other"),
            "has_post_survey": bool(post),
        })
    return rows


def _list_len(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, list):
        return len(value)
    return None


# --------------------------------------------------------------------------- #
# Public loaders
# --------------------------------------------------------------------------- #
def load_participant_puzzle_df() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for index, path in enumerate(list_log_files(), start=1):
        pid = f"P{index:03d}"
        events = read_event_log(path)
        rows.extend(extract_participant_rows(pid, path.name, events))
    df = pd.DataFrame(rows)
    return df


def load_text_responses() -> pd.DataFrame:
    """Long table: one row per free-text response (any of the text fields)."""
    base = load_participant_puzzle_df()
    records: list[dict[str, Any]] = []

    def add(row, kind, text, **extra):
        if text is None:
            return
        text_str = str(text).strip()
        if not text_str:
            return
        rec = {
            "participant_id": row["participant_id"],
            "source_file": row["source_file"],
            "response_kind": kind,
            "text": text_str,
            "char_len": len(text_str),
            "word_len": len(text_str.split()),
        }
        rec.update(extra)
        records.append(rec)

    # Per-puzzle rating reasons (vary by slot).
    for _, row in base.iterrows():
        add(row, "rating_reason", row.get("rating_reason"),
            order=int(row["order"]), puzzle_id=row.get("puzzle_id"),
            final_difficulty=row.get("final_difficulty"),
            immediate_difficulty=row.get("immediate_difficulty"),
            skill_nonogram=row.get("skill_nonogram"))

    # Participant-level fields appear once per participant.
    seen_participant: set[str] = set()
    for _, row in base.iterrows():
        pid = row["participant_id"]
        if pid in seen_participant:
            continue
        seen_participant.add(pid)
        add(row, "strategy", row.get("strategy_text"),
            order=None, puzzle_id=None, skill_nonogram=row.get("skill_nonogram"))
        add(row, "comments", row.get("comments_text"),
            order=None, puzzle_id=None, skill_nonogram=row.get("skill_nonogram"))
        add(row, "size_experience_other", row.get("size_experience_other"),
            order=None, puzzle_id=None, skill_nonogram=row.get("skill_nonogram"))

    return pd.DataFrame(records)


def load_solver_stats() -> pd.DataFrame:
    """Per-puzzle SAT solver statistics for MiniSat and Glucose."""
    if not SOLVER_STATS_TXT.exists():
        raise FileNotFoundError(SOLVER_STATS_TXT)
    rows: list[dict[str, Any]] = []
    current_puzzle: int | None = None
    current_solver: str | None = None
    for raw in SOLVER_STATS_TXT.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("puzzle id:"):
            current_puzzle = int(line.split(":", 1)[1].strip())
            current_solver = None
        elif line.startswith("Solver:"):
            current_solver = line.split(":", 1)[1].strip()
        elif line.startswith("{"):
            stats = ast.literal_eval(line)
            backend = current_solver or stats.get("backend")
            rows.append({
                "puzzle_id": current_puzzle,
                "solver": backend,
                "conflicts": stats.get("conflicts"),
                "decisions": stats.get("decisions"),
                "propagations": stats.get("propagations"),
                "sat_time_ms": stats.get("time_ms"),
            })
    df = pd.DataFrame(rows)
    for col in ["conflicts", "decisions", "propagations", "sat_time_ms"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


if __name__ == "__main__":
    df = load_participant_puzzle_df()
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 50)
    print("participant-puzzle rows:", len(df))
    print("participants:", df["participant_id"].nunique())
    print("puzzles:", sorted(df["puzzle_id"].dropna().unique().tolist()))
    print("\nattempts per puzzle:\n", df.groupby("puzzle_id").size())
    print("\nplayed_before values:", df["played_before"].value_counts(dropna=False).to_dict())
    print("puzzle_played_frequency:", df["puzzle_played_frequency"].value_counts(dropna=False).to_dict())
    print("immediate_guess values:", df["immediate_guess"].value_counts(dropna=False).to_dict())
    print("\nmissing final_difficulty:", int(df["final_difficulty"].isna().sum()))
    print("solved:", int(df["solved"].sum()), "skipped:", int(df["skipped"].sum()))
    print("\nbehavioural describe:\n", df[["n_actions", "n_hints", "n_incorrect_submissions", "time_to_solve"]].describe())

    txt = load_text_responses()
    print("\ntext responses by kind:\n", txt["response_kind"].value_counts())

    sat = load_solver_stats()
    print("\nsolver stats:\n", sat.to_string(index=False))
