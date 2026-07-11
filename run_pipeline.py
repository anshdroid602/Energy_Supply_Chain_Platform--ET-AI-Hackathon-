"""
Top-level pipeline controller. Runs each stage as a subprocess, in order,
stopping immediately if one fails. Doesn't touch the internals of any stage --
gdelt.py, gkg.py, merge.py, extract.py, hybrid_extract.py, and
load_to_postgres.py all stay exactly as they are and stay independently
runnable for debugging.

Usage:
  python run_pipeline.py                      # full run, deterministic extractor
  python run_pipeline.py --extractor hybrid    # use hybrid_extract.py instead of extract.py
  python run_pipeline.py --extractor llm       # use extract_events.py instead
  python run_pipeline.py --from merge          # skip gdelt/gkg, start at merge.py
  python run_pipeline.py --only extract        # run just one stage
  python run_pipeline.py --skip load           # run everything except Postgres load
"""

import argparse
import subprocess
import sys
import time

STAGES = [
    ("gdelt",  ["python3", "gdelt.py"]),
    ("gkg",    ["python3", "gkg.py"]),
    ("merge",  ["python3", "merge.py"]),
    ("extract", None),  # filled in below based on --extractor
    ("load",   ["python3", "load_to_postgres.py"]),
]

EXTRACTOR_COMMANDS = {
    "deterministic": ["python3", "extract.py"],
    "hybrid": ["python3", "hybrid_extract.py"],
    "llm": ["python3", "extract_events.py"],
}


def run_stage(name, cmd):
    print(f"\n{'=' * 60}")
    print(f"  STAGE: {name}   ({' '.join(cmd)})")
    print(f"{'=' * 60}")
    start = time.time()

    result = subprocess.run(cmd)

    elapsed = time.time() - start
    if result.returncode != 0:
        print(f"\n✗ Stage '{name}' failed (exit code {result.returncode}) after {elapsed:.1f}s")
        print(f"  Fix the issue, then resume with: python3 run_pipeline.py --from {name}")
        sys.exit(result.returncode)

    print(f"\n✓ Stage '{name}' done in {elapsed:.1f}s")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--extractor", choices=["deterministic", "hybrid", "llm"], default="deterministic",
                         help="which extraction stage to run (default: deterministic / extract.py)")
    parser.add_argument("--from", dest="from_stage", choices=[s for s, _ in STAGES],
                         help="skip earlier stages, start from this one")
    parser.add_argument("--only", choices=[s for s, _ in STAGES],
                         help="run exactly one stage and exit")
    parser.add_argument("--skip", action="append", default=[], choices=[s for s, _ in STAGES],
                         help="skip this stage (repeatable: --skip gdelt --skip gkg)")
    args = parser.parse_args()

    stages = [(name, EXTRACTOR_COMMANDS[args.extractor] if name == "extract" else cmd)
              for name, cmd in STAGES]

    if args.only:
        stages = [(name, cmd) for name, cmd in stages if name == args.only]
    else:
        if args.from_stage:
            stage_names = [s for s, _ in stages]
            start_idx = stage_names.index(args.from_stage)
            stages = stages[start_idx:]
        stages = [(name, cmd) for name, cmd in stages if name not in args.skip]

    print(f"Pipeline plan: {' -> '.join(name for name, _ in stages)}")

    pipeline_start = time.time()
    for name, cmd in stages:
        run_stage(name, cmd)

    print(f"\n{'=' * 60}")
    print(f"Pipeline complete in {time.time() - pipeline_start:.1f}s")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()