import os
import time
import threading
from collections import defaultdict, deque
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from upstox import option_chain
from engine import Contract, score_contract

load_dotenv()

TOKEN = os.getenv("UPSTOX_ACCESS_TOKEN", "")
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "10"))

app = FastAPI(title="Big Money Scanner V1")

history = defaultdict(lambda: deque(maxlen=20))
latest = {"NIFTY": [], "BANKNIFTY": []}
errors = []
lock = threading.Lock()

def build_rows(name, data):
    rows = []
    for item in data:
        for side, key in [("CE", "call_options"), ("PE", "put_options")]:
            opt = item.get(key) or {}
            md = opt.get("market_data") or {}
            if not md.get("ltp") or not opt.get("instrument_key"):
                continue
            c = Contract(
                instrument_key=opt["instrument_key"],
                strike=float(item.get("strike_price", 0)),
                side=side,
                ltp=float(md.get("ltp", 0)),
                prev_ltp=float(md.get("close_price", md.get("ltp", 0)) or 0),
                volume=float(md.get("volume", 0) or 0),
                oi=float(md.get("oi", 0) or 0),
                prev_oi=float(md.get("prev_oi", 0) or 0),
                bid=float(md.get("bid_price", 0) or 0),
                ask=float(md.get("ask_price", 0) or 0),
                bid_qty=float(md.get("bid_qty", 0) or 0),
                ask_qty=float(md.get("ask_qty", 0) or 0),
            )
            h = history[c.instrument_key]
            h.append(c.volume)
            avg = sum(h) / len(h) if len(h) > 1 else None
            row = score_contract(c, avg)
            row["underlying"] = name
            row["spot"] = item.get("underlying_spot_price")
            row["expiry"] = item.get("expiry")
            rows.append(row)
    return sorted(rows, key=lambda x: x["score"], reverse=True)

def worker():
    global latest
    while True:
        if TOKEN:
            for name in ("NIFTY", "BANKNIFTY"):
                try:
                    rows = build_rows(name, option_chain(TOKEN, name))
                    with lock:
                        latest[name] = rows[:100]
                except Exception as e:
                    with lock:
                        errors.append(f"{name}: {e}")
                        del errors[:-20]
        time.sleep(POLL_SECONDS)

@app.on_event("startup")
def startup():
    threading.Thread(target=worker, daemon=True).start()

@app.get("/api/status")
def status():
    with lock:
        return JSONResponse({
            "configured": bool(TOKEN),
            "poll_seconds": POLL_SECONDS,
            "nifty": latest["NIFTY"][:30],
            "banknifty": latest["BANKNIFTY"][:30],
            "errors": errors[-5:],
        })

@app.get("/", response_class=HTMLResponse)
def home():
    return HTMLResponse((Path(__file__).parent / "index.html").read_text(encoding="utf-8"))
