"""
build_coded_dataset.py
========================
Step 11 - Merge the thematic coding (codes.py) with the exported response
table and emit analysis-ready, multi-hot coded datasets + a human-readable
codebook.

Ported from an earlier standalone exploratory analysis's coded-dataset builder
(since removed from the repo).

Inputs
------
- analyze-data/out_features/text_coding/text_responses.csv (Step 10)
- codes.py (hand-authored codebook + coding)

Outputs
-------
- analyze-data/out_features/text_coding/codebook.md
- analyze-data/out_features/text_coding/coded_responses.csv
- analyze-data/out_features/text_coding/coded_difficulty_themes.csv
- analyze-data/out_features/text_coding/coded_strategies.csv

Usage
-----
  python analyze-data/build_coded_dataset.py
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from codes import (  # noqa: E402
    ALL_DIFFICULTY_CODES,
    ALL_STRATEGY_CODES,
    CODING,
    DIFFICULTY_THEMES,
    STRATEGY_TAXONOMY,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT_DIR = REPO_ROOT / "analyze-data" / "out_features" / "text_coding"

# Text values that mean "no informative content".
EMPTY_TOKENS = {"", "nan", "na", "n/a", "no", "no!", "none", "not applicable",
                "nothing else.", "no.", "no, i think i answered this in my other questions."}


def is_codeable(text: str) -> bool:
    return str(text).strip().lower() not in EMPTY_TOKENS


def validate() -> None:
    valid = set(ALL_DIFFICULTY_CODES) | set(ALL_STRATEGY_CODES)
    for rid, codes in CODING.items():
        for c in codes:
            if c not in valid:
                raise ValueError(f"{rid}: unknown code {c}")


def write_codebook(out_dir: Path) -> None:
    lines = ["# Nonogram open-text codebook", ""]
    lines.append("Grounded, bottom-up coding scheme built by reading every free-text response "
                 "in `backend/logs`. Multi-label: a response can receive several codes.")
    lines.append("")
    lines.append("## Difficulty themes (applied to `rating_reason` + `comments`)")
    lines.append("")
    lines.append("| Code | Theme | Definition |")
    lines.append("|---|---|---|")
    for code, meta in DIFFICULTY_THEMES.items():
        lines.append(f"| `{code}` | {meta['name']} | {meta['definition']} |")
    lines.append("")
    lines.append("## Strategy taxonomy (applied to `strategy`)")
    lines.append("")
    lines.append("| Code | Strategy | Definition |")
    lines.append("|---|---|---|")
    for code, meta in STRATEGY_TAXONOMY.items():
        lines.append(f"| `{code}` | {meta['name']} | {meta['definition']} |")
    lines.append("")
    (out_dir / "codebook.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="Merge codes.py onto text_responses.csv into multi-hot coded datasets.")
    ap.add_argument("--text_responses_csv", type=Path, default=DEFAULT_OUT_DIR / "text_responses.csv")
    ap.add_argument("--out_dir", type=Path, default=DEFAULT_OUT_DIR)
    args = ap.parse_args()

    if not args.text_responses_csv.exists():
        print(f"Text responses CSV not found: {args.text_responses_csv}")
        print("Run export_text_responses.py first.")
        return

    args.out_dir.mkdir(parents=True, exist_ok=True)

    validate()
    write_codebook(args.out_dir)

    df = pd.read_csv(args.text_responses_csv)
    df["codeable"] = df["text"].map(is_codeable)
    df["codes"] = df["response_id"].map(lambda r: CODING.get(r, []))
    df["n_codes"] = df["codes"].map(len)

    # Multi-hot encode every code.
    for code in ALL_DIFFICULTY_CODES + ALL_STRATEGY_CODES:
        df[f"code_{code}"] = df["codes"].map(lambda cs, c=code: int(c in cs))

    df["codes_str"] = df["codes"].map(lambda cs: "|".join(cs))
    df.drop(columns=["codes"]).to_csv(args.out_dir / "coded_responses.csv", index=False)

    # Split tables.
    diff = df[df["response_kind"].isin(["rating_reason", "comments"])].copy()
    diff_cols = ["response_id", "participant_id", "response_kind", "order", "puzzle_id",
                 "final_difficulty", "immediate_difficulty", "skill_nonogram",
                 "codeable", "n_codes", "codes_str"] + [f"code_{c}" for c in ALL_DIFFICULTY_CODES]
    diff[diff_cols].to_csv(args.out_dir / "coded_difficulty_themes.csv", index=False)

    strat = df[df["response_kind"] == "strategy"].copy()
    strat_cols = ["response_id", "participant_id", "skill_nonogram",
                  "codeable", "n_codes", "codes_str"] + [f"code_{c}" for c in ALL_STRATEGY_CODES]
    strat[strat_cols].to_csv(args.out_dir / "coded_strategies.csv", index=False)

    # Coverage report.
    print("=== Coding coverage ===")
    for kind in ["rating_reason", "comments", "strategy", "size_experience_other"]:
        sub = df[df["response_kind"] == kind]
        n = len(sub)
        codeable = int(sub["codeable"].sum())
        coded = int((sub["n_codes"] > 0).sum())
        print(f"{kind:22s} total={n:3d}  codeable={codeable:3d}  coded={coded:3d}")
    # Sanity: every coded response should be codeable.
    bad = df[(df["n_codes"] > 0) & (~df["codeable"])]
    print(f"\ncoded-but-flagged-empty (should be 0): {len(bad)}")
    coded_diff = diff[diff["n_codes"] > 0]
    print(f"\ndifficulty responses coded: {len(coded_diff)}; "
          f"mean codes/response = {coded_diff['n_codes'].mean():.2f}")
    print(f"strategy responses coded: {int((strat['n_codes']>0).sum())}; "
          f"mean codes/response = {strat[strat['n_codes']>0]['n_codes'].mean():.2f}")
    print(f"\nWrote codebook.md, coded_responses.csv, coded_difficulty_themes.csv, coded_strategies.csv -> {args.out_dir}")
    print("\nDone.")


if __name__ == "__main__":
    main()
