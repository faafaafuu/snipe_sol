from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sniper.config.settings import ExitConfig
from sniper.core.models import Position, TokenMetrics


@dataclass(slots=True)
class ExitDecision:
    should_exit: bool
    sell_pct: float
    reason: str
    update_stop_to: float | None = None


class ExitStrategy:
    def __init__(self, cfg: ExitConfig) -> None:
        self.cfg = cfg

    def evaluate(self, position: Position, metrics: TokenMetrics) -> ExitDecision:
        price = metrics.price_sol
        position.highest_price = max(position.highest_price or position.entry_price, price)

        if price <= position.stop_loss_price:
            return ExitDecision(True, position.remaining_pct, "stop loss")
        if metrics.liquidity_drop_pct_30s >= self.cfg.emergency_liquidity_drop_pct:
            return ExitDecision(True, position.remaining_pct, "emergency liquidity drop")
        if metrics.whale_dump_pct_30s >= self.cfg.emergency_whale_dump_pct:
            return ExitDecision(True, position.remaining_pct, "emergency whale dump")
        opened_at = position.opened_at if position.opened_at.tzinfo else position.opened_at.replace(tzinfo=timezone.utc)
        if (datetime.now(timezone.utc) - opened_at).total_seconds() >= self.cfg.time_exit_seconds:
            return ExitDecision(True, position.remaining_pct, "time based exit")

        gain_pct = (price - position.entry_price) / position.entry_price
        for idx, tp in enumerate(self.cfg.take_profit_ladder):
            if idx not in position.take_profit_hits and gain_pct >= tp["gain_pct"]:
                new_stop = position.entry_price if self.cfg.break_even_after_tp1 and idx == 0 else None
                return ExitDecision(True, min(position.remaining_pct, tp["sell_pct"]), f"take profit {idx + 1}", new_stop)

        trailing_stop = position.highest_price * (1 - self.cfg.trailing_stop_pct)
        if gain_pct > self.cfg.trailing_stop_pct * 2 and price <= trailing_stop:
            return ExitDecision(True, position.remaining_pct, "trailing stop")

        return ExitDecision(False, 0.0, "hold")
