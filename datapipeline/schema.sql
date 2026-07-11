-- All tables for the data platform. Idempotent (IF NOT EXISTS everywhere).
-- structured_events is also created by gdelt_and_gkg/load_to_postgres.py;
-- the definition here must stay in sync with it.

-- EIA: official daily Brent / WTI spot prices
CREATE TABLE IF NOT EXISTS prices (
    day     date    NOT NULL,
    ticker  text    NOT NULL,          -- 'BRENT' | 'WTI'
    usd     numeric NOT NULL,
    source  text    NOT NULL,          -- 'EIA'
    PRIMARY KEY (day, ticker, source)
);

-- yfinance: live/intraday price ticks
CREATE TABLE IF NOT EXISTS price_ticks (
    ts      timestamptz NOT NULL,
    ticker  text        NOT NULL,      -- 'BZ=F' (Brent) | 'CL=F' (WTI)
    usd     numeric     NOT NULL,
    PRIMARY KEY (ts, ticker)
);

-- OFAC SDN: sanctions list (vessels & entities)
CREATE TABLE IF NOT EXISTS sanctions (
    ent_num     integer PRIMARY KEY,
    name        text,
    sdn_type    text,                  -- 'vessel' | 'individual' | ...
    program     text,
    vessel_flag text,
    remarks     text
);

-- AISStream: vessel position reports (pruned to a rolling window by the controller)
CREATE TABLE IF NOT EXISTS vessels (
    mmsi    bigint            NOT NULL,
    lat     double precision,
    lon     double precision,
    sog     double precision,          -- speed over ground (knots)
    cog     double precision,          -- course over ground (deg)
    ts      timestamptz       NOT NULL,
    name    text,
    PRIMARY KEY (mmsi, ts)
);

-- PPAC: India monthly crude / petroleum import-export (quantity + value).
CREATE TABLE IF NOT EXISTS imports_india (
    period       date,      -- first of month, e.g. 2025-04-01 (for sorting/plots)
    month        text,      -- 'April'
    year         integer,
    product      text,      -- 'CRUDE OIL', 'LPG', 'NET IMPORT' ...
    trade        text,      -- 'Import' | 'Export'
    quantity_tmt numeric,   -- thousand metric tonnes
    value_inr_cr numeric,   -- value in crore rupees
    value_usd_mn numeric    -- value in million US dollars
);

-- GDELT pipeline output: structured risk signals
CREATE TABLE IF NOT EXISTS structured_events (
    event_id            TEXT PRIMARY KEY,
    event_date          DATE,
    actors              TEXT[],
    location_country    TEXT,
    corridor_affected   TEXT,
    event_category      TEXT,
    severity_score      REAL,
    confidence          REAL,
    summary             TEXT,
    loaded_at           TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_structured_events_corridor
    ON structured_events (corridor_affected);
CREATE INDEX IF NOT EXISTS idx_structured_events_date
    ON structured_events (event_date);
CREATE INDEX IF NOT EXISTS idx_structured_events_severity
    ON structured_events (severity_score DESC);

-- Controller bookkeeping: when did each feed last load, and how did it go.
-- Drives cadence gating in controller.py and the /freshness API endpoint.
CREATE TABLE IF NOT EXISTS ingest_runs (
    feed        text PRIMARY KEY,
    last_run    timestamptz,
    last_status text,       -- 'ok' | 'error' | 'skipped'
    last_rows   integer,
    note        text
);
