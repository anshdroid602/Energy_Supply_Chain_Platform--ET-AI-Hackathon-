"""OFAC SDN sdn.csv -> sanctions table.  No API key needed.

Run from the repo root:  python3 -m datapipeline.ofac.loader
"""
import csv
import io

from datapipeline.common import http
from datapipeline.common.db import upsert

URL = "https://www.treasury.gov/ofac/downloads/sdn.csv"
# sdn.csv has NO header row. Official column order:
COLS = ["ent_num", "name", "sdn_type", "program", "title", "call_sign",
        "vess_type", "tonnage", "grt", "vess_flag", "vess_owner", "remarks"]


def clean(v):
    v = (v or "").strip()
    return None if v in ("", "-0-") else v


def main():
    r = http.get(URL, timeout=60)
    r.raise_for_status()
    rows = []
    for rec in csv.reader(io.StringIO(r.text)):
        if len(rec) < 12:
            continue
        d = dict(zip(COLS, rec))
        try:
            ent = int(d["ent_num"])
        except ValueError:
            continue
        rows.append((ent, clean(d["name"]), clean(d["sdn_type"]),
                     clean(d["program"]), clean(d["vess_flag"]), clean(d["remarks"])))
    # The real SDN list has ~15k+ entries; far fewer means a truncated or
    # error-page download — fail loudly instead of loading a partial list
    # (upsert would silently leave the table looking fine but stale).
    if len(rows) < 1000:
        raise RuntimeError(f"OFAC download looks truncated: only {len(rows)} rows parsed")

    upsert("sanctions", ["ent_num", "name", "sdn_type", "program", "vessel_flag", "remarks"],
           rows, conflict=["ent_num"])
    vessels = sum(1 for x in rows if (x[2] or "").lower() == "vessel")
    print(f"OFAC: loaded {len(rows)} entries ({vessels} vessels)")
    return len(rows)


if __name__ == "__main__":
    main()
