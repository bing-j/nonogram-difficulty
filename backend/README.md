# Nonogram Backend API

This backend provides a REST API for the Nonogram puzzle website.  
It allows the frontend to create puzzles, track board state, handle user moves, and check solutions.

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

The backend is written in **FastAPI** and uses the Python Nonogram solver in `nonogram_pysat.py`.  
Puzzle sessions are stored in memory — restarting the server will clear all sessions.

---

## 📡 Endpoints

| Method | Endpoint | Description |
|:-------|:----------|:-------------|
| **POST** | `/puzzles` | Create a new puzzle session. Takes `row_clues` and `col_clues`, solves the puzzle, and returns a session ID. |
| **GET** | `/sessions/{session_id}/state` | Get the user's current board (2D array of 0/1/-1). |
| **POST** | `/sessions/{session_id}/move` | Update one cell. Send `{ "r": row, "c": col, "value": 1/0/-1 }`. |
| **POST** | `/sessions/{session_id}/check` | Check whether the board matches the solution. Returns `{ solved: true/false, mismatches: [...] }`. |

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
    "row_clues": [[2],[]],
    "col_clues": [[1],[1]]
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
- Each time the user toggles a cell, call **`/move`** and re-fetch **`/state`** to refresh the grid.  
- When the user clicks **Check**, call **`/check`** and display the result.  
- The Swagger UI (`/docs`) provides an interactive way to test all endpoints.

---

## 🚀 (Optional) Deployment Notes

When deploying:
- Use `uvicorn` or `gunicorn` to run the FastAPI app on a server (e.g. Render, Railway, or AWS EC2).
- Change `allow_origins` to your frontend’s domain (e.g. `https://yourfrontend.com`).
- If storing many sessions, consider saving puzzles and boards in a database or Redis instead of memory.

---

### ✅ Summary

- Backend: FastAPI (`backend/main.py`)  
- Solver: Python-SAT (`backend/nonogram_pysat.py`)  
- Frontend calls API via JSON (no direct imports)  
- Run locally at [http://localhost:8000](http://localhost:8000)

---
