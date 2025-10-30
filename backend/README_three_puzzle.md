# 🧩 Nonogram Backend API

*(Keep all your existing intro/setup text before this — just add the following section below your existing endpoint docs.)*

---

## 🎯 “Three Puzzle Challenge” Flow (Bank Mode)

This mode automatically picks **three random puzzles** from `unique_solution_nonograms.json` when the user starts a session.  
The backend manages puzzle progression and validation; the frontend just renders the clues and interacts via API calls.

---

### 🔁 API Flow Summary

| Step | Action | Endpoint | Who does what |
|:--|:--|:--|:--|
| 1️⃣ | Start a 3-puzzle session | **`POST /session/start_three`** | **Backend** randomly selects 3 puzzles and returns puzzle #1’s clues. |
| 2️⃣ | Render puzzle #1 | Frontend builds grid from the returned clues (no call to `/puzzles`). |
| 3️⃣ | User plays | **Frontend** calls **`/sessions/{id}/move`** as cells change. Backend updates the “current board.” |
| 4️⃣ | Check board | **Frontend** calls **`POST /sessions/{id}/check`**. Backend checks the stored board: <br>• if incorrect → `{ solved: false }` <br>• if solved → advances to next puzzle and returns new clues. |
| 5️⃣ | Render next puzzle | **Frontend** replaces its grid with the new clues returned by `/check`. Backend already reset the board internally. |
| 6️⃣ | Repeat for 3 puzzles | Steps 3–5 repeat for puzzles #2 and #3. |
| 7️⃣ | Finish | After puzzle #3 is solved, `/check` returns `{ "solved": true, "completed": true }`. The session ends. |

---

### 🧠 Key Behavior

- The backend **chooses puzzles and holds their true solutions** — the frontend never sends or receives them.
- Each successful `/check` automatically:
  - Increments the session’s internal index (`idx`).
  - Resets the stored board to a blank grid for the next puzzle.
  - Returns the next puzzle’s **row and column clues**.
- The frontend **must not call** `/puzzles` inside this flow. That endpoint is only for *custom* puzzles.
- Frontend only needs to:
  - Render clues.
  - Send `/move` updates.
  - Call `/check` to validate and fetch the next puzzle.

---

### 💾 Example Frontend Flow (TypeScript)

```ts
const BASE = "http://localhost:8000";

async function startChallenge() {
  const res = await fetch(`${BASE}/session/start_three`, { method: "POST" });
  const { session_id, puzzle } = await res.json();
  showPuzzle(puzzle, session_id);
}

async function makeMove(sessionId, r, c, value) {
  await fetch(`${BASE}/sessions/${sessionId}/move`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ r, c, value }),
  });
}

async function checkPuzzle(sessionId) {
  const res = await fetch(`${BASE}/sessions/${sessionId}/check`, { method: "POST" });
  const data = await res.json();

  if (data.solved && !data.completed) {
    showPuzzle(data.puzzle, sessionId); // next puzzle
  } else if (data.completed) {
    alert("🎉 All three puzzles completed!");
  } else {
    alert("❌ Not solved yet");
  }
}
```

---

### 🧩 Example Response When Advancing

```json
{
  "solved": true,
  "completed": false,
  "index": 1,
  "puzzle": {
    "id": 207,
    "rows": 10,
    "cols": 10,
    "row_clues": [[1],[2],[3],[1,1],...],
    "col_clues": [[2],[1,1],[3],...]
  }
}
```

---

### ✅ Summary for Frontend Devs

- Do **not** call `/puzzles` in this mode.  
- Start with `/session/start_three`.  
- Use `/sessions/{id}/move` for cell toggles.  
- Use `/sessions/{id}/check` to verify & advance.  
- Render the new puzzle’s clues each time `/check` returns a new one.  
- When `completed: true`, show the final screen or log results.