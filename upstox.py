from __future__ import annotations

import requests
import upstox_client


OPTION_CHAIN_URL = (
    "https://api.upstox.com/v2/option/chain"
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


def make_streamer(
    access_token
):

    configuration = (
        upstox_client.Configuration()
    )

    configuration.access_token = (
        access_token
    )

    return (
        upstox_client.MarketDataStreamerV3(
            upstox_client.ApiClient(
                configuration
            ),
            [],
            "full",
        )
        )
