from __future__ import annotations

import os
import threading
import time

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from engine import ContractState, score_state
from upstox import (
    option_chain,
    build_contract_metadata,
    make_streamer,
)

load_dotenv()

TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN", "")
MIN_MONEY_CR = float(os.getenv("MIN_MONEY_CR", "10"))
MAX_CONTRACTS = int(os.getenv("MAX_CONTRACTS", "1400"))

app = FastAPI(title="Big Money Scanner Live V2")

states = {}
metadata = {}

latest = {
    "NIFTY": [],
    "BANKNIFTY": [],
}

errors = []

connection = {
    "status": "starting",
    "last_message": None,
}

lock = threading.RLock()
streamer = None
current_keys = []


def add_error(err):
    with lock:
        errors.append(str(err))
        del errors[:-10]


def extract_tick(feed):
    if not isinstance(feed, dict):
        return None

    full = feed.get("fullFeed") or {}

    full = (
        full.get("marketFF")
        or feed.get("firstLevelWithGreeks")
        or {}
    )

    ltpc = full.get("ltpc") or {}

    level = full.get("marketLevel") or {}

    quotes = level.get("bidAskQuote") or []

    first = quotes[0] if quotes else {}

    greeks = full.get("optionGreeks") or {}

    ohlcs = (
        (full.get("marketOHLC") or {})
        .get("ohlc") or []
    )

    daily = next(
        (
            x for x in ohlcs
            if x.get("interval") == "1d"
        ),
        {},
    )

    return {
        "ltp": float(
            ltpc.get("ltp") or 0
        ),

        "volume": float(
            full.get("vtt")
            or daily.get("vol")
            or 0
        ),

        "oi": float(
            full.get("oi") or 0
        ),

        "bid": float(
            first.get("bidP") or 0
        ),

        "ask": float(
            first.get("askP") or 0
        ),

        "bid_qty": float(
            first.get("bidQ") or 0
        ),

        "ask_qty": float(
            first.get("askQ") or 0
        ),

        "delta": float(
            greeks.get("delta") or 0
        ),

        "iv": float(
            greeks.get("iv") or 0
        ),
    }


def refresh():
    grouped = {
        "NIFTY": [],
        "BANKNIFTY": [],
    }

    with lock:

        for s in states.values():

            if s.ltp <= 0:
                continue

            try:
                row = score_state(
                    s,
                    MIN_MONEY_CR
                )

                grouped[
                    s.underlying
                ].append(row)

            except Exception as exc:
                add_error(
                    f"score: {exc}"
                )

        for name in grouped:

            grouped[name].sort(
                key=lambda x:
                    x.get(
                        "score",
                        0
                    ),
                reverse=True,
            )

            latest[name] = (
                grouped[name][:150]
            )


def on_message(message):

    if not isinstance(message, dict):
        return

    if message.get("type") != "live_feed":
        return

    now = time.time()

    with lock:

        connection[
            "last_message"
        ] = now

        feeds = (
            message.get("feeds")
            or {}
        )

        for key, feed in feeds.items():

            meta = metadata.get(key)

            if not meta:
                continue

            tick = extract_tick(feed)

            if not tick:
                continue

            if tick["ltp"] <= 0:
                continue

            s = states.get(key)

            if s is None:

                s = ContractState(
                    instrument_key=key,
                    underlying=meta[
                        "underlying"
                    ],
                    strike=meta[
                        "strike"
                    ],
                    side=meta[
                        "side"
                    ],
                    expiry=meta[
                        "expiry"
                    ],
                    prev_oi=meta[
                        "prev_oi"
                    ],
                    close_price=meta[
                        "close_price"
                    ],
                )

                states[key] = s

            s.update(
                **tick,
                ts=now
            )

    refresh()


def on_open():

    global streamer

    connection["status"] = "connected"

    with lock:
        keys = list(current_keys)

    if not keys:
        add_error(
            "Connected but no contracts to subscribe."
        )
        return

    try:

        streamer.subscribe(
            keys,
            "full"
        )

        connection["status"] = (
            f"connected / subscribed "
            f"({len(keys)} contracts)"
        )

    except Exception as exc:

        connection["status"] = "subscription_error"

        add_error(
            f"subscribe: {exc}"
        )


def on_close():

    connection["status"] = "closed"


def on_error(err):

    connection["status"] = "error"

    add_error(
        f"websocket: {err}"
    )


def build_universe():

    combined = {}

    for name in (
        "NIFTY",
        "BANKNIFTY",
    ):

        try:

            chain = option_chain(
                TOKEN,
                name,
                "current_week"
            )

            meta = build_contract_metadata(
                chain,
                name
            )

            combined.update(meta)

        except Exception as exc:

            add_error(
                f"{name} option chain: {exc}"
            )

    if (
        len(combined)
        > MAX_CONTRACTS
    ):

        keys = sorted(
            combined,
            key=lambda k:
                combined[k].get(
                    "chain_volume",
                    0
                ),
            reverse=True,
        )[:MAX_CONTRACTS]

        combined = {
            k: combined[k]
            for k in keys
        }

    with lock:

        metadata.clear()

        metadata.update(
            combined
        )

    return list(combined)


def stream_worker():

    global streamer
    global current_keys

    if not TOKEN:

        connection[
            "status"
        ] = "missing_token"

        return

    while True:

        try:

            keys = build_universe()

            if not keys:

                raise RuntimeError(
                    "Upstox returned no option contracts."
                )

            with lock:
                current_keys = list(keys)

            streamer = make_streamer(
                TOKEN
            )

            streamer.on(
                "open",
                on_open
            )

            streamer.on(
                "message",
                on_message
            )

            streamer.on(
                "close",
                on_close
            )

            streamer.on(
                "error",
                on_error
            )

            streamer.on(
                "reconnecting",
                lambda msg=None:
                    connection.update(
                        status="reconnecting"
                    )
            )

            streamer.auto_reconnect(
                True,
                5,
                20
            )

            connection["status"] = (
                f"connecting "
                f"({len(keys)} contracts)"
            )

            # IMPORTANT:
            # Do NOT subscribe here.
            # Subscription happens inside on_open().

            streamer.connect()

        except Exception as exc:

            connection[
                "status"
            ] = "reconnecting"

            add_error(
                f"stream: {exc}"
            )

            time.sleep(10)


@app.on_event("startup")
def startup():

    threading.Thread(
        target=stream_worker,
        daemon=True
    ).start()


@app.get("/api/status")
def status():

    with lock:

        return JSONResponse({
            "configured":
                bool(TOKEN),

            "connection":
                dict(connection),

            "nifty":
                latest["NIFTY"],

            "banknifty":
                latest["BANKNIFTY"],

            "errors":
                errors[-5:],

            "contracts":
                len(metadata),

            "server_ts":
                time.time(),
        })


@app.get("/health")
def health():

    with lock:

        return {
            "ok": True,

            "configured":
                bool(TOKEN),

            "connection":
                connection["status"],

            "contracts":
                len(metadata),
        }


@app.get(
    "/",
    response_class=HTMLResponse
)
def home():

    with open(
        "index.html",
        "r",
        encoding="utf-8"
    ) as f:

        return HTMLResponse(
            f.read()
    )
