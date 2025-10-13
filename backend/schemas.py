# backend/schemas.py
from pydantic import BaseModel, conint, Field
from typing import List, Literal, Optional

PlayedBefore = Literal["never","few","many","regularly"]
Frequency    = Literal["never","few","many","regularly"]
SizeOpt      = Literal["<=5x5","10x10","15x15",">15","na"]
OtherPuzzles = Literal["Sudoku","Minesweeper","Norinori","Battleships","Other"]
GuessBucket  = Literal["0","1-5","6-10","10+"]

class PreSurvey(BaseModel):
    session_id: str
    q1_playedBefore: PlayedBefore               # Have you played Nonogram before?
    q2_selfSkillNonogram: conint(ge=1, le=10)   # In scale of 1 to 10, how would you rate your Nonogram skill?
    q3_sizes: List[SizeOpt]                     # If you have played Nonogram before, what are the sizes you have solved (select all that apply)?
    q4_otherPuzzles: List[OtherPuzzles]         # Have you played any other logic puzzles before (select all that apply)?
    q4_otherText: Optional[str] = None          # “Other”
    q5_frequencyLogic: Frequency                # How frequently do you play logic puzzles in general?
    q6_selfSkillLogic: conint(ge=1, le=10)      # In the scale of 1 to 10, how would you rate your logic-puzzle skill?

class Metrics(BaseModel):
    session_id: str
    puzzle_id: str
    # record data
    time_ms: int
    undos: int
    initial_rating: conint(ge=1, le=10)         # Ask for initial rating in scale of 1 to 10

class PostPerPuzzle(BaseModel):
    puzzle_id: str
    final_rating: conint(ge=1, le=10)           # Give the opportunity to adjust the final ratings of each puzzle
    reason_text: str = ""                       # Why did you rate this difficulty?
    guess_bucket: GuessBucket                   # How many times did you guess a cell (which means the decision was not based on logical deduction)?

class PostSurvey(BaseModel):
    session_id: str
    per_puzzle: List[PostPerPuzzle]
    strategies: List[str] = Field(default_factory=list)   # What strategies did you use?
    difficulty_signal: str                                # Which factor most signaled difficulty?
    anything_else: Optional[str] = None                   # Anything else…?
