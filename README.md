# EThackathon — Crude Oil Supply Chain Risk Pipeline

## Pipeline order

```
gdelt.py            pulls raw GDELT events -> gdelt_events_with_mentions.csv
gkg.py               pulls raw GDELT GKG context -> gdelt_gkg_events.csv
merge.py             joins events + GKG context by date/country, filters to
                      relevant themes -> event_bundles.json

extract.py            deterministic rule-based extraction (no LLM, fast)   \
extract_events.py     LLM-based extraction via OpenRouter free models       > pick one
hybrid_extract.py     deterministic first, LLM only on low-confidence ones /
                      -> structured_events.json

load_to_postgres.py   upserts structured_events.json into Postgres
```

Run in that order. Each stage reads the previous stage's output file by
default; override with `--input`/`--output` flags where scripts support them.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt   # or: pandas openai requests python-dotenv psycopg2-binary
```

`.env` needs:
```
OPENROUTER_API_KEY=...      # only if using extract_events.py / hybrid_extract.py
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres
```

Postgres via Docker: `docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:16`

## Important gotcha: FIPS vs ISO2 country codes

GDELT's `location_country` / `ActionGeo_CountryCode` field uses **FIPS 10-4**
country codes, not ISO 3166-1 alpha-2. They diverge for several countries
relevant to this pipeline:

| Country | ISO2 | FIPS (what GDELT actually sends) |
|---|---|---|
| Oman | OM | MU |
| UAE | AE | TC |
| Kuwait | KW | KU |
| Bahrain | BH | BA |
| Yemen | YE | YM |
| Sudan | SD | SU |

`extract.py`'s `CORRIDOR_MAP` is keyed on FIPS codes. If you add new
corridor countries, look up the FIPS code, not the ISO2 code.

Actor fields (`Actor1CountryCode`/`Actor2CountryCode`) use CAMEO 3-letter
codes instead (e.g. `IRN`, `USA`) — a third, separate coding scheme from
both ISO2 and FIPS. Don't cross-reference actor codes against `CORRIDOR_MAP`.

## Regenerating downstream data after a code change

Since `structured_events.json` etc. aren't committed (see `.gitignore`),
anyone pulling this repo needs to regenerate them:

```bash
python3 gdelt.py
python3 gkg.py
python3 merge.py
python3 extract.py            # or hybrid_extract.py
python3 load_to_postgres.py
```