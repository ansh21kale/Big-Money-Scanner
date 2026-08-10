from __future__ import annotations

import requests
import upstox_client


OPTION_CHAIN_URL = (
    "https://api.upstox.com/v2/option/chain"
)

AUTHORIZE_URL = (
    "https://api.upstox.com/v3/feed/market-data-feed/authorize"
)


UNDERLYINGS = {
    "NIFTY": "NSE_INDEX|Nifty 50",
    "BANKNIFTY": "NSE_INDEX|Nifty Bank",
}


def auth_headers(access_token):
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {access_token}",
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
        headers=auth_headers(access_token),
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


def get_authorized_ws_url(
    access_token
):

    response = requests.get(
        AUTHORIZE_URL,
        headers=auth_headers(access_token),
        timeout=20,
    )

    response.raise_for_status()

    payload = response.json()

    if payload.get("status") != "success":
        raise RuntimeError(
            f"WebSocket authorization failed: "
            f"{payload}"
        )

    data = payload.get("data") or {}

    url = data.get(
        "authorized_redirect_uri"
    )

    if not url:
        raise RuntimeError(
            "Upstox did not return "
            "authorized_redirect_uri"
        )

    return url


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


def make_streamer(
    access_token
):

    # First obtain the authorized V3
    # WebSocket URL.
    ws_url = get_authorized_ws_url(
        access_token
    )

    configuration = (
        upstox_client.Configuration()
    )

    configuration.access_token = (
        access_token
    )

    client = upstox_client.ApiClient(
        configuration
    )

    streamer = (
        upstox_client.MarketDataStreamerV3(
            client,
            [],
            "full",
        )
    )

    # Store the authorized URL so that
    # main.py can inspect it if required.
    streamer.authorized_ws_url = (
        ws_url
    )

    return streamer
