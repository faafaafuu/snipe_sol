from datetime import datetime, timezone, timedelta

from sniper.config.settings import ExitConfig
from sniper.core.models import Position
from sniper.strategy.exit import ExitStrategy
from tests.test_filters import good_metrics


def cfg() -> ExitConfig:
    return ExitConfig(
        stop_loss_pct=0.1,
        time_exit_seconds=120,
        emergency_liquidity_drop_pct=0.25,
        emergency_whale_dump_pct=0.2,
        break_even_after_tp1=True,
        trailing_stop_pct=0.15,
        take_profit_ladder=[{"gain_pct": 0.25, "sell_pct": 0.5}],
    )


def position() -> Position:
    return Position("mint", "MEME", 1.0, 1.0, 1.0, datetime.now(timezone.utc), 0.9)


def test_stop_loss() -> None:
    metrics = good_metrics()
    metrics.price_sol = 0.89
    decision = ExitStrategy(cfg()).evaluate(position(), metrics)
    assert decision.should_exit
    assert decision.reason == "stop loss"


def test_take_profit_sets_break_even() -> None:
    metrics = good_metrics()
    metrics.price_sol = 1.30
    decision = ExitStrategy(cfg()).evaluate(position(), metrics)
    assert decision.should_exit
    assert decision.sell_pct == 0.5
    assert decision.update_stop_to == 1.0


def test_time_exit() -> None:
    pos = position()
    pos.opened_at = datetime.now(timezone.utc) - timedelta(seconds=121)
    metrics = good_metrics()
    metrics.price_sol = 1.0
    decision = ExitStrategy(cfg()).evaluate(pos, metrics)
    assert decision.should_exit
    assert decision.reason == "time based exit"
