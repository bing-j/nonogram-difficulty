"""
Shared participant-expertise composite, ported from
riyad-analysis/04_build_expertise_score.py's "z-mean" method (Method A:
equal-weighted mean of standardized background dimensions). This is the
single source of truth for expertise across analyze-data/ and the root-level
run_*.py scripts -- no fixed skill_nonogram bins, no discrete tiers.

Dimensions (all oriented so higher = more expert), matching
riyad-analysis/nono_data.py exactly:
  skill_nonogram               self-rated Nonogram skill (1-10)
  skill_puzzles                self-rated general logic-puzzle skill (1-10)
  played_before_ord            Nonogram play frequency (0-3)
  puzzle_played_frequency_ord  general logic-puzzle frequency (0-3)
  n_nonogram_sizes             breadth of Nonogram sizes solved
  n_logic_puzzles              breadth of other logic puzzles known
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

# Ordinal encoding for the two self-reported frequency questions
# (backend/main.py SURVEY_SPEC "played_before" / "puzzle_played_frequency").
FREQUENCY_ORDER = {"never": 0, "few": 1, "many": 2, "regular": 3}

EXPERTISE_DIMS: List[str] = [
    "skill_nonogram",
    "skill_puzzles",
    "played_before_ord",
    "puzzle_played_frequency_ord",
    "n_nonogram_sizes",
    "n_logic_puzzles",
]


def _list_len(value: Any) -> Optional[int]:
    return len(value) if isinstance(value, list) else None


def extract_expertise_dims(pre_answers: Dict[str, Any]) -> Dict[str, Any]:
    """Raw per-participant expertise dimensions from a pre-survey answers dict."""
    return {
        "skill_nonogram": pre_answers.get("skill_nonogram"),
        "skill_puzzles": pre_answers.get("skill_puzzles"),
        "played_before_ord": FREQUENCY_ORDER.get(str(pre_answers.get("played_before")).lower()),
        "puzzle_played_frequency_ord": FREQUENCY_ORDER.get(
            str(pre_answers.get("puzzle_played_frequency")).lower()
        ),
        "n_nonogram_sizes": _list_len(pre_answers.get("nonogram_size_experience")),
        "n_logic_puzzles": _list_len(pre_answers.get("logic_experience")),
    }


def add_expertise_composite(df: pd.DataFrame, dims: List[str] = EXPERTISE_DIMS) -> pd.DataFrame:
    """Add an `expertise_composite` column: naive z-mean composite across `dims`,
    one score per participant_id, broadcast to every row of `df`.

    Mirrors riyad-analysis/04_build_expertise_score.py's exp_zmean -> exp_zmean_z:
    z-score each dimension (population std, ddof=0) across participants, average
    the available z-scores per participant (skipna), then re-standardize.
    """
    per_participant = df.groupby("participant_id")[dims].first().apply(pd.to_numeric, errors="coerce")
    z = (per_participant - per_participant.mean()) / per_participant.std(ddof=0)
    zmean = z.mean(axis=1, skipna=True)
    zmean_z = (zmean - zmean.mean()) / zmean.std(ddof=0)
    composite = zmean_z.rename("expertise_composite")
    return df.merge(composite, on="participant_id", how="left")
