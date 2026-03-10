import React, { useState, useEffect, useRef } from "react";
import Cell from "./Cell";

export default function Grid({
  grid,
  onCellClick,
  onCellRightClick,
  clues,
  highlightedCell,
  dragState,
  onDragStart,
  onDragUpdate,
  onDragEnd,
}) {

  const [hovered, setHovered] = useState({ row: null, col: null });
  const gridRef = useRef(null);

  const mouseMovedRef = useRef(false);
  const dragStartPosRef = useRef({ r: null, c: null });

  useEffect(() => {
    const handleMouseUp = () => {
      if (dragState.isDragging) {
        const wasDrag = mouseMovedRef.current;
        onDragEnd();

        if (wasDrag) {
          setTimeout(() => {
            mouseMovedRef.current = false;
          }, 150);
        } else {
          mouseMovedRef.current = false;
        }
      }
    };

    const handleGridMouseLeave = () => {
      if (dragState.isDragging) {
        const wasDrag = mouseMovedRef.current;
        onDragEnd();

        if (wasDrag) {
          setTimeout(() => {
            mouseMovedRef.current = false;
          }, 150);
        } else {
          mouseMovedRef.current = false;
        }
      }
    };

    const preventContextMenu = (e) => e.preventDefault();

    if (dragState.isDragging) {
      window.addEventListener("mouseup", handleMouseUp);
      window.addEventListener("contextmenu", preventContextMenu);
      if (gridRef.current) {
        gridRef.current.addEventListener("mouseleave", handleGridMouseLeave);
      }
    }

    return () => {
      window.removeEventListener("mouseup", handleMouseUp);
      window.removeEventListener("contextmenu", preventContextMenu);
      if (gridRef.current) {
        gridRef.current.removeEventListener("mouseleave", handleGridMouseLeave);
      }
    };
  }, [dragState.isDragging, onDragEnd]);

  if (!grid || grid.length === 0 || !Array.isArray(grid[0])) {
    return <p>Loading grid...</p>;
  }

  const numRows = grid.length;
  const numCols = grid[0].length;

  const handleMouseEnter = (r, c) => {
    setHovered({ row: r, col: c });
    if (dragState.isDragging) {
      if (dragStartPosRef.current.r !== r || dragStartPosRef.current.c !== c) {
        mouseMovedRef.current = true;
      }
      onDragUpdate(r, c);
    }
  };

  const handleCellMouseLeave = () => setHovered({ row: null, col: null });

  const isCellInSelection = (r, c) => {
    if (!dragState.isDragging) return false;
    const { startRow, startCol, endRow, endCol } = dragState;
    const minRow = Math.min(startRow, endRow);
    const maxRow = Math.max(startRow, endRow);
    const minCol = Math.min(startCol, endCol);
    const maxCol = Math.max(startCol, endCol);
    return r >= minRow && r <= maxRow && c >= minCol && c <= maxCol;
  };

  const handleCellMouseDown = (e, r, c) => {
    mouseMovedRef.current = false;
    dragStartPosRef.current = { r, c };

    if (e.button === 0) {
      onDragStart(r, c, false);
    } else if (e.button === 2) {
      e.preventDefault();
      onDragStart(r, c, true);
    }
  };

  const maxRowClues = Math.max(...clues.rows.map((r) => r.length));
  const rowCluesWidth = maxRowClues * 16 + 2;

  return (
    <div style={{ display: "flex", justifyContent: "center", marginTop: 30 }}>
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          transform: `translateX(-${rowCluesWidth / 2}px)`,
        }}
      >
        {/* column clues */}
        <div style={{ display: "flex", marginLeft: rowCluesWidth, alignItems: "flex-end" }}>
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
                  backgroundColor: isHighlighted ? "rgba(128, 128, 128, 0.2)" : "transparent",
                  borderRadius: 6,
                  transition: "background-color 0.2s ease",
                }}
              >
                {col.map((num, i) => (
                  <div
                    key={i}
                    style={{
                      color: isHighlighted ? "#666" : "black",
                      fontWeight: 500,
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
                    backgroundColor: isHighlighted ? "rgba(128, 128, 128, 0.2)" : "transparent",
                    borderRadius: 6,
                    transition: "background-color 0.2s ease",
                  }}
                >
                  {rowClue.map((num, i) => (
                    <span
                      key={i}
                      style={{
                        marginLeft: 4,
                        color: isHighlighted ? "#666" : "black",
                        fontWeight: 500,
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
            ref={gridRef}
            style={{
              display: "grid",
              gridTemplateColumns: `repeat(${numCols}, 40px)`,
              gridTemplateRows: `repeat(${numRows}, 40px)`,
            }}
            onContextMenu={(e) => e.preventDefault()}
          >
            {grid.map((row, r) =>
              row.map((cell, c) => {
                const isRightBorder = (c + 1) % 5 === 0 && c !== numCols - 1;
                const isBottomBorder = (r + 1) % 5 === 0 && r !== numRows - 1;
                const isInSelection = isCellInSelection(r, c);

                return (
                  <div
                    key={`${r}-${c}`}
                    onMouseEnter={() => handleMouseEnter(r, c)}
                    onMouseLeave={handleCellMouseLeave}
                    onMouseDown={(e) => handleCellMouseDown(e, r, c)}
                  >
                    <Cell
                      value={cell}
                      onClick={() => {
                        if (!mouseMovedRef.current && !dragState.isDragging) onCellClick(r, c);
                      }}
                      onRightClick={() => {
                        if (!mouseMovedRef.current && !dragState.isDragging && onCellRightClick) {
                          onCellRightClick(r, c);
                        }
                      }}
                      rightBorder={isRightBorder}
                      bottomBorder={isBottomBorder}
                      isHighlighted={highlightedCell && highlightedCell.r === r && highlightedCell.c === c}
                      isInSelection={isInSelection}
                      isDragging={dragState.isDragging}
                    />
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
