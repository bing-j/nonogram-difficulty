import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";
import Grid from "@/components/Grid";
import Timer from "@/components/Timer";
import ConfirmModal from "@/components/ConfirmModal";
import usePreventAccidentalExit from "@/hooks/usePreventAccidentalExit";
import {
  startTutorialSession,
  startThreePuzzleSession,
  makeMove,
  dragMove,
  checkBoard,
  resetBoard,
  getHint,
  undoBoard
} from "@/services/api";

const DEFAULT_HINT_LIMIT = 5;
const getHintAllowance = (elapsedSeconds) => {
  if (elapsedSeconds <= 0) return 0;
  if (elapsedSeconds < 240) return Math.floor(elapsedSeconds / 120);
  if (elapsedSeconds < 480) return 2 + Math.floor((elapsedSeconds - 240) / 60);
  return 6 + Math.floor((elapsedSeconds - 480) / 30);
};

export default function Tutorial() {
  const [sessionId, setSessionId] = useState(null);
  const [board, setBoard] = useState([]);
  const [clues, setClues] = useState({ rows: [], columns: [] });
  const [solved, setSolved] = useState(false);
  const [timerRunning, setTimerRunning] = useState(false);
  const [elapsedTime, setElapsedTime] = useState(0);
  const [solvedPuzzleTime, setSolvedPuzzleTime] = useState(null);
  const [timerKey, setTimerKey] = useState(0);
  const [showHintButton, setShowHintButton] = useState(false);
  const [highlightedCell, setHighlightedCell] = useState(null);
  const [hintsRemaining, setHintsRemaining] = useState(DEFAULT_HINT_LIMIT);
  const [hintsUsed, setHintsUsed] = useState(0);

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
  const { allowNextNavigation } = usePreventAccidentalExit(Boolean(sessionId) && timerRunning);

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
        setHintsRemaining(session.hints_remaining ?? 0);
        setHintsUsed(0);

        setSolved(false);
        setTimerRunning(true);
        setShowHintButton(true);
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
      if (isRightClick) {
        const current = board[startRow][startCol];
        const newValue = current === -1 ? 0 : -1;
        const res = await makeMove(sessionId, startRow, startCol, newValue);
        setBoard(res.board);
      }
      dragMovedRef.current = false;
      isProcessingDragRef.current = false;
      return;
    }

    const mode = isRightClick ? "cross_toggle" : "flip";
    const res = await dragMove(
      sessionId,
      { r: startRow, c: startCol },
      { r: endRow, c: endCol },
      mode
    );
    setBoard(res.board);

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
    if (hintsRemaining <= 0) {
      toast("No hints available yet.");
      return;
    }

    try {
      const res = await getHint(sessionId);
      if (res.solved) {
        toast.success("Puzzle is already solved!");
        if (typeof res.hints_remaining === "number") {
          setHintsRemaining(res.hints_remaining);
        }
      } else if (res.limit_reached) {
        setHintsRemaining(0);
        toast("No hints available yet.");
      } else if (res.hint) {
        setHighlightedCell({ r: res.hint.r, c: res.hint.c });
        setHintsUsed(prev => prev + 1);
        if (typeof res.hints_remaining === "number") {
          setHintsRemaining(res.hints_remaining);
        } else {
          setHintsRemaining(prev => Math.max(0, prev - 1));
        }
        toast("The highlighted cell is incorrect.", {
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

  useEffect(() => {
    const allowance = getHintAllowance(elapsedTime);
    const available = Math.max(0, allowance - hintsUsed);
    if (available !== hintsRemaining) {
      setHintsRemaining(available);
    }
  }, [elapsedTime, hintsUsed, hintsRemaining]);

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
        setShowHintButton(true);
        setHighlightedCell(null);
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

  const startExperiment = async () => {
    try {
      const session = await startThreePuzzleSession();
      if (typeof window !== "undefined") {
        allowNextNavigation();
        window.sessionStorage.setItem("experimentSession", JSON.stringify(session));
        window.location.href = `/experiment?session_id=${session.session_id}`;
      }
    } catch (error) {
      console.error("Failed to start experiment:", error);
      toast.error("Failed to start the experiment.");
    }
  };

  const handleSkip = () => {
    setConfirmModal({
      isOpen: true,
      message: "Are you sure you want to skip the tutorial and start the experiment?",
      onConfirm: () => {
        setConfirmModal({
          isOpen: false,
          message: "",
          onConfirm: null,
          onCancel: null
        });
        startExperiment();
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

  const handleUndo = async () => {
    if (!sessionId || solved) return;
    const res = await undoBoard(sessionId);
    setBoard(res.board);
    setHighlightedCell(null);
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

          <button
            onClick={handleUndo}
            disabled={solved}
            style={{
              padding: "0.75rem 2rem",
              backgroundColor: solved ? "#ccc" : "#5E6A75",
              color: "white",
              fontWeight: "bold",
              borderRadius: "8px",
              border: "none",
              cursor: solved ? "not-allowed" : "pointer",
              fontSize: "1rem",
            }}
          >
            Undo
          </button>

          {showHintButton && (
            <button
              onClick={handleHint}
              disabled={hintsRemaining <= 0}
              style={{
                padding: "0.75rem 2rem",
                backgroundColor: hintsRemaining <= 0 ? "#ccc" : "#8E24AA",
                color: "white",
                fontWeight: "bold",
                borderRadius: "8px",
                border: "none",
                cursor: hintsRemaining <= 0 ? "not-allowed" : "pointer",
                fontSize: "1rem"
              }}
            >
              Hint
            </button>
          )}
          <div style={{ fontSize: "0.95rem", color: "#555" }}>
            Hints available: {hintsRemaining}
          </div>
        </div>

        <div style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
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

          <button
            onClick={handleSkip}
            style={{
              padding: "0.75rem 2rem",
              backgroundColor: "#E3963E",
              color: "white",
              fontWeight: "bold",
              borderRadius: "8px",
              border: "none",
              cursor: "pointer",
              fontSize: "1rem"
            }}
          >
            Skip
          </button>
        </div>
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
