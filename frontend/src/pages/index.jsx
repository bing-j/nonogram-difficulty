import { useState, useEffect, useRef } from "react";
import toast from "react-hot-toast";
import Grid from "@/components/Grid";
import Timer from "@/components/Timer";
import Survey from "@/components/Survey";
import ConfirmModal from "@/components/ConfirmModal";
import HintModal from "@/components/HintModal";
import {
  startThreePuzzleSession,
  makeMove,
  checkBoard,
  resetBoard,
  getSurvey,
  submitSurvey,
  endSession,
  getHint,
  getSessionLog,
  advancePuzzle
} from "@/services/api";

const STAGES = {
  PRE_SURVEY: "pre_survey",
  PUZZLE: "puzzle",
  PUZZLE_SOLVED: "puzzle_solved",
  POST_PUZZLE_SURVEY: "post_puzzle_survey",
  POST_SURVEY: "post_survey",
  COMPLETED: "completed"
};

const DEFAULT_HINT_LIMIT = 5;

export default function Home() {
  const [stage, setStage] = useState(STAGES.PRE_SURVEY);
  const [sessionId, setSessionId] = useState(null);
  
  // Puzzle state
  const [puzzleIndex, setPuzzleIndex] = useState(0);
  const [puzzleInfo, setPuzzleInfo] = useState(null);
  const [board, setBoard] = useState([]);
  const [clues, setClues] = useState({ rows: [], columns: [] });
  const [solved, setSolved] = useState(false);
  const [timerRunning, setTimerRunning] = useState(false);
  const [elapsedTime, setElapsedTime] = useState(0);
  const [puzzleStartTime, setPuzzleStartTime] = useState(null);
  
  // Survey state
  const [currentSurvey, setCurrentSurvey] = useState(null);
  
  // Store the initial session data and next puzzle data
  const [initialSessionData, setInitialSessionData] = useState(null);
  const [nextPuzzleData, setNextPuzzleData] = useState(null);
  
  // Store per-puzzle survey answers for pre-filling post-survey
  const [puzzleSurveyAnswers, setPuzzleSurveyAnswers] = useState({});
  
  // Store solved puzzle time for success page
  const [solvedPuzzleTime, setSolvedPuzzleTime] = useState(null);
  const [puzzleSolvedFlags, setPuzzleSolvedFlags] = useState(null);
  const [puzzleSkippedFlags, setPuzzleSkippedFlags] = useState(null);
  
  const [showHintButton, setShowHintButton] = useState(false);
  
  // Confirmation modal state
  const [confirmModal, setConfirmModal] = useState({
    isOpen: false,
    message: "",
    onConfirm: null,
    onCancel: null
  });
  
  // Hint modal state (keeping for now but won't use it)
  const [hintModal, setHintModal] = useState({
    isOpen: false,
    hint: null
  });
  
  // Highlighted cell for hints
  const [highlightedCell, setHighlightedCell] = useState(null);
  const [hintLimit, setHintLimit] = useState(DEFAULT_HINT_LIMIT);
  const [hintsRemaining, setHintsRemaining] = useState(DEFAULT_HINT_LIMIT);
  
  // Drag selection state
  const [dragState, setDragState] = useState({
    isDragging: false,
    startRow: null,
    startCol: null,
    endRow: null,
    endCol: null,
    isRightClick: false
  });

  // Initialize session and get pre-survey
  useEffect(() => {
    async function init() {
      let session = null;

      if (typeof window !== "undefined") {
        const params = new URLSearchParams(window.location.search);
        const preloadedId = params.get("session_id");
        const storedSession = window.sessionStorage.getItem("experimentSession");

        if (preloadedId && storedSession) {
          try {
            const parsedSession = JSON.parse(storedSession);
            if (parsedSession.session_id === preloadedId) {
              session = parsedSession;
              window.sessionStorage.removeItem("experimentSession");
              window.history.replaceState({}, "", window.location.pathname);
            }
          } catch (error) {
            window.sessionStorage.removeItem("experimentSession");
          }
        }
      }

      // Start the three-puzzle session
      if (!session) {
        session = await startThreePuzzleSession();
      }
      setSessionId(session.session_id);
      setInitialSessionData(session);
      
      // Get pre-survey questions
      const survey = await getSurvey(session.session_id, "pre");
      setCurrentSurvey(survey);
    }
    init();
  }, []);

  // Handle pre-survey submission
  const handlePreSurveySubmit = async (answers) => {
    await submitSurvey(sessionId, "pre", answers);
    
    // Use the initial session data we stored
    const session = initialSessionData;
    setPuzzleIndex(session.index);
    setPuzzleInfo(session.puzzle);
    
    const rows = session.puzzle.rows;
    const cols = session.puzzle.cols;
    setBoard(Array(rows).fill(0).map(() => Array(cols).fill(0)));
    setClues({
      rows: session.puzzle.row_clues,
      columns: session.puzzle.col_clues
    });
    const limit = session.hint_limit ?? DEFAULT_HINT_LIMIT;
    setHintLimit(limit);
    setHintsRemaining(session.hints_remaining ?? limit);
    
    setStage(STAGES.PUZZLE);
    setTimerRunning(true);
    setShowHintButton(true);
    setHighlightedCell(null); // Clear any previous highlight
  };

  // Track if we actually moved during drag (to distinguish click from drag)
  const dragMovedRef = useRef(false);
  const isProcessingDragRef = useRef(false);

  // Handle drag start
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

  // Handle drag update
  const handleDragUpdate = (r, c) => {
    if (!dragState.isDragging) return;
    
    setDragState(prev => {
      // Mark that we've moved (so it's a drag, not a click)
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

  // Handle drag end - apply action to all selected cells
  const handleDragEnd = async () => {
    if (!dragState.isDragging || !sessionId || solved || isProcessingDragRef.current) return;
    
    // Mark that we're processing a drag to prevent duplicate calls
    isProcessingDragRef.current = true;
    
    // Capture the drag state before resetting
    const { startRow, startCol, endRow, endCol, isRightClick } = dragState;
    
    // Check if it was actually a drag (start != end) or just a click
    const wasDrag = (startRow !== endRow || startCol !== endCol) || dragMovedRef.current;
    
    // Reset drag state first
    setDragState({
      isDragging: false,
      startRow: null,
      startCol: null,
      endRow: null,
      endCol: null,
      isRightClick: false
    });
    
    // If it was just a click (no movement), let the normal click handler deal with it
    if (!wasDrag) {
      dragMovedRef.current = false;
      isProcessingDragRef.current = false;
      return;
    }
    
    // Calculate the range of cells to update
    const minRow = Math.min(startRow, endRow);
    const maxRow = Math.max(startRow, endRow);
    const minCol = Math.min(startCol, endCol);
    const maxCol = Math.max(startCol, endCol);
    
    // Collect all cells in the selection
    const cellsToUpdate = [];
    for (let r = minRow; r <= maxRow; r++) {
      for (let c = minCol; c <= maxCol; c++) {
        cellsToUpdate.push({ r, c });
      }
    }
    
    // Determine the action based on click type
    if (isRightClick) {
      // Right click drag: toggle cross (-1)
      // Use the state of the starting cell to determine action
      const startValue = board[startRow][startCol];
      const newValue = startValue === -1 ? 0 : -1;
      
      // Apply to all cells in selection
      for (const { r, c } of cellsToUpdate) {
        const res = await makeMove(sessionId, r, c, newValue);
        setBoard(res.board);
      }
    } else {
      // Left click drag: toggle based on the starting cell (match click behavior)
      const startValue = board[startRow][startCol];
      const newValue = startValue === 1 ? 0 : 1;
      
      // Apply to all cells in selection
      for (const { r, c } of cellsToUpdate) {
        const res = await makeMove(sessionId, r, c, newValue);
        setBoard(res.board);
      }
    }
    
    // Reset refs after processing
    dragMovedRef.current = false;
    // Reset processing flag after a delay to allow click handler to check it
    setTimeout(() => {
      isProcessingDragRef.current = false;
    }, 200);
  };

  // Handle left click - toggle between black (1) and white (0)
  const handleCellClick = async (r, c) => {
    if (!sessionId || solved) return;
    
    // Don't handle click if we're processing a drag or if drag state indicates we were dragging
    if (isProcessingDragRef.current || dragState.isDragging) {
      return;
    }
    
    // Also check if we just finished a drag (using a small delay check)
    if (dragMovedRef.current) {
      dragMovedRef.current = false;
      return;
    }

    // Clear highlight if user clicks on the highlighted cell
    if (highlightedCell && highlightedCell.r === r && highlightedCell.c === c) {
      setHighlightedCell(null);
    }

    const current = board[r][c];
    // Left click: switch between black (1) and white (0)
    // If it's black (1), make it white (0)
    // If it's white (0) or cross (-1), make it black (1)
    const newValue = current === 1 ? 0 : 1;

    const res = await makeMove(sessionId, r, c, newValue);
    setBoard(res.board);
  };

  // Handle right click - toggle cross (-1)
  const handleCellRightClick = async (r, c) => {
    if (!sessionId || solved) return;

    // Clear highlight if user clicks on the highlighted cell
    if (highlightedCell && highlightedCell.r === r && highlightedCell.c === c) {
      setHighlightedCell(null);
    }

    const current = board[r][c];
    // Right click: toggle cross (-1)
    // If it's a cross, make it white (0), otherwise make it a cross
    const newValue = current === -1 ? 0 : -1;

    const res = await makeMove(sessionId, r, c, newValue);
    setBoard(res.board);
  };

  // Handle hint request
  const handleHint = async () => {
    if (!sessionId) return;
    if (hintsRemaining <= 0) {
      toast(`Hint limit reached (${hintLimit} max).`);
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
        toast(`Hint limit reached (${hintLimit} max).`);
      } else if (res.hint) {
        // Highlight the cell and show notification
        setHighlightedCell({ r: res.hint.r, c: res.hint.c });
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

  // Handle time update from timer
  const handleTimeUpdate = (seconds) => {
    setElapsedTime(seconds);
  };

  // Check solution
  const handleCheck = async () => {
    if (!sessionId || solved) return;
    
    const res = await checkBoard(sessionId);
    
    if (!res.solved) {
      toast.error("Not correct yet. Try again!");
      return;
    }
    
    // Puzzle is solved
    setSolved(true);
    setTimerRunning(false);
    setSolvedPuzzleTime(elapsedTime);
    
    // Show success page
    setStage(STAGES.PUZZLE_SOLVED);
    
    // After 3 seconds, proceed to survey
    setTimeout(() => {
      proceedToSurvey(res);
    }, 3000);
  };

  // Proceed to survey after success page
  const proceedToSurvey = async (checkResponse) => {
    if (checkResponse && checkResponse.completed === true) {
      setPuzzleSolvedFlags([true, true, true]);
      setPuzzleSkippedFlags([false, false, false]);
    } else if (checkResponse && checkResponse.finished) {
      if (Array.isArray(checkResponse.solved_flags)) {
        setPuzzleSolvedFlags(checkResponse.solved_flags);
      }
      if (Array.isArray(checkResponse.skipped_flags)) {
        setPuzzleSkippedFlags(checkResponse.skipped_flags);
      }
    }

    // Always show per-puzzle survey first (even for puzzle 3)
    const surveyType = `puzzle_${puzzleIndex + 1}`;
    const survey = await getSurvey(sessionId, surveyType);
    setCurrentSurvey(survey);
    setStage(STAGES.POST_PUZZLE_SURVEY);
    
    // Store the next puzzle data if not completed (for puzzles 1 and 2)
    if (!checkResponse.completed) {
      setNextPuzzleData(checkResponse);
    }
  };

  // Handle give up - skip current puzzle and go to survey
  const handleGiveUp = () => {
    if (!sessionId || solved) return;
    
    // Show confirmation modal
    setConfirmModal({
      isOpen: true,
      message: "Are you sure you want to skip this puzzle?",
      onConfirm: async () => {
        setConfirmModal({ 
          isOpen: false, 
          message: "", 
          onConfirm: null, 
          onCancel: null
        });
        
        // Stop timer
        setTimerRunning(false);
        setSolvedPuzzleTime(elapsedTime);
        
        // Mark that this is a give-up (not a solved puzzle)
        // We'll handle the next puzzle after survey submission
        setNextPuzzleData({ 
          isGiveUp: true,
          nextIndex: puzzleIndex + 1
        });
        
        // Go directly to survey (skip success page for give-up)
        const surveyType = `puzzle_${puzzleIndex + 1}`;
        getSurvey(sessionId, surveyType).then(survey => {
          setCurrentSurvey(survey);
          setStage(STAGES.POST_PUZZLE_SURVEY);
        });
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


  // Handle post-puzzle survey submission
  const handlePostPuzzleSurveySubmit = async (answers) => {
    const surveyType = `puzzle_${puzzleIndex + 1}`;
    await submitSurvey(sessionId, surveyType, answers);
    
    // Store answers for pre-filling post-survey
    setPuzzleSurveyAnswers(prev => ({
      ...prev,
      [`puzzle_${puzzleIndex + 1}`]: answers
    }));
    
    // Check if this was puzzle 3 (index 2)
    if (puzzleIndex === 2) {
      if (nextPuzzleData && nextPuzzleData.isGiveUp) {
        try {
          const res = await advancePuzzle(sessionId);
          if (Array.isArray(res.solved_flags)) {
            setPuzzleSolvedFlags(res.solved_flags);
          }
          if (Array.isArray(res.skipped_flags)) {
            setPuzzleSkippedFlags(res.skipped_flags);
          }
        } catch (error) {
          console.error("Failed to finalize skipped puzzle:", error);
        }
      }

      const survey = await getSurvey(sessionId, "post");
      setCurrentSurvey(survey);
      setStage(STAGES.POST_SURVEY);
    } else if (nextPuzzleData && nextPuzzleData.puzzle) {
      // Use the next puzzle data we stored from check response (solved puzzle)
      const nextPuzzle = nextPuzzleData.puzzle;
      setPuzzleIndex(nextPuzzleData.index);
      setPuzzleInfo(nextPuzzle);
      
      const rows = nextPuzzle.rows;
      const cols = nextPuzzle.cols;
      setBoard(Array(rows).fill(0).map(() => Array(cols).fill(0)));
      setClues({
        rows: nextPuzzle.row_clues,
        columns: nextPuzzle.col_clues
      });
      const limit = nextPuzzleData.hint_limit ?? DEFAULT_HINT_LIMIT;
      setHintLimit(limit);
      setHintsRemaining(nextPuzzleData.hints_remaining ?? limit);
      
      setSolved(false);
      setNextPuzzleData(null);
      setStage(STAGES.PUZZLE);
      setTimerRunning(true);
      setShowHintButton(true);
      setHighlightedCell(null); // Clear any previous highlight
      if (nextPuzzleData.finished && Array.isArray(nextPuzzleData.solved_flags)) {
        setPuzzleSolvedFlags(nextPuzzleData.solved_flags);
      }
      if (nextPuzzleData.finished && Array.isArray(nextPuzzleData.skipped_flags)) {
        setPuzzleSkippedFlags(nextPuzzleData.skipped_flags);
      }
    } else if (nextPuzzleData && nextPuzzleData.isGiveUp) {
      // This is from give-up - use backend advance endpoint to get next puzzle
      const nextIndex = nextPuzzleData.nextIndex;
      
      if (nextIndex >= 3) {
        // Puzzle 3 was given up, go to post-survey
        try {
          const res = await advancePuzzle(sessionId);
          if (Array.isArray(res.solved_flags)) {
            setPuzzleSolvedFlags(res.solved_flags);
          }
          if (Array.isArray(res.skipped_flags)) {
            setPuzzleSkippedFlags(res.skipped_flags);
          }
        } catch (error) {
          console.error("Failed to finalize skipped puzzle:", error);
        }
        const survey = await getSurvey(sessionId, "post");
        setCurrentSurvey(survey);
        setStage(STAGES.POST_SURVEY);
      } else {
        // Advance to next puzzle using backend endpoint
        try {
          const res = await advancePuzzle(sessionId);
          
          if (res.completed) {
            // All puzzles done, go to post-survey
            setPuzzleSolvedFlags([true, true, true]);
            setPuzzleSkippedFlags([false, false, false]);
            const survey = await getSurvey(sessionId, "post");
            setCurrentSurvey(survey);
            setStage(STAGES.POST_SURVEY);
          } else if (res.puzzle) {
            // Set up next puzzle
            setPuzzleIndex(res.index);
            setPuzzleInfo(res.puzzle);
            
            const rows = res.puzzle.rows;
            const cols = res.puzzle.cols;
            setBoard(Array(rows).fill(0).map(() => Array(cols).fill(0)));
            setClues({
              rows: res.puzzle.row_clues,
              columns: res.puzzle.col_clues
            });
            const limit = res.hint_limit ?? DEFAULT_HINT_LIMIT;
            setHintLimit(limit);
            setHintsRemaining(res.hints_remaining ?? limit);
            
            setSolved(false);
            setNextPuzzleData(null);
            setStage(STAGES.PUZZLE);
            setTimerRunning(true);
            setShowHintButton(true);
            setHighlightedCell(null);
            if (Array.isArray(res.solved_flags)) {
              setPuzzleSolvedFlags(res.solved_flags);
            }
            if (Array.isArray(res.skipped_flags)) {
              setPuzzleSkippedFlags(res.skipped_flags);
            }
          }
        } catch (error) {
          console.error("Failed to advance puzzle:", error);
          toast.error("Failed to load next puzzle. Please refresh the page.");
        }
      }
    }
  };

  // Prepare initial answers for post-survey
  const getPostSurveyInitialAnswers = () => {
    const initial = {};
    
    // Pre-fill from per-puzzle surveys
    // Map difficulty -> puzzle_X_rate_again and puzzle_X_guesses -> puzzle_X_guesses
    for (let i = 1; i <= 3; i++) {
      if (Array.isArray(puzzleSolvedFlags) && puzzleSolvedFlags[i - 1] === false) {
        continue;
      }
      const puzzleKey = `puzzle_${i}`;
      const answers = puzzleSurveyAnswers[puzzleKey];
      if (answers) {
        // Map difficulty rating to rate_again field
        if (answers.difficulty !== undefined) {
          initial[`puzzle_${i}_rate_again`] = answers.difficulty;
        }
        // Map guesses field (same name in both surveys)
        if (answers[`puzzle_${i}_guesses`] !== undefined) {
          initial[`puzzle_${i}_guesses`] = answers[`puzzle_${i}_guesses`];
        }
      }
    }
    
    return initial;
  };

  const filterPostSurveyQuestions = (questions) => {
    if (!Array.isArray(puzzleSolvedFlags)) return questions;
    return questions.filter((q) => {
      const match = q.id && q.id.match(/^puzzle_(\d+)_/);
      if (!match) return true;
      const idx = Number(match[1]) - 1;
      if (Number.isNaN(idx) || idx < 0 || idx >= puzzleSolvedFlags.length) {
        return true;
      }
      return puzzleSolvedFlags[idx];
    });
  };

  // Handle post-survey submission
  const handlePostSurveySubmit = async (answers) => {
    await submitSurvey(sessionId, "post", answers);
    await endSession(sessionId);
    setStage(STAGES.COMPLETED);
  };

  // Reset puzzle
  const handleReset = () => {
    if (!sessionId) return;
    
    // Show confirmation modal
    setConfirmModal({
      isOpen: true,
      message: "Are you sure you want to reset this puzzle? All progress will be lost.",
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
        setHighlightedCell(null);
        setHintsRemaining(hintLimit);
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

  // Format time for display
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
        Nonogram Study
      </h1>

      {stage === STAGES.PRE_SURVEY && currentSurvey && (
        <div>
          <h2 style={{ textAlign: "center", marginBottom: "1rem" }}>Pre-Session Survey</h2>
          <Survey questions={currentSurvey.questions} onSubmit={handlePreSurveySubmit} />
        </div>
      )}

      {stage === STAGES.PUZZLE && (
        <div>
          <div style={{ textAlign: "center", marginBottom: "1rem" }}>
            <p style={{ fontSize: "1.2rem", fontWeight: 500 }}>
              Puzzle {puzzleIndex + 1} of 3
            </p>
          </div>
          
          <Timer key={`puzzle-${puzzleIndex}`} start={0} running={timerRunning} onTimeUpdate={handleTimeUpdate} />
          
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
            {/* Left side buttons - Reset and Hint */}
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
                Hints remaining: {hintsRemaining} / {hintLimit}
              </div>
            </div>
            
            {/* Right side buttons - Submit and Skip */}
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
                onClick={handleGiveUp}
                disabled={solved}
                style={{
                  padding: "0.75rem 2rem",
                  backgroundColor: solved ? "#ccc" : "#E3963E",
                  color: "white",
                  fontWeight: "bold",
                  borderRadius: "8px",
                  border: "none",
                  cursor: solved ? "not-allowed" : "pointer",
                  fontSize: "1rem"
                }}
              >
                Skip
              </button>
            </div>
          </div>
        </div>
      )}

      {stage === STAGES.PUZZLE_SOLVED && (
        <div style={{ textAlign: "center", marginTop: "3rem" }}>
          <h2 style={{ fontSize: "2rem", marginBottom: "1rem", color: "#4169E1" }}>
            Puzzle {puzzleIndex + 1} Solved!
          </h2>
          <p style={{ fontSize: "1.2rem", marginBottom: "1rem" }}>
            Time used: {formatTime(solvedPuzzleTime)}
          </p>
          <p style={{ fontSize: "1rem", color: "#666" }}>
            We will proceed in 3 seconds...
          </p>
        </div>
      )}

      {stage === STAGES.POST_PUZZLE_SURVEY && currentSurvey && (
        <div>
          <h2 style={{ textAlign: "center", marginBottom: "1rem" }}>
            Rate Puzzle {puzzleIndex + 1}
          </h2>
          <Survey questions={currentSurvey.questions} onSubmit={handlePostPuzzleSurveySubmit} />
        </div>
      )}

      {stage === STAGES.POST_SURVEY && currentSurvey && (
        <div>
          <h2 style={{ textAlign: "center", marginBottom: "1rem" }}>Post Survey</h2>
          <Survey 
            questions={filterPostSurveyQuestions(currentSurvey.questions)} 
            onSubmit={handlePostSurveySubmit}
            initialAnswers={getPostSurveyInitialAnswers()}
          />
        </div>
      )}

      {stage === STAGES.COMPLETED && (
        <div style={{ textAlign: "center", marginTop: "3rem" }}>
          <h1 style={{ fontSize: "1.5rem"}}>
            Thank you for participating!
          </h1>
        </div>
      )}

      {/* Confirmation Modal */}
      <ConfirmModal
        isOpen={confirmModal.isOpen}
        message={confirmModal.message}
        onConfirm={confirmModal.onConfirm || (() => {})}
        onCancel={confirmModal.onCancel || (() => {})}
      />

      {/* Hint Modal */}
      <HintModal
        isOpen={hintModal.isOpen}
        hint={hintModal.hint}
        onClose={() => setHintModal({ isOpen: false, hint: null })}
      />
    </main>
  );
}
