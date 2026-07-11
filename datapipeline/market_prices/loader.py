"""yfinance -> price_ticks table.  Intraday Brent (BZ=F) & WTI (CL=F).

Run from the repo root:  python3 -m datapipeline.market_prices.loader
"""
import yfinance as yf

from datapipeline.common.db import upsert

TICKERS = ["BZ=F", "CL=F"]


def main():
    df = yf.download(TICKERS, period="5d", interval="1m", progress=False, auto_adjust=True)
    close = df["Close"]
    rows = []
    for ts, row in close.iterrows():
        for tk in TICKERS:
            v = row.get(tk)
            if v is not None and v == v:  # skip NaN
                rows.append((ts.to_pydatetime(), tk, float(v)))
    upsert("price_ticks", ["ts", "ticker", "usd"], rows, conflict=["ts", "ticker"])
    print(f"yfinance: loaded {len(rows)} tick rows")
    return len(rows)


if __name__ == "__main__":
    main()
