"""
Pick a real cached event for the "Inject Signal" demo button, so it's a
matter of running this once against the live DB instead of hand-editing two
files. See task.md's "Two follow-ups before the live demo".

What it does:
  1. Queries structured_events for the best candidate: highest
     severity_score * confidence, optionally restricted to one corridor.
  2. Prints it, with enough context (date, summary, actors) to sanity-check
     it's a real, sensible, presentable event -- not just the highest number.
  3. With --write, patches the CACHED_DEMO_EVENT / CACHED_EVENT block in both
     frontend/src/demoFixtures.js and tests/test_pipeline.py in place
     (between the DEMO_EVENT_START / DEMO_EVENT_END markers), so both copies
     stay in sync.

Usage:
  python scripts/capture_demo_event.py                       # just look
  python scripts/capture_demo_event.py --corridor "Strait of Hormuz"
  python scripts/capture_demo_event.py --write                # look AND patch both files
  python scripts/capture_demo_event.py --min-confidence 0.7 --write

Requires DATABASE_URL in .env (same as the rest of the repo).
"""
import argparse
import os
import re
import sys

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_FIXTURE = os.path.join(ROOT, "frontend", "src", "demoFixtures.js")
TEST_FIXTURE = os.path.join(ROOT, "tests", "test_pipeline.py")

load_dotenv()


def find_candidate(conn, corridor=None, min_confidence=0.5, min_severity=6.0):
    where = ["confidence >= %s", "severity_score >= %s"]
    params = [min_confidence, min_severity]
    if corridor:
        where.append("corridor_affected = %s")
        params.append(corridor)

    sql = f"""
        SELECT event_id, event_date, corridor_affected, event_category,
               severity_score, confidence, summary, actors
        FROM structured_events
        WHERE {' AND '.join(where)}
        ORDER BY (severity_score / 10.0 * confidence) DESC
        LIMIT 1;
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def patch_block(path, new_body_lines, marker_prefix):
    with open(path) as f:
        text = f.read()

    start = f"{marker_prefix} DEMO_EVENT_START"
    end = f"{marker_prefix} DEMO_EVENT_END"
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)

    if not pattern.search(text):
        print(f"  ! could not find {start} ... {end} markers in {path}, skipping")
        return False

    replacement = start + "\n" + "\n".join(new_body_lines) + "\n" + end
    text = pattern.sub(replacement, text)

    with open(path, "w") as f:
        f.write(text)
    return True


def write_fixtures(event):
    corridor = event["corridor_affected"]
    severity = float(event["severity_score"])
    confidence = float(event["confidence"])

    js_lines = [
        "export const CACHED_DEMO_EVENT = {",
        f'  corridor: "{corridor}",',
        f"  severity_score: {severity},",
        f"  confidence: {confidence},",
        "};",
    ]
    py_lines = [
        "CACHED_EVENT = {",
        f'    "corridor": "{corridor}",',
        f'    "severity_score": {severity},',
        f'    "confidence": {confidence},',
        "}",
    ]

    ok_js = patch_block(FRONTEND_FIXTURE, js_lines, "//")
    ok_py = patch_block(TEST_FIXTURE, py_lines, "#")

    if ok_js:
        print(f"  wrote {os.path.relpath(FRONTEND_FIXTURE, ROOT)}")
    if ok_py:
        print(f"  wrote {os.path.relpath(TEST_FIXTURE, ROOT)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corridor", default=None, help="restrict to one corridor, e.g. 'Strait of Hormuz'")
    parser.add_argument("--min-confidence", type=float, default=0.5)
    parser.add_argument("--min-severity", type=float, default=6.0)
    parser.add_argument("--write", action="store_true", help="patch demoFixtures.js and test_pipeline.py in place")
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("Set DATABASE_URL in your .env file")

    conn = psycopg2.connect(database_url)
    try:
        event = find_candidate(conn, args.corridor, args.min_confidence, args.min_severity)
    finally:
        conn.close()

    if not event:
        print("No event matched the filters. Try lowering --min-confidence / --min-severity, "
              "or dropping --corridor.")
        sys.exit(1)

    print("Best candidate:")
    print(f"  event_id:   {event['event_id']}")
    print(f"  date:       {event['event_date']}")
    print(f"  corridor:   {event['corridor_affected']}")
    print(f"  category:   {event['event_category']}")
    print(f"  severity:   {event['severity_score']}")
    print(f"  confidence: {event['confidence']}")
    print(f"  actors:     {event['actors']}")
    print(f"  summary:    {event['summary']}")

    if args.write:
        print("\nWriting fixtures...")
        write_fixtures(event)
        print("Done. Re-run `pytest tests/test_pipeline.py` to confirm nothing broke.")
    else:
        print("\n(dry run — pass --write to patch demoFixtures.js and test_pipeline.py)")


if __name__ == "__main__":
    main()
