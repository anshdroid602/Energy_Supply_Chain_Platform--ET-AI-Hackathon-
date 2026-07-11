"""
Hybrid controller: deterministic-first, LLM-only-where-needed.

Runs the fast, free, deterministic rules from extract.py on every event.
Then routes ONLY the events that the deterministic pass was unsure about
to the LLM pipeline from extract_events.py, and merges the LLM's answers
back into the final structured_events.json in the original order.

Why route to the LLM at all, instead of just trusting extract.py everywhere:
the rule-based confidence score is a decent proxy for "the rules had enough
signal to work with". Low confidence usually means: sparse context articles,
no theme match at all (fell through to "other"), or thin/contradictory
Goldstein+tone signal. Those are exactly the cases an LLM reading the raw
text can add real value on -- so this reserves your free-tier LLM quota for
where it counts instead of burning it on obvious sanction/military events
the rules already nailed.

Routing rule (tune via CLI flags):
  - route to LLM if deterministic confidence < --confidence-threshold (default 0.65)
  - OR if deterministic event_category is in --force-llm-categories (default: "other")

Usage:
  python hybrid_extract.py
  python hybrid_extract.py --confidence-threshold 0.7 --force-llm-categories other,diplomatic
  python hybrid_extract.py --reset      # ignore any saved LLM checkpoint, redo the LLM subset

Requires everything extract.py and extract_events.py require:
  pip install openai requests python-dotenv
  OPENROUTER_API_KEY set in your .env file
extract.py and extract_events.py must sit in the same directory as this file.
"""

import argparse
import json
import os

import extract              # deterministic rules
import extract_events as llm  # LLM pipeline (model discovery, batching, retries)


def run_deterministic_pass(bundles):
    """Returns a list of (event, deterministic_result) pairs, same order as input."""
    return [(event, extract.safe_process_event(event, i)) for i, event in enumerate(bundles)]


def needs_llm(result, confidence_threshold, force_categories):
    if result["confidence"] < confidence_threshold:
        return True
    if result["event_category"] in force_categories:
        return True
    return False


def run_llm_pass(flagged_events, args):
    """Runs the same batching/retry/checkpoint machinery as extract_events.py,
    but only over the subset of events that were flagged. Returns a dict
    keyed by event_id -> LLM-produced record for whichever ones succeeded."""
    if not flagged_events:
        return {}

    models = llm.fetch_free_models()
    print(f"\n[LLM pass] {len(flagged_events)} events flagged for LLM review")
    print(f"[LLM pass] candidate models: {models[:5]}{' ...' if len(models) > 5 else ''}")

    checkpoint_key = f"hybrid::{args.input}"
    checkpoint = {} if args.reset else llm.load_checkpoint(args.checkpoint)
    start_batch = 0 if args.reset else checkpoint.get(checkpoint_key, {"next_batch": 0})["next_batch"]

    llm_results_by_id = {}
    if not args.reset and os.path.exists(args.llm_output):
        for rec in llm.load_json_list(args.llm_output):
            if "event_id" in rec:
                llm_results_by_id[rec["event_id"]] = rec

    failed_llm_events = [] if args.reset else llm.load_json_list(args.llm_failed)

    batches = list(llm.batch(flagged_events, args.llm_batch_size))
    total_batches = len(batches)

    if start_batch >= total_batches and total_batches > 0:
        print(f"[LLM pass] already fully processed ({total_batches} batches). Use --reset to redo it.")
    else:
        if start_batch:
            print(f"[LLM pass] resuming from batch {start_batch + 1}/{total_batches}")

        for i in range(start_batch, total_batches):
            chunk = batches[i]
            print(f"\n[LLM pass] batch {i + 1}/{total_batches} ({len(chunk)} events)")

            parsed, error = llm.process_batch(chunk, models)

            if parsed is not None:
                for rec in parsed:
                    if "event_id" in rec:
                        llm_results_by_id[rec["event_id"]] = rec
            else:
                print(f"  \u2717 batch {i + 1} failed after {llm.MAX_RETRIES} attempts: {error}")
                failed_llm_events.extend(chunk)

            # persist after every batch
            llm.save_json(args.llm_output, list(llm_results_by_id.values()))
            llm.save_json(args.llm_failed, failed_llm_events)
            checkpoint[checkpoint_key] = {"next_batch": i + 1}
            llm.save_checkpoint(args.checkpoint, checkpoint)

    return llm_results_by_id


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", default="event_bundles.json")
    parser.add_argument("--output", default="structured_events.json")
    parser.add_argument("--llm-output", default="llm_reviewed_events.json",
                         help="where LLM answers for flagged events are stored/checkpointed")
    parser.add_argument("--llm-failed", default="llm_failed_events.json")
    parser.add_argument("--checkpoint", default="checkpoint.json")
    parser.add_argument("--confidence-threshold", type=float, default=0.65)
    parser.add_argument("--force-llm-categories", default="other",
                         help="comma-separated event_category values that always go to the LLM")
    parser.add_argument("--llm-batch-size", type=int, default=llm.BATCH_SIZE)
    parser.add_argument("--reset", action="store_true", help="ignore saved LLM progress and redo the flagged subset")
    args = parser.parse_args()

    force_categories = {c.strip() for c in args.force_llm_categories.split(",") if c.strip()}

    with open(args.input) as f:
        bundles = json.load(f)

    # --- Pass 1: deterministic, on everything ---------------------------------
    pairs = run_deterministic_pass(bundles)
    deterministic_count = 0
    flagged_events = []
    flagged_ids = set()

    for event, result in pairs:
        if needs_llm(result, args.confidence_threshold, force_categories):
            flagged_events.append(event)
            flagged_ids.add(result["event_id"])
        else:
            deterministic_count += 1

    print(f"Deterministic pass: {len(bundles)} events processed")
    print(f"  kept as-is (confidence >= {args.confidence_threshold}, not in {force_categories}): {deterministic_count}")
    print(f"  flagged for LLM review: {len(flagged_events)}")

    # --- Pass 2: LLM, only on the flagged subset -------------------------------
    llm_results_by_id = run_llm_pass(flagged_events, args)

    # --- Merge: LLM result if we have one for that event_id, else deterministic ---
    final_results = []
    llm_used = 0
    llm_missing_fell_back = 0

    for event, det_result in pairs:
        event_id = det_result["event_id"]
        if event_id in flagged_ids:
            if event_id in llm_results_by_id:
                final_results.append(llm_results_by_id[event_id])
                llm_used += 1
            else:
                # LLM never got a usable answer for this one (still in the failed
                # queue or not yet run) - fall back to the deterministic record
                # rather than dropping the event.
                final_results.append(det_result)
                llm_missing_fell_back += 1
        else:
            final_results.append(det_result)

    with open(args.output, "w") as f:
        json.dump(final_results, f, indent=2)

    print("\n--------------------------------")
    print(f"Final: {len(final_results)} / {len(bundles)} events")
    print(f"  deterministic: {deterministic_count}")
    print(f"  LLM-reviewed:  {llm_used}")
    if llm_missing_fell_back:
        print(f"  flagged but no LLM answer yet, fell back to deterministic: {llm_missing_fell_back}")
        print(f"  (rerun this script to keep retrying the LLM subset -- it resumes automatically)")
    print(f"Saved {args.output}")


if __name__ == "__main__":
    main()