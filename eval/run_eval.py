# ─────────────────────────────────────────────────────────────
# run_eval.py
# Runs the full review pipeline on a directory of session files
# and writes predictions to a JSONL file for evaluation.
# Used by `make eval` to generate predictions on the train set.
#
# Usage:
#   python eval/run_eval.py --sessions dataset_candidate/train/sessions
#   python eval/run_eval.py --sessions dataset_candidate/test/sessions
#
# Output is written to eval/predictions_<set>.jsonl
# Then evaluated with: python dataset_candidate/eval.py --predictions ...
# ─────────────────────────────────────────────────────────────

from __future__ import annotations
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent

# Add backend/src to path so pipeline imports work without installing the package
sys.path.insert(0, str(ROOT_DIR / "backend" / "src"))

from pipeline import review_session_data


async def run_eval(sessions_dir: Path, output_path: Path, delay: float = 3.0):
    session_files = sorted(sessions_dir.glob("*.json"))

    if not session_files:
        print(f"No session files found in {sessions_dir}")
        return

    print(f"Found {len(session_files)} sessions")
    print(f"Output: {output_path}")
    print(f"Delay between calls: {delay}s")
    print("-" * 50)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    results = []
    failed = []

    for i, session_file in enumerate(session_files, 1):
        print(f"[{i:02d}/{len(session_files)}] {session_file.name} ... ", end="", flush=True)

        try:
            with open(session_file) as f:
                raw = json.load(f)
            result = await review_session_data(raw)
            results.append(result)
            print(f"{result['verdict']} (confidence: {result['confidence']:.2f})")
        except Exception as e:
            print(f"FAILED: {e}")
            failed.append(session_file.name)

        # Pause between sessions to stay within LLM rate limits
        if i < len(session_files):
            time.sleep(delay)

    with open(output_path, "w") as f:
        for result in results:
            f.write(json.dumps(result) + "\n")

    print("-" * 50)
    print(f"Done. {len(results)} predictions written to {output_path}")

    if failed:
        print(f"Failed sessions ({len(failed)}): {', '.join(failed)}")

    # Verdict distribution summary
    verdicts = [r["verdict"] for r in results]
    for v in ["PASS", "REJECT", "NEEDS_CORRECTION"]:
        count = verdicts.count(v)
        print(f"  {v}: {count} ({count/len(verdicts)*100:.0f}%)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sessions", required=True, help="Path to sessions directory")
    ap.add_argument("--output", default=None, help="Output JSONL path")
    ap.add_argument("--delay", type=float, default=3.0, help="Seconds between LLM calls")
    args = ap.parse_args()

    sessions_dir = Path(args.sessions)
    if not sessions_dir.exists():
        print(f"Directory not found: {sessions_dir}")
        sys.exit(1)

    output_path = (
        Path(args.output) if args.output
        else ROOT_DIR / "eval" / f"predictions_{sessions_dir.parent.name}.jsonl"
    )

    asyncio.run(run_eval(sessions_dir, output_path, args.delay))


if __name__ == "__main__":
    main()