import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";
import Grid from "@/components/Grid";
import Timer from "@/components/Timer";
import ConfirmModal from "@/components/ConfirmModal";
import {
  startTutorialSession,
  makeMove,
  checkBoard,
  resetBoard,
  getHint
} from "@/services/api";

// Hint button appears after 2 minutes (120 seconds)
const HINT_DELAY_SECONDS = 120;

export default function Tutorial() {
  const [sessionId, setSessionId] = useState(null);
  const [board, setBoard] = useState([]);
  const [clues, setClues] = useState({ rows: [], columns: [] });
  const [solved, setSolved] = useState(false);
  const [timerRunning, setTimerRunning] = useState(false);
  const [elapsedTime, setElapsedTime] = useState(0);
  const [solvedPuzzleTime, setSolvedPuzzleTime] = useState(null);
  const [timerKey, setTimerKey] = useState(0);
  const [puzzleStartTimestamp, setPuzzleStartTimestamp] = useState(null);
  const [showHintButton, setShowHintButton] = useState(false);
  const [highlightedCell, setHighlightedCell] = useState(null);

  const [confirmModal, setConfirmModal] = useState({
    isOpen: false,
    message: "",
    onConfirm: null,
    onCancel: null
  });

  const [dragState, setDragState] = useState({
    isDragging: false,
    startRow: null,
    startCol: null,
    endRow: null,
    endCol: null,
    isRightClick: false
  });

  // Track if we actually moved during drag (to distinguish click from drag)
  const dragMovedRef = useRef(false);
  const isProcessingDragRef = useRef(false);

  useEffect(() => {
    async function init() {
      try {
        const session = await startTutorialSession();
        setSessionId(session.session_id);

        const rows = session.puzzle.rows;
        const cols = session.puzzle.cols;
        setBoard(Array(rows).fill(0).map(() => Array(cols).fill(0)));
        setClues({
          rows: session.puzzle.row_clues,
          columns: session.puzzle.col_clues
        });

        setSolved(false);
        setTimerRunning(true);
        setPuzzleStartTimestamp(Date.now());
        setShowHintButton(false);
        setHighlightedCell(null);
        setSolvedPuzzleTime(null);
        setElapsedTime(0);
        setTimerKey(prev => prev + 1);
      } catch (error) {
        console.error("Failed to start tutorial session:", error);
        toast.error("Failed to start tutorial session.");
      }
    }
    init();
  }, []);

  // Check if hint button should be shown
  useEffect(() => {
    if (!puzzleStartTimestamp || timerRunning === false) {
      setShowHintButton(false);
      return;
    }

    const checkHintButton = () => {
      const elapsed = Math.floor((Date.now() - puzzleStartTimestamp) / 1000);
      setShowHintButton(elapsed >= HINT_DELAY_SECONDS);
    };

    checkHintButton();
    const interval = setInterval(checkHintButton, 1000);
    return () => clearInterval(interval);
  }, [puzzleStartTimestamp, timerRunning]);

  const handleDragStart = (r, c, isRightClick) => {
    if (!sessionId || solved) return;

    dragMovedRef.current = false;
    isProcessingDragRef.current = false;
    setDragState({
      isDragging: true,
      startRow: r,
      startCol: c,
      endRow: r,
      endCol: c,
      isRightClick: isRightClick
    });
  };

  const handleDragUpdate = (r, c) => {
    if (!dragState.isDragging) return;

    setDragState(prev => {
      if (r !== prev.startRow || c !== prev.startCol) {
        dragMovedRef.current = true;
      }

      return {
        ...prev,
        endRow: r,
        endCol: c
      };
    });
  };

  const handleDragEnd = async () => {
    if (!dragState.isDragging || !sessionId || solved || isProcessingDragRef.current) return;

    isProcessingDragRef.current = true;

    const { startRow, startCol, endRow, endCol, isRightClick } = dragState;
    const wasDrag = (startRow !== endRow || startCol !== endCol) || dragMovedRef.current;

    setDragState({
      isDragging: false,
      startRow: null,
      startCol: null,
      endRow: null,
      endCol: null,
      isRightClick: false
    });

    if (!wasDrag) {
      dragMovedRef.current = false;
      isProcessingDragRef.current = false;
      return;
    }

    const minRow = Math.min(startRow, endRow);
    const maxRow = Math.max(startRow, endRow);
    const minCol = Math.min(startCol, endCol);
    const maxCol = Math.max(startCol, endCol);

    const cellsToUpdate = [];
    for (let r = minRow; r <= maxRow; r++) {
      for (let c = minCol; c <= maxCol; c++) {
        cellsToUpdate.push({ r, c });
      }
    }

    if (isRightClick) {
      const startValue = board[startRow][startCol];
      const newValue = startValue === -1 ? 0 : -1;

      for (const { r, c } of cellsToUpdate) {
        const res = await makeMove(sessionId, r, c, newValue);
        setBoard(res.board);
      }
    } else {
      const newValue = 1;

      for (const { r, c } of cellsToUpdate) {
        const res = await makeMove(sessionId, r, c, newValue);
        setBoard(res.board);
      }
    }

    dragMovedRef.current = false;
    setTimeout(() => {
      isProcessingDragRef.current = false;
    }, 200);
  };

  const handleCellClick = async (r, c) => {
    if (!sessionId || solved) return;

    if (isProcessingDragRef.current || dragState.isDragging) {
      return;
    }

    if (dragMovedRef.current) {
      dragMovedRef.current = false;
      return;
    }

    if (highlightedCell && highlightedCell.r === r && highlightedCell.c === c) {
      setHighlightedCell(null);
    }

    const current = board[r][c];
    const newValue = current === 1 ? 0 : 1;

    const res = await makeMove(sessionId, r, c, newValue);
    setBoard(res.board);
  };

  const handleCellRightClick = async (r, c) => {
    if (!sessionId || solved) return;

    if (highlightedCell && highlightedCell.r === r && highlightedCell.c === c) {
      setHighlightedCell(null);
    }

    const current = board[r][c];
    const newValue = current === -1 ? 0 : -1;

    const res = await makeMove(sessionId, r, c, newValue);
    setBoard(res.board);
  };

  const handleHint = async () => {
    if (!sessionId) return;

    try {
      const res = await getHint(sessionId);
      if (res.solved) {
        toast.success("Puzzle is already solved!");
      } else if (res.hint) {
        setHighlightedCell({ r: res.hint.r, c: res.hint.c });
        toast("Take another look at the highlighted cell!\n There is a mismatch with the clues.", {
          duration: 6000,
        });
      }
    } catch (error) {
      toast.error("Failed to get hint");
    }
  };

  const handleTimeUpdate = (seconds) => {
    setElapsedTime(seconds);
  };

  const handleCheck = async () => {
    if (!sessionId || solved) return;

    const res = await checkBoard(sessionId);

    if (!res.solved) {
      toast.error("Not correct yet. Try again!");
      return;
    }

    setSolved(true);
    setTimerRunning(false);
    setSolvedPuzzleTime(elapsedTime);
  };

  const handleReset = () => {
    if (!sessionId) return;

    setConfirmModal({
      isOpen: true,
      message: "Are you sure you want to reset this tutorial? All progress will be lost.",
      onConfirm: async () => {
        setConfirmModal({
          isOpen: false,
          message: "",
          onConfirm: null,
          onCancel: null
        });
        const res = await resetBoard(sessionId);
        setBoard(res.board);
        setSolved(false);
        setTimerRunning(true);
        setPuzzleStartTimestamp(Date.now());
        setShowHintButton(false);
        setHighlightedCell(null);
        setSolvedPuzzleTime(null);
        setElapsedTime(0);
        setTimerKey(prev => prev + 1);
        toast.success("Puzzle reset", { duration: 2000 });
      },
      onCancel: () => {
        setConfirmModal({
          isOpen: false,
          message: "",
          onConfirm: null,
          onCancel: null
        });
      }
    });
  };

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  };

  return (
    <main
      style={{
        padding: "2rem",
        maxWidth: 800,
        margin: "0 auto",
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <h1
        style={{
          fontSize: "2rem",
          fontWeight: "bold",
          textAlign: "center",
          marginBottom: "1.5rem",
          color: "#2d3436",
        }}
      >
        Nonogram Tutorial
      </h1>

      <Timer key={`tutorial-${timerKey}`} start={0} running={timerRunning} onTimeUpdate={handleTimeUpdate} />

      <Grid
        grid={board}
        onCellClick={handleCellClick}
        onCellRightClick={handleCellRightClick}
        clues={clues}
        highlightedCell={highlightedCell}
        dragState={dragState}
        onDragStart={handleDragStart}
        onDragUpdate={handleDragUpdate}
        onDragEnd={handleDragEnd}
      />

      <div style={{ marginTop: 30, display: "flex", justifyContent: "space-between", alignItems: "center", width: "100%", maxWidth: 800 }}>
        <div style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
          <button
            onClick={handleReset}
            style={{
              padding: "0.75rem 2rem",
              backgroundColor: "#808080",
              color: "white",
              fontWeight: "bold",
              borderRadius: "8px",
              border: "none",
              cursor: "pointer",
              fontSize: "1rem",
            }}
          >
            Reset
          </button>

          {showHintButton && (
            <button
              onClick={handleHint}
              style={{
                padding: "0.75rem 2rem",
                backgroundColor: "#8E24AA",
                color: "white",
                fontWeight: "bold",
                borderRadius: "8px",
                border: "none",
                cursor: "pointer",
                fontSize: "1rem"
              }}
            >
              Hint
            </button>
          )}
        </div>

        <button
          onClick={handleCheck}
          disabled={solved}
          style={{
            padding: "0.75rem 2rem",
            backgroundColor: solved ? "#ccc" : "#4169E1",
            color: "white",
            fontWeight: "bold",
            borderRadius: "8px",
            border: "none",
            cursor: solved ? "not-allowed" : "pointer",
            fontSize: "1rem"
          }}
        >
          Submit
        </button>
      </div>

      {solved && (
        <div style={{ textAlign: "center", marginTop: "2rem" }}>
          <h2 style={{ fontSize: "1.8rem", marginBottom: "0.75rem", color: "#4169E1" }}>
            Tutorial Solved!
          </h2>
          <p style={{ fontSize: "1.1rem", color: "#666" }}>
            Time used: {formatTime(solvedPuzzleTime)}
          </p>
        </div>
      )}

      <ConfirmModal
        isOpen={confirmModal.isOpen}
        message={confirmModal.message}
        onConfirm={confirmModal.onConfirm || (() => {})}
        onCancel={confirmModal.onCancel || (() => {})}
      />
    </main>
  );
}
