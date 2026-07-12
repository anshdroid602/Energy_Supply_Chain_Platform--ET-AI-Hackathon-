"""Ingestion controller: reruns every feed on its natural cadence and keeps
the database a rolling window of fresh data.

Design notes:
  - Each feed has a minimum re-run interval matched to how fast its source
    actually changes (EIA publishes daily; yfinance ticks continuously; OFAC
    updates ~daily; PPAC is monthly; AIS is live; GDELT dumps land daily).
    Cadence state lives in the ingest_runs table, NOT in this process, so a
    fresh process (GitHub Actions, cron, laptop) picks up where the last run
    left off.
  - "Sliding window" applies to FETCHING (GDELT pulls now-X days, AIS
    snapshots now) and to the one table where old rows are obsolete
    (vessels — pruned past VESSEL_RETENTION_HOURS). Price, import, sanction
    and event HISTORY is never deleted: the scenario model calibrates on it
    and the risk score already down-weights old events by recency.
  - All loaders are idempotent (upserts), so overlapping runs are safe.

Usage (from the repo root — note the -m, this file lives inside the package):
  python3 -m datapipeline.controller                 # run whatever is due, then exit
  python3 -m datapipeline.controller --force         # ignore cadence, run everything now
  python3 -m datapipeline.controller --only ais --only market_prices
  python3 -m datapipeline.controller --skip gdelt
  python3 -m datapipeline.controller --loop 300      # keep running, wake every 300s (demo laptop mode)

Env knobs:
  GDELT_SOURCE            public | bigquery   (default public)
  GDELT_WINDOW_DAYS       GDELT rolling fetch window, default 30
  VESSEL_RETENTION_HOURS  prune AIS rows older than this, default 48
"""
import argparse
import os
import subprocess
import sys
import time
import traceback

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from datapipeline.common import db

# This file lives inside datapipeline/, so the gdelt pipeline is a sibling dir.
GDELT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gdelt_and_gkg")


def run_gdelt_pipeline():
    source = os.environ.get("GDELT_SOURCE", "public")
    cmd = [sys.executable, "run_pipeline.py", "--source", source]
    result = subprocess.run(cmd, cwd=GDELT_DIR)
    if result.returncode != 0:
        raise RuntimeError(f"gdelt pipeline exited {result.returncode}")
    return None  # row count is reported by load_to_postgres.py itself


def make_loader(module_path):
    def run():
        import importlib
        return importlib.import_module(module_path).main()
    return run


# (feed name, callable, minimum minutes between successful runs)
FEEDS = [
    ("eia",           make_loader("datapipeline.eia.loader"),           20 * 60),
    ("market_prices", make_loader("datapipeline.market_prices.loader"), 10),
    ("ofac",          make_loader("datapipeline.ofac.loader"),          20 * 60),
    ("ppac",          make_loader("datapipeline.ppac.loader"),          24 * 60),
    ("ais",           make_loader("datapipeline.ais.loader"),           10),
    ("gdelt",         run_gdelt_pipeline,                               4 * 60),
]


def run_once(force=False, only=None, skip=None):
    ran, failed = [], []
    for name, fn, interval_min in FEEDS:
        if only and name not in only:
            continue
        if skip and name in skip:
            continue

        if not force:
            since = db.minutes_since_last_run(name)
            if since is not None and since < interval_min:
                print(f"-- {name}: ran {since:.0f} min ago (< {interval_min} min cadence), skipping")
                continue

        print(f"\n>> {name}")
        try:
            rows = fn()
            db.record_run(name, "ok", rows or 0)
            ran.append(name)
        except SystemExit as e:  # missing API key etc. — skip, don't crash the rest
            print(f"SKIP {name}: {e}")
            db.record_run(name, "skipped", 0, note=str(e))
        except Exception as e:
            traceback.print_exc()
            failed.append(name)
            db.record_run(name, "error", 0, note=str(e)[:500])

    deleted = db.prune_vessels(int(os.environ.get("VESSEL_RETENTION_HOURS", "48")))
    if deleted:
        print(f"\nPruned {deleted} stale vessel positions")

    print(f"\nController done. ran={ran or 'nothing due'} failed={failed or 'none'}")
    return failed


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="ignore cadence gating, run everything")
    parser.add_argument("--only", action="append", choices=[f for f, _, _ in FEEDS],
                        help="run only these feeds (repeatable)")
    parser.add_argument("--skip", action="append", default=[], choices=[f for f, _, _ in FEEDS],
                        help="skip these feeds (repeatable)")
    parser.add_argument("--loop", type=int, metavar="SECONDS",
                        help="keep running, waking every SECONDS (demo laptop mode)")
    args = parser.parse_args()

    if args.loop:
        while True:
            run_once(force=args.force, only=args.only, skip=args.skip)
            print(f"\nSleeping {args.loop}s ...")
            time.sleep(args.loop)
    else:
        failed = run_once(force=args.force, only=args.only, skip=args.skip)
        sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
