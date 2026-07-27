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
| | `analyze-data/out_features/stats_puzzle_selection_representativeness.csv` |
| | `analyze-data/out_features/figures/solver_stats_diagnostics/puzzle_selection_representativeness.png` |

What's live: loads `nonogram_solver_stats.csv`, prints summary stats and a correlation matrix, and plots+saves a correlation heatmap and a conflicts-distribution histogram. This opens interactive `plt.show()` windows, so it isn't meant to run unattended — like Step 1 below, it's excluded from the "Full Pipeline" batch run. `plot_selection_representativeness()` is the one exception — headless (no `plt.show()`) — and reports, for all **three** SAT metrics (not just the `conflicts` the selection stratified on), each of the 6 already-selected puzzles' percentile rank within the full pool. This quantifies a real limitation: the top-5%-conflicts band was excluded before picking the "highest" puzzles, so they land around the 87th-93rd percentile pool-wide, not near the true max, on all three metrics.

What's historical: `select_six()` (the actual 6-puzzle selection logic — pick lowest/median/highest-conflict puzzles after dropping outliers) is present in the script but commented out, to avoid overwriting the already-finalized `selected_six_nonogram_stats.csv` / `nonograms_6.json` that the rest of this pipeline depends on. `plot_selection_representativeness()` reads that already-finalized CSV and does not touch this frozen logic.

---

## Step 0.5 — SAT Metric Redundancy Check

How correlated are the three SAT solver metrics used throughout this
pipeline (`decisions`, `propagations`, `conflicts`) with each other? If
`conflicts` alone captures nearly the same information as all three, that
justifies simplifying the downstream regression/ranking models to a single
predictor and explains the multicollinearity in their current 3-predictor
specifications.

```bash
python analyze-data/sat_metric_correlation.py
```

| | |
|---|---|
| **Inputs** | `nonogram_solver_stats.csv` (full 1000-puzzle pool) |
| | `selected_six_nonogram_stats.csv` (the 6 study puzzles) |
| **Outputs** | `analyze-data/out_features/stats_sat_metric_correlation.csv` |
| | `analyze-data/out_features/stats_sat_metric_vif.csv` |
| | `analyze-data/out_features/figures/sat_metric_correlation.png` |

For each sample (full pool, then the selected six), reports pairwise Pearson
r and Spearman ρ among the three metrics, R² of `decisions`/`propagations`
regressed on `conflicts` alone, and the Variance Inflation Factor of each
metric in the full 3-predictor design. On the full pool, the three metrics
are highly redundant (Pearson r = 0.90–0.93; `conflicts` alone explains
84–86% of the variance in the other two; VIF ≈ 7–9 for all three, above the
common VIF > 5 concern threshold) — the same pattern holds even more
strongly on the 6 study puzzles (r > 0.97). This is a diagnostic step, not a
model change: `PREDICTORS`/`SAT_METRICS` in `regression_analysis.py`,
`spearman_ranking.py`, and `moderation_analysis.py` still use all three
metrics; collapsing to `conflicts`-only is a follow-up decision, not made
here.

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
| | `analyze-data/out_features/behavioral_reg2_heatmap.png` |
| | `analyze-data/out_features/stats_behavioral_predictor_vif.csv` |
| | `analyze-data/out_features/stats_behavioral_vs_difficulty_per_puzzle.csv` |
| | `analyze-data/out_features/stats_behavioral_vs_difficulty_pooled.csv` |
| | `analyze-data/out_features/stats_behavioral_vs_sat_metrics.csv` |

Two regression families are run:
- **Reg 1**: `final_difficulty ~ behavioral_features` (per puzzle and pooled), plain OLS.
- **Reg 2**: `behavioral_signal ~ SAT_metric`, one crossed-random-effects LMM per behavioral-signal × SAT-metric pair (12 models: 4 signals × 3 metrics), random intercepts for `participant_id` and `puzzle_id` (Baayen, Davidson & Bates 2008) — same machinery as `moderation_analysis.py`'s `fit_crossed_lmm`. This used to be fit backwards (`SAT_metric ~ behavioral_features`, pooled OLS): a puzzle's SAT metric is a fixed, exogenous property that can't be "explained by" participant behavior, and pooling ~197-201 rows when the metric only has 6 truly distinct values (repeated ~30-40× each) overstated precision. The crossed-effects LMM fixes both the causal direction and the pseudoreplication. Same disclosed limitations as `moderation_analysis.py`'s identical situation: with only 6 puzzles, the puzzle-level variance component (and the metric's own coefficient) has an irreducible small-sample bound; `MixedLM`'s Wald inference is asymptotic, not small-sample-corrected; and the model's Gaussian-residual assumption is an approximation for the count/duration behavioral signals. Reg 2's coefficient table reports a Wald **z**-statistic, not the **t**-statistic Reg 1's OLS tables report.

Diagnostics added (CSV/console only — not surfaced in any figure): a one-time VIF (variance inflation factor) table across the 4 behavioral predictors for Reg 1, since `time_to_solve_sec` mechanically bounds pause/error opportunity — collinearity was never previously checked. Reg 1's saved coefficient tables get a Benjamini-Hochberg FDR-corrected p-value (`p_fdr`, one family per table — and, for Reg 1's per-puzzle results, one family across all puzzles×predictors together, in the new `stats_behavioral_vs_difficulty_per_puzzle.csv`), an `underpowered` flag (N < 15, since `MIN_OBS=5` permits fitting 4 predictors + intercept on as few as 5 observations), and per-model Breusch-Pagan/Shapiro-Wilk/max-Cook's-distance columns (heteroscedasticity, residual normality, leverage). Reg 2's `stats_behavioral_vs_sat_metrics.csv` has its own diagnostics instead: `var_participant`/`var_puzzle`/`var_residual` (crossed-effects variance components), `n_participants`/`n_puzzles`, `converged`/`convergence_warning` (per-model optimizer diagnostics), and one BH-FDR `p_fdr` family across all 12 tests together.

`pause_freq_per_min` (pauses per minute, normalized from `pause_count` by puzzle duration) was dropped from the behavioral-predictor set entirely on 2026-07-24 — it never produced a significant result in any model across Steps 3, 9, or 10. `pause_count` and the pause-threshold machinery (Step 1) are unaffected.

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
| | `analyze-data/out_features/stats_bt_vs_sat.csv` |
| | `analyze-data/out_features/bt_difficulty_vs_sat.csv` |
| | `analyze-data/out_features/stats_bt_model_fit.csv` |

The Bradley-Terry model corrects for the fact that each participant only sees 3 of the 6 puzzles. Within each participant's session, every pair of rated puzzles generates one pairwise comparison (higher-rated = "wins"; ties split 0.5/0.5). A global strength score θ_i is estimated via MLE. Participant-level traits that are constant across a session (e.g. expertise) cancel out exactly in a within-participant pairwise difference, so BT is already robust to them by construction — see `expertise_adjustment.py`'s docstring for the fuller explanation of why an expertise-adjusted BT variant was considered and dropped.

Diagnostics added (CSV/console only): a participant-cluster bootstrap 95% CI on each puzzle's θ (`theta_ci_lower`/`theta_ci_upper` in `bt_difficulty_vs_sat.csv` — resample `participant_id`, rebuild the win matrix, refit BT; same pattern as `moderation_analysis.py`'s bootstrap), and a likelihood-ratio goodness-of-fit test of the fitted model against the null that all puzzles are equally difficult (`stats_bt_model_fit.csv`) — previously the θ point estimates carried no uncertainty and the model's overall fit was never formally tested. The Spearman tests also get a `bt_p_fdr` column in `stats_bt_vs_sat.csv`, correcting the 3 SAT-metric tests and the 3 behavioral-aggregate tests as two separate Benjamini-Hochberg families per rating column (previously uncorrected, despite `decisions`/`propagations`/`conflicts` being highly intercorrelated — see Step 0.5).

---

## Step 5 — Raw Difficulty Means vs. SAT Metrics

Raw (non-BT) per-puzzle mean difficulty vs. SAT solver metrics, with error bars — the narrow companion to Step 4's BT-based analysis.

```bash
python analyze-data/regression_analysis.py
```

| | |
|---|---|
| **Inputs** | `analyze-data/out_features/behavioral_features.csv` |
| | `selected_six_nonogram_stats.csv` |
| **Outputs** | `analyze-data/out_features/figures/regression_per_puzzle_means.png` |

This used to also independently re-derive Bradley-Terry rankings and Spearman ρ vs. SAT metrics from raw `backend/logs/*.ndjson` via its own separately-written extraction/BT-fitting path — duplicating Step 4's exact analysis through a second implementation, with no single authoritative number to cite if the two ever diverged. Removed: this step now consumes `behavioral_features.csv` like every other downstream step (via `spearman_ranking.py`'s `load_features`/`load_solver_stats`) and computes only the one thing Step 4 doesn't — raw per-puzzle mean `final_difficulty` (not BT-based). `stats_bt_vs_sat.csv` / `bt_difficulty_vs_sat.csv` (Step 4) remain the single source of truth for the BT-based SAT-metric correlation claim.

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

## Step 9 — Expertise vs. Behavior and Difficulty

Does `expertise_composite` correlate with the behavioral signals and difficulty rating already tracked in this pipeline?

```bash
python analyze-data/expertise_adjustment.py
```

| | |
|---|---|
| **Inputs** | `analyze-data/out_features/behavioral_features.csv` |
| **Outputs** | `analyze-data/out_features/expertise_vs_outcomes.csv` |
| | `analyze-data/out_features/figures/expertise_vs_outcomes.png` |

Correlates `expertise_composite` against `behavioral_regression.py`'s own `BEHAVIORAL_FEATURES` (`time_to_solve_sec`, `pause_count`, `error_count`, `hint_count`) plus `final_difficulty`, aggregated to participant-level means. The 5 tests are now Benjamini-Hochberg FDR-corrected as one family (`spearman_p_fdr` column, previously uncorrected).

This step used to also produce an expertise-adjusted per-puzzle difficulty estimate via OLS residualization (`final_difficulty ~ expertise_composite + C(order)`, per-puzzle mean of residual + grand mean), correlated against SAT metrics. That was removed: it corrected raw per-puzzle *means* for imbalanced rater composition, but this pipeline's actual per-puzzle difficulty measure is Step 4's Bradley-Terry ranking, not raw means — and BT's within-participant pairwise design already cancels out participant-level traits like expertise by construction, so composing it into BT would have had zero effect on the ranking. See `expertise_adjustment.py`'s docstring for the fuller explanation.

---

## Step 10 — Moderation: Does Expertise Change How SAT Metrics Predict Difficulty?

Tests whether `expertise_composite` moderates the relationship between SAT solver metrics and retrospective difficulty rating — i.e. whether the slope relating SAT hardness to reported difficulty differs by expertise level, via a crossed-random-effects linear mixed model plus simple-slopes analysis.

```bash
python analyze-data/moderation_analysis.py
```

| | |
|---|---|
| **Inputs** | `analyze-data/out_features/behavioral_features.csv` |
| | `selected_six_nonogram_stats.csv` |
| **Outputs** | `analyze-data/out_features/stats_moderation_expertise.csv` |
| | `analyze-data/out_features/figures/moderation_expertise.png` |
| | `analyze-data/out_features/stats_moderation_behavioral.csv` |
| | `analyze-data/out_features/figures/moderation_behavioral_heatmap.png` |

For each SAT metric, fits `final_difficulty ~ SAT_metric * expertise_composite` as a linear mixed model with **crossed random intercepts for participant and puzzle** (statsmodels `MixedLM` via the variance-components workaround, since it has no native `(1|a)+(1|b)` syntax) — the standard specification for "participant crossed with item" designs (Baayen, Davidson & Bates 2008). This replaces an earlier participant-only cluster bootstrap, which corrected for repeated measures within a participant but ignored that the SAT metric itself is clustered by puzzle (only 6 distinct values). The model reports the participant/puzzle/residual variance components directly, so puzzle-level uncertainty is visible rather than hidden — though with only 6 puzzles that component is inherently imprecise, a data-collection limitation no method removes. Interaction is visualized via **simple slopes** (Aiken & West 1991) at expertise z = −1/0/+1 (representative low/average/high levels, since `expertise_composite` is already a population z-score by construction) with delta-method CIs, replacing a tercile split of the sample — dichotomizing a continuous moderator discards information and is best avoided. Moderation is the right frame here, not mediation: expertise is a participant trait fixed before a participant sees any puzzle, and puzzles are assigned independent of expertise (round-robin schedule), so a puzzle-level SAT metric cannot causally act *through* expertise — but expertise can still change how strongly the metric predicts a given participant's rating. Note: `MixedLM`'s Wald inference is asymptotic (z-based), not Satterthwaite/Kenward-Roger small-sample-corrected like R's `lmerTest` — worth a sensitivity cross-check in R if reviewers push on it.

The same crossed-effects-LMM + simple-slopes test also runs against the four canonical behavioral outcomes (`pause_count`, `time_to_solve_sec`, `error_count`, `hint_count` — matching `behavioral_regression.py`'s `BEHAVIORAL_FEATURES`), so a reader can check whether expertise moderates SAT-metric effects on behavior the same way it moderates their effect on reported difficulty. Results combine with the `final_difficulty` rows into `stats_moderation_behavioral.csv` (15 rows: 5 outcomes × 3 SAT metrics) and a comparison heatmap, `moderation_behavioral_heatmap.png` — colored by the interaction **z-statistic** (β/SE) rather than the raw coefficient, since outcomes span incompatible units (Likert points, seconds, raw counts) and a shared raw-coefficient scale would be dominated by `time_to_solve_sec`; each cell is still annotated with its own raw β in native units. Two of the four behavioral outcomes are non-negative counts and one is a right-skewed duration, unlike the ~ordinal 1-5 scale the Gaussian-residual LMM was built for — following this repo's existing convention of using raw untransformed continuous outcomes (as in `behavioral_regression.py`'s OLS and `expertise_adjustment.py`'s Spearman correlations), no transform is applied, so treat these p-values/CIs as approximate. The original `final_difficulty`-only outputs (`stats_moderation_expertise.csv`, `moderation_expertise.png`) are unchanged and continue to feed `analyze-data/latex/render_correlation_tables_latex.py`.

---

## Step 11 — Export Free-Text Survey Responses

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

## Step 12 — Build Coded Text Dataset

Merge the hand-authored codebook (`codes.py`) onto `text_responses.csv` and multi-hot encode every code.

```bash
python analyze-data/build_coded_dataset.py
```

| | |
|---|---|
| **Inputs** | `analyze-data/out_features/text_coding/text_responses.csv` (Step 11) |
| | `codes.py` — hand-authored codebook (13 difficulty themes, 8 strategy codes) + `CODING` map |
| **Outputs** | `analyze-data/out_features/text_coding/codebook.md` |
| | `analyze-data/out_features/text_coding/coded_responses.csv` |
| | `analyze-data/out_features/text_coding/coded_difficulty_themes.csv` |
| | `analyze-data/out_features/text_coding/coded_strategies.csv` |
| | `analyze-data/out_features/text_coding/coding_coverage.csv` — per-response-kind total/codeable/coded counts (previously console-output only) |

`codes.py` is a verbatim port of an earlier standalone exploratory analysis's codebook (since removed from the repo) — hand-authored data, not something this pipeline recomputes. Difficulty themes apply to `rating_reason`/`comments` responses; strategy codes apply to `strategy` responses. Ported from that analysis's coded-dataset builder; verified byte-identical to its original `coded_responses.csv` output before removal.

---

## Step 13 — Text Coding Analysis: Prevalence + Rank-Biserial Correlation

Two analyses over the coded responses: how prevalent each theme/strategy is among coded responses, and whether a theme's presence tracks a higher/lower behavioral or subjective outcome (rank-biserial effect size + Mann-Whitney U).

```bash
python analyze-data/text_coding_analysis.py
```

| | |
|---|---|
| **Inputs** | `analyze-data/out_features/text_coding/coded_responses.csv` (Step 12) |
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

Prevalence = % of *coded* responses (of that response kind) containing each code. Rank-biserial correlation (via Mann-Whitney U) compares an outcome's distribution between theme-present and theme-absent responses, applied to: theme vs. final difficulty rating, theme vs. behaviour (raw + within-participant-centred `time_to_solve`/`n_hints`/`n_incorrect_submissions`/`n_actions`), theme vs. self-reported guessing frequency, a curated set of convergent-validity pairs (e.g. `HINT` theme vs. logged hint count), and strategy vs. participant-level outcomes (skill, mean solve time, mean difficulty, solve rate). Benjamini-Hochberg FDR correction (`mw_p_fdr`, via the shared `stats_utils.benjamini_hochberg`) is applied per test family; it already covered the theme-vs-difficulty/behaviour/guessing blocks and now also covers convergent validity (6 tests) and strategy-vs-outcomes (up to 32 tests), which were previously uncorrected.

Ported from an earlier standalone exploratory analysis's text-analysis script (since removed from the repo), narrowed to prevalence + rank-biserial only — co-occurrence (Jaccard) heatmaps and the strategy-breadth-vs-outcomes Spearman correlations are excluded (neither is prevalence nor rank-biserial). All seven stats tables verified identical to that analysis's original `stats_*.csv` outputs before removal.

---

## Known Limitations

Surfaced by a methodology audit conducted ahead of paper submission. The
statistical-rigor gaps found (missing multiple-comparisons correction,
undiagnosed collinearity/OLS assumptions, no BT model CIs, uncorrected
qualitative-coding test families) were fixed pipeline-wide (see Steps 0, 3,
4, 9, 12, 13 above). These remaining items were explicitly scoped out for
now — documented here so they're tracked for the paper's limitations section
/ future work rather than silently dropped:

- **Board-state reconstruction is unvalidated against ground truth.** Every
  script that reconstructs board state by replaying `move`/`drag`/`undo`/
  `reset` events (`extract_behavioral_features.py`, `solve_trajectory.py`)
  does so via code that mirrors the backend's logic, but is never
  automatically cross-checked against the `mismatches` array the backend
  independently logs at every `check_bank` event — the actual ground truth
  is sitting in the logs, unused for validation.
- **`error_count` conflates exploratory fill/undo cycling with genuine
  unrecovered mistakes**, and excludes drag-fills entirely (drag events
  don't log per-cell coordinates) — a real construct-validity gap for a
  predictor used throughout Steps 3 and 9.
- **`time_to_solve_sec` conflates near-instant abandonment with fast
  solving**: when a puzzle is never solved, it falls back to full session
  duration (or is near-zero for an immediate skip), and no script filters or
  controls for `solved_flag` when using it as a regressor.
- **Participant attrition is uncounted.** Sessions missing
  `session_start_three` or a required survey are dropped wholesale
  (`extract_behavioral_features.py`), with only a printed message — no tally
  of how many participants/rows were excluded, and no check for whether
  droppers differ systematically (e.g. higher difficulty, lower expertise)
  from completers.
- **No inter-rater reliability check anywhere for the qualitative
  codebook** (13 difficulty themes, 8 strategy codes) — it was coded in a
  single LLM-assisted pass with no second coder, no Cohen's/Fleiss' kappa,
  and no percent-agreement statistic. This is the single most reviewer-
  visible gap found in the audit and the most involved to close (would need
  an independent second coding pass); out of scope for the statistical-rigor
  pass above.
- **`Michael-p11`'s `final_difficulty` was imputed, not participant-
  submitted.** This participant skipped all 3 puzzles without solving any
  (`solved_flags: [false, false, false]`), and their `post` survey
  submission was missing `puzzle_1/2/3_rate_again` entirely (not blank —
  the keys didn't exist), which otherwise silently dropped them from any
  analysis conditioned on `final_difficulty` (e.g.
  `moderation_analysis.py`'s crossed-effects models fell to n=66). Fixed
  2026-07-24 by editing `backend/logs/Michael-p11.ndjson` directly to set
  `puzzle_1_rate_again=4`, `puzzle_2_rate_again=4`, `puzzle_3_rate_again=5`
  — copied from that same participant's own initial per-puzzle `difficulty`
  ratings (the only genuine difficulty signal they produced), since no
  other rating exists to substitute. Any analysis using this participant's
  `final_difficulty` should be aware it's an imputed value, not a distinct
  re-rating.

---

## Script Dependencies

```
nonogram_solver_stats.csv + selected_six_nonogram_stats.csv
    ↑
    └── sat_metric_correlation.py        (Step 0.5)

extract_features.py  ← shared library (imported by steps 2, 6, and this step)
    ↑
    ├── extract_behavioral_features.py  (Step 2)  → behavioral_features.csv
    ├── solve_trajectory.py             (Step 6)  ← also provides reconstruct_final_board,
    │                                                compute_mismatches to Step 2
    └── plot_gap_distribution.py        (Step 1)

behavioral_features.csv
    ↑
    ├── behavioral_regression.py        (Step 3)
    ├── spearman_ranking.py             (Step 4)  ← also provides load_features,
    │                                                load_solver_stats to Step 5
    ├── regression_analysis.py          (Step 5)  ← imports load_features/load_solver_stats
    │                                                from spearman_ranking.py; no longer
    │                                                touches backend/logs directly (see Step 5)
    ├── expertise_diagnostics.py        (Step 8)
    ├── expertise_adjustment.py         (Step 9)
    └── moderation_analysis.py          (Step 10)

stats_utils.py  ← shared library (benjamini_hochberg FDR correction)
    ↑
    used by: behavioral_regression.py (3), spearman_ranking.py (4),
             expertise_adjustment.py (9), text_coding_analysis.py (13)

text_response_loader.py  ← shared library (independent of extract_features.py)
    ↑
    └── export_text_responses.py        (Step 11) → text_responses.csv
                                                          │
                                          codes.py (hand-authored) ─┤
                                                          ▼
                                    build_coded_dataset.py         (Step 12) → coded_responses.csv
                                                          │
                                                          ▼
                                    text_coding_analysis.py        (Step 13)  ← also calls
                                                                                text_response_loader.py
                                                                                directly for behavioural outcomes
```

---

## Full Pipeline (run in order)

```bash
# Step 0.5 — diagnostic, independent of the rest of the pipeline
python analyze-data/sat_metric_correlation.py

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

# Steps 8-10 can also be run any time after Step 2
python analyze-data/expertise_diagnostics.py
python analyze-data/expertise_adjustment.py
python analyze-data/moderation_analysis.py

# Steps 11-13 are independent of Steps 2-10 (their own log-parsing chain) — run in order
python analyze-data/export_text_responses.py
python analyze-data/build_coded_dataset.py
python analyze-data/text_coding_analysis.py

# Optional
python analyze-data/extract_features.py \
  --input_glob "backend/logs/*.ndjson" \
  --out_dir analyze-data/out_features
```
