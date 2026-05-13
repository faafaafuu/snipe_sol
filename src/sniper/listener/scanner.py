from __future__ import annotations

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import AsyncIterator

import httpx
import websockets

from sniper.core.models import RawEvent, TokenMetadata, TokenMetrics, utc_now

log = logging.getLogger(__name__)


class Scanner(ABC):
    @abstractmethod
    async def events(self) -> AsyncIterator[RawEvent]:
        raise NotImplementedError


class PumpFunScanner(Scanner):
    def __init__(
        self,
        websocket_url: str | None,
        polling_url: str | None,
        polling_interval_seconds: float,
        subscription_message: dict | None = None,
        auto_subscribe_trades: bool = True,
        max_watched_tokens: int = 100,
        watch_seconds: int = 120,
    ) -> None:
        self.websocket_url = websocket_url
        self.polling_url = polling_url
        self.polling_interval_seconds = polling_interval_seconds
        self.subscription_message = subscription_message or {"method": "subscribeNewToken"}
        self.auto_subscribe_trades = auto_subscribe_trades
        self.max_watched_tokens = max_watched_tokens
        self.watch_seconds = watch_seconds

    async def events(self) -> AsyncIterator[RawEvent]:
        if self.websocket_url:
            try:
                async for event in self._websocket_events():
                    yield event
            except Exception as exc:
                log.warning("websocket scanner failed; falling back to polling: %s", exc)
        async for event in self._polling_events():
            yield event

    async def _websocket_events(self) -> AsyncIterator[RawEvent]:
        assert self.websocket_url
        watched: dict[str, float] = {}
        async with websockets.connect(self.websocket_url, ping_interval=20) as ws:
            await ws.send(json.dumps(self.subscription_message))
            async for message in ws:
                payload = json.loads(message)
                mint = payload.get("mint") or payload.get("token") or ""
                if not mint:
                    log.info("pumpportal message without mint: %s", payload)
                if mint:
                    tx_type = str(payload.get("txType", payload.get("type", "token_event")))
                    if tx_type == "create" and self.auto_subscribe_trades:
                        await self._subscribe_trade(ws, mint, watched)
                    await self._cleanup_watched(ws, watched)
                    yield RawEvent("pumpfun_ws", tx_type, mint, utc_now(), payload)

    async def _subscribe_trade(self, ws, mint: str, watched: dict[str, float]) -> None:
        if mint in watched:
            return
        while len(watched) >= self.max_watched_tokens:
            old_mint = next(iter(watched))
            await ws.send(json.dumps({"method": "unsubscribeTokenTrade", "keys": [old_mint]}))
            watched.pop(old_mint, None)
        await ws.send(json.dumps({"method": "subscribeTokenTrade", "keys": [mint]}))
        log.info("subscribed token trades mint=%s", mint)
        watched[mint] = time.monotonic()

    async def _cleanup_watched(self, ws, watched: dict[str, float]) -> None:
        now = time.monotonic()
        expired = [mint for mint, started in watched.items() if now - started > self.watch_seconds]
        for mint in expired:
            await ws.send(json.dumps({"method": "unsubscribeTokenTrade", "keys": [mint]}))
            watched.pop(mint, None)

    async def _polling_events(self) -> AsyncIterator[RawEvent]:
        if not self.polling_url:
            while True:
                await asyncio.sleep(self.polling_interval_seconds)
        seen: set[str] = set()
        async with httpx.AsyncClient(timeout=10) as client:
            while True:
                response = await client.get(self.polling_url)
                response.raise_for_status()
                payload = response.json()
                items = payload if isinstance(payload, list) else payload.get("data", [])
                for item in items:
                    mint = item.get("mint") or item.get("address")
                    if mint and mint not in seen:
                        seen.add(mint)
                        yield RawEvent("pumpfun_poll", "token_created", mint, utc_now(), item)
                await asyncio.sleep(self.polling_interval_seconds)


def event_to_metadata(event: RawEvent) -> TokenMetadata:
    payload = event.payload
    created = payload.get("created_at") or payload.get("createdAt")
    created_at = datetime.fromisoformat(created.replace("Z", "+00:00")) if isinstance(created, str) else event.ts
    return TokenMetadata(
        mint=event.mint,
        symbol=payload.get("symbol", "UNKNOWN"),
        name=payload.get("name", "Unknown"),
        deployer=payload.get("deployer") or payload.get("creator") or "",
        created_at=created_at,
        supply=float(payload.get("supply", payload.get("totalSupply", 1_000_000_000))),
        creator_allocation_pct=float(payload.get("creator_allocation_pct", payload.get("creatorAllocationPct", 0.0))),
        freeze_authority=payload.get("freeze_authority"),
        mint_authority=payload.get("mint_authority"),
        metadata_uri=payload.get("metadata_uri"),
    )


def event_to_metrics(event: RawEvent) -> TokenMetrics:
    p = event.payload
    created = p.get("created_at") or p.get("createdAt")
    if isinstance(created, str):
        created_at = datetime.fromisoformat(created.replace("Z", "+00:00"))
        age = max(0.0, (event.ts - created_at).total_seconds())
    else:
        age = float(p.get("age_seconds", p.get("ageSeconds", 0)))
    return TokenMetrics(
        mint=event.mint,
        ts=event.ts,
        age_seconds=age,
        market_cap_sol=float(p.get("market_cap_sol", p.get("marketCapSol", 0))),
        liquidity_sol=float(p.get("liquidity_sol", p.get("liquiditySol", p.get("vSolInBondingCurve", 0)))),
        volume_60s_sol=float(p.get("volume_60s_sol", p.get("volume60sSol", p.get("solAmount", 0)))),
        unique_buyers_60s=int(p.get("unique_buyers_60s", p.get("uniqueBuyers60s", 0))),
        buy_count_60s=int(p.get("buy_count_60s", p.get("buyCount60s", 0))),
        sell_count_60s=int(p.get("sell_count_60s", p.get("sellCount60s", 0))),
        buy_velocity=float(p.get("buy_velocity", p.get("buyVelocity", 0))),
        price_sol=float(p.get("price_sol", p.get("priceSol", _pumpportal_price(p)))),
        price_change_30s_pct=float(p.get("price_change_30s_pct", p.get("priceChange30sPct", 0))),
        top10_holder_pct=float(p.get("top10_holder_pct", p.get("top10HolderPct", 1))),
        top1_holder_pct=float(p.get("top1_holder_pct", p.get("top1HolderPct", 1))),
        creator_holder_pct=float(p.get("creator_holder_pct", p.get("creatorHolderPct", 1))),
        whale_dump_pct_30s=float(p.get("whale_dump_pct_30s", 0)),
        liquidity_drop_pct_30s=float(p.get("liquidity_drop_pct_30s", 0)),
        suspicious_wallet_hits=int(p.get("suspicious_wallet_hits", 0)),
        repeated_deployer_pattern=bool(p.get("repeated_deployer_pattern", False)),
        wash_trade_score=float(p.get("wash_trade_score", 0)),
        bot_activity_score=float(p.get("bot_activity_score", 0)),
        estimated_slippage_pct=float(p.get("estimated_slippage_pct", 0)),
    )


def _pumpportal_price(payload: dict) -> float:
    sol = float(payload.get("vSolInBondingCurve", 0) or 0)
    tokens = float(payload.get("vTokensInBondingCurve", 0) or 0)
    return sol / tokens if sol > 0 and tokens > 0 else 0.0
