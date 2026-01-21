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
        },
        {
            "id": "puzzle_1_guesses",
            "prompt": "How many times did you guess a cell (which means the decision was not based on logical deduction) on Puzzle 1?",
            "type": "single",
            "options": [
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
        },
        {
            "id": "puzzle_2_guesses",
            "prompt": "How many times did you guess a cell (which means the decision was not based on logical deduction) on Puzzle 2?",
            "type": "single",
            "options": [
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
        },
        {
            "id": "puzzle_3_guesses",
            "prompt": "How many times did you guess a cell (which means the decision was not based on logical deduction) on Puzzle 3?",
            "type": "single",
            "options": [
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


# --- Puzzle bank (three-at-a-time sessions) ---
ROOT_DIR = BASE_DIR.parent  # project root
BANK_PATH = ROOT_DIR / "unique_solution_nonograms_50.json"
with BANK_PATH.open("r", encoding="utf-8") as f:
    PUZZLE_BANK = json.load(f)            # list[dict]
BANK_BY_ID = {p["id"]: p for p in PUZZLE_BANK}

# --- Tutorial puzzle bank ---
TUTORIAL_BANK_PATH = ROOT_DIR / "tutorial_nonograms_5x5.json"
with TUTORIAL_BANK_PATH.open("r", encoding="utf-8") as f:
    TUTORIAL_PUZZLE_BANK = json.load(f)

TUTORIAL_BANK_BY_ID = {p["id"]: p for p in TUTORIAL_PUZZLE_BANK}

# --- Warmup puzzle bank (single 2x2 puzzle) ---
WARMUP_BANK_PATH = ROOT_DIR / "warmup_nonogram_2x2.json"
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
        # intentionally no logging
    }

    return {
        "session_id": sid,
        "puzzle": _pack_public_from_bank(p)
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
        "puzzle": _pack_public_from_bank(p)
    }


@app.post("/session/start_three")
def start_three():
    # choose 3 distinct puzzles uniformly at random
    chosen = random.sample(PUZZLE_BANK, k=3)
    queue_ids = [p["id"] for p in chosen]

    # session memory
    sid = uuid.uuid4().hex
    first = chosen[0]
    SESSIONS[sid] = {
        "mode": "bank_three",
        "queue": queue_ids,
        "idx": 0,
        "answers": {p["id"]: p["solution"] for p in chosen},
        "board": blank_board(len(first["solution"]), len(first["solution"][0])),
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
            "surveys": {"pre": None, "puzzle": [None, None, None], "post": None}
        }
    }

    append_event(sid, {"type": "session_start_three", "queue": queue_ids, "t": now_iso()})
    return {
        "session_id": sid,
        "index": 0,
        "puzzle": _pack_public_from_bank(first)  # send only clues+size
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
    s["board"][move.r][move.c] = move.value

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

        # advance to next puzzle (or finish)
        s["idx"] += 1
        if s["idx"] >= 3:
            if s["log"].get("end_time") is None:
                s["log"]["end_time"] = now_iso()
            append_event(session_id, {"type": "completed_all_three", "t": s["log"]["end_time"]})
            return {"solved": True, "completed": True}

        # next puzzle metadata to send to client
        next_id = s["queue"][s["idx"]]
        next_pz = BANK_BY_ID[next_id]
        rows, cols = len(next_pz["solution"]), len(next_pz["solution"][0])

        # reset server board for the next puzzle
        s["board"] = blank_board(rows, cols)
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
            }
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
        append_event(session_id, {
            "type": "hint_none",
            "t": now_iso()
        })
        return {"solved": True, "hint": None}


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

    if s.get("mode") != "warmup":  # skip for warmup
        append_event(session_id, {
            "type": "hint",
            "r": r,
            "c": c,
            "t": now_iso()
        })
    return {"solved": False, "hint": {"r": r, "c": c}}

@app.post("/sessions/{session_id}/advance")
def advance_puzzle(session_id: str):
    """
    Advance to the next puzzle in the three-puzzle flow (for give-up scenarios).
    Only works for bank_three mode.
    """
    s = ensure_session(session_id)
    
    if s.get("mode") != "bank_three":
        raise HTTPException(400, "advance only works for three-puzzle sessions")
    
    # Advance to next puzzle (similar to check when solved)
    s["idx"] += 1
    if s["idx"] >= 3:
        if s["log"].get("end_time") is None:
            s["log"]["end_time"] = now_iso()
        append_event(session_id, {"type": "completed_all_three", "t": s["log"]["end_time"]})
        return {"completed": True}
    
    # Get next puzzle metadata
    next_id = s["queue"][s["idx"]]
    next_pz = BANK_BY_ID[next_id]
    rows, cols = len(next_pz["solution"]), len(next_pz["solution"][0])
    
    # Reset server board for the next puzzle
    s["board"] = blank_board(rows, cols)
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
        }
    }

@app.post("/sessions/{session_id}/reset", response_model=Board)
def reset_board(session_id: str):
    s = ensure_session(session_id)

    # Reset board to current size (works for both single and bank_three)
    rows, cols = len(s["board"]), len(s["board"][0])
    s["board"] = blank_board(rows, cols)

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
