```python
from __future__ import annotations

import time
import requests
import upstox_client


OPTION_CHAIN_URL = (
    "https://api.upstox.com/v2/option/chain"
)

MARKET_DATA_AUTHORIZE_URL = (
    "https://api.upstox.com/v3/feed/market-data-feed/authorize"
)

UNDERLYINGS = {
    "NIFTY": "NSE_INDEX|Nifty 50",
    "BANKNIFTY": "NSE_INDEX|Nifty Bank",
}


def option_chain(
    access_token,
    underlying,
    expiry="current_week",
):
    if underlying not in UNDERLYINGS:
        raise ValueError(
            f"Unsupported underlying: {underlying}"
        )

    response = requests.get(
        OPTION_CHAIN_URL,
        headers={
            "Accept": "application/json",
            "Authorization":
                f"Bearer {access_token}",
        },
        params={
            "instrument_key":
                UNDERLYINGS[underlying],
            "expiry_date":
                expiry,
        },
        timeout=20,
    )

    response.raise_for_status()

    payload = response.json()

    if payload.get("status") != "success":
        raise RuntimeError(
            str(payload)
        )

    return payload.get(
        "data",
        []
    )


def build_contract_metadata(
    data,
    underlying,
):
    contracts = {}

    for row in data:
        strike = float(
            row.get(
                "strike_price",
                0,
            )
            or 0
        )

        expiry = (
            row.get("expiry")
            or ""
        )

        for side, field in (
            ("CE", "call_options"),
            ("PE", "put_options"),
        ):
            option = (
                row.get(field)
                or {}
            )

            instrument_key = (
                option.get(
                    "instrument_key"
                )
            )

            market_data = (
                option.get(
                    "market_data"
                )
                or {}
            )

            if not instrument_key:
                continue

            contracts[
                instrument_key
            ] = {
                "underlying":
                    underlying,

                "strike":
                    strike,

                "side":
                    side,

                "expiry":
                    expiry,

                "prev_oi":
                    float(
                        market_data.get(
                            "prev_oi",
                            0,
                        )
                        or 0
                    ),

                "close_price":
                    float(
                        market_data.get(
                            "close_price",
                            0,
                        )
                        or 0
                    ),

                "chain_volume":
                    float(
                        market_data.get(
                            "volume",
                            0,
                        )
                        or 0
                    ),
            }

    return contracts


def authorize_market_feed(
    access_token,
):
    """
    Get a fresh one-time authorized
    WebSocket redirect URI from Upstox.
    """

    response = requests.get(
        MARKET_DATA_AUTHORIZE_URL,
        headers={
            "Accept":
                "application/json",
            "Authorization":
                f"Bearer {access_token}",
        },
        timeout=20,
    )

    response.raise_for_status()

    payload = response.json()

    if payload.get("status") != "success":
        raise RuntimeError(
            f"Market feed authorization failed: "
            f"{payload}"
        )

    uri = (
        payload.get("data", {})
        .get("authorized_redirect_uri")
    )

    if not uri:
        raise RuntimeError(
            "Upstox did not return "
            "authorized_redirect_uri."
        )

    return uri


def make_streamer(
    access_token
):
    """
    Create the official Upstox V3
    MarketDataStreamer.

    We first request a fresh authorized
    feed URL so every connection attempt
    gets a new one-time authorization.
    """

    # Fresh authorization request.
    # The returned URI is one-time-use.
    authorized_uri = authorize_market_feed(
        access_token
    )

    configuration = (
        upstox_client.Configuration()
    )

    configuration.access_token = (
        access_token
    )

    # Keep the URI available for diagnostics.
    # The official SDK handles the V3
    # websocket authentication itself.
    streamer = (
        upstox_client.MarketDataStreamerV3(
            upstox_client.ApiClient(
                configuration
            ),
            [],
            "full",
        )
    )

    # Store only non-sensitive information.
    streamer._authorized_feed_ready = True
    streamer._authorized_feed_uri_created_at = time.time()

    return streamer
```
