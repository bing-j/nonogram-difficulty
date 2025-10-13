from typing import List, Dict, Tuple
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uuid

from .solver_adapter import solve_nonogram, UnsolvableError

app = FastAPI(title="Nonogram API")

# Allow frontend to talk to backend (during development)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    mismatches: List[Tuple[int,int]] = []

# --- In-memory stores ---
PUZZLES: Dict[str, PuzzleInfo] = {}
SOLUTIONS: Dict[str, List[List[int]]] = {}
SESSIONS: Dict[str, Dict] = {}

# --- Helpers ---
def blank_board(rows: int, cols: int):
    return [[0 for _ in range(cols)] for _ in range(rows)]

def check_board(board, solution):
    mismatches = []
    for r in range(len(board)):
        for c in range(len(board[0])):
            val = 1 if board[r][c] == 1 else 0
            if val != solution[r][c]:
                mismatches.append((r, c))
    return mismatches

# --- Routes ---

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
    SESSIONS[session_id] = {"puzzle_id": puzzle_id, "board": blank_board(len(payload.row_clues), len(payload.col_clues))}

    return {"puzzle": PUZZLES[puzzle_id].model_dump(), "session_id": session_id}

@app.get("/sessions/{session_id}/state", response_model=Board)
def get_state(session_id: str):
    s = SESSIONS.get(session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    return Board(board=s["board"])

@app.post("/sessions/{session_id}/move", response_model=Board)
def move(session_id: str, move: Move):
    s = SESSIONS.get(session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    if not (0 <= move.r < len(s["board"]) and 0 <= move.c < len(s["board"][0])):
        raise HTTPException(400, "Invalid coordinates")
    if move.value not in (-1, 0, 1):
        raise HTTPException(400, "Invalid value")
    s["board"][move.r][move.c] = move.value
    return Board(board=s["board"])

@app.post("/sessions/{session_id}/check", response_model=CheckResult)
def check(session_id: str):
    s = SESSIONS.get(session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    sol = SOLUTIONS[s["puzzle_id"]]
    mismatches = check_board(s["board"], sol)
    return CheckResult(solved=(len(mismatches) == 0), mismatches=mismatches)
