import React, { useState } from "react";
import Grid from "@/components/Grid";
import Controls from "@/components/Controls";
import Timer from "@/components/Timer";
import nonograms from "@/data/nonograms.json";

export default function App() {
  const puzzle = nonograms.find((p) => p.name === "Boat");

  const numRows = puzzle.clues.rows.length;
  const numCols = puzzle.clues.columns.length;

  const [grid, setGrid] = useState(
    Array.from({ length: numRows }, () => Array(numCols).fill(0))
  );

  const cycleCell = (r, c) => {
    setGrid((prev) =>
      prev.map((row, i) =>
        row.map((cell, j) =>
          i === r && j === c ? (cell + 1) % 3 : cell
        )
      )
    );
  };

  const resetGrid = () => {
    setGrid(Array.from({ length: numRows }, () => Array(numCols).fill(0)));
  };

  return (
    <div className="App">
      <h1 className="text-5xl font-bold text-center mt-8 mb-4">
        Nonogram Puzzle
      </h1>
      <Timer />
      <Grid grid={grid} onCellClick={cycleCell} clues={puzzle.clues} />
      <Controls onReset={resetGrid} onSubmit={() => null} grid={grid} />
    </div>
  );
}
