# Tutorial Mode – Frontend Integration Guide

This document explains **only the Tutorial mode**.
The goal of Tutorial mode is to let you use the **same UI and interactions** as normal gameplay, but with **one fixed 5×5 puzzle**, for recording demos or walkthrough videos.

You do **not** need to special-case UI logic beyond how the session is started.

---

## What Tutorial Mode Is

* A single, fixed **5×5 nonogram**
* Loaded from a JSON file on the backend
* Uses the **same board mechanics** as normal puzzles:

  * fill a cell
  * cross a cell
  * reset the board
  * request a hint
  * submit/check the solution

From the frontend’s perspective, Tutorial mode behaves like a normal single-puzzle session.

---

## Start a Tutorial Session

### Endpoint

```
POST /session/start_tutorial
```

### Response

```json
{
  "session_id": "abc123...",
  "puzzle": {
    "id": "tutorial_5x5",
    "rows": 5,
    "cols": 5,
    "row_clues": [...],
    "col_clues": [...]
  }
}
```

### What to do with this response

1. Store `session_id`
2. Render a **5×5 board**
3. Render row and column clues
4. Initialize all cells as empty

No solution data is ever sent to the frontend.

---

## Gameplay Actions (Same as Normal Mode)

All tutorial interactions reuse existing endpoints.

### Make a move (fill / erase / cross)

```
POST /sessions/{session_id}/move
```

**Body**

```json
{
  "r": 2,
  "c": 3,
  "value": 1
}
```

* `value = 1` → filled cell
* `value = 0` → empty
* `value = -1` → crossed (X)

---

### Reset the board

```
POST /sessions/{session_id}/reset
```

Resets the tutorial puzzle back to an empty 5×5 board.

---

### Get a hint

```
GET /sessions/{session_id}/hint
```

**Response**

```json
{
  "solved": false,
  "hint": { "r": 1, "c": 4 }
}
```

* The backend returns **one incorrect cell**
* Highlight it or animate it however you want
* If already solved:

```json
{
  "solved": true,
  "hint": null
}
```

---

### Submit / Check solution

```
POST /sessions/{session_id}/check
```

**Response**

```json
{
  "solved": false,
  "mismatches": [[0,2], [3,1]]
}
```

* `solved = true` → puzzle complete
* `mismatches` gives incorrect cells (can be ignored or highlighted)

This is the endpoint your **Submit** button should call.

---

## Important Notes for Frontend

* Tutorial mode **does not advance to another puzzle**
* There is **no puzzle index**
* There is **no survey flow**
* The UI does **not** need to distinguish tutorial vs normal mode after session start
* Treat it as a **single-puzzle session with size 5×5**

---

## Minimal Frontend Logic Summary

```text
if tutorial:
  POST /session/start_tutorial
else:
  POST /session/start_three

// then always use:
POST /sessions/{id}/move
GET  /sessions/{id}/hint
POST /sessions/{id}/reset
POST /sessions/{id}/check
```

---

If anything feels unclear or the UI needs extra metadata (e.g. “Tutorial” label), tell the backend teammate — no API changes should be needed.
