# Analysis Pipeline

This document describes the full analysis pipeline for the nonogram difficulty study.
All commands are run from the **repository root** with the virtual environment active.

```bash
source .venv/Scripts/activate   # Windows (bash)
source .venv/bin/activate        # macOS/Linux
```

---

## Participant Expertise

Participant expertise is a single continuous score, `expertise_composite`: a naive z-mean composite of six pre-survey background items (`skill_nonogram`, `skill_puzzles`, ordinal-encoded `played_before`/`puzzle_played_frequency`, and the breadth of `nonogram_size_experience`/`logic_experience` selections). Each item is z-scored across participants, averaged (skipping missing items), then re-standardized. See `expertise.py` for the implementation — ported from `riyad-analysis/04_build_expertise_score.py`'s "z-mean" method.

There are no discrete experience tiers anywhere in this pipeline: `expertise_composite` is used directly as a continuous covariate rather than being cut into groups.

---

## Step 0 — Pause Threshold (one-time, already done)

Determine the inter-event gap threshold that separates deliberate pauses from normal interaction.

```bash
python analyze-data/plot_gap_distribution.py
```

| | |
|---|---|
| **Input** | `backend/logs/*.ndjson` |
| **Outputs** | `analyze-data/out_features/gap_distribution.png` — four-panel diagnostic |
| | `analyze-data/out_features/gap_log_intervals.png` — GMM fit |
| | `analyze-data/out_features/pause_sensitivity.png` — threshold sensitivity |

The recommended threshold is **2.36 s**, derived from the equal-posterior crossover of a 3-component Gaussian Mixture Model on log-transformed inter-event gaps. See [`PAUSE_THRESHOLD_REPORT.md`](PAUSE_THRESHOLD_REPORT.md) for the full methodology.

---

## Step 1 — Extract Behavioral Features

Extract per-participant, per-puzzle behavioral signals from raw event logs.

```bash
python analyze-data/extract_behavioral_features.py \
  --input_glob "backend/logs/*.ndjson" \
  --puzzles_json nonograms_6.json \
  --out_dir analyze-data/out_features
```

| | |
|---|---|
| **Inputs** | `backend/logs/*.ndjson` |
| | `nonograms_6.json` (puzzle solutions) |
| **Output** | `analyze-data/out_features/behavioral_features.csv` |

### Output columns

| Column | Description |
|--------|-------------|
| `participant_id` | From log filename stem (e.g. `Bing-p1`) |
| `puzzle_id` | Puzzle index 0–5 |
| `pause_count` | Inter-event gaps ≥ 2.36 s |
| `pause_freq_per_min` | `pause_count / duration_min` |
| `time_to_solve_sec` | First interaction to first successful check; falls back to full duration |
| `total_time_spent_sec` | Full interaction duration (first to last interaction event), regardless of solve outcome |
| `check_count` | Number of `check_bank` events (times "check my solution" was clicked) |
| `error_count` | Move events where cell is filled but solution is empty |
| `percent_error` | Fraction of all 100 grid cells wrong in the final (end-of-session) board state |
| `percent_incomplete` | Fraction of the 50 black solution cells not correctly filled in the final board state |
| `hint_count` | Hint events (excludes `hint_none`) |
| `initial_difficulty` | Rating immediately after the puzzle |
| `final_difficulty` | Retrospective rating from the post-survey |
| `solved_flag` | Whether the participant solved the puzzle |
| `order` | 1/2/3 — the participant's presentation order for this puzzle |
| `skill_nonogram` | Self-reported nonogram experience (1–10) |
| `skill_puzzles` | Self-reported logic-puzzle experience (1–10) |
| `played_before_ord` | Nonogram play frequency, ordinal-encoded (never=0 … regular=3) |
| `puzzle_played_frequency_ord` | Other logic-puzzle play frequency, ordinal-encoded (never=0 … regular=3) |
| `n_nonogram_sizes` | Breadth of Nonogram sizes solved (count of selections) |
| `n_logic_puzzles` | Breadth of other logic puzzles known (count of selections) |
| `expertise_composite` | Naive z-mean composite of the six items above (see "Participant Expertise") |

**This CSV is required by Steps 2, 3, 4, and 7.** `total_time_spent_sec`, `check_count`, `percent_error`, and `percent_incomplete` mirror the paper's own Table 1 measures (see Step 7) — `percent_error`/`percent_incomplete` are computed from a final-board reconstruction shared with `solve_trajectory.py` (`reconstruct_final_board`).

---

## Step 2 — Behavioral Regression

OLS regression: behavioral features → difficulty ratings.

```bash
python analyze-data/behavioral_regression.py
```

| | |
|---|---|
| **Inputs** | `analyze-data/out_features/behavioral_features.csv` |
| | `selected_six_nonogram_stats.csv` |
| **Outputs** | `analyze-data/out_features/behavioral_reg1_coef_heatmap_final_difficulty.png` |
| | `analyze-data/out_features/behavioral_reg2_scatter_grid_decisions.png` |

Two regression families are run:
- **Reg 1**: `final_difficulty ~ behavioral_features` (per puzzle and pooled)
- **Reg 2**: `behavioral_features ~ SAT_decisions` (pooled)

---

## Step 3 — Bradley-Terry Ranking + Spearman Correlation

Fit a Bradley-Terry pairwise comparison model, then test Spearman ρ between BT ranks and SAT metrics / behavioral aggregates.

```bash
python analyze-data/spearman_ranking.py
```

| | |
|---|---|
| **Inputs** | `analyze-data/out_features/behavioral_features.csv` |
| | `selected_six_nonogram_stats.csv` |
| **Outputs** | `analyze-data/out_features/bt_scores.png` |
| | `analyze-data/out_features/bt_ranking_vs_sat.png` |

The Bradley-Terry model corrects for the fact that each participant only sees 3 of the 6 puzzles. Within each participant's session, every pair of rated puzzles generates one pairwise comparison (higher-rated = "wins"; ties split 0.5/0.5). A global strength score θ_i is estimated via MLE.

---

## Step 4 — SAT vs. Human Ratings

BT ranking of puzzles by human difficulty ratings, correlated against SAT solver metrics.

```bash
python analyze-data/regression_analysis.py
```

| | |
|---|---|
| **Inputs** | `backend/logs/*.ndjson` |
| | `selected_six_nonogram_stats.csv` |
| **Outputs** | `analyze-data/out_features/figures/spearman_rank_scatter.png` |
| | `analyze-data/out_features/figures/regression_per_puzzle_means.png` |

---

## Step 5 — Solve Trajectories

Reconstruct and visualize how participants progress through each puzzle over time.

```bash
python analyze-data/solve_trajectory.py
```

| | |
|---|---|
| **Inputs** | `backend/logs/*.ndjson` |
| | `nonograms_6.json` |
| **Outputs** | `analyze-data/out_features/solve_trajectories_individual.png` — one line per participant |
| | `analyze-data/out_features/solve_trajectories_aggregated.png` — median ± IQR band |
| | `analyze-data/out_features/solve_trajectories_first_action_heatmap.png` — first-cell frequency |

Trajectories are measured as the fraction of black cells correctly filled over elapsed time. Board state is reconstructed by replaying move/drag/undo/reset events.

---

## Step 6 — Rating Overview Figure (optional)

Generate the overview final-difficulty rating boxplot and survey dumps.

```bash
python analyze-data/extract_features.py \
  --input_glob "backend/logs/*.ndjson" \
  --out_dir analyze-data/out_features
```

| | |
|---|---|
| **Input** | `backend/logs/*.ndjson` |
| **Outputs** | `analyze-data/out_features/figures/ratings_overview_all_puzzles.png` |
| | `analyze-data/out_features/survey_dumps/{participant_id}_surveys.json` |

---

## Script Dependencies

```
extract_features.py  ← shared library (imported by steps 1, 5, and this step)
    ↑
    ├── extract_behavioral_features.py  (Step 1)  → behavioral_features.csv
    ├── solve_trajectory.py             (Step 5)  ← also provides reconstruct_final_board,
    │                                                compute_mismatches to Step 1
    └── plot_gap_distribution.py        (Step 0)

behavioral_features.csv
    ↑
    ├── behavioral_regression.py        (Step 2)
    └── spearman_ranking.py             (Step 3)  ← also provides build_win_matrix,
                                                                  fit_bradley_terry to Step 4

backend/logs/*.ndjson
    ↑
    └── regression_analysis.py          (Step 4)  ← imports from spearman_ranking.py
```

---

## Full Pipeline (run in order)

```bash
# Step 1 — required first; all downstream steps depend on this CSV
python analyze-data/extract_behavioral_features.py \
  --input_glob "backend/logs/*.ndjson" \
  --puzzles_json nonograms_6.json \
  --out_dir analyze-data/out_features

# Steps 2–5 can be run in any order after Step 1
python analyze-data/behavioral_regression.py
python analyze-data/spearman_ranking.py
python analyze-data/regression_analysis.py
python analyze-data/solve_trajectory.py

# Optional
python analyze-data/extract_features.py \
  --input_glob "backend/logs/*.ndjson" \
  --out_dir analyze-data/out_features
```
