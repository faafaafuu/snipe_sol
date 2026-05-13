from sniper.config.settings import RiskConfig
from sniper.core.models import Signal
from tests.test_filters import good_metrics
from sniper.risk.manager import RiskManager


def risk_cfg() -> RiskConfig:
    return RiskConfig(
        max_entry_size_sol=0.1,
        max_deposit_pct_per_trade=0.02,
        max_concurrent_positions=1,
        daily_loss_limit_pct=0.05,
        max_loss_streak=2,
        cooldown_seconds=0,
        min_sol_balance=0.05,
        max_priority_fee_sol=0.01,
    )


def signal(mint: str = "mint") -> Signal:
    return Signal(mint=mint, score=90, passed=True, reasons=["ok"], mode="balanced", metrics=good_metrics())


def test_sizes_by_pct_and_cap() -> None:
    manager = RiskManager(risk_cfg(), starting_balance_sol=10)
    decision = manager.evaluate_entry(signal(), {})
    assert decision.allowed
    assert decision.size_sol == 0.1


def test_blocks_reentry() -> None:
    manager = RiskManager(risk_cfg(), starting_balance_sol=10)
    manager.record_entry("mint", 0.1)
    decision = manager.evaluate_entry(signal("mint"), {})
    assert not decision.allowed
    assert any("already traded" in reason for reason in decision.reasons)


def test_pauses_after_loss_streak() -> None:
    manager = RiskManager(risk_cfg(), starting_balance_sol=10)
    manager.record_exit(-0.1, 0)
    manager.record_exit(-0.1, 0)
    decision = manager.evaluate_entry(signal("new"), {})
    assert not decision.allowed
    assert manager.paused
