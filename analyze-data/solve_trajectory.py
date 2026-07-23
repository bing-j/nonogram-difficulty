"""
Reconstruct and visualize nonogram solve trajectories from NDJSON event logs.

For each participant × puzzle, replays move/drag/undo/reset events to reconstruct
board state over time, then computes percentage of black cells correctly filled.
Produces three figures: individual trajectories, aggregated median/IQR, and a
first-action heatmap showing which cell each participant touched first per puzzle.

Inputs:
    --input_glob  : glob pattern for .ndjson session logs (e.g. "backend/logs/*.ndjson")
    --puzzles_file: path to nonograms_6.json (puzzle solution grids)
    --out_dir     : output directory for saved figures

Outputs:
    <out_dir>/solve_trajectories_individual.png        -- Figure A: one thin line per participant
    <out_dir>/solve_trajectories_aggregated.png        -- Figure B: median ± IQR band
    <out_dir>/solve_trajectories_first_action_heatmap.png -- Figure C: first-cell frequency per puzzle

Usage:
    python analyze-data/solve_trajectory.py \\
        --input_glob "backend/logs/*.ndjson" \\
        --puzzles_file nonograms_6.json \\
        --out_dir analyze-data/out_features
"""

import argparse
import copy
import glob
import io
import json
import os
import sys
from typing import Dict, List, Optional, Tuple

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np

# ---------------------------------------------------------------------------
# Windows console encoding fix (must come before any print statements)
# ---------------------------------------------------------------------------
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Import utilities from extract_features (sibling module in analyze-data/)
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(__file__))
from extract_features import (  # noqa: E402
    first_event_of_type,
    parse_time,
    read_ndjson,
    segment_puzzles,
    slice_events_by_time,
)
from plot_style import PUZZLE_COLORS, apply_style  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BOARD_SIZE: int = 10  # All research puzzles are 10x10
N_BLACK_CELLS: int = 50  # All 6 puzzles have exactly 50 black cells

# Time grid resolution for trajectory interpolation (seconds)
GRID_STEP_SEC: int = 5

# State-changing event types (others are read-only and do not affect board state)
STATE_CHANGE_TYPES = {"move", "drag", "undo", "reset"}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_puzzles(path: str) -> Dict[int, List[List[int]]]:
    """Load puzzle solutions from nonograms_6.json.

    Args:
        path: Absolute or repo-root-relative path to nonograms_6.json.

    Returns:
        Mapping from puzzle_id (int) to 10x10 solution grid (list of lists of int),
        where 1 = black cell and 0 = empty cell.

    Raises:
        FileNotFoundError: If the puzzles file does not exist.
        ValueError: If any puzzle entry is missing required fields.

    Example:
        >>> solutions = load_puzzles("nonograms_6.json")
        >>> solutions[0]  # 10x10 grid of 0s and 1s
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Puzzles file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        puzzles_raw = json.load(f)

    solutions: Dict[int, List[List[int]]] = {}
    for entry in puzzles_raw:
        pid = entry.get("id")
        solution = entry.get("solution")
        if pid is None or solution is None:
            raise ValueError(
                f"Puzzle entry missing 'id' or 'solution' field: {entry!r}"
            )
        solutions[pid] = solution

    return solutions


def load_clues(path: str) -> Dict[int, Dict]:
    """Load row and column clues for each puzzle from nonograms_6.json.

    Args:
        path: Path to nonograms_6.json.

    Returns:
        Mapping from puzzle_id to {"rows": [...], "columns": [...]}, where each
        value is a list of clue lists (e.g. rows[0] = [1, 1, 2]).
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Puzzles file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        puzzles_raw = json.load(f)

    clues: Dict[int, Dict] = {}
    for entry in puzzles_raw:
        pid = entry.get("id")
        c = entry.get("clues")
        if pid is not None and c is not None:
            clues[pid] = {"rows": c["rows"], "columns": c["columns"]}
    return clues


# ---------------------------------------------------------------------------
# Board state helpers
# ---------------------------------------------------------------------------


def compute_pct_solved(
    board: List[List[int]], solution: List[List[int]]
) -> float:
    """Compute the fraction of black cells that are correctly filled.

    A cell counts as correctly filled only when board[r][c] == 1 AND
    solution[r][c] == 1.  Crossed-out cells (value -1) and empty cells (0)
    never contribute positively.

    Args:
        board: Current 10x10 board state (int values: 0, 1, or -1).
        solution: 10x10 target solution (int values: 0 or 1).

    Returns:
        Float in [0.0, 1.0]: proportion of black solution cells currently filled.
        Returns 0.0 when the solution has no black cells (avoids division by zero).

    Example:
        >>> board = [[1, 0], [0, 0]]
        >>> solution = [[1, 1], [0, 0]]
        >>> compute_pct_solved(board, solution)
        0.5
    """
    correct = 0
    total_black = 0
    for r in range(len(solution)):
        for c in range(len(solution[r])):
            if solution[r][c] == 1:
                total_black += 1
                if board[r][c] == 1:
                    correct += 1
    if total_black == 0:
        return 0.0
    return correct / total_black


def compute_mismatches(
    board: List[List[int]], solution: List[List[int]]
) -> int:
    """Count cells where the board disagrees with the solution.

    Mirrors backend/main.py's check_board(): a cell counts as filled if its
    value is 1 (crossed-out (-1) and empty (0) both count as "not filled").

    Args:
        board: Current 10x10 board state (int values: 0, 1, or -1).
        solution: 10x10 target solution (int values: 0 or 1).

    Returns:
        Number of cells (0-100) where board disagrees with solution.
    """
    count = 0
    for r in range(len(solution)):
        for c in range(len(solution[r])):
            val = 1 if board[r][c] == 1 else 0
            if val != solution[r][c]:
                count += 1
    return count


def _empty_board() -> List[List[int]]:
    """Return a fresh 10x10 board initialised to all zeros.

    Returns:
        10x10 list of lists, all values 0.
    """
    return [[0] * BOARD_SIZE for _ in range(BOARD_SIZE)]


def apply_drag(
    board: List[List[int]], event: Dict
) -> List[Tuple[int, int, int]]:
    """Apply a drag event to the board in-place and return the undo snapshot.

    A drag covers every cell in the rectangle defined by normalized_start and
    normalized_end (both inclusive).  The rectangle may span rows, columns, or
    both (though in practice the frontend always drags in one axis).

    Drag modes:
        - "flip"        : set each cell to 1 (fill black)
        - "cross"       : set each cell to -1 (cross out)
        - "cross_toggle": toggle each cell between -1 and 0

    Args:
        board: Current 10x10 board, mutated in-place.
        event: Drag event dict with keys "mode", "normalized_start", "normalized_end".

    Returns:
        List of (r, c, old_value) tuples for all cells touched — used to push
        onto the undo stack so the operation can be fully reversed.

    Raises:
        KeyError: If required event fields are absent.
    """
    mode = event["mode"]
    r0 = event["normalized_start"]["r"]
    c0 = event["normalized_start"]["c"]
    r1 = event["normalized_end"]["r"]
    c1 = event["normalized_end"]["c"]

    snapshot: List[Tuple[int, int, int]] = []

    for r in range(min(r0, r1), max(r0, r1) + 1):
        for c in range(min(c0, c1), max(c0, c1) + 1):
            old_val = board[r][c]
            snapshot.append((r, c, old_val))

            if mode == "flip":
                board[r][c] = 1
            elif mode == "cross":
                board[r][c] = -1
            elif mode == "cross_toggle":
                # Toggle: if currently -1 → 0, otherwise → -1
                board[r][c] = 0 if old_val == -1 else -1
            # Unknown modes: skip without crashing (forward-compatible)

    return snapshot


# ---------------------------------------------------------------------------
# Trajectory reconstruction
# ---------------------------------------------------------------------------


def _apply_event(
    board: List[List[int]],
    undo_stack: List[List[Tuple[int, int, int]]],
    event: Dict,
) -> List[List[int]]:
    """Apply one state-changing event to board, updating undo_stack.

    Shared by reconstruct_trajectory (which records pct_solved after every
    event) and reconstruct_final_board (which only needs the end state).

    Args:
        board: Current 10x10 board state.
        undo_stack: Mutated in-place; a snapshot is pushed for undo/reset.
        event: A move/drag/undo/reset event dict.

    Returns:
        The board reference (a *new* list on "reset", otherwise the same
        mutated-in-place board) — callers must use the return value.
    """
    ev_type = event.get("type", "")

    if ev_type == "move":
        r, c, new_val = event["r"], event["c"], event["value"]
        old_val = board[r][c]
        board[r][c] = new_val
        undo_stack.append([(r, c, old_val)])

    elif ev_type == "drag":
        snapshot = apply_drag(board, event)
        if snapshot:  # Only push if anything was actually changed
            undo_stack.append(snapshot)

    elif ev_type == "undo":
        if undo_stack:
            snapshot = undo_stack.pop()
            for r, c, old_val in snapshot:
                board[r][c] = old_val

    elif ev_type == "reset":
        # Snapshot the entire board so reset is itself undoable
        full_snapshot: List[Tuple[int, int, int]] = []
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                if board[r][c] != 0:
                    full_snapshot.append((r, c, board[r][c]))
        undo_stack.append(full_snapshot)
        board = _empty_board()

    return board


def reconstruct_trajectory(
    puzzle_events: List[Dict],
    solution: List[List[int]],
) -> List[Tuple[float, float]]:
    """Replay board events and return a (elapsed_sec, pct_solved) time series.

    Board state is reconstructed by processing move/drag/undo/reset events
    in chronological order.  After every state-changing event, the percentage
    of black cells correctly filled is recorded alongside elapsed time.

    Time zero (t0) is the timestamp of the very first event in puzzle_events,
    regardless of its type.  A synthetic (0.0, 0.0) point is always prepended.

    Args:
        puzzle_events: Chronologically sorted list of event dicts for a single
            puzzle window (as returned by slice_events_by_time).
        solution: 10x10 solution grid for this puzzle.

    Returns:
        List of (elapsed_sec, pct_solved*100) tuples — pct_solved expressed as
        a percentage (0–100), not a fraction (0–1).  Always starts with (0.0, 0.0).
        Returns [(0.0, 0.0)] if puzzle_events is empty.

    Notes:
        - undo on an empty undo_stack is silently skipped (mirrors frontend).
        - reset snapshots the full board so it too is undoable.
        - Drag events with unrecognised modes are skipped (no board change).
    """
    if not puzzle_events:
        return [(0.0, 0.0)]

    t0 = parse_time(puzzle_events[0]["t"])
    board: List[List[int]] = _empty_board()
    undo_stack: List[List[Tuple[int, int, int]]] = []

    # Start with the synthetic zero-point
    trajectory: List[Tuple[float, float]] = [(0.0, 0.0)]

    for event in puzzle_events:
        ev_type = event.get("type", "")
        if ev_type not in STATE_CHANGE_TYPES:
            continue

        elapsed = (parse_time(event["t"]) - t0).total_seconds()
        board = _apply_event(board, undo_stack, event)

        pct = compute_pct_solved(board, solution) * 100.0
        trajectory.append((elapsed, pct))

    return trajectory


def reconstruct_final_board(puzzle_events: List[Dict]) -> List[List[int]]:
    """Replay move/drag/undo/reset events and return only the final board state.

    Reuses the same event semantics as reconstruct_trajectory via _apply_event,
    without recording a time series — used by feature-extraction code that
    only needs the end-of-session board (e.g. percent_error, percent_incomplete).

    Args:
        puzzle_events: Chronologically sorted list of event dicts for a single
            puzzle window.

    Returns:
        Final 10x10 board state. All-zero board if puzzle_events is empty or
        contains no state-changing events.
    """
    board: List[List[int]] = _empty_board()
    undo_stack: List[List[Tuple[int, int, int]]] = []

    for event in puzzle_events:
        if event.get("type", "") not in STATE_CHANGE_TYPES:
            continue
        board = _apply_event(board, undo_stack, event)

    return board


# ---------------------------------------------------------------------------
# Loading all trajectories
# ---------------------------------------------------------------------------


def load_all_trajectories(
    input_glob: str,
    puzzles_file: str,
) -> Dict[int, List[Tuple[str, List[Tuple[float, float]]]]]:
    """Load and reconstruct solving trajectories for all participants.

    Parses every .ndjson log matched by input_glob, segments each session into
    three puzzle windows, and calls reconstruct_trajectory for each window.

    Args:
        input_glob: Shell glob pattern for .ndjson log files
            (e.g. "backend/logs/*.ndjson").
        puzzles_file: Path to nonograms_6.json.

    Returns:
        Dict mapping puzzle_id (0–5) to a list of (participant_id, trajectory)
        tuples.  Each trajectory is a list of (elapsed_sec, pct_solved*100)
        pairs.  Puzzle IDs with no participant data map to empty lists.

    Warnings:
        Files that cannot be processed (missing surveys, malformed JSON, etc.)
        are skipped with a printed warning — they do not raise exceptions.
    """
    solutions = load_puzzles(puzzles_file)

    # Initialise empty buckets for all 6 puzzle IDs
    all_trajectories: Dict[int, List[Tuple[str, List[Tuple[float, float]]]]] = {
        pid: [] for pid in range(6)
    }

    paths = sorted(glob.glob(input_glob))
    if not paths:
        print(f"WARNING: No files matched glob: {input_glob}", file=sys.stderr)
        return all_trajectories

    for path in paths:
        participant_id = os.path.basename(path).replace(".ndjson", "")
        try:
            events = read_ndjson(path)

            # Identify the queue (which 3 puzzles this participant solved)
            ss_event = first_event_of_type(events, "session_start_three")
            if ss_event is None or "queue" not in ss_event:
                print(
                    f"WARNING: {participant_id}: missing session_start_three "
                    f"with queue — skipping",
                    file=sys.stderr,
                )
                continue

            queue: List[int] = ss_event["queue"]
            if len(queue) != 3:
                print(
                    f"WARNING: {participant_id}: expected queue length 3, "
                    f"got {len(queue)} — skipping",
                    file=sys.stderr,
                )
                continue

            # segment_puzzles raises ValueError if any survey is missing
            windows = segment_puzzles(events)

            for puzzle_idx, (start_t, end_t) in enumerate(windows):
                puzzle_id = queue[puzzle_idx]
                if puzzle_id not in solutions:
                    print(
                        f"WARNING: {participant_id}: puzzle_id {puzzle_id} "
                        f"not found in puzzles file — skipping puzzle {puzzle_idx + 1}",
                        file=sys.stderr,
                    )
                    continue

                puzzle_events = slice_events_by_time(events, start_t, end_t)
                solution = solutions[puzzle_id]
                trajectory = reconstruct_trajectory(puzzle_events, solution)
                all_trajectories[puzzle_id].append((participant_id, trajectory))

        except Exception as exc:  # noqa: BLE001
            print(
                f"WARNING: {participant_id}: failed to process ({type(exc).__name__}: "
                f"{exc}) — skipping",
                file=sys.stderr,
            )

    return all_trajectories


# ---------------------------------------------------------------------------
# Figure A — Individual trajectories
# ---------------------------------------------------------------------------


def plot_individual(
    trajectories: Dict[int, List[Tuple[str, List[Tuple[float, float]]]]],
    out_dir: str,
) -> None:
    """Save Figure A: individual participant solve trajectories, one subplot per puzzle.

    Each participant's trajectory is drawn as a thin, semi-transparent line so
    that overlapping paths remain visible.  Puzzles with no data still receive
    an empty subplot with an explanatory title.

    Args:
        trajectories: Mapping from puzzle_id to list of (participant_id, trajectory).
        out_dir: Directory where the PNG will be saved (created if absent).

    Returns:
        None.  Saves ``<out_dir>/solve_trajectories_individual.png`` at 150 dpi.
    """
    os.makedirs(out_dir, exist_ok=True)

    fig, axes = plt.subplots(2, 3, figsize=(15, 8))

    for puzzle_id in range(6):
        row, col = divmod(puzzle_id, 3)
        ax = axes[row][col]
        color = PUZZLE_COLORS[puzzle_id]
        data = trajectories.get(puzzle_id, [])
        n = len(data)

        if n == 0:
            ax.set_title(f"Puzzle {puzzle_id} (no data)")
            ax.text(
                0.5, 0.5, "No participants",
                ha="center", va="center", transform=ax.transAxes,
                fontsize=10, color="grey",
            )
        else:
            for _pid, traj in data:
                if not traj:
                    continue
                times = [pt[0] for pt in traj]
                pcts = [pt[1] for pt in traj]
                ax.plot(times, pcts, color=color, alpha=0.4, linewidth=1.0)

            ax.set_title(f"Puzzle {puzzle_id} (n={n})")

        ax.set_xlabel("Time (s)")
        ax.set_ylabel("% Solved")
        ax.set_ylim(0, 105)
        ax.set_xlim(left=0)

    fig.tight_layout()
    out_path = os.path.join(out_dir, "solve_trajectories_individual.png")
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"Saved: {out_path}")


# ---------------------------------------------------------------------------
# Figure B — Aggregated median ± IQR
# ---------------------------------------------------------------------------


def _build_interpolated_matrix(
    data: List[Tuple[str, List[Tuple[float, float]]]],
    grid: np.ndarray,
) -> np.ndarray:
    """Interpolate all trajectories onto a common time grid.

    For each trajectory, np.interp is used with left=0.0 (flat at 0 before the
    first recorded event) and right=last_value (flat at the final recorded
    percentage after the participant stopped making moves).

    Args:
        data: List of (participant_id, trajectory) pairs.
        grid: 1-D array of time points (seconds) at which to evaluate.

    Returns:
        2-D numpy array of shape (n_participants, len(grid)).
        Rows with empty trajectories are excluded silently.
    """
    rows = []
    for _pid, traj in data:
        if len(traj) < 2:
            # Only the synthetic (0,0) point — no moves recorded
            rows.append(np.zeros(len(grid)))
            continue
        times = np.array([pt[0] for pt in traj])
        pcts = np.array([pt[1] for pt in traj])
        interpolated = np.interp(grid, times, pcts, left=0.0, right=pcts[-1])
        rows.append(interpolated)
    return np.array(rows) if rows else np.empty((0, len(grid)))


def plot_aggregated(
    trajectories: Dict[int, List[Tuple[str, List[Tuple[float, float]]]]],
    out_dir: str,
) -> None:
    """Save Figure B: aggregated median solve trajectories with IQR shading.

    For each puzzle, all participant trajectories are interpolated onto a common
    5-second time grid.  The median and 25th/75th percentiles are computed and
    plotted as a solid line with a shaded band.

    Args:
        trajectories: Mapping from puzzle_id to list of (participant_id, trajectory).
        out_dir: Directory where the PNG will be saved (created if absent).

    Returns:
        None.  Saves ``<out_dir>/solve_trajectories_aggregated.png`` at 150 dpi.
    """
    os.makedirs(out_dir, exist_ok=True)

    fig, axes = plt.subplots(2, 3, figsize=(15, 8))

    for puzzle_id in range(6):
        row, col = divmod(puzzle_id, 3)
        ax = axes[row][col]
        color = PUZZLE_COLORS[puzzle_id]
        data = trajectories.get(puzzle_id, [])
        n = len(data)

        if n == 0:
            ax.set_title(f"Puzzle {puzzle_id} (no data)")
            ax.text(
                0.5, 0.5, "No participants",
                ha="center", va="center", transform=ax.transAxes,
                fontsize=10, color="grey",
            )
        else:
            # Determine common time grid: 0 to the maximum recorded elapsed time
            max_time = max(
                traj[-1][0]
                for _, traj in data
                if traj
            )
            grid = np.arange(0, max_time + GRID_STEP_SEC, GRID_STEP_SEC)

            matrix = _build_interpolated_matrix(data, grid)

            if matrix.shape[0] == 0:
                ax.set_title(f"Puzzle {puzzle_id} (no valid data)")
            else:
                median = np.nanpercentile(matrix, 50, axis=0)
                p25 = np.nanpercentile(matrix, 25, axis=0)
                p75 = np.nanpercentile(matrix, 75, axis=0)

                ax.plot(grid, median, color=color, linewidth=2.0, label="Median")
                ax.fill_between(
                    grid, p25, p75,
                    color=color, alpha=0.25, label="IQR (25th–75th pct)",
                )
                ax.legend(fontsize=8, loc="lower right")
                ax.set_title(f"Puzzle {puzzle_id} (n={n})")

        ax.set_xlabel("Time (s)")
        ax.set_ylabel("% Solved")
        ax.set_ylim(0, 105)
        ax.set_xlim(left=0)

    fig.tight_layout()
    out_path = os.path.join(out_dir, "solve_trajectories_aggregated.png")
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"Saved: {out_path}")


# ---------------------------------------------------------------------------
# Figure C — First-action heatmaps
# ---------------------------------------------------------------------------


def get_first_action_cell(
    puzzle_events: List[Dict],
) -> Optional[Tuple[int, int]]:
    """Return (r, c) of the first move or drag event in the puzzle window.

    For drag events, uses normalized_start as the representative cell (the
    corner where the participant initiated the drag gesture).

    Args:
        puzzle_events: Chronologically sorted event dicts for one puzzle window.

    Returns:
        (row, col) tuple of the first action cell, or None if no move/drag events.
    """
    for event in puzzle_events:
        ev_type = event.get("type", "")
        if ev_type == "move":
            return (event["r"], event["c"])
        elif ev_type == "drag":
            return (event["normalized_start"]["r"], event["normalized_start"]["c"])
    return None


def compute_first_action_heatmaps(
    input_glob: str,
    puzzles_file: str,
) -> Dict[int, np.ndarray]:
    """Count how many participants had each cell as their first action per puzzle.

    Mirrors the loading loop in load_all_trajectories with the same skip/warn logic.

    Args:
        input_glob: Shell glob pattern for .ndjson log files.
        puzzles_file: Path to nonograms_6.json (only used to validate puzzle IDs).

    Returns:
        Dict mapping puzzle_id (0–5) to a 10×10 int array where each element is
        the number of participants whose first move/drag event was that cell.
    """
    solutions = load_puzzles(puzzles_file)
    heatmaps: Dict[int, np.ndarray] = {
        pid: np.zeros((BOARD_SIZE, BOARD_SIZE), dtype=int) for pid in range(6)
    }

    paths = sorted(glob.glob(input_glob))
    if not paths:
        print(f"WARNING: No files matched glob: {input_glob}", file=sys.stderr)
        return heatmaps

    for path in paths:
        participant_id = os.path.basename(path).replace(".ndjson", "")
        try:
            events = read_ndjson(path)

            ss_event = first_event_of_type(events, "session_start_three")
            if ss_event is None or "queue" not in ss_event:
                continue

            queue: List[int] = ss_event["queue"]
            if len(queue) != 3:
                continue

            windows = segment_puzzles(events)

            for puzzle_idx, (start_t, end_t) in enumerate(windows):
                puzzle_id = queue[puzzle_idx]
                if puzzle_id not in solutions:
                    continue

                puzzle_events = slice_events_by_time(events, start_t, end_t)
                cell = get_first_action_cell(puzzle_events)
                if cell is not None:
                    r, c = cell
                    heatmaps[puzzle_id][r, c] += 1

        except Exception as exc:  # noqa: BLE001
            print(
                f"WARNING: {participant_id}: failed to process "
                f"({type(exc).__name__}: {exc}) — skipping",
                file=sys.stderr,
            )

    return heatmaps


def plot_first_action_heatmaps(
    heatmaps: Dict[int, np.ndarray],
    solutions: Dict[int, List[List[int]]],
    out_dir: str,
    clues: Optional[Dict[int, Dict]] = None,
) -> None:
    """Save Figure C: first-cell-acted-upon frequency heatmaps overlaid on puzzle solutions.

    Each subplot shows a 10×10 grid for one puzzle. Cell colour encodes how many
    participants chose that cell as their very first action.  Solution-filled cells
    (value 1 in the solution) are tinted with a semi-transparent dark overlay so the
    nonogram pattern is visible underneath the heatmap.

    Args:
        heatmaps: Mapping from puzzle_id to 10×10 count array (from compute_first_action_heatmaps).
        solutions: Mapping from puzzle_id to 10×10 solution grid (from load_puzzles).
        out_dir: Directory where the PNG will be saved (created if absent).

    Returns:
        None.  Saves ``<out_dir>/solve_trajectories_first_action_heatmap.png`` at 150 dpi.
    """
    os.makedirs(out_dir, exist_ok=True)

    fig, axes = plt.subplots(2, 3, figsize=(15, 9))

    # Shared colour scale across all puzzles so intensities are comparable
    global_max = max(
        (heatmaps[pid].max() for pid in range(6) if heatmaps[pid].max() > 0),
        default=1,
    )

    for puzzle_id in range(6):
        row, col = divmod(puzzle_id, 3)
        ax = axes[row][col]
        count_matrix = heatmaps.get(puzzle_id, np.zeros((BOARD_SIZE, BOARD_SIZE), dtype=int))
        solution = solutions.get(puzzle_id, [[0] * BOARD_SIZE for _ in range(BOARD_SIZE)])
        n_total = int(count_matrix.sum())

        # Layer 1: heatmap of first-action counts
        im = ax.imshow(
            count_matrix,
            cmap="YlOrRd",
            vmin=0,
            vmax=global_max,
            aspect="equal",
        )

        # Layer 2: semi-transparent dark overlay for solution=1 cells
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                if solution[r][c] == 1:
                    rect = mpatches.Rectangle(
                        [c - 0.5, r - 0.5], 1, 1,
                        facecolor="black", alpha=0.18,
                        edgecolor="black", linewidth=1.5,
                        zorder=2,
                    )
                    ax.add_patch(rect)

        # Layer 3: count annotations for non-zero cells
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                cnt = count_matrix[r, c]
                if cnt > 0:
                    ax.text(
                        c, r, str(cnt),
                        ha="center", va="center",
                        fontsize=8, fontweight="bold",
                        color="black", zorder=3,
                    )

        # Grid lines via minor ticks
        ax.set_xticks(np.arange(-0.5, BOARD_SIZE, 1), minor=True)
        ax.set_yticks(np.arange(-0.5, BOARD_SIZE, 1), minor=True)
        ax.tick_params(which="minor", length=0)
        ax.grid(which="minor", color="gray", linewidth=0.4, zorder=1)

        # Tick labels: clue strings if available, otherwise numeric indices
        ax.set_xticks(range(BOARD_SIZE))
        ax.set_yticks(range(BOARD_SIZE))
        if clues and puzzle_id in clues:
            puzzle_clues = clues[puzzle_id]
            row_labels = [" ".join(map(str, puzzle_clues["rows"][r])) for r in range(BOARD_SIZE)]
            # Reversed because rotation=90 + va="bottom" + tick_top() renders the
            # *last* joined token nearest the grid — reverse so the first clue
            # (topmost run) ends up closest to row 0, matching the solution.
            col_labels = [" ".join(map(str, reversed(puzzle_clues["columns"][c]))) for c in range(BOARD_SIZE)]
            ax.set_yticklabels(row_labels, fontsize=7, ha="right")
            ax.xaxis.tick_top()
            ax.set_xticklabels(col_labels, fontsize=7, rotation=90, ha="center", va="bottom")
        else:
            ax.set_xticklabels(range(BOARD_SIZE), fontsize=7)
            ax.set_yticklabels(range(BOARD_SIZE), fontsize=7)

        plt.colorbar(im, ax=ax, label="# participants", shrink=0.8)
        ax.set_title(f"Puzzle {puzzle_id}  (n={n_total})", fontsize=10)

    fig.tight_layout()
    out_path = os.path.join(out_dir, "solve_trajectories_first_action_heatmap.png")
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Parse arguments and run trajectory reconstruction + visualisation.

    Expects to be called from the repo root so that input_glob patterns like
    ``"backend/logs/*.ndjson"`` resolve correctly.
    """
    ap = argparse.ArgumentParser(
        description=(
            "Reconstruct nonogram solve trajectories from NDJSON logs "
            "and produce trajectory visualisation figures."
        )
    )
    ap.add_argument(
        "--input_glob",
        type=str,
        required=True,
        help='Glob pattern for .ndjson log files, e.g. "backend/logs/*.ndjson"',
    )
    ap.add_argument(
        "--puzzles_file",
        type=str,
        default="nonograms_6.json",
        help="Path to nonograms_6.json (default: nonograms_6.json)",
    )
    ap.add_argument(
        "--out_dir",
        type=str,
        default="analyze-data/out_features",
        help="Output directory for figures (default: analyze-data/out_features)",
    )
    args = ap.parse_args()

    apply_style()

    print(f"Loading trajectories from: {args.input_glob}")
    trajectories = load_all_trajectories(args.input_glob, args.puzzles_file)

    # Print a brief summary so the user can spot missing data early
    print("\nTrajectory counts per puzzle:")
    for pid in range(6):
        n = len(trajectories[pid])
        print(f"  Puzzle {pid}: {n} participant(s)")

    print(f"\nSaving figures to: {args.out_dir}")
    plot_individual(trajectories, args.out_dir)
    plot_aggregated(trajectories, args.out_dir)

    solutions = load_puzzles(args.puzzles_file)
    clues = load_clues(args.puzzles_file)
    heatmaps = compute_first_action_heatmaps(args.input_glob, args.puzzles_file)
    plot_first_action_heatmaps(heatmaps, solutions, args.out_dir, clues=clues)

    print("\nDone.")


if __name__ == "__main__":
    main()
