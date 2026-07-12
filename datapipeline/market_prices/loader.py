"""yfinance -> price_ticks table.  Intraday Brent (BZ=F) & WTI (CL=F).

Run from the repo root:  python3 -m datapipeline.market_prices.loader
"""
import yfinance as yf

from datapipeline.common.db import upsert

TICKERS = ["BZ=F", "CL=F"]
PRICE_MIN, PRICE_MAX = 1.0, 500.0  # sanity range: outside this it's a bad tick, not a price


def main():
    df = yf.download(TICKERS, period="5d", interval="1m", progress=False, auto_adjust=True)
    close = df["Close"]
    rows, rejected = [], 0
    for ts, row in close.iterrows():
        for tk in TICKERS:
            v = row.get(tk)
            if v is None or v != v:  # skip NaN
                continue
            if not (PRICE_MIN <= float(v) <= PRICE_MAX):
                rejected += 1
                continue
            rows.append((ts.to_pydatetime(), tk, float(v)))
    if rejected:
        print(f"yfinance: WARNING rejected {rejected} out-of-range ticks")
    upsert("price_ticks", ["ts", "ticker", "usd"], rows, conflict=["ts", "ticker"])
    print(f"yfinance: loaded {len(rows)} tick rows")
    return len(rows)


if __name__ == "__main__":
    main()
