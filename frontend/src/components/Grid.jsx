import React from "react";
import Cell from "./Cell";

export default function Grid({ grid, onCellClick, clues }) {
  const numRows = grid.length;
  const numCols = grid[0].length;

  return (
    <div style={{ display: "flex", justifyContent: "center", marginTop: "30px" }}>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: `repeat(${numCols + 1}, 40px)`,
          gridTemplateRows: `repeat(${numRows + 1}, 40px)`,
          gap: "4px",
        }}
      >
        {/* Empty top-left corner */}
        <div></div>

        {/* Column clues */}
        {clues.columns.map((col, idx) => (
          <div
            key={`col-${idx}`}
            style={{
              display: "flex",
              flexDirection: "column",
              justifyContent: "end",
              alignItems: "center",
              fontSize: "16px",
              height: "40px",
            }}
          >
            {col.map((clue, i) => (
              <div key={i}>{clue}</div>
            ))}
          </div>
        ))}

        {/* Row clues + grid cells */}
        {grid.map((row, r) => (
          <React.Fragment key={r}>
            {/* Row clue */}
            <div
              style={{
                display: "flex",
                justifyContent: "right",
                alignItems: "center",
                fontSize: "16px",
                paddingRight: "4px",
              }}
            >
              {clues.rows[r].join(" ")}
            </div>

            {/* Cells */}
            {row.map((cell, c) => (
              <Cell
                key={`${r}-${c}`}
                value={cell}
                onClick={() => onCellClick(r, c)}
              />
            ))}
          </React.Fragment>
        ))}
      </div>
    </div>
  );
}