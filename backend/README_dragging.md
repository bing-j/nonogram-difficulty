# Dragging Feature – Frontend Integration

This document explains how the **dragging interaction** should work between the frontend and backend.

---

# Endpoint

```
POST /sessions/{session_id}/drag
```

This endpoint applies an action to **all cells inside a rectangular region**.

---

# Request Body

```json
{
  "start": { "r": 0, "c": 0 },
  "end": { "r": 1, "c": 2 },
  "mode": "flip"
}
```

### Fields

| field   | type    | description                        |
| ------- | ------- | ---------------------------------- |
| `start` | `{r,c}` | starting cell where the drag began |
| `end`   | `{r,c}` | cell where the drag ended          |
| `mode`  | string  | `"flip"` or `"cross"`              |

Coordinates are **0-indexed**.

---

# Rectangle Behavior

The rectangle is **inclusive**.

Example request:

```
start: (0,0)
end: (1,2)
```

Cells affected:

```
(0,0) (0,1) (0,2)
(1,0) (1,1) (1,2)
```

Dragging direction does **not matter**.
The backend normalizes the rectangle automatically.

---

# Modes

## flip (left mouse drag)

Cell transitions:

```
0  -> 1
-1 -> 1
1  -> 0
```

---

## cross (right mouse drag)

Cell transitions:

```
any -> -1
```

---

# Response

The endpoint returns the updated board:

```json
{
  "board": [...]
}
```

Frontend should **replace the current board state with this response**.

---

# Drag Interaction Rules

### Left Mouse Drag

```
mode = "flip"
```

### Right Mouse Drag

```
mode = "cross"
```

Disable the browser context menu so right-drag works:

```javascript
document.addEventListener("contextmenu", e => e.preventDefault());
```

---

# Recommended Interaction Flow

```
mouse down  → record start cell
mouse move  → optional drag preview
mouse up    → send drag request
```

Example request:

```javascript
fetch(`/sessions/${session_id}/drag`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    start: { r: startRow, c: startCol },
    end: { r: endRow, c: endCol },
    mode: dragMode
  })
})
```

After receiving the response, **re-render the board using the returned state**.

---

# Important Notes

* The backend treats the entire drag as **one action** (important for undo).
* Only cells that actually change will be recorded internally.
* Always trust the **server response** as the source of truth.
