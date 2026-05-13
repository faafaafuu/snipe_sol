from datetime import datetime, timezone

from sniper.analysis.filters import TokenAnalyzer
from sniper.config.settings import FilterConfig
from sniper.core.models import TokenMetadata, TokenMetrics


def cfg() -> FilterConfig:
    return FilterConfig(
        min_age_seconds=5,
        max_age_seconds=300,
        min_liquidity_sol=10,
        min_unique_buyers_60s=5,
        min_buy_velocity=0.1,
        min_volume_60s_sol=5,
        max_top10_holder_pct=0.35,
        max_top1_holder_pct=0.10,
        max_creator_allocation_pct=0.05,
        max_creator_holder_pct=0.05,
        max_initial_market_cap_sol=500,
        max_slippage_pct=0.10,
        max_wash_trade_score=0.3,
        max_bot_activity_score=0.5,
        min_momentum_30s_pct=0.04,
    )


def metadata() -> TokenMetadata:
    return TokenMetadata("mint", "MEME", "Meme", "deployer", datetime.now(timezone.utc), 1_000_000_000, 0.01)


def good_metrics() -> TokenMetrics:
    return TokenMetrics(
        mint="mint",
        ts=datetime.now(timezone.utc),
        age_seconds=30,
        market_cap_sol=120,
        liquidity_sol=30,
        volume_60s_sol=12,
        unique_buyers_60s=10,
        buy_count_60s=12,
        sell_count_60s=2,
        buy_velocity=0.25,
        price_sol=0.000001,
        price_change_30s_pct=0.12,
        top10_holder_pct=0.2,
        top1_holder_pct=0.04,
        creator_holder_pct=0.01,
    )


def test_good_token_passes() -> None:
    signal = TokenAnalyzer(cfg(), set()).analyze(metadata(), good_metrics(), "balanced")
    assert signal.passed
    assert signal.score > 0


def test_rejects_holder_concentration() -> None:
    metrics = good_metrics()
    metrics.top10_holder_pct = 0.80
    signal = TokenAnalyzer(cfg(), set()).analyze(metadata(), metrics, "balanced")
    assert not signal.passed
    assert any("top10 concentration" in reason for reason in signal.reasons)


def test_rejects_blacklisted_deployer() -> None:
    signal = TokenAnalyzer(cfg(), {"deployer"}).analyze(metadata(), good_metrics(), "balanced")
    assert not signal.passed
    assert any("blacklisted deployer" in reason for reason in signal.reasons)
