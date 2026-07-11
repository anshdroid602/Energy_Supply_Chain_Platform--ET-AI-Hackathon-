import os

import pandas as pd
import json

events_df = pd.read_csv("gdelt_events_with_mentions.csv")

# GKG context is optional: the public/no-key fetch path (fetch_public.py)
# produces events only. Without it every bundle gets empty context_articles
# and extract.py falls back to CAMEO-code categorisation.
if os.path.exists("gdelt_gkg_events.csv"):
    gkg_df = pd.read_csv("gdelt_gkg_events.csv")
else:
    print("No gdelt_gkg_events.csv found — building bundles without GKG context.")
    gkg_df = pd.DataFrame(columns=["DATE", "SourceCommonName", "DocumentIdentifier",
                                   "Themes", "Locations", "Persons", "Organizations", "Tone"])

events_df['date_only'] = events_df['SQLDATE'].astype(str)
gkg_df['date_only'] = gkg_df['DATE'].astype(str).str[:8]

gkg_df['theme_list'] = gkg_df['Themes'].fillna('').apply(
    lambda x: [t.split(',')[0] for t in x.split(';') if t]
)

gkg_df['tone_score'] = gkg_df['Tone'].str.split(',').str[0].astype(float)

def extract_country_codes(locations_str):
    if pd.isna(locations_str):
        return set()
    codes = set()
    for loc in str(locations_str).split(';'):
        parts = loc.split('#')
        if len(parts) > 2:
            codes.add(parts[2])
    return codes

gkg_df['country_codes'] = gkg_df['Locations'].apply(extract_country_codes)

# Only these themes count as "actually relevant" — matches gdelt.py's WHERE clause
SIGNAL_THEMES = {
    'ENV_OIL', 'ECON_OILPRICE', 'MARITIME', 'MARITIME_INCIDENT',
    'ARMEDCONFLICT', 'MILITARY', 'SANCTIONS', 'ECON_GOLDPRICE'
}

def relevance_score(theme_list):
    return sum(1 for t in theme_list if t in SIGNAL_THEMES)

gkg_df['relevance'] = gkg_df['theme_list'].apply(relevance_score)

bundles = []

for _, event in events_df.iterrows():
    event_date = event['date_only']
    event_country = event['ActionGeo_CountryCode']

    matches = gkg_df[
        (gkg_df['date_only'] == event_date) &
        (gkg_df['country_codes'].apply(lambda codes: event_country in codes))
    ]

    # Drop anything with zero relevant themes — this is the actual fix
    matches = matches[matches['relevance'] > 0].copy()

    # Rank by relevance first, absolute tone second (as tiebreaker)
    matches['abs_tone'] = matches['tone_score'].abs()
    top_matches = matches.sort_values(
        by=['relevance', 'abs_tone'],
        ascending=[False, False]
    ).head(2)

    context_articles = [
        {
            "source": row['SourceCommonName'],
            "themes": [t for t in row['theme_list'] if t in SIGNAL_THEMES][:5],
            "tone": row['tone_score']
        }
        for _, row in top_matches.iterrows()
    ]

    bundle = {
        "event_id": str(event['GlobalEventID']),
        "event_date": event_date,
        "event_code": str(event['EventCode']),
        "actor1": event['Actor1CountryCode'] if pd.notna(event['Actor1CountryCode']) else None,
        "actor2": event['Actor2CountryCode'] if pd.notna(event['Actor2CountryCode']) else None,
        "goldstein_scale": event['GoldsteinScale'],
        "num_mentions": event['NumMentions'],
        "avg_tone": event['AvgTone'],
        "location_country": event_country,
        "mention_count": event['mention_count'] if pd.notna(event['mention_count']) else 0,
        "avg_mention_tone": event['avg_mention_tone'] if pd.notna(event['avg_mention_tone']) else None,
        "context_articles": context_articles
    }
    bundles.append(bundle)

print(f"Built {len(bundles)} event bundles")
print(f"Bundles with relevant GKG context: {sum(1 for b in bundles if b['context_articles'])}")

with open("event_bundles.json", "w") as f:
    json.dump(bundles, f, indent=2)

print("Saved to event_bundles.json")
if bundles:
    print("\nSample bundle:")
    print(json.dumps(bundles[0], indent=2))

# Spot check: print a few bundles for Iran/Yemen/Saudi actors specifically,
# since those matter most for your actual use case
print("\n--- IRN/YEM/SAU spot checks ---")
priority_actors = {'IRN', 'YEM', 'SAU'}
count = 0
for b in bundles:
    if (b['actor1'] in priority_actors or b['actor2'] in priority_actors) and b['context_articles']:
        print(json.dumps(b, indent=2))
        count += 1
        if count >= 3:
            break
if count == 0:
    print("No IRN/YEM/SAU events with relevant GKG matches found.")