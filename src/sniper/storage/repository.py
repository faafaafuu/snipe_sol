from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import desc, func, select

from sniper.core.models import OrderResult, RawEvent, Signal, TokenMetadata
from sniper.storage.db import (
    BlacklistRow,
    Database,
    PerformanceStatRow,
    RawEventRow,
    SignalRow,
    TokenRow,
    TradeRow,
)


class Repository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def upsert_token(self, meta: TokenMetadata, score: float = 0.0) -> None:
        with self.db.session() as session:
            row = session.get(TokenRow, meta.mint) or TokenRow(
                mint=meta.mint,
                symbol=meta.symbol,
                name=meta.name,
                deployer=meta.deployer,
                created_at=meta.created_at,
                creator_allocation_pct=meta.creator_allocation_pct,
            )
            row.last_score = score
            row.last_seen_at = datetime.now(timezone.utc)
            session.merge(row)

    def save_signal(self, signal: Signal) -> None:
        with self.db.session() as session:
            session.add(
                SignalRow(
                    mint=signal.mint,
                    score=signal.score,
                    passed=signal.passed,
                    mode=signal.mode,
                    reasons="\n".join(signal.reasons),
                    created_at=signal.metrics.ts,
                )
            )

    def save_event(self, event: RawEvent) -> None:
        with self.db.session() as session:
            session.add(
                RawEventRow(
                    source=event.source,
                    event_type=event.event_type,
                    mint=event.mint,
                    payload_json=json.dumps(event.payload, default=str),
                    created_at=event.ts,
                )
            )

    def save_trade(self, result: OrderResult, reason: str, pnl_sol: float = 0.0, paper: bool = True) -> None:
        with self.db.session() as session:
            session.add(
                TradeRow(
                    mint=result.mint,
                    side=result.side.value,
                    price_sol=result.price_sol,
                    size_sol=result.size_sol,
                    token_amount=result.token_amount,
                    pnl_sol=pnl_sol,
                    reason=reason,
                    tx_signature=result.tx_signature,
                    paper=paper,
                    created_at=datetime.now(timezone.utc),
                )
            )

    def is_blacklisted(self, value: str, kind: str | None = None) -> bool:
        with self.db.session() as session:
            query = select(BlacklistRow).where(BlacklistRow.value == value)
            if kind:
                query = query.where(BlacklistRow.kind == kind)
            return session.execute(query).first() is not None

    def add_blacklist(self, value: str, kind: str, reason: str) -> None:
        with self.db.session() as session:
            session.merge(BlacklistRow(value=value, kind=kind, reason=reason, created_at=datetime.now(timezone.utc)))

    def last_trades(self, limit: int = 20) -> list[TradeRow]:
        with self.db.session() as session:
            return list(session.scalars(select(TradeRow).order_by(desc(TradeRow.created_at)).limit(limit)))

    def last_signals(self, limit: int = 100, passed: bool | None = None) -> list[SignalRow]:
        with self.db.session() as session:
            query = select(SignalRow).order_by(desc(SignalRow.created_at)).limit(limit)
            if passed is not None:
                query = select(SignalRow).where(SignalRow.passed == passed).order_by(desc(SignalRow.created_at)).limit(limit)
            return list(session.scalars(query))

    def last_raw_events(self, limit: int = 100) -> list[RawEventRow]:
        with self.db.session() as session:
            return list(session.scalars(select(RawEventRow).order_by(desc(RawEventRow.created_at)).limit(limit)))

    def performance_snapshot(self) -> dict[str, float]:
        with self.db.session() as session:
            trades = session.scalar(select(func.count()).select_from(TradeRow)) or 0
            pnl = session.scalar(select(func.coalesce(func.sum(TradeRow.pnl_sol), 0.0))) or 0.0
            wins = session.scalar(select(func.count()).select_from(TradeRow).where(TradeRow.pnl_sol > 0)) or 0
            losses = session.scalar(select(func.count()).select_from(TradeRow).where(TradeRow.pnl_sol < 0)) or 0
            signals = session.scalar(select(func.count()).select_from(SignalRow)) or 0
            accepted = session.scalar(select(func.count()).select_from(SignalRow).where(SignalRow.passed.is_(True))) or 0
            skipped = session.scalar(select(func.count()).select_from(SignalRow).where(SignalRow.passed.is_(False))) or 0
            return {
                "trades": float(trades),
                "pnl_sol": float(pnl),
                "wins": float(wins),
                "losses": float(losses),
                "winrate": float(wins / max(wins + losses, 1)),
                "signals": float(signals),
                "accepted_signals": float(accepted),
                "skipped_signals": float(skipped),
            }
