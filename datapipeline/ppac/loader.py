"""PPAC India monthly import/export CSV -> imports_india (typed).

Reads datapipeline/ppac/data/ppac.csv (data.gov.in PPAC monthly sheet):
Month, Year, PRODUCTS, TRADE, Quantity (000 MT), Value (Rs Crore), Value (US$ Mn).
Adds a `period` date (first of month) for easy time-series queries.

Run from the repo root:  python3 -m datapipeline.ppac.loader
"""
import csv
import os
from datetime import date

from datapipeline.common.db import connect, upsert

CSV_PATH = os.path.join(os.path.dirname(__file__), "data", "ppac.csv")
MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December"], start=1)}


def num(v):
    v = (v or "").strip().replace(",", "")
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def main():
    if not os.path.exists(CSV_PATH):
        print("PPAC: no data/ppac.csv found -> skipping.")
        return 0

    rows = []
    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            month = (r.get("Month") or "").strip()
            try:
                year = int((r.get("Year") or "").strip())
            except ValueError:
                year = None
            mnum = MONTHS.get(month)
            period = date(year, mnum, 1) if (year and mnum) else None
            rows.append((
                period, month, year,
                (r.get("PRODUCTS") or "").strip(),
                (r.get("TRADE") or "").strip(),
                num(r.get("Quantity (000 Metric Tonnes)")),
                num(r.get("Value in Rupees (Crore)")),
                num(r.get("Value in Dollars (Million US dollar)")),
            ))

    with connect() as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE imports_india")   # fresh load every run
        conn.commit()
    upsert("imports_india",
           ["period", "month", "year", "product", "trade",
            "quantity_tmt", "value_inr_cr", "value_usd_mn"], rows)
    print(f"PPAC: loaded {len(rows)} monthly rows into imports_india (typed)")
    return len(rows)


if __name__ == "__main__":
    main()
