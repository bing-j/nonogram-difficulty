# Pause Threshold Selection — Methods Report

**Threshold chosen:** 2.36 s  
**Script:** `analyze-data/plot_gap_distribution.py`  
**Reproduce:** `python analyze-data/extract_behavioral_features.py --pause_threshold 2.36`

---

## 1. Motivation

Behavioural difficulty signals require distinguishing *deliberate pauses* (moments where the participant stopped to think or re-evaluate) from the ordinary rhythm of interaction (moving cells, requesting hints, checking progress). The raw log records a timestamp for every interaction event; the feature of interest is the count and rate of inter-event gaps that exceed some threshold. The choice of threshold is consequential: a value that is too low conflates normal interaction speed with reflection; a value that is too high misses brief but genuine moments of hesitation.

The original threshold of 5 s was a conservative heuristic. This report documents the data-driven procedure used to replace it.

---

## 2. Data

Inter-event gaps were collected from all complete participant sessions stored in `backend/logs/*.ndjson`. One session was excluded because it was missing the survey events needed to segment puzzle windows. Only gaps *within* a single puzzle window were retained; gaps at puzzle boundaries (between the end of one puzzle and the start of the next) were excluded.

**Interaction events** included: `move`, `drag`, `hint`, `check_bank`, `reset`, `undo`, `skip_puzzle`, `puzzle_advanced`. Non-interaction events (`session_start_three`, `survey_submit`, `session_end`) were excluded before computing gaps.

| Statistic | Value |
|-----------|-------|
| Total gaps | 29,156 |
| Minimum | 0.000 s |
| Median | 1.20 s |
| 75th percentile | 3.70 s |
| 90th percentile | 10.15 s |
| 95th percentile | 16.99 s |
| Maximum | 207.5 s |

The linear-scale histogram is heavily right-skewed: most gaps are sub-second (rapid successive moves), with a long tail of multi-second delays.

---

## 3. Log-transformation rationale

Inter-event gap distributions in interaction research are typically log-normally distributed: they span several orders of magnitude (milliseconds to minutes), and the *ratio* between gap lengths is more behaviourally meaningful than the *difference*. Applying a natural-log transform compresses the range, renders the distribution approximately symmetric, and makes Gaussian mixture models (which assume normally distributed components) an appropriate modelling choice.

All mixture fitting was performed on `log(gap_s)` for gaps strictly greater than zero.

---

## 4. Exploratory plots

Four diagnostic plots were generated before fitting any model (`out_features/gap_distribution.png`):

- **Linear histogram (0–30 s):** confirms extreme right-skew; almost all density below 5 s.
- **Log-scale histogram (full range):** reveals a dominant mode near 0.5–2 s and a secondary, broader distribution extending from ~2 s to ~100 s.
- **ECDF (log x-axis):** shows that 90% of gaps fall below 9.2 s and 95% below 15.7 s.
- **Zoomed histogram (0–60 s) with candidate thresholds:** illustrates how the heuristic candidates (3 s, 5 s, 10 s, 20 s) relate to the bulk of the data.

The log-scale panel suggested possible multi-modal structure, motivating formal mixture modelling.

---

## 5. Gaussian Mixture Model fitting

### 5.1 Model selection via BIC

Gaussian Mixture Models with 1, 2, and 3 components were fitted to `log(gap_s)` using `sklearn.mixture.GaussianMixture` (full covariance, `n_init=10`, `random_state=42`). Model complexity was compared using the Bayesian Information Criterion (BIC); a lower BIC indicates a better trade-off between fit and parsimony.

| Components | BIC |
|-----------|-----|
| 1 | *baseline* |
| 2 | baseline − 2,973.7 |
| 3 | baseline − 7,387.1 |

The 3-component model achieves a BIC improvement of **7,387.1** over the single-component baseline, far exceeding the conventional significance threshold of 10. The 3-component model was therefore selected as the basis for threshold selection.

### 5.2 Component interpretation

After fitting, components were sorted by ascending mean. The three components identified were:

| Component | Mean (seconds) | SD (log-space) | Weight | Interpretation |
|-----------|---------------|----------------|--------|----------------|
| 0 | 0.012 s | 1.084 | 2.4% | **UI artifact** |
| 1 | 0.794 s | 0.642 | 62.1% | **Normal interaction** |
| 2 | 6.014 s | 0.937 | 35.5% | **Deliberate pause** |

**Component 0 (0.012 s, 2.4%)** captures gaps well below the physiological limit for deliberate action (~100–200 ms). These arise from the nonogram interface allowing multi-cell drag selections: a single drag gesture generates multiple `move` events in rapid succession with near-zero inter-event delays. This component is a UI artifact and is excluded from threshold selection.

**Component 1 (0.794 s, 62%)** represents the normal rhythm of interaction — consecutive cell fills, hint requests, and checks that flow without a distinct break in attention.

**Component 2 (6.014 s, 36%)** represents genuinely deliberate pauses: gaps during which the participant was likely reassessing their strategy, re-reading clues, or experiencing uncertainty. The mean of 6.0 s and the weight of 36% are consistent with an effortful puzzle-solving task in which participants frequently pause to think.

---

## 6. Threshold derivation: equal-posterior crossover

The pause threshold was defined as the point in log-space where the *posterior probability* of belonging to the pause component (Component 2) first equals the posterior probability of belonging to the interaction component (Component 1):

```
P(comp=2 | x) = P(comp=1 | x)
⟺  w₁ · N(x; μ₁, σ₁) = w₂ · N(x; μ₂, σ₂)
```

This equality was solved numerically using Brent's method (`scipy.optimize.brentq`) on the interval `[μ₁, μ₂]` in log-space. The root is the crossover beyond which a gap is more likely to belong to the pause component than the interaction component.

**Result:**

- Crossover in log-space: **0.857**
- Threshold in seconds: **exp(0.857) = 2.36 s**

A gap of ≥ 2.36 s is classified as a pause.

This derivation is preferable to minimising the full mixture density in `[μ₁, μ₂]` (the naive approach) because the overlapping tails of the two components mean the mixture density has no interior valley — the mixture minimum in that interval collapses to the boundary. The equal-posterior formulation is well-defined regardless of component overlap.

---

## 7. Sensitivity analysis

To assess robustness, pause counts were recomputed at 20 log-spaced thresholds spanning 2 s to 30 s (`out_features/pause_sensitivity.png`). At each threshold, the mean and standard deviation of pause count across all participant-puzzle observations were recorded.

| Threshold | Mean pause count | SD |
|-----------|-----------------|-----|
| 2 s | ~54 | ~29 |
| 2.36 s (chosen) | ~49 | ~27 |
| 5 s | ~29 | ~18 |
| 10 s | ~15 | ~10 |
| 30 s | ~3 | ~3 |

The sensitivity curve is smooth and monotonically decreasing with no discontinuities, confirming there is no better-supported natural break in the 2–30 s range beyond the one identified by the GMM. The chosen threshold sits at the lower end of the band, reflecting that at 2.36 s roughly one-third of all gaps are classified as pauses — consistent with the 35.5% weight of Component 2 in the mixture.

---

## 8. Summary and reproducibility

The 2.36 s threshold was derived by:

1. Collecting 29,156 within-puzzle inter-event gaps across all complete sessions.
2. Log-transforming the gaps and fitting a 3-component Gaussian Mixture Model.
3. Identifying the three components as a UI-artifact cluster (0.012 s), a normal-interaction cluster (0.794 s), and a deliberate-pause cluster (6.014 s).
4. Computing the equal-posterior crossover between the interaction and pause components using Brent's method, yielding **2.36 s**.

To regenerate all plots and the threshold recommendation from raw logs:
```bash
python analyze-data/plot_gap_distribution.py
```

To regenerate `behavioral_features.csv` with this threshold:
```bash
python analyze-data/extract_behavioral_features.py --pause_threshold 2.36
```

All fitted model parameters, BIC values, and the crossover computation are printed to stdout by `plot_gap_distribution.py` and are embedded in the `gap_log_intervals.png` figure annotation.
