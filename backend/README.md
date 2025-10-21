# 🧩 Nonogram Backend API

This backend provides a REST API for the Nonogram puzzle website.  
It allows the frontend to create puzzles, track board state, handle user moves, check solutions, **and record gameplay logs** for analysis.

---

## ⚙️ Setup

### 1️⃣ Create a virtual environment (recommended)
```bash
python -m venv .venv
source .venv/bin/activate   # macOS/Linux
# or
.venv\Scripts\activate      # Windows
```

### 2️⃣ Install dependencies
```bash
pip install -r backend/requirements.txt
```

### 3️⃣ Run the backend server
```bash
uvicorn backend.main:app --reload --port 8000
```

The API will be available at:  
👉 [http://localhost:8000](http://localhost:8000)

Interactive documentation at:  
👉 [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 🧠 Overview

The backend is built with **FastAPI** and uses the Python Nonogram solver defined in `nonogram_pysat.py`.  
Each user session is stored in memory while the backend runs and is automatically **logged to disk** under `backend/logs/`.

These logs include:
- Puzzle metadata (`puzzle_id`, `start_time`, `end_time`)
- All moves made by the user
- Number of times the board was checked
- Number of resets
- Timestamps for every event

When you deploy, the logs will automatically be stored **on the remote server's disk**, and you can download them via API endpoints.

---

## 📡 Endpoints

| Method | Endpoint | Description |
|:-------|:----------|:-------------|
| **POST** | `/puzzles` | Create a new puzzle session. Takes `row_clues` and `col_clues`, solves the puzzle, and returns a `session_id`. |
| **GET** | `/sessions/{session_id}/state` | Get the user's current board (2D array of 0/1/-1). |
| **POST** | `/sessions/{session_id}/move` | Update one cell. Send `{ "r": row, "c": col, "value": 1/0/-1 }`. |
| **POST** | `/sessions/{session_id}/check` | Check if the current board matches the solution. Returns `{ solved: true/false, mismatches: [...] }`. |
| **POST** | `/sessions/{session_id}/reset` | Reset the current board and increment reset count. |
| **POST** | `/sessions/{session_id}/end` | Mark session end and log final timestamp. |
| **GET** | `/sessions/{session_id}/log` | Return the in-memory log object for the session. |
| **GET** | `/sessions/{session_id}/log/download.ndjson` | Download the NDJSON event log. |
| **GET** | `/sessions/{session_id}/log/download.json` | Download the full JSON log snapshot. |
| **GET** | `/sessions/{session_id}/log/download.zip` | Download a ZIP bundle containing NDJSON, JSON, and metadata. |

---

## 🧾 Example Usage

### Create a new puzzle
**Request**
```bash
POST /puzzles
{
  "row_clues": [[2], []],
  "col_clues": [[1], [1]]
}
```

**Response**
```json
{
  "puzzle": {
    "id": "a83f8a9b",
    "rows": 2,
    "cols": 2,
    "row_clues": [[2], []],
    "col_clues": [[1], [1]]
  },
  "session_id": "f13d4be1aa"
}
```

---

### Make a move
**Request**
```bash
POST /sessions/f13d4be1aa/move
{
  "r": 0,
  "c": 1,
  "value": 1
}
```

**Response**
```json
{ "board": [[0,1],[0,0]] }
```

---

### Check if solved
**Request**
```bash
POST /sessions/f13d4be1aa/check
```

**Response**
```json
{ "solved": false, "mismatches": [[0,0]] }
```

---

### View logs
**Request**
```bash
GET /sessions/f13d4be1aa/log
```

**Response**
```json
{
  "puzzle_id": "a83f8a9b",
  "start_time": "2025-10-18T23:14:00.102Z",
  "end_time": null,
  "moves": [
    {"r":0,"c":1,"value":1,"t":"2025-10-18T23:14:05Z"}
  ],
  "checks_count": 1,
  "resets_count": 0
}
```

---

### Download logs
You can download the logs stored on disk using these endpoints:

| Type | URL | Format |
|:------|:----|:--------|
| NDJSON event stream | `/sessions/{session_id}/log/download.ndjson` | `.ndjson` |
| Full JSON snapshot | `/sessions/{session_id}/log/download.json` | `.json` |
| ZIP bundle | `/sessions/{session_id}/log/download.zip` | `.zip` |

All logs are saved under:
```
backend/logs/<SESSION_ID>.ndjson
backend/logs/<SESSION_ID>.json
```
These files exist both locally (during development) and on your deployed backend server.

---

## 🧱 Data Format

| Value | Meaning |
|:------|:--------|
| `1` | Filled cell (black) |
| `0` | Empty cell (white) |
| `-1` | Crossed-out cell (optional visual mark) |

---

## 🧑‍💻 Example Frontend Usage (JavaScript / TypeScript)

```js
const BASE_URL = "http://localhost:8000";

// Create puzzle
export async function createPuzzle(rowClues, colClues) {
  const res = await fetch(`${BASE_URL}/puzzles`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ row_clues: rowClues, col_clues: colClues })
  });
  return await res.json();
}

// Update one cell
export async function makeMove(sessionId, r, c, value) {
  const res = await fetch(`${BASE_URL}/sessions/${sessionId}/move`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ r, c, value })
  });
  return await res.json();
}

// Check board
export async function checkBoard(sessionId) {
  const res = await fetch(`${BASE_URL}/sessions/${sessionId}/check`, {
    method: "POST"
  });
  return await res.json();
}

// Download logs
export async function downloadLogs(sessionId) {
  const res = await fetch(`${BASE_URL}/sessions/${sessionId}/log/download.zip`);
  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${sessionId}_logs.zip`;
  a.click();
}
```

---

## 🔒 CORS Configuration

CORS is enabled for all origins during development:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

This allows the frontend (e.g. running on `http://localhost:3000`) to access the API freely.

---

## 🧰 Notes for Frontend Developers

- Call **`/puzzles`** once when the user starts a new puzzle.  
- Store the returned **`session_id`** locally.  
- Each time the user toggles a cell, call **`/move`**.  
- When the user clicks **Check**, call **`/check`**.  
- When the user resets the puzzle, call **`/reset`**.  
- When the user finishes, call **`/end`** (sets `end_time`).  
- Logs are written automatically to `backend/logs/` (on local or server).  
- You can download them from `/sessions/{id}/log/download.zip`.

---

## 🚀 Deployment Notes

When deploying:
- Use `uvicorn` or `gunicorn` to run the FastAPI app on a server (Render, Railway, AWS, etc.).
- Logs are written automatically to the **remote server’s disk** under `/app/backend/logs/` (or equivalent).
- You can download logs using the `/download` endpoints.
- Add `backend/logs/` to `.gitignore` so logs aren’t committed to GitHub.
- Change CORS to your production frontend domain.

---

### ✅ Summary

- Backend: FastAPI (`backend/main.py`)  
- Solver: Python-SAT (`backend/nonogram_pysat.py`)  
- Logs: NDJSON + JSON written to `backend/logs/`  
- Download via `/sessions/{id}/log/download.*`  
- Run locally at [http://localhost:8000](http://localhost:8000)

---

Made with ❤️ by the Nonogram Difficulty team.
