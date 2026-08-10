from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from time import time


CR = 10_000_000


def clamp(value, low=0.0, high=100.0):
    return max(low, min(high, float(value)))


def safe_pct(current, previous):
    if not previous:
        return 0.0

    return ((current - previous) / previous) * 100.0


@dataclass
class FlowPoint:
    ts: float
    signed_value: float
    value: float


@dataclass
class ContractState:

    instrument_key: str
    underlying: str
    strike: float
    side: str
    expiry: str

    prev_oi: float = 0.0
    close_price: float = 0.0

    ltp: float = 0.0
    prev_ltp: float = 0.0

    volume: float = 0.0
    prev_volume: float = 0.0

    oi: float = 0.0

    bid: float = 0.0
    ask: float = 0.0

    bid_qty: float = 0.0
    ask_qty: float = 0.0

    delta: float = 0.0
    iv: float = 0.0

    vwap_pv: float = 0.0
    vwap_volume: float = 0.0

    flow: deque = field(
        default_factory=deque
    )

    oi_history: deque = field(
        default_factory=lambda:
        deque(maxlen=120)
    )

    volume_samples: deque = field(
        default_factory=lambda:
        deque(maxlen=60)
    )

    def update(
        self,
        *,
        ltp,
        volume,
        oi,
        bid,
        ask,
        bid_qty,
        ask_qty,
        delta=0.0,
        iv=0.0,
        ts=None,
    ):

        now = ts or time()

        self.prev_ltp = (
            self.ltp
            or float(ltp or 0)
        )

        self.prev_volume = self.volume
        self.prev_oi = self.oi

        self.ltp = float(ltp or 0)

        self.volume = max(
            float(volume or 0),
            0
        )

        self.oi = max(
            float(oi or 0),
            0
        )

        self.bid = float(bid or 0)
        self.ask = float(ask or 0)

        self.bid_qty = float(
            bid_qty or 0
        )

        self.ask_qty = float(
            ask_qty or 0
        )

        self.delta = float(
            delta or 0
        )

        self.iv = float(
            iv or 0
        )

        self.oi_history.append(
            (now, self.oi)
        )

        volume_change = max(
            self.volume -
            self.prev_volume,
            0
        )

        if (
            volume_change > 0
            and self.ltp > 0
        ):

            self.vwap_pv += (
                self.ltp *
                volume_change
            )

            self.vwap_volume += (
                volume_change
            )

            tolerance = max(
                self.ltp * 0.0002,
                0.01
            )

            if (
                self.ask > 0
                and self.ltp >=
                self.ask - tolerance
            ):

                sign = 1.0

            elif (
                self.bid > 0
                and self.ltp <=
                self.bid + tolerance
            ):

                sign = -1.0

            else:

                sign = (
                    1.0
                    if self.ltp >=
                    self.prev_ltp
                    else -1.0
                )

            value = (
                self.ltp *
                volume_change
            )

            self.flow.append(
                FlowPoint(
                    now,
                    sign * value,
                    value
                )
            )

        cutoff = now - 60

        while (
            self.flow
            and self.flow[0].ts <
            cutoff
        ):

            self.flow.popleft()

        self.volume_samples.append(
            self.volume
        )

    @property
    def vwap(self):

        if self.vwap_volume:

            return (
                self.vwap_pv /
                self.vwap_volume
            )

        return self.ltp

    @property
    def money_flow_60s(self):

        return sum(
            x.signed_value
            for x in self.flow
        )

    @property
    def turnover_60s(self):

        return sum(
            x.value
            for x in self.flow
        )

    @property
    def volume_spike(self):

        if len(
            self.volume_samples
        ) < 5:

            return 1.0

        baseline = (
            sum(
                self.volume_samples
            )
            /
            len(
                self.volume_samples
            )
        )

        if baseline <= 0:

            return 1.0

        return (
            self.volume /
            baseline
        )

    @property
    def oi_change(self):

        return (
            self.oi -
            self.prev_oi
        )

    @property
    def oi_change_pct(self):

        return safe_pct(
            self.oi,
            self.prev_oi
        )

    @property
    def price_change_pct(self):

        reference = (
            self.close_price
            or self.prev_ltp
        )

        return safe_pct(
            self.ltp,
            reference
        )

    @property
    def signal(self):

        price = self.price_change_pct
        oi = self.oi_change

        if (
            price > 0.15
            and oi > 0
        ):

            return "LONG BUILD-UP"

        if (
            price < -0.15
            and oi > 0
        ):

            return "SHORT BUILD-UP"

        if (
            price > 0.15
            and oi < 0
        ):

            return "SHORT COVERING"

        if (
            price < -0.15
            and oi < 0
        ):

            return "LONG UNWINDING"

        return "NEUTRAL"


def score_state(
    state: ContractState,
    min_money_cr=10.0
):

    flow_cr = (
        abs(
            state.money_flow_60s
        )
        / CR
    )

    turnover_cr = (
        state.turnover_60s
        / CR
    )

    money_score = clamp(
        flow_cr /
        max(
            min_money_cr,
            1.0
        )
        * 70
    )

    volume_score = clamp(
        (
            state.volume_spike -
            1.0
        )
        * 45
    )

    oi_score = clamp(
        min(
            abs(
                state.oi_change_pct
            ),
            20.0
        )
        * 4
    )

    if (
        state.ltp
        and state.ask > 0
        and state.bid > 0
    ):

        spread_pct = (
            (
                state.ask -
                state.bid
            )
            /
            state.ltp
            * 100
        )

    else:

        spread_pct = 100.0

    liquidity_score = clamp(
        100 -
        spread_pct * 20
    )

    price_score = clamp(
        abs(
            state.price_change_pct
        )
        * 20
    )

    score = (

        0.35 *
        money_score

        +

        0.20 *
        volume_score

        +

        0.20 *
        oi_score

        +

        0.15 *
        liquidity_score

        +

        0.10 *
        price_score
    )

    if (
        flow_cr >= 50
        and score >= 85
    ):

        label = "WHALE"

    elif (
        flow_cr >= 25
        and score >= 70
    ):

        label = "VERY BIG MONEY"

    elif (
        flow_cr >= 10
        and score >= 55
    ):

        label = "BIG MONEY"

    elif score >= 40:

        label = "WATCH"

    else:

        label = "NORMAL"

    if state.money_flow_60s > 0:

        pressure = "BUY PRESSURE"

    elif state.money_flow_60s < 0:

        pressure = "SELL PRESSURE"

    else:

        pressure = "BALANCED"

    return {

        "instrument_key":
            state.instrument_key,

        "underlying":
            state.underlying,

        "strike":
            state.strike,

        "side":
            state.side,

        "expiry":
            state.expiry,

        "ltp":
            round(
                state.ltp,
                2
            ),

        "vwap":
            round(
                state.vwap,
                2
            ),

        "turnover_60s_cr":
            round(
                turnover_cr,
                2
            ),

        "net_flow_60s_cr":
            round(
                state.money_flow_60s
                / CR,
                2
            ),

        "volume":
            int(
                state.volume
            ),

        "volume_spike":
            round(
                state.volume_spike,
                2
            ),

        "oi":
            int(
                state.oi
            ),

        "oi_change":
            int(
                state.oi_change
            ),

        "oi_change_pct":
            round(
                state.oi_change_pct,
                2
            ),

        "oi_change_60s":
            int(
                state.oi_change_60s
            ),

        "oi_change_60s_pct":
            round(
                state.oi_change_60s_pct,
                2
            ),

        "price_change_pct":
            round(
                state.price_change_pct,
                2
            ),

        "bid":
            round(
                state.bid,
                2
            ),

        "ask":
            round(
                state.ask,
                2
            ),

        "bid_qty":
            int(
                state.bid_qty
            ),

        "ask_qty":
            int(
                state.ask_qty
            ),

        "spread_pct":
            round(
                spread_pct,
                3
            ),

        "delta":
            round(
                state.delta,
                4
            ),

        "iv":
            round(
                state.iv,
                4
            ),

        "signal":
            state.signal,

        "pressure":
            pressure,

        "money_action":
            state.money_action,

        "money_event":
            (
                label != "NORMAL"
                and state.money_action != "NO ACTION"
            ),

        "event_type":
            (
                "ENTRY"
                if "ENTRY" in state.money_action
                else (
                    "EXIT"
                    if "EXIT" in state.money_action
                    else "NONE"
                )
            ),

        "score":
            round(
                score,
                1
            ),

        "label":
            label,
    }
