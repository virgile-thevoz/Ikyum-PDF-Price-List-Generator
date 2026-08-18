"""Live CHF -> EUR exchange rate fetch, with a buffer and an offline fallback.

Rate source: the Frankfurter API (https://frankfurter.dev), a free, no-key
service that republishes ECB reference rates. This is NOT XE.com's own feed --
XE's API is a paid product with no free tier. Frankfurter tracks the same
mid-market rate family XE does, and is used here as a free equivalent. If a
paid XE subscription is added later, this is the function to swap.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone

import requests


@dataclass
class RateResult:
    mid_market_rate: float       # raw rate as fetched (or fallback value)
    buffered_rate: float         # rate actually used to compute EUR prices
    buffer_percent: float
    source: str                  # "live" or "fallback"
    fetched_at: datetime
    warning: str | None = None   # set when the fallback rate had to be used


def load_config(config_path: str = "config.json") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_live_rate(config: dict) -> float:
    """Calls the Frankfurter API and returns the raw CHF->EUR mid-market rate.

    Raises on any network/parsing failure -- the caller is responsible for
    falling back.
    """
    fx = config["fx"]
    params = {"base": fx["base_currency"], "symbols": fx["target_currency"]}
    response = requests.get(
        fx["api_url"], params=params, timeout=fx.get("request_timeout_seconds", 8)
    )
    response.raise_for_status()
    data = response.json()
    return float(data["rates"][fx["target_currency"]])


def get_current_rate(
    config: dict | None = None, config_path: str = "config.json", apply_buffer: bool = True
) -> RateResult:
    """Fetches the current CHF->EUR rate, optionally applies the configured
    buffer, and falls back to a manually-configured rate if the live fetch
    fails.

    apply_buffer lets the client turn the buffer off for a given generation
    (e.g. a UI checkbox) without touching config.json's buffer_percent,
    which stays the source of truth for *what* the buffer is when it's on.
    RateResult.buffer_percent always reflects what was actually applied (0
    when apply_buffer is False), not just what's configured.
    """
    if config is None:
        config = load_config(config_path)
    fx = config["fx"]
    buffer_percent = fx["buffer_percent"] if apply_buffer else 0.0
    now = datetime.now(timezone.utc)

    try:
        mid_market_rate = fetch_live_rate(config)
        buffered_rate = round(mid_market_rate * (1 + buffer_percent / 100), 6)
        return RateResult(
            mid_market_rate=mid_market_rate,
            buffered_rate=buffered_rate,
            buffer_percent=buffer_percent,
            source="live",
            fetched_at=now,
            warning=None,
        )
    except Exception as exc:
        fallback_rate = fx["fallback_rate"]
        buffered_rate = round(fallback_rate * (1 + buffer_percent / 100), 6)
        warning = (
            f"Live exchange rate fetch failed ({exc}). Used the fallback rate "
            f"from config.json ({fallback_rate}) instead -- double-check this "
            f"against a live rate before sending the price list out."
        )
        return RateResult(
            mid_market_rate=fallback_rate,
            buffered_rate=buffered_rate,
            buffer_percent=buffer_percent,
            source="fallback",
            fetched_at=now,
            warning=warning,
        )


if __name__ == "__main__":
    result = get_current_rate()
    print(result)
