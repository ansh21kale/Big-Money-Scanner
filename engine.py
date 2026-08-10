from dataclasses import dataclass
from typing import Optional

@dataclass
class Contract:
    instrument_key: str
    strike: float
    side: str
    ltp: float
    prev_ltp: float
    volume: float
    oi: float
    prev_oi: float
    bid: float
    ask: float
    bid_qty: float
    ask_qty: float

def clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))

def money_flow(ltp, volume):
    return max(0.0, float(ltp or 0) * float(volume or 0))

def classify(price_delta, oi_delta):
    if price_delta > 0 and oi_delta > 0:
        return "LONG BUILD-UP"
    if price_delta < 0 and oi_delta > 0:
        return "SHORT BUILD-UP"
    if price_delta > 0 and oi_delta < 0:
        return "SHORT COVERING"
    if price_delta < 0 and oi_delta < 0:
        return "LONG UNWINDING"
    return "NEUTRAL"

def score_contract(c: Contract, avg_volume: Optional[float] = None):
    mf = money_flow(c.ltp, c.volume)
    # Money-flow component: 0 at 0Cr, 100 at 50Cr.
    money_score = clamp((mf / 50_00_00_000) * 100)

    if avg_volume and avg_volume > 0:
        vol_spike = c.volume / avg_volume
    else:
        vol_spike = 1.0

    # 1x=0, 2x=50, 3x+=100.
    volume_score = clamp((vol_spike - 1.0) * 50)

    oi_delta = c.oi - c.prev_oi
    oi_pct = (oi_delta / c.prev_oi * 100) if c.prev_oi else 0.0
    oi_score = clamp(abs(oi_pct) * 5)

    spread = ((c.ask - c.bid) / c.ltp * 100) if c.ltp and c.ask and c.bid else 100
    liquidity_score = clamp(100 - spread * 20)

    score = (
        0.35 * money_score +
        0.25 * volume_score +
        0.25 * oi_score +
        0.15 * liquidity_score
    )

    label = (
        "WHALE" if mf >= 50_00_00_000 and score >= 90 else
        "VERY BIG MONEY" if mf >= 25_00_00_000 and score >= 75 else
        "BIG MONEY" if mf >= 10_00_00_000 and score >= 60 else
        "WATCH" if score >= 40 else
        "NORMAL"
    )

    return {
        "instrument_key": c.instrument_key,
        "strike": c.strike,
        "side": c.side,
        "ltp": round(c.ltp, 2),
        "money_flow": round(mf, 2),
        "money_flow_cr": round(mf / 1e7, 2),
        "volume": int(c.volume),
        "volume_spike": round(vol_spike, 2),
        "oi": int(c.oi),
        "oi_change": int(oi_delta),
        "oi_change_pct": round(oi_pct, 2),
        "price_change_pct": round(((c.ltp-c.prev_ltp)/c.prev_ltp*100) if c.prev_ltp else 0, 2),
        "liquidity_score": round(liquidity_score, 1),
        "score": round(score, 1),
        "signal": classify(c.ltp-c.prev_ltp, oi_delta),
        "label": label,
    }
