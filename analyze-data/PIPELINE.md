# Analysis Pipeline

This document describes the full analysis pipeline for the nonogram difficulty study.
All commands are run from the **repository root** with the virtual environment active.

```bash
source .venv/Scripts/activate   # Windows (bash)
source .venv/bin/activate        # macOS/Linux
```

---

## Participant Expertise

Participant expertise is a single continuous score, `expertise_composite`: a naive z-mean composite of six pre-survey background items (`skill_nonogram`, `skill_puzzles`, ordinal-encoded `played_before`/`puzzle_played_frequency`, and the breadth of `nonogram_size_experience`/`logic_experience` selections). Each item is z-scored across participants, averaged (skipping missing items), then re-standardized. See `expertise.py` for the implementation — ported from an earlier standalone exploratory analysis's "z-mean" method (since removed from the repo).

There are no discrete experience tiers anywhere in this pipeline: `expertise_composite` is used directly as a continuous covariate rather than being cut into groups.

---

## Step 0 — Puzzle Selection: SAT Solver Statistics (one-time, already done)

Analyze the full SAT-solver-stats candidate pool and (historically) select the study's 6 puzzles from it.

```bash
python analyze-data/solver_stats_analysis.py
```

| | |
|---|---|
| **Input** | `nonogram_solver_stats.csv` |
| **Outputs** | `analyze-data/out_features/figures/solver_stats_diagnostics/solver_stats_correlation_matrix.png` |
| | `analyze-data/out_features/figures/solver_stats_diagnostics/solver_stats_conflicts_distribution.png` |

What's live: loads `nonogram_solver_stats.csv`, prints summary stats and a correlation matrix, and plots+saves a correlation heatmap and a conflicts-distribution histogram. This opens interactive `plt.show()` windows, so it isn't meant to run unattended — like Step 1 below, it's excluded from the "Full Pipeline" batch run.

What's historical: `select_six()` (the actual 6-puzzle selection logic — pick lowest/median/highest-conflict puzzles after dropping outliers) is present in the script but commented out, to avoid overwriting the already-finalized `selected_six_nonogram_stats.csv` / `nonograms_6.json` that the rest of this pipeline depends on.

---

## Step 1 — Pause Threshold (one-time, already done)

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

## Step 2 — Extract Behavioral Features

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

**This CSV is required by Steps 3 and 4.** `total_time_spent_sec`, `check_count`, `percent_error`, and `percent_incomplete` are computed from a final-board reconstruction shared with `solve_trajectory.py` (`reconstruct_final_board`).

---

## Step 3 — Behavioral Regression

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

## Step 4 — Bradley-Terry Ranking + Spearman Correlation

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

## Step 5 — SAT vs. Human Ratings

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

## Step 6 — Solve Trajectories

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

## Step 7 — Rating Overview Figure (optional)

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

## Step 8 — Expertise Composite Diagnostics

Validate the `expertise_composite` z-mean composite (see "Participant Expertise" above) against a PCA of the same six background dimensions. This step does not recompute or modify `expertise_composite` — `expertise.py` / Step 2 remain the single source of truth. It only checks that the six dimensions form one coherent construct and that an independent PCA agrees with the z-mean composite.

```bash
python analyze-data/expertise_diagnostics.py
```

| | |
|---|---|
| **Input** | `analyze-data/out_features/behavioral_features.csv` |
| **Outputs** | `analyze-data/out_features/expertise_dimension_correlations.csv` |
| | `analyze-data/out_features/expertise_diagnostics.csv` — Cronbach's alpha, PCA variance explained, composite/PCA agreement |
| | `analyze-data/out_features/expertise_loadings.csv` |
| | `analyze-data/out_features/figures/expertise_dimension_correlations.png` |
| | `analyze-data/out_features/figures/expertise_pca_scree_loadings.png` |
| | `analyze-data/out_features/figures/expertise_composite_agreement.png` |

Ported from an earlier standalone exploratory analysis's z-mean/PCA methods (since removed from the repo; its third method, Factor Analysis, is intentionally excluded).

---

## Step 9 — Expertise-Adjusted Difficulty

Three related analyses over `expertise_composite`: (1) does expertise correlate with the behavioral signals and difficulty rating already tracked in this pipeline? (2) an expertise-adjusted per-puzzle difficulty estimate via residualization; (3) how that adjusted difficulty correlates with SAT solver metrics, compared to the raw (unadjusted) correlation.

```bash
python analyze-data/expertise_adjustment.py
```

| | |
|---|---|
| **Inputs** | `analyze-data/out_features/behavioral_features.csv` |
| | `selected_six_nonogram_stats.csv` |
| **Outputs** | `analyze-data/out_features/expertise_vs_outcomes.csv` |
| | `analyze-data/out_features/figures/expertise_vs_outcomes.png` |
| | `analyze-data/out_features/expertise_adjusted_puzzle_difficulty.csv` |
| | `analyze-data/out_features/expertise_adjustment_model_params.csv` |
| | `analyze-data/out_features/stats_expertise_adjusted_difficulty_vs_sat.csv` |
| | `analyze-data/out_features/figures/expertise_adjusted_difficulty_vs_sat.png` |

Part 1 correlates `expertise_composite` against `behavioral_regression.py`'s own `BEHAVIORAL_FEATURES` (`time_to_solve_sec`, `pause_count`, `pause_freq_per_min`, `error_count`, `hint_count`) plus `final_difficulty`. Part 2 is the **M2 residualization method only** — `final_difficulty ~ expertise_composite + C(order)`, per-puzzle mean of (residual + grand mean) — the raw per-puzzle mean is kept alongside it purely as a reference column, not as an alternative method. M1 (within-participant), M3 (mixed model), M4 (stratification — would reintroduce discrete expertise tiers, which this pipeline doesn't use anywhere), and M5 (expertise×SAT interaction) are all excluded. Part 3 Spearman-correlates the Part 2 adjusted difficulty against `decisions`/`propagations`/`conflicts`.

Ported from an earlier standalone exploratory analysis's `motivation()` and M2 methods (since removed from the repo).

---

## Step 10 — Export Free-Text Survey Responses

Export every open-text survey response (rating reasons, strategy descriptions, comments, size-experience free text) into a structured CSV, plus a human-readable dump for coding/audit.

```bash
python analyze-data/export_text_responses.py
```

| | |
|---|---|
| **Inputs** | `backend/logs/*.ndjson`, `*.json` (via `text_response_loader.py`) |
| | `nonograms_6.json` (puzzle solutions) |
| **Outputs** | `analyze-data/out_features/text_coding/text_responses.csv` |
| | `analyze-data/out_features/text_coding/text_responses_readable.txt` |

Each response gets a stable `response_id` (`R0000`, `R0001`, ...) — a deterministic index over the exact row order this step produces. **This ordering must never change**: `codes.py`'s hand-authored `CODING` dict keys are these exact IDs, assigned during the original LLM-assisted coding pass over this same ordering. Ported from an earlier standalone exploratory analysis's participant-log loader and response exporter (since removed from the repo); verified byte-identical to that analysis's original `text_responses.csv` output before removal.

---

## Step 11 — Build Coded Text Dataset

Merge the hand-authored codebook (`codes.py`) onto `text_responses.csv` and multi-hot encode every code.

```bash
python analyze-data/build_coded_dataset.py
```

| | |
|---|---|
| **Inputs** | `analyze-data/out_features/text_coding/text_responses.csv` (Step 10) |
| | `codes.py` — hand-authored codebook (13 difficulty themes, 8 strategy codes) + `CODING` map |
| **Outputs** | `analyze-data/out_features/text_coding/codebook.md` |
| | `analyze-data/out_features/text_coding/coded_responses.csv` |
| | `analyze-data/out_features/text_coding/coded_difficulty_themes.csv` |
| | `analyze-data/out_features/text_coding/coded_strategies.csv` |

`codes.py` is a verbatim port of an earlier standalone exploratory analysis's codebook (since removed from the repo) — hand-authored data, not something this pipeline recomputes. Difficulty themes apply to `rating_reason`/`comments` responses; strategy codes apply to `strategy` responses. Ported from that analysis's coded-dataset builder; verified byte-identical to its original `coded_responses.csv` output before removal.

---

## Step 12 — Text Coding Analysis: Prevalence + Rank-Biserial Correlation

Two analyses over the coded responses: how prevalent each theme/strategy is among coded responses, and whether a theme's presence tracks a higher/lower behavioral or subjective outcome (rank-biserial effect size + Mann-Whitney U).

```bash
python analyze-data/text_coding_analysis.py
```

| | |
|---|---|
| **Inputs** | `analyze-data/out_features/text_coding/coded_responses.csv` (Step 11) |
| | `backend/logs/*.ndjson`, `*.json` (via `text_response_loader.py`, for behavioral outcomes) |
| **Outputs** | `analyze-data/out_features/text_coding/stats_difficulty_theme_prevalence.csv` |
| | `analyze-data/out_features/text_coding/stats_strategy_prevalence.csv` |
| | `analyze-data/out_features/text_coding/stats_theme_vs_difficulty.csv` |
| | `analyze-data/out_features/text_coding/stats_theme_vs_behaviour.csv` |
| | `analyze-data/out_features/text_coding/stats_theme_vs_guessfreq.csv` |
| | `analyze-data/out_features/text_coding/stats_convergent_validity.csv` |
| | `analyze-data/out_features/text_coding/stats_strategy_vs_outcomes.csv` |
| | `analyze-data/out_features/figures/text_coding/01_difficulty_theme_prevalence.png` |
| | `analyze-data/out_features/figures/text_coding/02_strategy_prevalence.png` |
| | `analyze-data/out_features/figures/text_coding/03_theme_vs_difficulty.png` |
| | `analyze-data/out_features/figures/text_coding/04_convergent_validity.png` |

Prevalence = % of *coded* responses (of that response kind) containing each code. Rank-biserial correlation (via Mann-Whitney U) compares an outcome's distribution between theme-present and theme-absent responses, applied to: theme vs. final difficulty rating, theme vs. behaviour (raw + within-participant-centred `time_to_solve`/`n_hints`/`n_incorrect_submissions`/`n_actions`), theme vs. self-reported guessing frequency, a curated set of convergent-validity pairs (e.g. `HINT` theme vs. logged hint count), and strategy vs. participant-level outcomes (skill, mean solve time, mean difficulty, solve rate).

Ported from an earlier standalone exploratory analysis's text-analysis script (since removed from the repo), narrowed to prevalence + rank-biserial only — co-occurrence (Jaccard) heatmaps and the strategy-breadth-vs-outcomes Spearman correlations are excluded (neither is prevalence nor rank-biserial). All seven stats tables verified identical to that analysis's original `stats_*.csv` outputs before removal.

---

## Script Dependencies

```
extract_features.py  ← shared library (imported by steps 2, 6, and this step)
    ↑
    ├── extract_behavioral_features.py  (Step 2)  → behavioral_features.csv
    ├── solve_trajectory.py             (Step 6)  ← also provides reconstruct_final_board,
    │                                                compute_mismatches to Step 2
    └── plot_gap_distribution.py        (Step 1)

behavioral_features.csv
    ↑
    ├── behavioral_regression.py        (Step 3)
    ├── spearman_ranking.py             (Step 4)  ← also provides build_win_matrix,
    │                                                             fit_bradley_terry to Step 5
    ├── expertise_diagnostics.py        (Step 8)
    └── expertise_adjustment.py         (Step 9)

backend/logs/*.ndjson
    ↑
    └── regression_analysis.py          (Step 5)  ← imports from spearman_ranking.py

text_response_loader.py  ← shared library (independent of extract_features.py)
    ↑
    └── export_text_responses.py        (Step 10) → text_responses.csv
                                                          │
                                          codes.py (hand-authored) ─┤
                                                          ▼
                                    build_coded_dataset.py         (Step 11) → coded_responses.csv
                                                          │
                                                          ▼
                                    text_coding_analysis.py        (Step 12)  ← also calls
                                                                                text_response_loader.py
                                                                                directly for behavioural outcomes
```

---

## Full Pipeline (run in order)

```bash
# Step 2 — required first; all downstream steps depend on this CSV
python analyze-data/extract_behavioral_features.py \
  --input_glob "backend/logs/*.ndjson" \
  --puzzles_json nonograms_6.json \
  --out_dir analyze-data/out_features

# Steps 3–6 can be run in any order after Step 2
python analyze-data/behavioral_regression.py
python analyze-data/spearman_ranking.py
python analyze-data/regression_analysis.py
python analyze-data/solve_trajectory.py

# Steps 8-9 can also be run any time after Step 2
python analyze-data/expertise_diagnostics.py
python analyze-data/expertise_adjustment.py

# Steps 10-12 are independent of Steps 2-9 (their own log-parsing chain) — run in order
python analyze-data/export_text_responses.py
python analyze-data/build_coded_dataset.py
python analyze-data/text_coding_analysis.py

# Optional
python analyze-data/extract_features.py \
  --input_glob "backend/logs/*.ndjson" \
  --out_dir analyze-data/out_features
```
