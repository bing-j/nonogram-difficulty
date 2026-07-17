# Analysis Pipeline

This document describes the full analysis pipeline for the nonogram difficulty study.
All commands are run from the **repository root** with the virtual environment active.

```bash
source .venv/Scripts/activate   # Windows (bash)
source .venv/bin/activate        # macOS/Linux
```

---

## Participant Groups

Participants are stratified by self-reported nonogram experience (`skill_nonogram`, 1–10 scale from the pre-survey):

| Group          | skill_nonogram range |
|----------------|----------------------|
| beginner       | 1–3                  |
| intermediate   | 4–6                  |
| experienced    | 7–10                 |

Every analysis script that produces a pooled result also produces per-group figures (when ≥ 5 participants are in a group). Group suffixes follow the pattern `_beginner`, `_intermediate`, `_experienced`.

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
| `error_count` | Move events where cell is filled but solution is empty |
| `hint_count` | Hint events (excludes `hint_none`) |
| `initial_difficulty` | Rating immediately after the puzzle |
| `final_difficulty` | Retrospective rating from the post-survey |
| `solved_flag` | Whether the participant solved the puzzle |
| `skill_nonogram` | Self-reported nonogram experience (1–10) |

**This CSV is required by Steps 2, 3, and 4.**

---

## Step 2 — Behavioral Regression

OLS regression: behavioral features → difficulty ratings, pooled and per experience group.

```bash
python analyze-data/behavioral_regression.py
```

| | |
|---|---|
| **Inputs** | `analyze-data/out_features/behavioral_features.csv` |
| | `selected_six_nonogram_stats.csv` |
| **Outputs** | `analyze-data/out_features/behavioral_reg1_coef_heatmap_final_difficulty.png` |
| | `analyze-data/out_features/behavioral_reg1_coef_heatmap_final_difficulty_{group}.png` (per group) |
| | `analyze-data/out_features/behavioral_reg2_scatter_grid_decisions.png` |
| | `analyze-data/out_features/behavioral_reg2_scatter_grid_decisions_{group}.png` (per group) |

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
| **Outputs** | `analyze-data/out_features/bt_scores.png` (pooled) |
| | `analyze-data/out_features/bt_ranking_vs_sat.png` (pooled) |
| | `analyze-data/out_features/bt_scores_{group}.png` (per group) |
| | `analyze-data/out_features/bt_ranking_vs_sat_{group}.png` (per group) |

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
| | `analyze-data/out_features/behavioral_features.csv` *(optional, for groups)* |
| **Outputs** | `analyze-data/out_features/figures/spearman_rank_scatter.png` (pooled) |
| | `analyze-data/out_features/figures/regression_per_puzzle_means.png` (pooled) |
| | `analyze-data/out_features/figures/spearman_rank_scatter_{group}.png` (per group) |
| | `analyze-data/out_features/figures/regression_per_puzzle_means_{group}.png` (per group) |

If `behavioral_features.csv` is absent, the script runs the pooled analysis only and prints a warning. Per-group analysis requires Step 1 to be complete first.

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

## Step 6 — Per-Puzzle Rating Figures (optional)

Generate per-puzzle final-difficulty rating histograms and survey dumps.

```bash
python analyze-data/extract_features.py \
  --input_glob "backend/logs/*.ndjson" \
  --out_dir analyze-data/out_features
```

| | |
|---|---|
| **Input** | `backend/logs/*.ndjson` |
| **Outputs** | `analyze-data/out_features/figures/puzzle_{id}_ratings.png` (per puzzle) |
| | `analyze-data/out_features/figures/ratings_overview_all_puzzles.png` |
| | `analyze-data/out_features/survey_dumps/{participant_id}_surveys.json` |

---

## Script Dependencies

```
extract_features.py  ← shared library (imported by steps 1, 5, and this step)
    ↑
    ├── extract_behavioral_features.py  (Step 1)  → behavioral_features.csv
    ├── solve_trajectory.py             (Step 5)
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
