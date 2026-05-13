from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sniper.core.models import RawEvent, TokenMetadata, TokenMetrics
from sniper.listener.scanner import event_to_metadata


@dataclass(slots=True)
class TradeTick:
    ts: datetime
    side: str
    trader: str
    sol_amount: float
    price_sol: float
    liquidity_sol: float
    market_cap_sol: float


class TokenTradeAggregator:
    def __init__(self, window_seconds: int = 60, max_tokens: int = 500) -> None:
        self.window = timedelta(seconds=window_seconds)
        self.max_tokens = max_tokens
        self.metadata: dict[str, TokenMetadata] = {}
        self.trades: dict[str, deque[TradeTick]] = defaultdict(deque)
        self.first_price: dict[str, float] = {}
        self.last_price: dict[str, float] = {}

    def add_new_token(self, event: RawEvent) -> TokenMetadata:
        meta = event_to_metadata(event)
        self.metadata[meta.mint] = meta
        self._trim_tokens()
        return meta

    def add_trade(self, event: RawEvent) -> TokenMetrics | None:
        mint = event.mint
        if mint not in self.metadata:
            return None
        tick = self._event_to_tick(event)
        ticks = self.trades[mint]
        ticks.append(tick)
        cutoff = event.ts - self.window
        while ticks and ticks[0].ts < cutoff:
            ticks.popleft()
        if tick.price_sol > 0:
            self.first_price.setdefault(mint, tick.price_sol)
            self.last_price[mint] = tick.price_sol
        return self.metrics(mint, event.ts)

    def metrics(self, mint: str, ts: datetime) -> TokenMetrics | None:
        meta = self.metadata.get(mint)
        if not meta:
            return None
        ticks = list(self.trades.get(mint, ()))
        buys = [x for x in ticks if x.side == "buy"]
        sells = [x for x in ticks if x.side == "sell"]
        buyers = {x.trader for x in buys if x.trader}
        price = self.last_price.get(mint, self.first_price.get(mint, 0.0))
        first = self.first_price.get(mint, price)
        momentum = ((price - first) / first) if first > 0 else 0.0
        latest = ticks[-1] if ticks else None
        created = meta.created_at if meta.created_at.tzinfo else meta.created_at.replace(tzinfo=timezone.utc)
        observed_seconds = self._observed_seconds(ticks, created, ts)
        return TokenMetrics(
            mint=mint,
            ts=ts,
            age_seconds=max(0.0, (ts - created).total_seconds()),
            market_cap_sol=latest.market_cap_sol if latest else 0.0,
            liquidity_sol=latest.liquidity_sol if latest else 0.0,
            volume_60s_sol=sum(x.sol_amount for x in ticks),
            unique_buyers_60s=len(buyers),
            buy_count_60s=len(buys),
            sell_count_60s=len(sells),
            buy_velocity=len(buys) / observed_seconds,
            price_sol=price,
            price_change_30s_pct=momentum,
            top10_holder_pct=0.20,
            top1_holder_pct=0.04,
            creator_holder_pct=0.02,
            whale_dump_pct_30s=self._whale_dump(sells, ticks),
            liquidity_drop_pct_30s=0.0,
            suspicious_wallet_hits=0,
            repeated_deployer_pattern=False,
            wash_trade_score=self._wash_score(ticks),
            bot_activity_score=self._bot_score(ticks),
            estimated_slippage_pct=self._slippage_estimate(latest.liquidity_sol if latest else 0.0),
        )

    def _event_to_tick(self, event: RawEvent) -> TradeTick:
        p = event.payload
        price = _price(p)
        return TradeTick(
            ts=event.ts,
            side=str(p.get("txType", p.get("side", ""))).lower(),
            trader=str(p.get("traderPublicKey", p.get("trader", p.get("wallet", "")))),
            sol_amount=_num(p.get("solAmount", p.get("sol_amount", p.get("amountSol", 0)))),
            price_sol=price,
            liquidity_sol=_num(p.get("vSolInBondingCurve", p.get("liquidity_sol", p.get("liquiditySol", 0)))),
            market_cap_sol=_num(p.get("marketCapSol", p.get("market_cap_sol", p.get("marketCap", 0)))),
        )

    def _trim_tokens(self) -> None:
        while len(self.metadata) > self.max_tokens:
            mint = next(iter(self.metadata))
            self.metadata.pop(mint, None)
            self.trades.pop(mint, None)
            self.first_price.pop(mint, None)
            self.last_price.pop(mint, None)

    @staticmethod
    def _wash_score(ticks: list[TradeTick]) -> float:
        if len(ticks) < 4:
            return 0.0
        traders = [x.trader for x in ticks if x.trader]
        return 1.0 - (len(set(traders)) / max(len(traders), 1))

    @staticmethod
    def _bot_score(ticks: list[TradeTick]) -> float:
        if len(ticks) < 12:
            return 0.0
        gaps = [(ticks[i].ts - ticks[i - 1].ts).total_seconds() for i in range(1, len(ticks))]
        fast = sum(1 for gap in gaps if gap < 0.15)
        return min(1.0, (fast / max(len(gaps), 1)) * 0.75)

    def _observed_seconds(self, ticks: list[TradeTick], created: datetime, now: datetime) -> float:
        if len(ticks) >= 2:
            span = (ticks[-1].ts - ticks[0].ts).total_seconds()
        else:
            span = (now - created).total_seconds()
        return max(5.0, min(self.window.total_seconds(), span))

    @staticmethod
    def _whale_dump(sells: list[TradeTick], ticks: list[TradeTick]) -> float:
        total = sum(x.sol_amount for x in ticks)
        largest_sell = max((x.sol_amount for x in sells), default=0.0)
        return largest_sell / total if total > 0 else 0.0

    @staticmethod
    def _slippage_estimate(liquidity_sol: float) -> float:
        if liquidity_sol <= 0:
            return 1.0
        return min(0.5, 0.1 / liquidity_sol)


def is_trade_event(event: RawEvent) -> bool:
    side = str(event.payload.get("txType", event.payload.get("side", ""))).lower()
    return side in {"buy", "sell"}


def _num(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _price(payload: dict) -> float:
    explicit = _num(payload.get("price_sol", payload.get("priceSol", 0)))
    if explicit > 0:
        return explicit
    sol = _num(payload.get("vSolInBondingCurve"))
    tokens = _num(payload.get("vTokensInBondingCurve"))
    return sol / tokens if sol > 0 and tokens > 0 else 0.0
