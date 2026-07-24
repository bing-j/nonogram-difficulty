"""
export_text_responses.py
=========================
Step 10 - Export every free-text survey response into structured artifacts.

Ported from an earlier standalone exploratory analysis's response exporter
(since removed from the repo).

Inputs
------
- backend/logs/*.ndjson, *.json (via text_response_loader.py)
- nonograms_6.json (puzzle solutions)

Outputs
-------
- analyze-data/out_features/text_coding/text_responses.csv
- analyze-data/out_features/text_coding/text_responses_readable.txt

Usage
-----
  python analyze-data/export_text_responses.py
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
from text_response_loader import load_text_responses  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT_DIR = REPO_ROOT / "analyze-data" / "out_features" / "text_coding"


def main() -> None:
    ap = argparse.ArgumentParser(description="Export every free-text survey response to CSV + a readable dump.")
    ap.add_argument("--out_dir", type=Path, default=DEFAULT_OUT_DIR)
    args = ap.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)

    df = load_text_responses().reset_index(drop=True)
    # Stable response id so coding can be merged back deterministically.
    df.insert(0, "response_id", [f"R{idx:04d}" for idx in range(len(df))])
    df.to_csv(args.out_dir / "text_responses.csv", index=False)

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

    (args.out_dir / "text_responses_readable.txt").write_text("\n".join(lines), encoding="utf-8")

    print(f"Wrote {len(df)} responses to {args.out_dir / 'text_responses.csv'}")
    print(f"Readable dump: {args.out_dir / 'text_responses_readable.txt'}")
    print(df["response_kind"].value_counts().to_string())
    print("\nDone.")


if __name__ == "__main__":
    main()
