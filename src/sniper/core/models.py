from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class TradeSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class TradingMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"
    REPLAY = "replay"


@dataclass(slots=True)
class TokenMetadata:
    mint: str
    symbol: str
    name: str
    deployer: str
    created_at: datetime
    supply: float
    creator_allocation_pct: float
    freeze_authority: str | None = None
    mint_authority: str | None = None
    metadata_uri: str | None = None


@dataclass(slots=True)
class TokenMetrics:
    mint: str
    ts: datetime
    age_seconds: float
    market_cap_sol: float
    liquidity_sol: float
    volume_60s_sol: float
    unique_buyers_60s: int
    buy_count_60s: int
    sell_count_60s: int
    buy_velocity: float
    price_sol: float
    price_change_30s_pct: float
    top10_holder_pct: float
    top1_holder_pct: float
    creator_holder_pct: float
    whale_dump_pct_30s: float = 0.0
    liquidity_drop_pct_30s: float = 0.0
    suspicious_wallet_hits: int = 0
    repeated_deployer_pattern: bool = False
    wash_trade_score: float = 0.0
    bot_activity_score: float = 0.0
    estimated_slippage_pct: float = 0.0


@dataclass(slots=True)
class RawEvent:
    source: str
    event_type: str
    mint: str
    ts: datetime
    payload: dict[str, Any]


@dataclass(slots=True)
class Signal:
    mint: str
    score: float
    passed: bool
    reasons: list[str]
    mode: str
    metrics: TokenMetrics
    metadata: TokenMetadata | None = None


@dataclass(slots=True)
class Position:
    mint: str
    symbol: str
    entry_price: float
    size_sol: float
    token_amount: float
    opened_at: datetime
    stop_loss_price: float
    remaining_pct: float = 1.0
    realized_pnl_sol: float = 0.0
    highest_price: float = 0.0
    take_profit_hits: set[int] = field(default_factory=set)


@dataclass(slots=True)
class OrderResult:
    ok: bool
    tx_signature: str | None
    side: TradeSide
    mint: str
    price_sol: float
    size_sol: float
    token_amount: float
    error: str | None = None


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
