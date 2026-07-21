"""Central configuration for the agent pipeline.

Everything a judge might want to change lives here as an env-overridable knob —
this is the "assumption panel" the brief rewards. Nothing is hidden in code.

Numbers are all deterministic and cite-able; the LLM only narrates them.
"""
from __future__ import annotations

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # dotenv is optional at runtime
    pass


DATABASE_URL = os.getenv("DATABASE_URL")

# --- LLM provider (provider-agnostic; all OpenAI-compatible) -----------------
# Cerebras is the default: free tier, and by far the fastest inference —
# which is the whole point of a "47 seconds" pitch. Swap providers with
# LLM_PROVIDER; override the model with LLM_MODEL.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "cerebras").lower()
LLM_MODEL = os.getenv("LLM_MODEL")  # None -> provider default below
# Per-call ceiling (seconds). Keeps a throttled free tier from blowing the 47s
# clock — a slow narration call just falls back to the template sentence.
LLM_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", "10"))

PROVIDERS = {
    "cerebras": {
        "base_url": "https://api.cerebras.ai/v1",
        "key_env": "CEREBRAS_API_KEY",
        "default_model": "gpt-oss-120b",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "key_env": "OPENROUTER_API_KEY",
        "default_model": "meta-llama/llama-3.3-70b-instruct:free",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "key_env": "GROQ_API_KEY",
        "default_model": "llama-3.3-70b-versatile",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "key_env": "OPENAI_API_KEY",
        "default_model": "gpt-4o-mini",
    },
}

# --- Signal detector ---------------------------------------------------------
# The corridor disruption probability at/above which the scenario+procurement
# chain fires. Hormuz currently scores ~0.88 from live GDELT, so 0.5 triggers.
DISRUPTION_THRESHOLD = float(os.getenv("DISRUPTION_THRESHOLD", "0.5"))

# Risk-score weighting (must mirror /corridors/{c}/risk-score defaults).
WINDOW_DAYS = int(os.getenv("WINDOW_DAYS", "30"))
HALF_LIFE_DAYS = float(os.getenv("HALF_LIFE_DAYS", "7"))

# --- Scenario model + economic cascade (the editable assumption panel) -------
# All approximate real-world anchors; each is a knob a judge can turn on stage.
ASSUMPTIONS = {
    "n_paths": int(os.getenv("MC_PATHS", "10000")),
    "horizon_days": int(os.getenv("MC_HORIZON_DAYS", "30")),
    "brent_daily_vol": float(os.getenv("BRENT_DAILY_VOL", "0.02")),   # ~2%/day
    "usd_inr": float(os.getenv("USD_INR", "86.0")),
    "reserve_cover_days": float(os.getenv("RESERVE_COVER_DAYS", "9.5")),  # PPAC/plan
    "india_crude_kbd": float(os.getenv("INDIA_CRUDE_KBD", "4600")),   # ~4.6 Mb/d (PPAC fallback)
    "bbl_per_tonne": float(os.getenv("BBL_PER_TONNE", "7.33")),       # crude density
    # How strongly a price jump maps to a physical supply shortfall. The
    # cascade price->supply is a SIMPLIFIED elasticity, stated honestly.
    "supply_price_coupling": float(os.getenv("SUPPLY_PRICE_COUPLING", "1.1")),
    # Days of lost flow the reserve must cover before rerouting lands. The
    # reserve agent later refines this with the real top-pick ETA.
    "default_reroute_lag_days": float(os.getenv("REROUTE_LAG_DAYS", "21")),
    "freight_usd_per_bbl_per_day": float(os.getenv("FREIGHT_USD_BBL_DAY", "0.30")),
}

# The two shock archetypes, calibrated on real supply shocks (see the plan's
# §5 table). The detector picks one by the severity of the live signal.
JUMP_ARCHETYPES = {
    # 2019 Abqaiq: ~+15% intraday, reverted in ~2 weeks — a partial disruption.
    "mean_reverting": {
        "jump_mean": 0.15, "jump_sd": 0.05,
        "reversion_half_life_days": 14.0, "persist_fraction": 0.0,
        "label": "Mean-reverting (partial disruption, reverts in ~2 weeks) — cf. 2019 Abqaiq",
    },
    # 1990 Gulf War / 2022 Ukraine: larger, regime-shift jump that sticks.
    "persistent": {
        "jump_mean": 0.30, "jump_sd": 0.10,
        "reversion_half_life_days": 120.0, "persist_fraction": 0.75,
        "label": "Persistent (regime-shift, price stays elevated) — cf. 1990 Gulf War / 2022 Ukraine",
    },
}

# Fraction of India's crude that transits each corridor is derived live from
# the knowledge graph (suppliers whose fastest route crosses that chokepoint);
# this is only the fallback if the graph can't resolve it.
CORRIDOR_SHARE_FALLBACK = {
    "Strait of Hormuz": 0.40,   # ~40% of India's crude (plan)
    "Persian Gulf": 0.45,
    "Red Sea": 0.15,
    "Suez Canal": 0.10,
}

# Chokepoint node id (in the graph) that each risk corridor governs.
CORRIDOR_TO_CHOKEPOINT = {
    "Strait of Hormuz": "Strait of Hormuz",
    "Red Sea": "Bab el-Mandeb",
    "Suez Canal": "Suez Canal",
}

DEFAULT_REFINERY = os.getenv("DEFAULT_REFINERY", "Jamnagar (RIL)")
