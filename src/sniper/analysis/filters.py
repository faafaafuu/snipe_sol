from __future__ import annotations

from sniper.config.settings import FilterConfig
from sniper.core.models import Signal, TokenMetadata, TokenMetrics


class TokenAnalyzer:
    def __init__(self, cfg: FilterConfig, blacklist_wallets: set[str]) -> None:
        self.cfg = cfg
        self.blacklist_wallets = blacklist_wallets

    def analyze(self, metadata: TokenMetadata, metrics: TokenMetrics, mode: str) -> Signal:
        rejects: list[str] = []
        positives: list[str] = []

        checks = [
            (metrics.age_seconds >= self.cfg.min_age_seconds, f"age too low: {metrics.age_seconds:.1f}s"),
            (metrics.age_seconds <= self.cfg.max_age_seconds, f"age too high: {metrics.age_seconds:.1f}s"),
            (metrics.liquidity_sol >= self.cfg.min_liquidity_sol, f"liquidity too low: {metrics.liquidity_sol:.3f} SOL"),
            (metrics.unique_buyers_60s >= self.cfg.min_unique_buyers_60s, f"unique buyers too low: {metrics.unique_buyers_60s}"),
            (metrics.buy_velocity >= self.cfg.min_buy_velocity, f"buy velocity too low: {metrics.buy_velocity:.2f}/s"),
            (metrics.volume_60s_sol >= self.cfg.min_volume_60s_sol, f"60s volume too low: {metrics.volume_60s_sol:.3f} SOL"),
            (metrics.market_cap_sol <= self.cfg.max_initial_market_cap_sol, f"initial market cap too high: {metrics.market_cap_sol:.2f} SOL"),
            (metrics.top10_holder_pct <= self.cfg.max_top10_holder_pct, f"top10 concentration too high: {metrics.top10_holder_pct:.2%}"),
            (metrics.top1_holder_pct <= self.cfg.max_top1_holder_pct, f"top1 concentration too high: {metrics.top1_holder_pct:.2%}"),
            (
                metadata.creator_allocation_pct <= self.cfg.max_creator_allocation_pct,
                f"creator allocation too high: {metadata.creator_allocation_pct:.2%}",
            ),
            (metrics.creator_holder_pct <= self.cfg.max_creator_holder_pct, f"creator holder pct too high: {metrics.creator_holder_pct:.2%}"),
            (metrics.estimated_slippage_pct <= self.cfg.max_slippage_pct, f"slippage too high: {metrics.estimated_slippage_pct:.2%}"),
            (metrics.wash_trade_score <= self.cfg.max_wash_trade_score, f"wash trading score too high: {metrics.wash_trade_score:.2f}"),
            (metrics.bot_activity_score <= self.cfg.max_bot_activity_score, f"bot activity score too high: {metrics.bot_activity_score:.2f}"),
            (metrics.price_change_30s_pct >= self.cfg.min_momentum_30s_pct, f"momentum too weak: {metrics.price_change_30s_pct:.2%}"),
            (metadata.deployer not in self.blacklist_wallets, f"blacklisted deployer: {metadata.deployer}"),
            (metrics.suspicious_wallet_hits == 0, f"suspicious wallet hits: {metrics.suspicious_wallet_hits}"),
            (not metrics.repeated_deployer_pattern, "repeated deployer rug pattern"),
            (metadata.freeze_authority in (None, ""), "freeze authority still enabled"),
        ]

        for ok, reason in checks:
            if ok:
                positives.append(reason.replace(" too ", " ok: "))
            else:
                rejects.append(reason)

        score = self._score(metrics, metadata)
        reasons = positives if not rejects else rejects
        return Signal(
            mint=metadata.mint,
            score=score,
            passed=not rejects,
            reasons=reasons,
            mode=mode,
            metrics=metrics,
            metadata=metadata,
        )

    def _score(self, metrics: TokenMetrics, metadata: TokenMetadata) -> float:
        momentum = min(max(metrics.price_change_30s_pct / 0.5, 0.0), 1.0) * 25
        buyers = min(metrics.unique_buyers_60s / max(self.cfg.min_unique_buyers_60s * 3, 1), 1.0) * 20
        liquidity = min(metrics.liquidity_sol / max(self.cfg.min_liquidity_sol * 4, 1), 1.0) * 15
        velocity = min(metrics.buy_velocity / max(self.cfg.min_buy_velocity * 3, 0.1), 1.0) * 15
        concentration_penalty = (metrics.top10_holder_pct + metadata.creator_allocation_pct) * 30
        bot_penalty = (metrics.bot_activity_score + metrics.wash_trade_score) * 10
        return max(0.0, min(100.0, momentum + buyers + liquidity + velocity + 25 - concentration_penalty - bot_penalty))
