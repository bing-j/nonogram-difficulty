# Nonogram open-text codebook

Grounded, bottom-up coding scheme built by reading every free-text response in `backend/logs`. Multi-label: a response can receive several codes.

## Difficulty themes (applied to `rating_reason` + `comments`)

| Code | Theme | Definition |
|---|---|---|
| `FOOT` | Starting footholds / forced lines | References to the availability (easier) or absence (harder) of lines that can be solved immediately: 'freebies', 'fixed/guaranteed arrangements', full rows, lines that sum to the grid width, or 'where to start'. |
| `CLUE` | Clue magnitude | Difficulty attributed to the size/composition of the clue numbers (large numbers easier; many small numbers / lots of 1s harder). |
| `PROP` | Constraint propagation / chaining | Deductions chain smoothly: one solved line/cell forces the next, working off crossing rows/columns; emphasis on logical flow. |
| `AMBIG` | Combinatorial ambiguity / overlap reasoning | Having to weigh many possible arrangements, consider overlaps of extremes, or cope with uncertainty about where blocks go. |
| `GUESS` | Guessing / certainty | Salient mention of guessing, trial-and-error, or (lack of) a deterministic/logical path forward. |
| `HINT` | Hint usage | References to using, waiting for, or relying on the Hint button. |
| `ERR` | Mistakes / error recovery | Made a mistake, hard to trace back, had to restart, undo, or recover from a wrong deduction. |
| `LEARN` | Learning / practice / fatigue | Order/experience effects within the session: first time, warming up, getting better with practice, learning techniques, or fatigue. |
| `LOAD` | Cognitive load / tracking | Mental bookkeeping burden: keeping track of state, remembering possibilities, holding deductions in the head, feeling overwhelmed. |
| `VIS` | Visual / spatial layout | Spatial layout cues: edges vs middle starts, sparsity/blank space, 1s blending together, grid size, lack of a picture/symmetry. |
| `TIME` | Time pressure | Difficulty/behaviour driven by time limits or social time pressure. |
| `UI` | Interface friction | Comments about the tool/UI: cross-toggle swapping colours, button placement, hint refresh timing, wanting paper annotations. |
| `AFF` | Confidence / affect | Affective / self-efficacy framing: confidence, frustration, nervousness, enjoyment, gut-feeling difficulty judgements. |

## Strategy taxonomy (applied to `strategy`)

| Code | Strategy | Definition |
|---|---|---|
| `S_FORCED` | Forced-line solving | Find and fill fully-determined lines first (lines summing to grid width, '(N-1)+T=10', guaranteed/fixed lines, certain cells). |
| `S_CONSTR` | Most-constrained-first ordering | Heuristic of starting from the most constrained lines: largest sum, largest numbers, or the most numbers in a line. |
| `S_OVERLAP` | Overlap analysis | Compare extreme (leftmost/rightmost) placements and fill the cells common to all arrangements; 'guaranteed in every combination'. |
| `S_EDGE` | Edge / anchor exploitation | Use borders and the start/end of sequences, or extend from cells already filled at an edge. |
| `S_CROSS` | Row/column cross-referencing | After each fill, propagate to the perpendicular rows/columns; iterate row<->column until stuck. |
| `S_NEG` | Negative marking (X-ing whites) | Actively cross out / X cells that must be empty to constrain the remaining space and track the board. |
| `S_TRIAL` | Trial-and-error / contradiction | Make guesses, enumerate possibilities, or assume-and-check for contradictions, then backtrack. |
| `S_HINT` | Hint-as-tool | Deliberate use of the Hint button to verify guesses, debug mistakes, or unstick progress. |
