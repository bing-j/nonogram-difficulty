from typing import List, Dict, Tuple
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from pydantic import BaseModel
import random
import uuid
import json, io, zipfile
import yaml

from backend.solver_adapter import solve_nonogram, UnsolvableError

HINT_LIMIT = 5

SURVEY_SPEC = {
    "pre": [
        {
            "id": "played_before",
            "prompt": "Have you played Nonograms before?",
            "type": "single",  # one choice only
            "options": [
                {"value": "never", "label": "Never"},
                {"value": "few", "label": "A few times"},
                {"value": "many", "label": "Many times"},
                {"value": "regular", "label": "Regularly"},
            ],
        },
        {
            "id": "skill_nonogram",
            "prompt": "On a scale of 1 to 10 (1 indicates beginner, 10 indicates expert), how would you rate your Nonogram skills?",
            "type": "scale",
            "min": 1,
            "max": 10,
        },
        {
            "id": "nonogram_size_experience",
            "prompt": "If you have played Nonogram before, what are the sizes you have solved? (select all that apply)",
            "type": "multi",  # multiple choices allowed
            "options": [
                {"value": "<=10*10", "label": "≤ 10 by 10"},
                {"value": "10*10", "label": "10 by 10"},
                {"value": ">=10*10", "label": "≥ 10 by 10"},
                {"value": "N/A", "label": "Not sure or not applicable"},
                {"value": "other", "label": "Other:"},
            ],
            "allow_free_text": True
        },
        {
            "id": "logic_experience",
            "prompt": "Have you played any other logic puzzles before (select all that apply)?",
            "type": "multi",  # multiple choices allowed
            "options": [
                {"value": "sudoku", "label": "Sudoku"},
                {"value": "minesweeper", "label": "Minesweeper"},
                {"value": "norinoti", "label": "Norinori"},
                {"value": "battleships", "label": "Battleships"},
                {"value": "other", "label": "Other:"},
            ],
            "allow_free_text": True
        },
        {
            "id": "puzzle_played_frequency",
            "prompt": "Have you played any other logic puzzles before? (select all that apply)",
            "type": "single",  # one choice only
            "options": [
                {"value": "never", "label": "Never"},
                {"value": "few", "label": "A few times"},
                {"value": "many", "label": "Many times"},
                {"value": "regular", "label": "Regularly"},
            ],
        },
        {
            "id": "skill_puzzles",
            "prompt": "On a scale of 1 to 10 (1 indicates beginner, 10 indicates expert), how would you rate your logic-puzzle skills?",
            "type": "scale",
            "min": 1,
            "max": 10,
        },
    ],
    "puzzle_1": [
        {
            "id": "difficulty",
            "prompt": "On a scale of 1 to 5 (1 indicates easiest, 10 indicates hardest), how would you rate the difficulty of this puzzle?",
            "type": "scale",
            "min": 1,
            "max": 5,
            "n/a": -1,
        },
        {
            "id": "puzzle_1_guesses",
            "prompt": "How many times did you guess a cell (which means the decision was not based on logical deduction) on Puzzle 1?",
            "type": "single",
            "options": [
                {"value": "n/a", "label": "N/A"},
                {"value": "never", "label": "Never"},
                {"value": "few", "label": "A few times"},
                {"value": "many", "label": "Many times"},
                {"value": "all", "label": "All the times"},
            ],
        },
    ],
    "puzzle_2": [
        {
            "id": "difficulty",
            "prompt": "On a scale of 1 to 5 (1 indicates easiest, 10 indicates hardest), how would you rate the difficulty of this puzzle?",
            "type": "scale",
            "min": 1,
            "max": 5,
            "n/a": -1,
        },
        {
            "id": "puzzle_2_guesses",
            "prompt": "How many times did you guess a cell (which means the decision was not based on logical deduction) on Puzzle 2?",
            "type": "single",
            "options": [
                {"value": "n/a", "label": "N/A"},
                {"value": "never", "label": "Never"},
                {"value": "few", "label": "A few times"},
                {"value": "many", "label": "Many times"},
                {"value": "all", "label": "All the times"},
            ],
        },
    ],
    "puzzle_3": [
        {
            "id": "difficulty",
            "prompt": "On a scale of 1 to 5 (1 indicates easiest, 10 indicates hardest), how would you rate the difficulty of this puzzle?",
            "type": "scale",
            "min": 1,
            "max": 5,
            "n/a": -1,
        },
        {
            "id": "puzzle_3_guesses",
            "prompt": "How many times did you guess a cell (which means the decision was not based on logical deduction) on Puzzle 3?",
            "type": "single",
            "options": [
                {"value": "n/a", "label": "N/A"},
                {"value": "never", "label": "Never"},
                {"value": "few", "label": "A few times"},
                {"value": "many", "label": "Many times"},
                {"value": "all", "label": "All the times"},
            ],
        },
    ],
    "post": [
        {
            "id": "puzzle_1_rate_again",
            "prompt": "Would you like to adjust your difficulty rating for Puzzle 1? The value is preset to the rating you rated earlier.", # show original rating
            "type": "scale",
            "min": 1,
            "max": 5,
            "n/a": -1,
        },
        {
            "id": "puzzle_1_rating_reason",
            "prompt": "Why did you rate this difficulty? What made it easy/hard?",
            "type": "text",
            "allow_free_text": True
        },
        {
            "id": "puzzle_1_guesses",
            "prompt": "How many times did you guess a cell (which means the decision was not based on logical deduction) on Puzzle 1?",
            "type": "single",
            "options": [
                {"value": "n/a", "label": "N/A"},
                {"value": "never", "label": "Never"},
                {"value": "few", "label": "A few times"},
                {"value": "many", "label": "Many times"},
                {"value": "all", "label": "All the times"},
            ],
        },
        {
            "id": "puzzle_2_rate_again",
            "prompt": "Would you like to adjust your difficulty rating for Puzzle 2? The value is preset to the rating you rated earlier.", # show original rating
            "type": "scale",
            "min": 1,
            "max": 5,
            "n/a": -1,
        },
        {
            "id": "puzzle_2_rating_reason",
            "prompt": "Why did you rate this difficulty? What made it easy/hard?",
            "type": "text",
            "allow_free_text": True
        },
        {
            "id": "puzzle_2_guesses",
            "prompt": "How many times did you guess a cell (which means the decision was not based on logical deduction) on Puzzle 2?",
            "type": "single",
            "options": [
                {"value": "n/a", "label": "N/A"},
                {"value": "never", "label": "Never"},
                {"value": "few", "label": "A few times"},
                {"value": "many", "label": "Many times"},
                {"value": "all", "label": "All the times"},
            ],
        },
        {
            "id": "puzzle_3_rate_again",
            "prompt": "Would you like to adjust your difficulty rating for Puzzle 3? The value is preset to the rating you rated earlier.", # show original rating
            "type": "scale",
            "min": 1,
            "max": 5,
            "n/a": -1,
        },
        {
            "id": "puzzle_3_rating_reason",
            "prompt": "Why did you rate this difficulty? What made it easy/hard?",
            "type": "text",
            "allow_free_text": True
        },
        {
            "id": "puzzle_3_guesses",
            "prompt": "How many times did you guess a cell (which means the decision was not based on logical deduction) on Puzzle 3?",
            "type": "single",
            "options": [
                {"value": "n/a", "label": "N/A"},
                {"value": "never", "label": "Never"},
                {"value": "few", "label": "A few times"},
                {"value": "many", "label": "Many times"},
                {"value": "all", "label": "All the times"},
            ],
        },
        {
            "id": "strategy",
            "prompt": "What strategies did you use when solving the puzzles?",
            "type": "text",
            "allow_free_text": True
        },
        # {
        #     "id": "difficulty_factor",
        #     "prompt": "Which factor most signaled difficulty to you?",
        #     "type": "text",
        #     "allow_free_text": True
        # },
        {
            "id": "comments",
            "prompt": "Anything else about what made puzzles feel easy or hard?",
            "type": "text",
            "allow_free_text": True
        },
    ]
}

app = FastAPI(title="Nonogram API")

# Allow frontend to talk to backend (during development)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- Filesystem logging config ----
BASE_DIR = Path(__file__).resolve().parent   # .../backend
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

ROOT_DIR = BASE_DIR.parent  # project root

# # --- Puzzle bank (three-at-a-time sessions) ---
# BANK_PATH = ROOT_DIR / "unique_solution_nonograms_50.json"
# with BANK_PATH.open("r", encoding="utf-8") as f:
#     PUZZLE_BANK = json.load(f)            # list[dict]
# BANK_BY_ID = {p["id"]: p for p in PUZZLE_BANK}

# --- 6-puzzle pool (ids 0-5) ---
POOL6_PATH = ROOT_DIR / "nonograms_6.json"
with POOL6_PATH.open("r", encoding="utf-8") as f:
    POOL6 = json.load(f)  # list[dict]
POOL6_BY_ID = {p["id"]: p for p in POOL6}

# --- Assignment schedule (ordered triples of ids 0-5) ---
SCHEDULE_PATH = ROOT_DIR / "assignment_schedule_6puzzles_3perms.json"
with SCHEDULE_PATH.open("r", encoding="utf-8") as f:
    ASSIGNMENT_SCHEDULE = json.load(f)["sequences"]  # list[list[int]]

# --- Assignment state (tracked by git) ---
STATE_PATH = ROOT_DIR / "assignment_state.json"

def load_assignment_state() -> dict:
    if not STATE_PATH.exists():
        data = {"next_idx": 0}
        STATE_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return data
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))

def save_assignment_state(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")

# --- Tutorial puzzle bank ---
TUTORIAL_BANK_PATH = ROOT_DIR / "tutorial_nonograms_10x10.json"
with TUTORIAL_BANK_PATH.open("r", encoding="utf-8") as f:
    TUTORIAL_PUZZLE_BANK = json.load(f)

TUTORIAL_BANK_BY_ID = {p["id"]: p for p in TUTORIAL_PUZZLE_BANK}

# --- Warmup puzzle bank (single 2x2 puzzle) ---
WARMUP_BANK_PATH = ROOT_DIR / "warmup_nonogram_10x10.json"
with WARMUP_BANK_PATH.open("r", encoding="utf-8") as f:
    WARMUP_PUZZLE_BANK = json.load(f)   # list[dict] with exactly one element

WARMUP_BANK_BY_ID = {p["id"]: p for p in WARMUP_PUZZLE_BANK}

def _pack_public_from_bank(p: dict) -> dict:
    """Only the safe bits to send to the client."""
    rows = len(p["solution"])
    cols = len(p["solution"][0])
    return {
        "id": p["id"],
        "rows": rows,
        "cols": cols,
        "row_clues": p["clues"]["rows"],
        "col_clues": p["clues"]["columns"],
    }


def now_iso():
    return datetime.now(timezone.utc).isoformat()

def log_file_ndjson(session_id: str) -> Path:
    return LOG_DIR / f"{session_id}.ndjson"

def log_file_json(session_id: str) -> Path:
    return LOG_DIR / f"{session_id}.json"

def log_file_yaml(session_id: str) -> Path:
    return LOG_DIR / f"{session_id}.yaml"

def convert_json_to_yaml(session_id: str) -> Path:
    """
    Ensure the latest JSON snapshot exists, then convert it to YAML.
    """
    p_json = write_snapshot_json(session_id)  # refresh JSON from in-memory log
    with p_json.open("r", encoding="utf-8") as f:
        data = json.load(f)
    p_yaml = log_file_yaml(session_id)
    with p_yaml.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
    return p_yaml

def append_event(session_id: str, event: dict) -> None:
    """Append a single event to NDJSON log on disk."""
    p = log_file_ndjson(session_id)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

def write_snapshot_json(session_id: str) -> Path:
    """Write the full log snapshot (current in-memory log) to a JSON file."""
    s = SESSIONS.get(session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    p = log_file_json(session_id)
    with p.open("w", encoding="utf-8") as f:
        json.dump(s["log"], f, ensure_ascii=False, indent=2)
    return p

# --- Models ---
class PuzzleCreate(BaseModel):
    row_clues: List[List[int]]
    col_clues: List[List[int]]

class PuzzleInfo(BaseModel):
    id: str
    rows: int
    cols: int
    row_clues: List[List[int]]
    col_clues: List[List[int]]

class Move(BaseModel):
    r: int
    c: int
    value: int  # 1 = filled, 0 = empty, -1 = X

class Board(BaseModel):
    board: List[List[int]]

class CheckResult(BaseModel):
    solved: bool
    mismatches: List[Tuple[int, int]] = []

# --- In-memory stores ---
PUZZLES: Dict[str, PuzzleInfo] = {}
SOLUTIONS: Dict[str, List[List[int]]] = {}
SESSIONS: Dict[str, Dict] = {}

# --- Helpers ---
def blank_board(rows: int, cols: int):
    return [[0 for _ in range(cols)] for _ in range(rows)]

def ensure_session(session_id: str) -> Dict:
    s = SESSIONS.get(session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    return s

def check_board(board, solution):
    mismatches = []
    for r in range(len(board)):
        for c in range(len(board[0])):
            val = 1 if board[r][c] == 1 else 0
            if val != solution[r][c]:
                mismatches.append((r, c))
    return mismatches

def _get_hint_count(session: Dict) -> int:
    if session.get("mode") == "bank_three":
        idx = session.get("idx", 0)
        hint_counts = session.setdefault("hint_counts", [0, 0, 0])
        if 0 <= idx < len(hint_counts):
            return hint_counts[idx]
        return 0
    return session.get("hint_count", 0)

def _increment_hint_count(session: Dict) -> None:
    if session.get("mode") == "bank_three":
        idx = session.get("idx", 0)
        hint_counts = session.setdefault("hint_counts", [0, 0, 0])
        if 0 <= idx < len(hint_counts):
            hint_counts[idx] += 1
        return
    session["hint_count"] = session.get("hint_count", 0) + 1

def _ensure_undo(session: Dict) -> None:
    session.setdefault("undo_stack", [])

def _push_undo(session: Dict, diffs: List[Dict], label: str) -> None:
    if not diffs:
        return
    _ensure_undo(session)
    session["undo_stack"].append({
        "label": label,
        "t": now_iso(),
        "diffs": diffs
    })

def _apply_undo_group(session: Dict, group: Dict) -> None:
    board = session["board"]
    rows, cols = len(board), len(board[0])
    # revert in reverse order (not strictly required here, but good practice)
    for d in reversed(group.get("diffs", [])):
        r, c = int(d["r"]), int(d["c"])
        if 0 <= r < rows and 0 <= c < cols:
            board[r][c] = int(d["from"])

# --- Routes ---

@app.post("/session/start_warmup")
def start_warmup():
    # since there is exactly one warmup puzzle
    p = WARMUP_PUZZLE_BANK[0]

    sid = uuid.uuid4().hex
    rows = len(p["solution"])
    cols = len(p["solution"][0])

    SESSIONS[sid] = {
        "mode": "warmup",
        "board": blank_board(rows, cols),
        "answer": p["solution"],  # ground truth
        "hint_count": 0,
        "hint_limit": HINT_LIMIT,
        "undo_stack": [],
        # intentionally no logging
    }

    return {
        "session_id": sid,
        "puzzle": _pack_public_from_bank(p),
        "hint_limit": HINT_LIMIT,
        "hints_remaining": HINT_LIMIT
    }


@app.post("/session/start_tutorial")
def start_tutorial(tutorial_id: str = "tutorial_5x5"):
    p = TUTORIAL_BANK_BY_ID.get(tutorial_id)
    if not p:
        raise HTTPException(404, "Unknown tutorial_id")

    sid = uuid.uuid4().hex

    rows = len(p["solution"])
    cols = len(p["solution"][0])

    SESSIONS[sid] = {
        "mode": "tutorial",
        "tutorial_id": tutorial_id,
        "board": blank_board(rows, cols),
        "answer": p["solution"],
        "hint_count": 0,
        "hint_limit": HINT_LIMIT,
        "undo_stack": [],
        "log": {
            "puzzle_id": f"tutorial:{tutorial_id}",
            "start_time": now_iso(),
            "end_time": None,
            "moves": [],
            "checks_count": 0,
            "resets_count": 0,
            "checks": [[]],
            "resets": [[]],
        }
    }

    append_event(sid, {
        "type": "session_start_tutorial",
        "tutorial_id": tutorial_id,
        "t": now_iso()
    })

    return {
        "session_id": sid,
        "puzzle": _pack_public_from_bank(p),
        "hint_limit": HINT_LIMIT,
        "hints_remaining": HINT_LIMIT
    }


@app.post("/session/start_three")
def start_three():
    state = load_assignment_state()
    next_idx = int(state.get("next_idx", 0))

    if next_idx >= len(ASSIGNMENT_SCHEDULE):
        raise HTTPException(409, "No more scheduled sequences available")

    queue_ids = ASSIGNMENT_SCHEDULE[next_idx]  # e.g. [0, a, b]

    # pull the 3 puzzles from the 6-puzzle pool by id (in order)
    try:
        chosen = [POOL6_BY_ID[pid] for pid in queue_ids]
    except KeyError as e:
        raise HTTPException(500, f"Schedule contains unknown puzzle id: {e}")

    sid = uuid.uuid4().hex
    first = chosen[0]
    SESSIONS[sid] = {
        "mode": "bank_three",
        "queue": queue_ids,
        "idx": 0,
        "solved_flags": [False, False, False],
        "skipped_flags": [False, False, False],
        "hint_counts": [0, 0, 0],
        "hint_limit": HINT_LIMIT,
        "undo_stack": [],
        "answers": {p["id"]: p["solution"] for p in chosen},
        "board": blank_board(len(first["solution"]), len(first["solution"][0])),
        "schedule_idx": next_idx,  # store for commit-on-completion
        "log": {
            "puzzle_id": f"bank:{queue_ids[0]}",
            "start_time": now_iso(),
            "end_time": None,
            "moves": [],
            "checks_count": 0,
            "resets_count": 0,
            "checks": [[], [], []],
            "resets": [[], [], []],
            "queue": queue_ids,
            "schedule_idx": next_idx,  # helpful for analysis/audit
            "surveys": {"pre": None, "puzzle": [None, None, None], "post": None}
        }
    }

    append_event(sid, {"type": "session_start_three", "queue": queue_ids, "schedule_idx": next_idx, "t": now_iso()})
    return {
        "session_id": sid,
        "index": 0,
        "puzzle": _pack_public_from_bank(first),  # send only clues+size
        "hint_limit": HINT_LIMIT,
        "hints_remaining": HINT_LIMIT
    }

# -------- SURVEY ENDPOINTS --------
@app.get("/sessions/{session_id}/survey/{survey_type}")
def get_survey(session_id: str, survey_type: str):
    ensure_session(session_id)
    spec = SURVEY_SPEC.get(survey_type)
    if not spec:
        raise HTTPException(404, f"Unknown survey type: {survey_type}")
    return {"survey_type": survey_type, "questions": spec}


@app.post("/sessions/{session_id}/survey_submit")
def survey_submit(session_id: str, payload: dict):
    """
    Accepts answers for survey blocks defined in SURVEY_SPEC:
      survey_type ∈ {"pre", "puzzle_1", "puzzle_2", "puzzle_3", "post"}
    Body shape (no strict validation):
      {
        "survey_type": "pre" | "puzzle_1" | "puzzle_2" | "puzzle_3" | "post",
        "answers": { "<question_id>": <value>, ... }
      }
    """
    s = ensure_session(session_id)

    survey_type = (payload.get("survey_type") or "").strip()
    answers = payload.get("answers") or {}

    # Ensure surveys container exists (defensive, keeps structure stable)
    s.setdefault("log", {})
    s["log"].setdefault("surveys", {"pre": None, "puzzle": [None, None, None], "post": None})

    # Build the record we store (what was submitted + timestamp)
    record = {
        "t": now_iso(),
        "survey_type": survey_type,
        "answers": answers,
    }

    # Route by survey_type exactly as in SURVEY_SPEC
    if survey_type == "pre":
        s["log"]["surveys"]["pre"] = record

    elif survey_type in ("puzzle_1", "puzzle_2", "puzzle_3"):
        # Map "puzzle_1"->0, "puzzle_2"->1, "puzzle_3"->2
        idx = int(survey_type.split("_")[1]) - 1
        record["puzzle_idx"] = idx

        # Make sure the list can hold this index
        lst = s["log"]["surveys"].setdefault("puzzle", [None, None, None])
        if idx >= len(lst):
            lst.extend([None] * (idx + 1 - len(lst)))
        lst[idx] = record

    elif survey_type == "post":
        s["log"]["surveys"]["post"] = record

    else:
        raise HTTPException(status_code=400, detail=f"Unknown survey_type: {survey_type!r}")

    # Persist a flat event line for easy CSV/NDJSON processing
    append_event(session_id, {
        "type": "survey_submit",
        "survey_type": survey_type,
        "puzzle_idx": record.get("puzzle_idx"),
        "answers": answers,
        "t": record["t"],
    })

    return {"ok": True, "saved": record}


@app.post("/puzzles")
def create_puzzle(payload: PuzzleCreate):
    """Create a new puzzle and session (solves it once)."""
    try:
        solution = solve_nonogram(payload.row_clues, payload.col_clues)
    except UnsolvableError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(400, f"Error: {e}")

    puzzle_id = uuid.uuid4().hex[:8]
    PUZZLES[puzzle_id] = PuzzleInfo(
        id=puzzle_id,
        rows=len(payload.row_clues),
        cols=len(payload.col_clues),
        row_clues=payload.row_clues,
        col_clues=payload.col_clues,
    )
    SOLUTIONS[puzzle_id] = solution

    session_id = uuid.uuid4().hex
    SESSIONS[session_id] = {
        "puzzle_id": puzzle_id,
        "board": blank_board(len(payload.row_clues), len(payload.col_clues)),
        "log": {
            "puzzle_id": puzzle_id,
            "start_time": now_iso(),
            "end_time": None,
            "moves": [],
            "checks_count": 0,
            "resets_count": 0,
            "checks": [[]],
            "resets": [[]],
        }
    }

    # first event: session created (disk)
    append_event(session_id, {
        "type": "session_start",
        "puzzle_id": puzzle_id,
        "t": now_iso()
    })

    return {"puzzle": PUZZLES[puzzle_id].model_dump(), "session_id": session_id}

@app.get("/puzzles/{puzzle_id}", response_model=PuzzleInfo)
def get_puzzle(puzzle_id: str):
    p = PUZZLES.get(puzzle_id)
    if not p:
        raise HTTPException(404, "Puzzle not found")
    return p

@app.get("/sessions/{session_id}/state", response_model=Board)
def get_state(session_id: str):
    s = ensure_session(session_id)
    return Board(board=s["board"])

@app.post("/sessions/{session_id}/move", response_model=Board)
def move(session_id: str, move: Move):
    s = ensure_session(session_id)
    rows, cols = len(s["board"]), len(s["board"][0])
    if not (0 <= move.r < rows and 0 <= move.c < cols):
        raise HTTPException(400, "Invalid coordinates")
    if move.value not in (-1, 0, 1):
        raise HTTPException(400, "Invalid value")
    prev = s["board"][move.r][move.c]
    nxt = move.value
    if prev == nxt:
        return Board(board=s["board"])

    s["board"][move.r][move.c] = nxt

    # Record undo (only cell modifications)
    _push_undo(s, [{
        "r": move.r,
        "c": move.c,
        "from": prev,
        "to": nxt
    }], label="cell")

    if s.get("mode") != "warmup":  # logging (skip for warmup)
        # log the move (memory)
        s["log"]["moves"].append({
            "r": move.r,
            "c": move.c,
            "value": move.value,
            "t": now_iso()
        })
        # log the move (disk)
        append_event(session_id, {
            "type": "move",
            "r": move.r,
            "c": move.c,
            "value": move.value,
            "t": now_iso()
        })
    return Board(board=s["board"])

@app.post("/sessions/{session_id}/check")
def check_session(session_id: str):
    s = ensure_session(session_id)

    # Board the user has built via /move calls
    board = s["board"]

    # ========== warmup flow ==========
    if s.get("mode") == "warmup":
        truth = s.get("answer")
        if truth is None:
            raise HTTPException(500, "Warmup answer not available for this session")

        board01 = [[1 if c == 1 else 0 for c in row] for row in board]
        mismatches = check_board(board01, truth)

        if mismatches:
            return {"solved": False, "mismatches": mismatches}
        return {"solved": True, "completed": True}

    # ========== tutorial flow (single fixed puzzle) ==========
    if s.get("mode") == "tutorial":
        truth = s.get("answer")
        if truth is None:
            raise HTTPException(500, "Tutorial answer not available for this session")

        board01 = [[1 if c == 1 else 0 for c in row] for row in board]
        mismatches = check_board(board01, truth)

        s["log"]["checks_count"] = s["log"].get("checks_count", 0) + 1
        s["log"]["checks"][0].append(now_iso())

        append_event(session_id, {
            "type": "check_tutorial",
            "solved": len(mismatches) == 0,
            "mismatches": mismatches,
            "t": now_iso(),
        })

        return {"solved": len(mismatches) == 0, "mismatches": mismatches}

    # ========== 3-puzzle bank flow ==========
    if s.get("mode") == "bank_three":
        # What puzzle are we on?
        cur_id = s["queue"][s["idx"]]
        truth = s["answers"][cur_id]  # 2D 0/1 ground truth

        # (Optional) ensure board values are 0/1 if you allow -1 in UI
        board01 = [[1 if c == 1 else 0 for c in row] for row in board]

        mismatches = check_board(board01, truth)
        solved = (len(mismatches) == 0)

        # logging
        s["log"]["checks_count"] = s["log"].get("checks_count", 0) + 1
        s["log"]["checks"][s["idx"]].append(now_iso())  # NEW: timestamp per current puzzle
        append_event(session_id, {
            "type": "check_bank",
            "puzzle_id": cur_id,
            "solved": solved,
            "mismatches": mismatches,
            "t": now_iso(),
        })

        if not solved:
            return {"solved": False, "mismatches": mismatches}

        s["solved_flags"][s["idx"]] = True
        # advance to next puzzle (or finish)
        s["idx"] += 1
        if s["idx"] >= 3:
            completed_all_three = all(s.get("solved_flags", [False, False, False]))
            if completed_all_three:
                if s["log"].get("end_time") is None:
                    s["log"]["end_time"] = now_iso()
                append_event(session_id, {"type": "completed_all_three", "t": s["log"]["end_time"]})

                # commit schedule index only on full completion
                state = load_assignment_state()
                cur = int(state.get("next_idx", 0))
                used = int(s.get("schedule_idx", cur))
                if used == cur:
                    state["next_idx"] = cur + 1
                    save_assignment_state(state)

                return {"solved": True, "completed": True}

            # Not all solved (some skipped)
            if s["log"].get("end_time") is None:
                s["log"]["end_time"] = now_iso()
            append_event(session_id, {"type": "ended_without_full_completion", "solved_flags": s["solved_flags"],
                                      "t": s["log"]["end_time"]})

            return {
                "solved": True,  # the last puzzle they checked was solved
                "completed": False,  # but NOT all three solved
                "finished": True,  # optional convenience flag for frontend
                "solved_flags": s.get("solved_flags"),
                "skipped_flags": s.get("skipped_flags")
            }

        # next puzzle metadata to send to client
        next_id = s["queue"][s["idx"]]
        next_pz = POOL6_BY_ID[next_id]
        rows, cols = len(next_pz["solution"]), len(next_pz["solution"][0])

        # reset server board for the next puzzle
        s["board"] = blank_board(rows, cols)
        s["undo_stack"] = []
        s["log"]["puzzle_id"] = f"bank:{next_id}"

        return {
            "solved": True,
            "completed": False,
            "index": s["idx"],
            "puzzle": {
                "id": next_pz["id"],
                "rows": rows,
                "cols": cols,
                "row_clues": next_pz["clues"]["rows"],
                "col_clues": next_pz["clues"]["columns"],
            },
            "hint_limit": s.get("hint_limit", HINT_LIMIT),
            "hints_remaining": max(0, s.get("hint_limit", HINT_LIMIT) - _get_hint_count(s))
        }

    # ========== original single-puzzle flow ==========
    truth = s["puzzle"]["solution"]
    board01 = [[1 if c == 1 else 0 for c in row] for row in board]
    mismatches = check_board(board01, truth)
    s["log"]["checks_count"] = s["log"].get("checks_count", 0) + 1
    s["log"]["checks"][0].append(now_iso())
    return {"solved": len(mismatches) == 0, "mismatches": mismatches}

@app.get("/sessions/{session_id}/hint")
def get_hint(session_id: str):
    """
    Return a random mismatched cell coordinate between the player's current
    board and the puzzle solution. If there are no mismatches, indicate solved.
    """
    s = ensure_session(session_id)
    hint_limit = s.get("hint_limit", HINT_LIMIT)

    # Current board (may contain -1 / 0 / 1)
    board = s["board"]
    board01 = [[1 if c == 1 else 0 for c in row] for row in board]

    # Resolve the correct ground-truth solution based on mode
    if s.get("mode") == "bank_three":
        cur_id = s["queue"][s["idx"]]
        truth = s["answers"][cur_id]  # 2D 0/1
    elif s.get("mode") == "tutorial" or s.get("mode") == "warmup":
        truth = s.get("answer")
        if truth is None:
            raise HTTPException(500, "Tutorial answer not available for this session")
    else:
        # Single-puzzle mode: use the global SOLUTIONS by puzzle_id
        pid = s.get("puzzle_id")
        if pid is None or pid not in SOLUTIONS:
            raise HTTPException(500, "Solution not available for this session")
        truth = SOLUTIONS[pid]

    # Find mismatches (reuse your existing logic)
    mismatches = check_board(board01, truth)

    # Nothing to hint if already matching the solution
    if not mismatches:
        if s.get("mode") != "warmup":  # skip for warmup
            append_event(session_id, {
                "type": "hint_none",
                "t": now_iso()
            })
        return {
            "solved": True,
            "hint": None,
            "hint_limit": hint_limit,
            "hints_used": _get_hint_count(s),
            "hints_remaining": max(0, hint_limit - _get_hint_count(s)),
            "limit_reached": False
        }

    hints_used = _get_hint_count(s)
    if hints_used >= hint_limit:
        if s.get("mode") != "warmup":  # skip for warmup
            append_event(session_id, {
                "type": "hint_limit",
                "t": now_iso()
            })
        return {
            "solved": False,
            "hint": None,
            "hint_limit": hint_limit,
            "hints_used": hints_used,
            "hints_remaining": 0,
            "limit_reached": True
        }


    # Prioritize hint selection:
    # 1) false positives: user filled black (1) but truth is white (0)
    # 2) crossed-out but should be black: user marked X (-1) but truth is black (1)
    # 3) otherwise: any mismatched cell
    false_positives = [(r, c) for (r, c) in mismatches if board[r][c] == 1 and truth[r][c] == 0]
    # print(false_positives)
    if false_positives:
        # print("in false_positives")
        r, c = random.choice(false_positives)
        # print("r, c", r, c)
    else:
        # print("not in false_positives")
        crossed_should_be_black = [(r, c) for (r, c) in mismatches if board[r][c] == -1 and truth[r][c] == 1]
        if crossed_should_be_black:
            # print("in crossed_should_be_black")
            r, c = random.choice(crossed_should_be_black)
            # print("r, c", r, c)
        else:
            # print("not in crossed_should_be_black")
            r, c = random.choice(mismatches)
            # print("r, c", r, c)

    # print("r, c", r, c)

    _increment_hint_count(s)

    if s.get("mode") != "warmup":  # skip for warmup
        append_event(session_id, {
            "type": "hint",
            "r": r,
            "c": c,
            "t": now_iso()
        })
    hints_used = _get_hint_count(s)
    return {
        "solved": False,
        "hint": {"r": r, "c": c},
        "hint_limit": hint_limit,
        "hints_used": hints_used,
        "hints_remaining": max(0, hint_limit - hints_used),
        "limit_reached": False
    }

@app.post("/sessions/{session_id}/advance")
def advance_puzzle(session_id: str):
    """
    Advance to the next puzzle in the three-puzzle flow (for give-up scenarios).
    Only works for bank_three mode.
    """
    s = ensure_session(session_id)
    
    if s.get("mode") != "bank_three":
        raise HTTPException(400, "advance only works for three-puzzle sessions")

    # mark current puzzle as skipped (only if not already solved)
    if not s["solved_flags"][s["idx"]]:
        s["skipped_flags"][s["idx"]] = True
        append_event(session_id,
                     {"type": "skip_puzzle", "idx": s["idx"], "puzzle_id": s["queue"][s["idx"]], "t": now_iso()})

    # Advance to next puzzle (similar to check when solved)
    s["idx"] += 1
    if s["idx"] >= 3:
        # if s["log"].get("end_time") is None:
        #     s["log"]["end_time"] = now_iso()
        # append_event(session_id, {"type": "completed_all_three", "t": s["log"]["end_time"]})
        # return {"completed": True}
        if s["log"].get("end_time") is None:
            s["log"]["end_time"] = now_iso()

        completed_all_three = all(s.get("solved_flags", [False, False, False]))
        if completed_all_three:
            append_event(session_id, {"type": "completed_all_three", "t": s["log"]["end_time"]})
            return {"completed": True}

        append_event(session_id, {
            "type": "ended_without_full_completion",
            "solved_flags": s.get("solved_flags"),
            "skipped_flags": s.get("skipped_flags"),
            "t": s["log"]["end_time"]
        })
        return {"completed": False, "finished": True, "solved_flags": s.get("solved_flags"),
                "skipped_flags": s.get("skipped_flags")}
    
    # Get next puzzle metadata
    next_id = s["queue"][s["idx"]]
    next_pz = POOL6_BY_ID[next_id]
    rows, cols = len(next_pz["solution"]), len(next_pz["solution"][0])
    
    # Reset server board for the next puzzle
    s["board"] = blank_board(rows, cols)
    s["undo_stack"] = []
    s["log"]["puzzle_id"] = f"bank:{next_id}"
    
    append_event(session_id, {
        "type": "puzzle_advanced",
        "from_idx": s["idx"] - 1,
        "to_idx": s["idx"],
        "puzzle_id": next_id,
        "t": now_iso()
    })
    
    return {
        "index": s["idx"],
        "puzzle": {
            "id": next_pz["id"],
            "rows": rows,
            "cols": cols,
            "row_clues": next_pz["clues"]["rows"],
            "col_clues": next_pz["clues"]["columns"],
        },
        "hint_limit": s.get("hint_limit", HINT_LIMIT),
        "hints_remaining": max(0, s.get("hint_limit", HINT_LIMIT) - _get_hint_count(s))
    }

@app.post("/sessions/{session_id}/reset", response_model=Board)
def reset_board(session_id: str):
    s = ensure_session(session_id)

    # Reset board to current size (works for both single and bank_three)
    rows, cols = len(s["board"]), len(s["board"][0])

    diffs = []
    for r in range(rows):
        for c in range(cols):
            prev = s["board"][r][c]
            if prev != 0:
                diffs.append({"r": r, "c": c, "from": prev, "to": 0})

    s["board"] = blank_board(rows, cols)

    _push_undo(s, diffs, label="reset")

    if s.get("mode") == "bank_three":
        hint_counts = s.setdefault("hint_counts", [0, 0, 0])
        idx = s.get("idx", 0)
        if 0 <= idx < len(hint_counts):
            hint_counts[idx] = 0
    else:
        s["hint_count"] = 0

    if s.get("mode") != "warmup":  # skip for warmup
        # Log counters + per-puzzle timestamp (NO pseudo-move)
        s["log"]["resets_count"] = s["log"].get("resets_count", 0) + 1
        if s.get("mode") == "bank_three":
            s["log"]["resets"][s["idx"]].append(now_iso())   # NEW
        else:
            s["log"]["resets"][0].append(now_iso())          # NEW

        # Disk event remains
        append_event(session_id, {"type": "reset", "t": now_iso()})
    return Board(board=s["board"])

@app.post("/sessions/{session_id}/undo", response_model=Board)
def undo(session_id: str):
    s = ensure_session(session_id)
    _ensure_undo(s)

    if not s["undo_stack"]:
        # nothing to undo
        return Board(board=s["board"]), "Nothing to undo."

    group = s["undo_stack"].pop()
    _apply_undo_group(s, group)

    if s.get("mode") != "warmup":
        append_event(session_id, {
            "type": "undo",
            "label": group.get("label"),
            "diffs_len": len(group.get("diffs", [])),
            "t": now_iso()
        })

    return Board(board=s["board"])

@app.get("/sessions/{session_id}/log")
def get_log(session_id: str):
    s = ensure_session(session_id)
    return s["log"]

@app.post("/sessions/{session_id}/end")
def end_session(session_id: str):
    s = ensure_session(session_id)
    if s["log"]["end_time"] is None:
        s["log"]["end_time"] = now_iso()
    # logging (disk)
    append_event(session_id, {"type": "session_end", "t": s["log"]["end_time"]})
    return {"ok": True, "end_time": s["log"]["end_time"]}

# ---- Download endpoints ----

@app.get("/sessions/{session_id}/log/download.yaml")
def download_yaml_snapshot(session_id: str):
    ensure_session(session_id)  # your existing helper
    p = convert_json_to_yaml(session_id)  # generate from JSON snapshot
    return FileResponse(
        path=str(p),
        media_type="application/x-yaml",
        filename=f"{session_id}.yaml",
    )

@app.get("/sessions/{session_id}/log/download.ndjson")
def download_ndjson(session_id: str):
    ensure_session(session_id)
    p = log_file_ndjson(session_id)
    if not p.exists():
        p.touch()
    return FileResponse(
        path=str(p),
        media_type="application/x-ndjson",
        filename=f"{session_id}.ndjson"
    )

@app.get("/sessions/{session_id}/log/download.json")
def download_json_snapshot(session_id: str):
    ensure_session(session_id)
    p = write_snapshot_json(session_id)   # refresh snapshot before serving
    return FileResponse(
        path=str(p),
        media_type="application/json",
        filename=f"{session_id}.json"
    )

@app.get("/sessions/{session_id}/log/download.zip")
def download_zip(session_id: str):
    s = ensure_session(session_id)
    # Ensure latest snapshot
    json_path = write_snapshot_json(session_id)
    ndjson_path = log_file_ndjson(session_id)
    if not ndjson_path.exists():
        ndjson_path.touch()

    meta = {
        "session_id": session_id,
        "puzzle_id": s["puzzle_id"],
        "rows": len(s["board"]),
        "cols": len(s["board"][0]),
        "start_time": s["log"]["start_time"],
        "end_time": s["log"]["end_time"]
    }

    mem_zip = io.BytesIO()
    with zipfile.ZipFile(mem_zip, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(json_path, arcname=f"{session_id}.json")
        zf.write(ndjson_path, arcname=f"{session_id}.ndjson")
        zf.writestr("metadata.json", json.dumps(meta, ensure_ascii=False, indent=2))
    mem_zip.seek(0)

    return StreamingResponse(
        mem_zip,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{session_id}_logs.zip"'}
    )
