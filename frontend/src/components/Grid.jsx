import React, { useState } from "react";
import Cell from "./Cell";

export default function Grid({ grid, onCellClick, clues }) {
  const [hovered, setHovered] = useState({ row: null, col: null });
  const numRows = grid.length;
  const numCols = grid[0].length;

  const handleMouseEnter = (r, c) => setHovered({ row: r, col: c });
  const handleMouseLeave = () => setHovered({ row: null, col: null });

  return (
    <div style={{ display: "flex", justifyContent: "center", marginTop: 30 }}>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
        
        {/* column clues */}
        <div style={{ display: "flex", marginLeft: 40 }}>
          {clues.columns.map((col, c) => {
            const isHighlighted = hovered.col === c;
            return (
              <div
                key={`col-${c}`}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "flex-end",
                  alignItems: "center",
                  minWidth: 40,
                  padding: 4,
                  backgroundColor: isHighlighted
                    ? "rgba(155, 89, 182, 0.15)"
                    : "transparent",
                  borderRadius: 6,
                  transition: "background-color 0.2s ease",
                }}
              >
                {col.map((num, i) => (
                  <div
                    key={i}
                    style={{
                      color: isHighlighted ? "#6C5CE7" : "black",
                      fontWeight: isHighlighted ? 600 : 400,
                      lineHeight: "1.2em",
                    }}
                  >
                    {num}
                  </div>
                ))}
              </div>
            );
          })}
        </div>

        {/* row clues + grid */}
        <div style={{ display: "flex" }}>
          
          {/* row clues */}
          <div style={{ display: "flex", flexDirection: "column" }}>
            {clues.rows.map((rowClue, r) => {
              const isHighlighted = hovered.row === r;
              return (
                <div
                  key={`row-${r}`}
                  style={{
                    display: "flex",
                    justifyContent: "flex-end",
                    alignItems: "center",
                    minHeight: 40,
                    paddingRight: 6,
                    paddingLeft: 4,
                    backgroundColor: isHighlighted
                      ? "rgba(155, 89, 182, 0.15)"
                      : "transparent",
                    borderRadius: 6,
                    transition: "background-color 0.2s ease",
                  }}
                >
                  {rowClue.map((num, i) => (
                    <span
                      key={i}
                      style={{
                        marginLeft: 4,
                        color: isHighlighted ? "#6C5CE7" : "black",
                        fontWeight: isHighlighted ? 600 : 400,
                      }}
                    >
                      {num}
                    </span>
                  ))}
                </div>
              );
            })}
          </div>

          {/* grid cells */}
          
          <div
            style={{
              display: "grid",
              gridTemplateColumns: `repeat(${numCols}, 40px)`,
              gridTemplateRows: `repeat(${numRows}, 40px)`,
            }}
          >
            {grid.map((row, r) =>
              row.map((cell, c) => {
                const isRightBorder = (c + 1) % 5 === 0 && c !== numCols - 1; 
                const isBottomBorder = (r + 1) % 5 === 0 && r !== numRows - 1;

                return (
                  <div
                    key={`${r}-${c}`}
                    onMouseEnter={() => handleMouseEnter(r, c)}
                    onMouseLeave={handleMouseLeave}
                  >
                    <Cell value={cell} onClick={() => onCellClick(r, c)} rightBorder={isRightBorder} bottomBorder={isBottomBorder} />
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
