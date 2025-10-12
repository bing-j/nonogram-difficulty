import React, { useState } from "react";
import { useRouter } from "next/router";
import Grid from "@/components/Grid";
import Controls from "@/components/Controls";
import Timer from "@/components/Timer";
import nonograms from "@/data/nonograms.json";

export default function PuzzlePage() {
  const router = useRouter();
  const { id } = router.query;

  const puzzle = nonograms.find(
    (p) => String(p.id) === id
  );

  if (!puzzle) return <p className="text-center mt-10">Puzzle not found.</p>;

  const numRows = puzzle.clues.rows.length;
  const numCols = puzzle.clues.columns.length;

  const [grid, setGrid] = useState(
    Array.from({ length: numRows }, () => Array(numCols).fill(0))
  );

  const cycleCell = (r, c) => {
    setGrid((prev) =>
      prev.map((row, i) =>
        row.map((cell, j) => (i === r && j === c ? (cell + 1) % 3 : cell))
      )
    );
  };

  const resetGrid = () => {
    setGrid(Array.from({ length: numRows }, () => Array(numCols).fill(0)));
  };

  return (
    <div className="App">
      <h1 className="text-5xl font-bold text-center mt-8 mb-4">
        Puzzle {puzzle.id}
      </h1>
      <Timer />
      <Grid grid={grid} onCellClick={cycleCell} clues={puzzle.clues} />
      <Controls onReset={resetGrid} onSubmit={() => null} grid={grid} />
    </div>
  );
}
