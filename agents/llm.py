"""Provider-agnostic LLM client for agent narration.

Default provider is Cerebras (fastest inference available — the point of a
"47 seconds" pitch), reached through the OpenAI-compatible SDK so no extra
dependency is needed. Swap providers with LLM_PROVIDER / LLM_MODEL (see
config.PROVIDERS).

Critical property: this layer is OPTIONAL. Every number in the pipeline is
computed deterministically elsewhere; the LLM only writes prose. If no key is
set, or a call fails, `.narrate()` returns None and the caller falls back to a
templated sentence. The pipeline therefore always runs end-to-end — even with
Cerebras down on stage.
"""
from __future__ import annotations

import os
from typing import Optional

from . import config


class LLM:
    def __init__(self) -> None:
        self.provider = config.LLM_PROVIDER
        spec = config.PROVIDERS.get(self.provider)
        self.model = config.LLM_MODEL or (spec["default_model"] if spec else None)
        self.client = None
        self.enabled = False
        self.reason_disabled = None

        if spec is None:
            self.reason_disabled = f"unknown LLM_PROVIDER '{self.provider}'"
            return
        key = os.getenv(spec["key_env"])
        if not key:
            self.reason_disabled = f"{spec['key_env']} not set"
            return
        try:
            from openai import OpenAI
        except ImportError:
            self.reason_disabled = "openai package not installed"
            return
        # Bound every call so a throttled free tier can't blow the 47s clock:
        # short timeout and NO retries — a rate-limited call fails fast and
        # falls back to its template instead of waiting on 429 backoff.
        self.client = OpenAI(api_key=key, base_url=spec["base_url"],
                             timeout=float(config.LLM_TIMEOUT_S), max_retries=0)
        self.enabled = True

    def narrate(self, system: str, user: str, max_tokens: int = 500,
                temperature: float = 0.3) -> Optional[str]:
        """Return a short plain-text completion, or None if unavailable."""
        if not self.enabled:
            return None
        # gpt-oss is a reasoning model; keep reasoning cheap so latency stays
        # low and the token budget isn't eaten before the answer.
        extra = {"reasoning_effort": "low"} if (self.model or "").startswith("gpt-oss") else None
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_tokens=max_tokens,
                temperature=temperature,
                extra_body=extra,
            )
            text = (resp.choices[0].message.content or "").strip()
            return text or None
        except Exception as e:  # network / rate-limit / bad model — never fatal
            print(f"[llm] narrate failed ({self.provider}/{self.model}): {e}")
            return None


_LLM: Optional[LLM] = None


def get_llm() -> LLM:
    global _LLM
    if _LLM is None:
        _LLM = LLM()
    return _LLM
