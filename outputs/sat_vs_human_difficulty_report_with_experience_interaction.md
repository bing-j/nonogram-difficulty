# SAT Solver Statistics vs Human-Evaluated Nonogram Difficulty

## 1. Research Question

How do SAT solver statistics correlate with human-evaluated puzzle difficulty?

## 2. Data Summary

The cleaned participant-puzzle dataset contains:

- Participants: 68
- Puzzles: 6
- Participant-puzzle attempts: 204
- Completed attempts: 176
- Incomplete attempts: 28
- Missing initial ratings: 4
- Missing final adjusted ratings: 30
- Missing rating-change values: 30

Puzzle assignment was not perfectly balanced. Puzzle assignment counts ranged from 29 to 42 attempts per puzzle. Order-position counts ranged from 7 to 18 within puzzle-by-order cells, and puzzle-pair counts ranged from 6 to 22. This is acceptable for exploratory analysis, but assignment imbalance should be kept in mind when interpreting human ratings.

## 3. Human Difficulty Measure

The primary human difficulty measure is `mean_final_rating`, based on participants' final adjusted difficulty ratings. This is preferred over the initial rating because participants rated each puzzle again after seeing all 3 puzzles in their session, giving them a chance to recalibrate difficulty judgments against the other puzzles they solved.

## 4. Main Method

The main analysis is puzzle-level. SAT solver statistics vary only by puzzle, not by participant-puzzle attempt, so the effective sample size for SAT-vs-human comparisons is 6 puzzles, not 204 participant-puzzle rows.

For this reason, the main analysis compares each SAT statistic separately against `mean_final_rating` using Spearman rank correlation, Kendall tau, and Pearson correlation as a secondary descriptive check. A multiple regression using conflicts, decisions, propagations, and SAT time together is not appropriate here because there are only 6 puzzle-level observations and the SAT statistics are likely correlated.

## 5. Main Results

The strongest Spearman association with `mean_final_rating` was for `conflicts` with rho = 0.121. This is a very small association.

The strongest Kendall association by absolute value was for `decisions` with tau = 0.138. This is also very small.

Pearson correlations were somewhat larger descriptively, with `propagations` highest at r = 0.469, but Pearson is secondary here and unstable with only 6 observations.

Overall, the main puzzle-level evidence does not show a strong monotonic relationship between MiniSat22 statistics and mean final human difficulty ratings.

## 6. Ranking Comparison

Human difficulty ranking used `mean_final_rating`, with rank 1 as easiest and rank 6 as hardest.

Spearman correlations between the primary human ranking and SAT-based rankings were small:

- conflicts_rank: rho = 0.121
- decisions_rank: rho = 0.116
- propagations_rank: rho = 0.116
- sat_time_rank: rho = -0.029
- log_conflicts_rank: rho = 0.121
- log_decisions_rank: rho = 0.116
- log_propagations_rank: rho = 0.116
- log_sat_time_rank: rho = -0.029

This suggests that the SAT statistics do not rank the 6 puzzles in a similar easiest-to-hardest order as the human final ratings.

## 7. Sensitivity Checks

Sensitivity checks gave mixed but still exploratory results:

- completion_rate_harder_low: strongest Spearman with decisions, rho = -0.812
- mean_centered_final_rating: strongest Spearman with conflicts, rho = 0.478
- mean_final_rating_max_incomplete: strongest Spearman with sat_time_to_solve, rho = -0.257
- mean_human_time_to_solve: strongest Spearman with decisions, rho = 0.429
- mean_initial_rating: strongest Spearman with decisions, rho = 0.257

Initial ratings, participant-centered final ratings, completion rate, and human solve time do not produce a stable conclusion that SAT statistics strongly reproduce human difficulty. Completion-rate sensitivity is especially inconsistent with the primary rating-based ordering.

## 8. Incomplete Data

The main rating analysis uses available final adjusted ratings. Incomplete attempts remain in assignment and completion-rate summaries, but they do not contribute a final rating when no final adjusted rating was submitted.

As a sensitivity check, incomplete attempts without usable final ratings were treated as maximum difficulty. Under that approach, the SAT correlations did not become stronger in a way that changes the conclusion. The main finding remains that SAT statistics do not clearly align with human-evaluated difficulty in this 6-puzzle dataset.

## 9. Robustness Model

A secondary participant-level robustness check was also run. This is not the main analysis because SAT statistics vary only across 6 puzzles; expanding to participant-level rows does not increase the effective sample size for SAT statistics.

Mixed-effects modeling was unavailable in the current environment, so the script used fallback OLS models with participant-clustered standard errors:

`final_rating ~ SAT_stat + order + experience_level`

Each SAT statistic was modeled separately. The largest standardized fallback-model coefficient was for `propagations` at beta = 0.205.

- propagations: beta = 0.205, SE = 0.064, p = 0.001
- log_propagations: beta = 0.187, SE = 0.064, p = 0.003
- conflicts: beta = 0.184, SE = 0.063, p = 0.004
- decisions: beta = 0.181, SE = 0.067, p = 0.007

These participant-level models should be interpreted only as robustness checks. They partly support a positive association for some SAT statistics, but they do not override the weaker puzzle-level rank correlations.

## 10. Conclusion

Among the SAT solver statistics, `propagations` appears most aligned with human-evaluated difficulty in some secondary summaries. However, the primary rank-based puzzle-level analysis shows only very weak associations, with `conflicts` having the largest Spearman rho at only 0.121.

The safest conclusion is that MiniSat22 statistics show at most weak exploratory alignment with human-evaluated difficulty in this dataset. No SAT statistic clearly reproduces the human easiest-to-hardest ordering.

Key limitations:

- There are only 6 puzzles, so puzzle-level analyses have an effective sample size of 6.
- SAT time varies over a very small range, making it especially hard to interpret.
- Human ratings may depend on participant experience, puzzle order, and which other puzzles were shown in the same session.
- Puzzle assignment was not perfectly balanced.
- Results should be treated as exploratory rather than confirmatory.

## 11. Participant Experience Interaction Analysis

This analysis was added to test whether SAT solver statistics align better or worse with human difficulty ratings depending on participant background experience.

Experience was encoded from `experience_level`, which comes from the pre-survey `skill_nonogram` response. The numeric 1-10 value was preserved and z-scored as `z_experience` for interaction models. For grouped summaries, correlations, and plots, experience was grouped as beginner = 1-3, intermediate = 4-6, and experienced = 7-10.

Experience availability:

- Missing participant-puzzle rows: 3
- Participants with missing experience: 1

Grouped experience counts:

- beginner: 27 participants, 81 rows
- experienced: 19 participants, 57 rows
- intermediate: 21 participants, 63 rows
- missing: 1 participants, 3 rows

Separate models were fit for each SAT statistic:

`final_rating ~ z_SAT_stat * z_experience + C(order)`

Mixed-effects modeling was unavailable in this environment, so the analysis used OLS with participant-clustered standard errors. Puzzle fixed effects were not included because SAT statistics vary only by puzzle and would be collinear with puzzle indicators.

The strongest SAT-by-experience interaction by absolute estimate was for `sat_time_to_solve`:

- sat_time_to_solve: interaction estimate = -0.134, SE = 0.054, p = 0.014
- log_sat_time: interaction estimate = -0.134, SE = 0.054, p = 0.014
- decisions: interaction estimate = -0.114, SE = 0.056, p = 0.043
- log_decisions: interaction estimate = -0.095, SE = 0.056, p = 0.091

These interaction terms should not be overinterpreted. They are exploratory, and the effective SAT-level variation is still only 6 puzzles.

Group-specific Spearman correlations between group-level `mean_final_rating` and SAT statistics were:

- beginner: strongest Spearman with decisions, rho = 0.657, n_puzzles = 6
- experienced: strongest Spearman with decisions, rho = -0.143, n_puzzles = 6
- intermediate: strongest Spearman with conflicts, rho = 0.717, n_puzzles = 6

Overall, there is some suggestion that alignment differs by experience group, but the pattern is not stable enough to change the main conclusion. The experience interaction analysis does not provide strong evidence that SAT statistics reliably track human difficulty for one experience group more than another.

Limitations:

- This is exploratory.
- SAT statistics still vary only across 6 puzzles.
- Experience groups have modest sample sizes.
- Participant ratings may be affected by order and by which other puzzles they saw.
- Interaction p-values should not be overinterpreted.

