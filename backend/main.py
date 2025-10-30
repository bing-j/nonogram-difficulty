from typing import List, Dict, Tuple
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from datetime import datetime, timezone
from pathlib import Path
import uuid
import json, io, zipfile

from backend.solver_adapter import solve_nonogram, UnsolvableError

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

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def log_file_ndjson(session_id: str) -> Path:
    return LOG_DIR / f"{session_id}.ndjson"

def log_file_json(session_id: str) -> Path:
    return LOG_DIR / f"{session_id}.json"

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
            "moves": [],          # list of {r,c,value,t}
            "checks_count": 0,
            "resets_count": 0
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

@app.post("/sessions/{session_id}/check", response_model=CheckResult)
def check(session_id: str):
    s = ensure_session(session_id)
    sol = SOLUTIONS[s["puzzle_id"]]
    mismatches = check_board(s["board"], sol)

    # logging (memory)
    s["log"]["checks_count"] += 1
    solved = (len(mismatches) == 0)
    if solved and s["log"]["end_time"] is None:
        s["log"]["end_time"] = now_iso()

    # logging (disk)
    append_event(session_id, {
        "type": "check",
        "solved": solved,
        "mismatches": mismatches,
        "t": now_iso()
    })

    return CheckResult(solved=solved, mismatches=mismatches)

@app.post("/sessions/{session_id}/reset", response_model=Board)
def reset_board(session_id: str):
    s = ensure_session(session_id)
    p = PUZZLES[s["puzzle_id"]]
    s["board"] = blank_board(p.rows, p.cols)

    # logging (memory)
    s["log"]["resets_count"] += 1
    s["log"]["moves"].append({"r": None, "c": None, "value": "RESET", "t": now_iso()})
    # logging (disk)
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
