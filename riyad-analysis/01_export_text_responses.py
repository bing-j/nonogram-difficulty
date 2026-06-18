"""
Step 01 - Export every free-text response into structured, READ-ONLY artifacts.

Outputs (all written under riyad-analysis/derived/, none touch the repo):
  * text_responses.csv          - one row per response (machine readable)
  * text_responses_readable.txt - grouped & numbered for human/LLM coding
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from nono_data import load_text_responses

HERE = Path(__file__).resolve().parent
DERIVED = HERE / "derived"
DERIVED.mkdir(exist_ok=True)


def main() -> None:
    df = load_text_responses().reset_index(drop=True)
    # Stable response id so coding can be merged back deterministically.
    df.insert(0, "response_id", [f"R{idx:04d}" for idx in range(len(df))])
    df.to_csv(DERIVED / "text_responses.csv", index=False)

    lines: list[str] = []
    for kind in ["rating_reason", "strategy", "comments", "size_experience_other"]:
        sub = df[df["response_kind"] == kind]
        lines.append("=" * 100)
        lines.append(f"RESPONSE KIND: {kind}   (n = {len(sub)})")
        lines.append("=" * 100)
        for _, r in sub.iterrows():
            ctx = []
            if pd.notna(r.get("puzzle_id")):
                ctx.append(f"puzzle={int(r['puzzle_id'])}")
            if pd.notna(r.get("order")):
                ctx.append(f"order={int(r['order'])}")
            if pd.notna(r.get("final_difficulty")):
                ctx.append(f"final_diff={int(r['final_difficulty'])}")
            if pd.notna(r.get("skill_nonogram")):
                ctx.append(f"skill_nono={int(r['skill_nonogram'])}")
            ctx_str = ", ".join(ctx)
            lines.append(f"[{r['response_id']}] ({r['participant_id']}; {ctx_str})")
            lines.append(f"    {r['text']}")
            lines.append("")
        lines.append("")

    (DERIVED / "text_responses_readable.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {len(df)} responses to {DERIVED/'text_responses.csv'}")
    print(f"Readable dump: {DERIVED/'text_responses_readable.txt'}")
    print(df["response_kind"].value_counts().to_string())


if __name__ == "__main__":
    main()
