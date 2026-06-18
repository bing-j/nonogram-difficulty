# riyad-analysis

Self-contained, **read-only** analysis package for two tasks on the Nonogram
study. Nothing in the parent repository (logs, scripts, outputs) is modified;
everything new lives here.

1. **Open-text thematic coding** of participants' free-text answers (difficulty
   explanations, strategy descriptions, general comments) and quantitative
   analysis of the resulting codes against behavioural / subjective / expertise
   variables.
2. **Expertise adjustment**: building a composite expertise score and comparing
   several principled ways to factor reported expertise into reported and
   behavioural difficulty.

## Layout

| File | Purpose |
|---|---|
| `nono_data.py` | Read-only loader: parses `backend/logs/*` into participant-puzzle, text, and solver tables. |
| `analysis_utils.py` | Shared stats (Mann-Whitney, point-biserial, Cohen's d, BH-FDR) + plotting setup. |
| `codes.py` | The codebook (difficulty themes + strategy taxonomy) and the hand-authored thematic coding. |
| `01_export_text_responses.py` | Dumps every free-text response to `derived/`. |
| `02_build_coded_dataset.py` | Merges coding with responses; writes `derived/codebook.md` + coded CSVs. |
| `03_analyze_text.py` | Figures + stats for the coded text (prevalence, co-occurrence, code-vs-variable, strategy). |
| `04_build_expertise_score.py` | Composite expertise (z-mean / PCA / factor analysis) + diagnostics. |
| `05_expertise_adjustment.py` | Five adjustment methods on subjective & behavioural difficulty. |
| `REPORT.md` | Narrative writeup of methods, findings, figures, and recommendations. |
| `derived/` | Generated CSVs, codebook, coded datasets. |
| `figures/` | Generated PNG figures (`text/`, `expertise/`, `expertise_adjustment/`). |

## Run

```bash
bash riyad-analysis/run_all.sh
```

This creates a local `.venv` (Python 3.12) with pandas/numpy/scipy/scikit-learn/
matplotlib/statsmodels if needed and runs steps 01-05 in order.
