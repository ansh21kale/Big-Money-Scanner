import os
import requests

BASE = "https://api.upstox.com/v2/option/chain"

UNDERLYINGS = {
    "NIFTY": "NSE_INDEX|Nifty 50",
    "BANKNIFTY": "NSE_INDEX|Nifty Bank",
}

def option_chain(access_token: str, underlying: str, expiry="current_week"):
    if underlying not in UNDERLYINGS:
        raise ValueError("Unsupported underlying")
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {access_token}",
    }
    params = {
        "instrument_key": UNDERLYINGS[underlying],
        "expiry_date": expiry,
    }
    r = requests.get(BASE, headers=headers, params=params, timeout=15)
    r.raise_for_status()
    payload = r.json()
    if payload.get("status") != "success":
        raise RuntimeError(payload)
    return payload["data"]
