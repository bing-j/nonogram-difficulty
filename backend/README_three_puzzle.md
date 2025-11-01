# 🧩 Nonogram Backend API — Three-Puzzle Challenge

This backend powers a 3-puzzle Nonogram challenge with integrated pre-, per-puzzle, and post-session surveys.  
It manages random puzzle selection, board state, validation, and logging.

---

## ⚙️ Setup

1. Install dependencies  
   ```bash
   pip install fastapi uvicorn pyyaml
   ```

2. Run the backend  
   ```bash
   uvicorn main:app --reload
   ```

3. Open the interactive UI:  
   [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 🧭 Three-Puzzle Flow

| Step | Action | Endpoint | Who Does What |
|:--|:--|:--|:--|
| 1️⃣ | Start a new 3-puzzle session | `POST /session/start_three` | Backend randomly selects 3 puzzles and returns puzzle #1 clues. |
| 2️⃣ | Render puzzle | Frontend builds the grid using returned clues. |
| 3️⃣ | Play moves | `POST /sessions/{id}/move` | Frontend sends cell updates; backend updates the stored board. |
| 4️⃣ | Check puzzle | `POST /sessions/{id}/check` | Backend validates the board. If solved, advances to next puzzle and returns new clues. |
| 5️⃣ | Repeat for 3 puzzles | The backend automatically progresses puzzles until completion. |
| 6️⃣ | End | After puzzle #3 is solved, backend returns `{ completed: true }`. |

---

## 🧩 Endpoints

### `POST /session/start_three`
Start a new session.  
Backend selects three random puzzles from `unique_solution_nonograms.json`.

**Response**
```json
{
  "session_id": "abc123",
  "index": 0,
  "puzzle": {
    "id": 42,
    "rows": 10,
    "cols": 10,
    "row_clues": [[3],[1,1],...],
    "col_clues": [[2],[3],...]
  }
}
```

---

### `POST /sessions/{session_id}/move`
Update the current board when the player marks or clears a cell.

**Body**
```json
{ "r": 2, "c": 4, "value": 1 }
```

**Notes**
- Values are integers (e.g., 1 = filled, 0 = empty).
- Each move is logged with a timestamp.

---

### `POST /sessions/{session_id}/check`
Checks whether the stored board matches the current puzzle’s true solution.

**Responses**
```json
{ "solved": false }  // board incorrect
```
```json
{
  "solved": true,
  "completed": false,
  "index": 1,
  "puzzle": { ...next puzzle clues... }
}
```
```json
{ "solved": true, "completed": true }  // all three solved
```

---

### `POST /sessions/{session_id}/reset`
Clears the current puzzle board to blank (does *not* affect others).  
Also logged with a timestamp.

---

## 🧾 Surveys

The backend defines a `SURVEY_SPEC` with five survey blocks:
- `"pre"`
- `"puzzle_1"`, `"puzzle_2"`, `"puzzle_3"`
- `"post"`

Frontend calls two endpoints to interact with these surveys.

---

### `GET /sessions/{session_id}/survey`
Fetch questions for a survey section.

**Query parameters**
```
?survey_type=pre | puzzle_1 | puzzle_2 | puzzle_3 | post
```

**Response**
```json
{
  "survey_type": "pre",
  "questions": [
    { "id": "played_before", "prompt": "Have you played Nonogram before?", "type": "single", "options": [...] },
    { "id": "skill_nonogram", "prompt": "...", "type": "scale", "min": 1, "max": 10 }
  ]
}
```

---

### `POST /sessions/{session_id}/survey_submit`
Submit survey answers.

**Body**
```json
{
  "survey_type": "puzzle_1",
  "answers": {
    "difficulty": 4
  }
}
```

**Response**
```json
{
  "ok": true,
  "saved": {
    "t": "2025-11-01T15:45:00Z",
    "survey_type": "puzzle_1",
    "answers": { "difficulty": 4 },
    "puzzle_idx": 0
  }
}
```

**Behavior**
- For `"puzzle_1"`, `"puzzle_2"`, `"puzzle_3"`, responses are saved to `log.surveys.puzzle[i]`.
- For `"pre"` and `"post"`, responses go to `log.surveys.pre` and `log.surveys.post`.
- Each submission also emits a `survey_submit` event to the log.

---

## 🗂 Logging

Each session is stored in `/logs/<session_id>.ndjson`.

### Logged fields include:
| Key | Description |
|:--|:--|
| `type` | Event type (`move`, `check`, `survey_submit`, etc.) |
| `t` | ISO timestamp |
| `r`, `c`, `value` | For move events |
| `survey_type` | For survey events |
| `answers` | Flattened JSON of the answers |
| `puzzle_idx` | For per-puzzle surveys |

The in-memory structure (`SESSIONS[sid]["log"]`) mirrors this with:
```python
"log": {
  "moves": [],
  "checks": [[], [], []],
  "resets": [[], [], []],
  "surveys": {"pre": None, "puzzle": [None, None, None], "post": None}
}
```

---

## ✅ Frontend Responsibilities

- Begin session → `POST /session/start_three`
- Render puzzles using returned clues
- Send cell updates → `POST /sessions/{id}/move`
- Validate → `POST /sessions/{id}/check`
- Handle surveys between puzzles:
  - Fetch → `GET /sessions/{id}/survey?survey_type=...`
  - Submit → `POST /sessions/{id}/survey_submit`
- Stop when `completed: true`

---

## 🧠 Summary

The backend now supports:
- Automatic random puzzle selection and progression.
- Structured, timestamped event logging.
- Integrated survey collection (pre, per-puzzle, post).
- Ready-to-use API for frontend orchestration.
