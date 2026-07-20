"""
Verify (or recalibrate) scenario/engine.py's MAX_JUMP_PCT against the real
`prices` table, instead of trusting the plan's approximate historical anchor
by eye. See task.md's "Two follow-ups before the live demo".

Default anchor is the 2022 Ukraine invasion (Brent ~$90 -> ~$130 sustained,
the plan's own "persistent jump" example) but any baseline date + ticker
works -- useful for cross-checking other anchors too (2019 Abqaiq, etc.).

What it does:
  1. Finds the last known price on/before --baseline-date.
  2. Finds the peak price in the following --peak-window-days.
  3. Computes the real % move between them.
  4. Prints it next to the current MAX_JUMP_PCT constant in
     scenario/engine.py.
  5. With --write, patches MAX_JUMP_PCT in place (rounded to 2 decimals),
     with a comment recording exactly what was used to derive it.

Usage:
  python scripts/calibrate_jump_size.py
  python scripts/calibrate_jump_size.py --baseline-date 2019-09-13 --peak-window-days 14 --ticker BRENT
  python scripts/calibrate_jump_size.py --write

Requires DATABASE_URL in .env (same as the rest of the repo).
"""
import argparse
import os
import re
from datetime import date, timedelta

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE_PATH = os.path.join(ROOT, "scenario", "engine.py")

load_dotenv()


def find_baseline_and_peak(conn, ticker, baseline_date, peak_window_days):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT day, usd FROM prices
            WHERE ticker = %s AND day <= %s
            ORDER BY day DESC LIMIT 1;
            """,
            (ticker, baseline_date),
        )
        baseline = cur.fetchone()

        cur.execute(
            """
            SELECT day, usd FROM prices
            WHERE ticker = %s AND day > %s AND day <= %s
            ORDER BY usd DESC LIMIT 1;
            """,
            (ticker, baseline_date, baseline_date + timedelta(days=peak_window_days)),
        )
        peak = cur.fetchone()

    return baseline, peak


def current_max_jump_pct():
    with open(ENGINE_PATH) as f:
        text = f.read()
    m = re.search(r"^MAX_JUMP_PCT\s*=\s*([0-9.]+)", text, re.MULTILINE)
    return float(m.group(1)) if m else None


def write_max_jump_pct(new_value, note):
    with open(ENGINE_PATH) as f:
        text = f.read()

    pattern = re.compile(r"^MAX_JUMP_PCT\s*=\s*[0-9.]+.*$", re.MULTILINE)
    if not pattern.search(text):
        print(f"  ! could not find MAX_JUMP_PCT assignment in {ENGINE_PATH}, skipping")
        return False

    replacement = f"MAX_JUMP_PCT = {new_value:.2f}  # {note}"
    text = pattern.sub(replacement, text, count=1)

    with open(ENGINE_PATH, "w") as f:
        f.write(text)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ticker", default="BRENT", choices=["BRENT", "WTI"])
    parser.add_argument("--baseline-date", default="2022-02-23", help="YYYY-MM-DD, day before the shock")
    parser.add_argument("--peak-window-days", type=int, default=120)
    parser.add_argument("--write", action="store_true", help="patch MAX_JUMP_PCT in scenario/engine.py")
    args = parser.parse_args()

    baseline_date = date.fromisoformat(args.baseline_date)

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("Set DATABASE_URL in your .env file")

    conn = psycopg2.connect(database_url)
    try:
        baseline, peak = find_baseline_and_peak(conn, args.ticker, baseline_date, args.peak_window_days)
    finally:
        conn.close()

    if not baseline or not peak:
        print("Not enough price history around that date in the `prices` table "
              "(need EIA data loaded for the relevant range). Nothing computed.")
        return

    real_pct = float(peak["usd"]) / float(baseline["usd"]) - 1.0
    current = current_max_jump_pct()

    print(f"Baseline: {baseline['day']} — ${baseline['usd']:.2f} ({args.ticker})")
    print(f"Peak:     {peak['day']} — ${peak['usd']:.2f} (within {args.peak_window_days}d)")
    print(f"Real move: {real_pct:+.1%}")
    print(f"Current MAX_JUMP_PCT in scenario/engine.py: {current}")

    if abs(real_pct - (current or 0)) < 0.03:
        print("Within 3 points of the real move — no change needed.")
    else:
        print(f"Differs from the real move by {abs(real_pct - (current or 0)):.1%}. "
              f"Consider updating MAX_JUMP_PCT to ~{real_pct:.2f}.")

    if args.write:
        note = f"recalibrated: {args.ticker} {baseline['day']}->{peak['day']}, real move {real_pct:+.1%}"
        if write_max_jump_pct(real_pct, note):
            print(f"\nWrote MAX_JUMP_PCT = {real_pct:.2f} to scenario/engine.py")
            print("Re-run `pytest tests/test_scenario.py` to confirm nothing broke.")


if __name__ == "__main__":
    main()
