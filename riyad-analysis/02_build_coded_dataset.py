"""
Step 02 - Merge the thematic coding (codes.py) with the response table and emit
analysis-ready, multi-hot coded datasets + a human-readable codebook.

Outputs under riyad-analysis/derived/:
  * codebook.md                  - the codebook + strategy taxonomy
  * coded_responses.csv          - every response, multi-hot code columns, context
  * coded_difficulty_themes.csv  - rating_reason + comments only (theme columns)
  * coded_strategies.csv         - strategy responses only (strategy columns)
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from codes import (
    ALL_DIFFICULTY_CODES,
    ALL_STRATEGY_CODES,
    CODING,
    DIFFICULTY_THEMES,
    STRATEGY_TAXONOMY,
)

HERE = Path(__file__).resolve().parent
DERIVED = HERE / "derived"

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


def write_codebook() -> None:
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
    (DERIVED / "codebook.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    validate()
    write_codebook()

    df = pd.read_csv(DERIVED / "text_responses.csv")
    df["codeable"] = df["text"].map(is_codeable)
    df["codes"] = df["response_id"].map(lambda r: CODING.get(r, []))
    df["n_codes"] = df["codes"].map(len)

    # Multi-hot encode every code.
    for code in ALL_DIFFICULTY_CODES + ALL_STRATEGY_CODES:
        df[f"code_{code}"] = df["codes"].map(lambda cs, c=code: int(c in cs))

    df["codes_str"] = df["codes"].map(lambda cs: "|".join(cs))
    df.drop(columns=["codes"]).to_csv(DERIVED / "coded_responses.csv", index=False)

    # Split tables.
    diff = df[df["response_kind"].isin(["rating_reason", "comments"])].copy()
    diff_cols = ["response_id", "participant_id", "response_kind", "order", "puzzle_id",
                 "final_difficulty", "immediate_difficulty", "skill_nonogram",
                 "codeable", "n_codes", "codes_str"] + [f"code_{c}" for c in ALL_DIFFICULTY_CODES]
    diff[diff_cols].to_csv(DERIVED / "coded_difficulty_themes.csv", index=False)

    strat = df[df["response_kind"] == "strategy"].copy()
    strat_cols = ["response_id", "participant_id", "skill_nonogram",
                  "codeable", "n_codes", "codes_str"] + [f"code_{c}" for c in ALL_STRATEGY_CODES]
    strat[strat_cols].to_csv(DERIVED / "coded_strategies.csv", index=False)

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
    print("\nWrote codebook.md, coded_responses.csv, coded_difficulty_themes.csv, coded_strategies.csv")


if __name__ == "__main__":
    main()
