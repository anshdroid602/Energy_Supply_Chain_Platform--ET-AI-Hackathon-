"""
GDELT event bundle -> structured risk signal extractor (OpenRouter, free-tier models)

What changed vs. the previous version:
  - Free models are discovered LIVE from OpenRouter's /models endpoint instead of
    being hardcoded, so this keeps working after OpenRouter rotates its free lineup.
    A small static fallback list (incl. "openrouter/free", OpenRouter's own free
    auto-router) is used only if the live fetch fails.
  - Progress is checkpointed after EVERY batch. If the script dies, gets rate
    limited into the ground, or you just Ctrl+C it, re-running the same command
    picks up exactly where it left off instead of reprocessing everything.
  - Fixed two bugs from the previous version:
      1) MODELS = ["a" "b"] was string concatenation (missing comma), not a list
         of two models -> it was silently only ever trying one garbage model id.
      2) An unconditional `break` after the retry loop meant the script quit
         after batch 1 no matter what happened.

Usage:
  python extract_events.py                                   # normal run
  python extract_events.py --reset                            # ignore checkpoint, start over
  python extract_events.py --input failed_bundles.json \\
                            --output structured_events_retry.json \\
                            --failed failed_bundles_2.json     # reprocess just the failures

Requires: pip install openai requests python-dotenv
OPENROUTER_API_KEY must be set in your .env file.

Free-tier heads up: OpenRouter caps free models at ~20 requests/min and 50/day
(1000/day once you've ever bought $10 of credits). If you're blowing through
that, either raise BATCH_SIZE (fewer requests total) or buy the $10 credits.
"""

import argparse
import json
import os
import re
import time

import requests
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

API_KEY = os.getenv("OPENROUTER_API_KEY")
if not API_KEY:
    raise SystemExit("Set OPENROUTER_API_KEY in your .env file")

client = OpenAI(api_key=API_KEY, base_url="https://openrouter.ai/api/v1")

BATCH_SIZE = 5
MAX_RETRIES = 3
MODELS_CACHE_FILE = "free_models_cache.json"
MODELS_CACHE_TTL = 6 * 3600  # don't hit /models more than once every 6h

# Last-resort models, only used if the live /models fetch fails entirely.
# "openrouter/free" is OpenRouter's own auto-router that picks a working free
# model for you, so it's the safest single fallback to lean on.
STATIC_FALLBACK_MODELS = [
    "openrouter/free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "qwen/qwen-2.5-7b-instruct:free",
]

EXTRACTION_PROMPT = """You are a supply-chain risk analyst.

Given these GDELT event bundles, extract structured risk signals.

Return ONLY a valid JSON array.
No markdown.
No explanation.
No extra text.
No <think> tags.

Event bundles:
{bundles}

For each event return EXACTLY:

{{
  "event_id": string,
  "event_date": "YYYY-MM-DD",
  "actors": [string],
  "location_country": string,
  "corridor_affected": string,
  "event_category": string,
  "severity_score": float,
  "confidence": float,
  "summary": string
}}

Rules:

corridor_affected must be one of:
- Strait of Hormuz
- Red Sea
- Suez Canal
- Persian Gulf
- none

event_category must be one of:
- military_strike
- sanction
- maritime_incident
- diplomatic
- other

severity_score:
0-10 derived from
- Goldstein scale
- Mention count
- Tone
- Context articles

confidence:
0-1

Return ONLY JSON.
"""


def batch(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


def clean_response(raw_text: str) -> str:
    """Strip reasoning-model <think> blocks and markdown fences before parsing."""
    raw_text = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL).strip()

    if raw_text.startswith("```"):
        raw_text = raw_text.split("```")[1]
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
        raw_text = raw_text.strip()

    start = raw_text.find("[")
    end = raw_text.rfind("]")
    if start != -1 and end != -1:
        raw_text = raw_text[start:end + 1]

    return raw_text.strip()


def fetch_free_models():
    """Ask OpenRouter which models are currently free, biggest context first.
    Falls back to a short-lived local cache, then to STATIC_FALLBACK_MODELS,
    if the live request fails."""
    if os.path.exists(MODELS_CACHE_FILE):
        age = time.time() - os.path.getmtime(MODELS_CACHE_FILE)
        if age < MODELS_CACHE_TTL:
            try:
                with open(MODELS_CACHE_FILE) as f:
                    cached = json.load(f)
                if cached:
                    return cached
            except (json.JSONDecodeError, OSError):
                pass

    try:
        resp = requests.get("https://openrouter.ai/api/v1/models", timeout=15)
        resp.raise_for_status()
        data = resp.json()["data"]

        free = []
        for m in data:
            model_id = m.get("id", "")
            pricing = m.get("pricing", {}) or {}
            is_free = model_id.endswith(":free") or (
                str(pricing.get("prompt")) in ("0", "0.0")
                and str(pricing.get("completion")) in ("0", "0.0")
            )
            modality = (m.get("architecture") or {}).get("modality", "")
            # keep text-output models only (skip image/audio-output-only models)
            if is_free and ("text->text" in modality or modality == ""):
                free.append((m.get("context_length") or 0, model_id))

        free.sort(reverse=True)  # bigger context tends to mean a more capable model
        free_ids = [model_id for _, model_id in free]

        if free_ids:
            with open(MODELS_CACHE_FILE, "w") as f:
                json.dump(free_ids, f, indent=2)
            return free_ids

    except Exception as e:
        print(f"Could not fetch live model list ({e}); using static fallback list")

    return STATIC_FALLBACK_MODELS[:]


def load_json_list(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return []


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_checkpoint(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def save_checkpoint(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def call_model(model, prompt):
    """Single attempt against a single model. Raises on any failure."""
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        max_tokens=3000,
        messages=[
            {"role": "system", "content": "Return ONLY valid JSON."},
            {"role": "user", "content": prompt},
        ],
    )
    raw_text = (response.choices[0].message.content or "").strip()
    if not raw_text:
        raise ValueError("empty response body")
    return raw_text


def process_batch(chunk, models):
    """Try each candidate model, retrying the whole batch up to MAX_RETRIES times
    on transient errors. Returns (parsed_events, None) on success or
    (None, last_error_message) if every attempt failed."""
    prompt = EXTRACTION_PROMPT.format(bundles=json.dumps(chunk, indent=2))
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        for model in models:
            try:
                print(f"  trying {model} (attempt {attempt}/{MAX_RETRIES})")
                raw_text = call_model(model, prompt)
                cleaned = clean_response(raw_text)
                parsed = json.loads(cleaned)
                print(f"  \u2713 {model} -> {len(parsed)} events")
                return parsed, None

            except json.JSONDecodeError as e:
                last_error = f"bad JSON from {model}: {e}"
                print(f"    parse failed: {e} (raw start: {raw_text[:150]!r})")
                continue

            except Exception as e:
                err = str(e)
                last_error = f"{model}: {err}"

                if "429" in err:
                    wait = 30 * attempt
                    print(f"    rate limited on {model}, waiting {wait}s")
                    time.sleep(wait)
                elif "502" in err or "503" in err:
                    print(f"    gateway error on {model}, waiting 10s")
                    time.sleep(10)
                else:
                    print(f"    {model} failed: {err}")
                continue

        time.sleep(2)  # brief pause before the next full attempt across all models

    return None, last_error


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", default="event_bundles.json")
    parser.add_argument("--output", default="structured_events.json")
    parser.add_argument("--failed", default="failed_bundles.json")
    parser.add_argument("--checkpoint", default="checkpoint.json")
    parser.add_argument("--reset", action="store_true", help="ignore saved progress for this input and start over")
    args = parser.parse_args()

    with open(args.input) as f:
        bundles = json.load(f)

    models = fetch_free_models()
    preview = models[:5]
    print(f"Found {len(models)} candidate free model(s): {preview}{' ...' if len(models) > 5 else ''}")

    checkpoint = {} if args.reset else load_checkpoint(args.checkpoint)
    run_state = checkpoint.get(args.input, {"next_batch": 0})
    start_batch = run_state["next_batch"]

    all_results = [] if args.reset else load_json_list(args.output)
    failed_batches = [] if args.reset else load_json_list(args.failed)

    batches = list(batch(bundles, BATCH_SIZE))
    total_batches = len(batches)

    if start_batch >= total_batches and total_batches > 0:
        print(f"'{args.input}' is already fully processed ({total_batches} batches). Use --reset to redo it.")
        return

    if start_batch:
        print(f"Resuming '{args.input}' from batch {start_batch + 1}/{total_batches}")

    for i in range(start_batch, total_batches):
        chunk = batches[i]
        print(f"\nBatch {i + 1}/{total_batches} ({len(chunk)} events)")

        parsed, error = process_batch(chunk, models)

        if parsed is not None:
            all_results.extend(parsed)
        else:
            print(f"  \u2717 batch {i + 1} failed after {MAX_RETRIES} attempts: {error}")
            failed_batches.extend(chunk)

        # Persist after every single batch so a crash never costs more than
        # the batch currently in flight.
        save_json(args.output, all_results)
        save_json(args.failed, failed_batches)
        checkpoint[args.input] = {"next_batch": i + 1}
        save_checkpoint(args.checkpoint, checkpoint)

        time.sleep(2)

    print("\n--------------------------------")
    print(f"Extracted {len(all_results)} / {len(bundles)} events")
    print(f"Failed events (need reprocessing): {len(failed_batches)}")
    if failed_batches:
        print(f"Saved unprocessed events to {args.failed}")
        print(f"Retry them with: python extract_events.py --input {args.failed} "
              f"--output structured_events_retry.json --failed failed_bundles_2.json")
    print(f"Saved {args.output}")

    if all_results:
        print("\nSample output:\n")
        print(json.dumps(all_results[0], indent=2))


if __name__ == "__main__":
    main()