import { useState, useEffect } from "react";
import toast from "react-hot-toast";
import Grid from "@/components/Grid";
import Timer from "@/components/Timer";
import Survey from "@/components/Survey";
import {
  startThreePuzzleSession,
  makeMove,
  checkBoard,
  resetBoard,
  getSurvey,
  submitSurvey,
  endSession
} from "@/services/api";

const STAGES = {
  PRE_SURVEY: "pre_survey",
  PUZZLE: "puzzle",
  POST_PUZZLE_SURVEY: "post_puzzle_survey",
  POST_SURVEY: "post_survey",
  COMPLETED: "completed"
};

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
  
  // Survey state
  const [currentSurvey, setCurrentSurvey] = useState(null);
  
  // Store the initial session data and next puzzle data
  const [initialSessionData, setInitialSessionData] = useState(null);
  const [nextPuzzleData, setNextPuzzleData] = useState(null);

  // Initialize session and get pre-survey
  useEffect(() => {
    async function init() {
      // Start the three-puzzle session
      const session = await startThreePuzzleSession();
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
    
    setStage(STAGES.PUZZLE);
    setTimerRunning(true);
  };

  // Handle cell click
  const handleCellClick = async (r, c) => {
    if (!sessionId || solved) return;

    const current = board[r][c];
    const newValue = current === 0 ? 1 : current === 1 ? -1 : 0;

    const res = await makeMove(sessionId, r, c, newValue);
    setBoard(res.board);
  };

  // Check solution
  const handleCheck = async () => {
    if (!sessionId || solved) return;
    
    const res = await checkBoard(sessionId);
    setSolved(res.solved);
    
    if (!res.solved) {
      toast.error("Not correct yet. Try again!");
      return;
    } else {
      setTimerRunning(false);
      
      // If not all puzzles completed, show per-puzzle survey
      if (!res.completed) {
        // Store the next puzzle data for later
        setNextPuzzleData(res);
        const surveyType = `puzzle_${puzzleIndex + 1}`;
        const survey = await getSurvey(sessionId, surveyType);
        setCurrentSurvey(survey);
        setStage(STAGES.POST_PUZZLE_SURVEY);
      } else {
        // All puzzles completed, get post-survey
        const survey = await getSurvey(sessionId, "post");
        setCurrentSurvey(survey);
        setStage(STAGES.POST_SURVEY);
      }
    }
  };

  // Handle post-puzzle survey submission
  const handlePostPuzzleSurveySubmit = async (answers) => {
    const surveyType = `puzzle_${puzzleIndex + 1}`;
    await submitSurvey(sessionId, surveyType, answers);
    
    // Use the next puzzle data we stored from check response
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
    
    setSolved(false);
    setNextPuzzleData(null);
    setStage(STAGES.PUZZLE);
    setTimerRunning(true);
  };

  // Handle post-survey submission
  const handlePostSurveySubmit = async (answers) => {
    await submitSurvey(sessionId, "post", answers);
    await endSession(sessionId);
    setStage(STAGES.COMPLETED);
  };

  // Reset puzzle
  const handleReset = async () => {
    if (!sessionId) return;
    const res = await resetBoard(sessionId);
    setBoard(res.board);
    setSolved(false);
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
        Nonogram Game
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
          
          <Timer start={0} running={timerRunning} />
          
          <Grid grid={board} onCellClick={handleCellClick} clues={clues} />
          
          <div style={{ marginTop: 20, display: "flex", justifyContent: "center", gap: "1rem" }}>
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
              Check Solution
            </button>
            <button
              onClick={handleReset}
              style={{
                padding: "0.75rem 2rem",
                backgroundColor: "#FFD3AC",
                fontWeight: "bold",
                borderRadius: "8px",
                border: "none",
                cursor: "pointer",
                fontSize: "1rem"
              }}
            >
              Reset
            </button>
          </div>
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
          <h2 style={{ textAlign: "center", marginBottom: "1rem" }}>Final Survey</h2>
          <Survey questions={currentSurvey.questions} onSubmit={handlePostSurveySubmit} />
        </div>
      )}

      {stage === STAGES.COMPLETED && (
        <div style={{ textAlign: "center", marginTop: "3rem" }}>
          <p style={{ fontSize: "1.2rem" }}>
            Thank you for participating!
          </p>
        </div>
      )}
    </main>
  );
}
