from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

from sniper.config.settings import RiskConfig
from sniper.core.models import Position, Signal


@dataclass(slots=True)
class RiskDecision:
    allowed: bool
    size_sol: float
    reasons: list[str]


class RiskManager:
    def __init__(self, cfg: RiskConfig, starting_balance_sol: float) -> None:
        self.cfg = cfg
        self.starting_balance_sol = starting_balance_sol
        self.current_balance_sol = starting_balance_sol
        self.daily_realized_pnl_sol = 0.0
        self.loss_streak = 0
        self.last_trade_at: datetime | None = None
        self.seen_tokens: set[str] = set()
        self.paused = False

    def evaluate_entry(self, signal: Signal, positions: dict[str, Position]) -> RiskDecision:
        reasons: list[str] = []
        if self.paused:
            reasons.append("bot paused by risk manager")
        if signal.mint in self.seen_tokens:
            reasons.append("token already traded")
        if len(positions) >= self.cfg.max_concurrent_positions:
            reasons.append("max concurrent positions reached")
        if self.current_balance_sol < self.cfg.min_sol_balance:
            reasons.append("SOL balance below minimum")
        if self.loss_streak >= self.cfg.max_loss_streak:
            reasons.append("max loss streak reached")
        daily_limit = -self.starting_balance_sol * self.cfg.daily_loss_limit_pct
        if self.daily_realized_pnl_sol <= daily_limit:
            reasons.append("daily loss limit reached")
        if self.last_trade_at and datetime.now(timezone.utc) - self.last_trade_at < timedelta(seconds=self.cfg.cooldown_seconds):
            reasons.append("cooldown active")

        size_by_pct = self.current_balance_sol * self.cfg.max_deposit_pct_per_trade
        size_sol = min(self.cfg.max_entry_size_sol, size_by_pct)
        if size_sol <= 0:
            reasons.append("computed position size is zero")
        return RiskDecision(allowed=not reasons, size_sol=size_sol, reasons=reasons or ["risk accepted"])

    def record_entry(self, mint: str, size_sol: float) -> None:
        self.seen_tokens.add(mint)
        self.current_balance_sol -= size_sol
        self.last_trade_at = datetime.now(timezone.utc)

    def record_exit(self, pnl_sol: float, returned_sol: float) -> None:
        self.current_balance_sol += returned_sol
        self.daily_realized_pnl_sol += pnl_sol
        self.loss_streak = self.loss_streak + 1 if pnl_sol < 0 else 0
        if self.loss_streak >= self.cfg.max_loss_streak:
            self.paused = True
