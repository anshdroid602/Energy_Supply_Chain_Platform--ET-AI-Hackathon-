"""
Top-level pipeline controller. Runs each stage as a subprocess, in order,
stopping immediately if one fails. Doesn't touch the internals of any stage --
every stage stays independently runnable for debugging.

Two fetch sources:
  --source public    (default) fetch_public.py — GDELT public daily dumps,
                     no key, no GCP account, events only (no GKG context;
                     extract.py falls back to CAMEO-code categorisation)
  --source bigquery  gdelt.py + gkg.py — needs Google Cloud credentials,
                     richer data (mentions join + GKG themes)

Usage:
  python run_pipeline.py                       # public fetch, deterministic extractor
  python run_pipeline.py --source bigquery     # BigQuery fetch (needs GCP creds)
  python run_pipeline.py --extractor hybrid    # use hybrid_extract.py instead of extract.py
  python run_pipeline.py --extractor llm       # use extract_events.py instead
  python run_pipeline.py --from merge          # skip fetching, start at merge.py
  python run_pipeline.py --only extract        # run just one stage
  python run_pipeline.py --skip load           # run everything except Postgres load
"""

import argparse
import subprocess
import sys
import time

FETCH_STAGES = {
    "public": [("fetch", ["python3", "fetch_public.py"])],
    "bigquery": [("gdelt", ["python3", "gdelt.py"]),
                 ("gkg", ["python3", "gkg.py"])],
}

TAIL_STAGES = [
    ("merge", ["python3", "merge.py"]),
    ("extract", None),  # filled in below based on --extractor
    ("load", ["python3", "load_to_postgres.py"]),
]

ALL_STAGE_NAMES = ["fetch", "gdelt", "gkg", "merge", "extract", "load"]

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
    parser.add_argument("--source", choices=["public", "bigquery"], default="public",
                         help="where to fetch GDELT data from (default: public, no key needed)")
    parser.add_argument("--extractor", choices=["deterministic", "hybrid", "llm"], default="deterministic",
                         help="which extraction stage to run (default: deterministic / extract.py)")
    parser.add_argument("--from", dest="from_stage", choices=ALL_STAGE_NAMES,
                         help="skip earlier stages, start from this one")
    parser.add_argument("--only", choices=ALL_STAGE_NAMES,
                         help="run exactly one stage and exit")
    parser.add_argument("--skip", action="append", default=[], choices=ALL_STAGE_NAMES,
                         help="skip this stage (repeatable: --skip fetch --skip merge)")
    args = parser.parse_args()

    stages = FETCH_STAGES[args.source] + [
        (name, EXTRACTOR_COMMANDS[args.extractor] if name == "extract" else cmd)
        for name, cmd in TAIL_STAGES
    ]

    if args.only:
        stages = [(name, cmd) for name, cmd in stages if name == args.only]
        if not stages:
            sys.exit(f"Stage '{args.only}' is not part of the --source {args.source} pipeline.")
    else:
        if args.from_stage:
            stage_names = [s for s, _ in stages]
            if args.from_stage not in stage_names:
                sys.exit(f"Stage '{args.from_stage}' is not part of the --source {args.source} pipeline.")
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
