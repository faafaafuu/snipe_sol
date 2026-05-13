from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

from sniper.analysis.filters import TokenAnalyzer
from sniper.config.settings import AppConfig
from sniper.core.models import Position, TradingMode
from sniper.execution.broker import Broker, LiveSolanaBroker, PaperBroker
from sniper.listener.aggregator import TokenTradeAggregator, is_trade_event
from sniper.listener.scanner import PumpFunScanner, event_to_metadata, event_to_metrics
from sniper.risk.manager import RiskManager
from sniper.storage.repository import Repository
from sniper.strategy.entry import EntryStrategy
from sniper.strategy.exit import ExitStrategy
from sniper.telegram.bot import TelegramNotifier

log = logging.getLogger(__name__)


class SniperBot:
    def __init__(self, cfg: AppConfig, repo: Repository) -> None:
        self.cfg = cfg
        self.repo = repo
        starting_balance = float(os.getenv("PAPER_STARTING_BALANCE_SOL", "10"))
        self.risk = RiskManager(cfg.risk, starting_balance)
        self.broker: Broker = (
            PaperBroker(starting_balance)
            if cfg.mode != TradingMode.LIVE
            else LiveSolanaBroker(cfg.rpc, os.getenv("SOLANA_KEYPAIR_PATH"))
        )
        analyzer = TokenAnalyzer(cfg.active_filter, cfg.blacklist_wallets)
        min_score = {"ultra_safe": 82.0, "balanced": 68.0, "aggressive": 55.0}[cfg.strategy_mode]
        self.entry = EntryStrategy(analyzer, min_score)
        self.exit = ExitStrategy(cfg.active_exit)
        self.scanner = PumpFunScanner(
            cfg.scanner.get("websocket_url"),
            cfg.scanner.get("polling_url"),
            float(cfg.scanner.get("polling_interval_seconds", 2)),
            cfg.scanner.get("subscription_message"),
            bool(cfg.scanner.get("auto_subscribe_trades", True)),
            int(cfg.scanner.get("max_watched_tokens", 100)),
            int(cfg.scanner.get("watch_seconds", 120)),
        )
        self.aggregator = TokenTradeAggregator(
            window_seconds=int(cfg.scanner.get("aggregation_window_seconds", 60)),
            max_tokens=int(cfg.scanner.get("max_watched_tokens", 100)),
        )
        self.notifier = TelegramNotifier.from_env(enabled=cfg.telegram_enabled)
        self.positions: dict[str, Position] = {}
        self.running = True

    def settings_snapshot(self) -> dict:
        f = self.cfg.active_filter
        r = self.cfg.risk
        e = self.cfg.active_exit
        return {
            "mode": self.cfg.mode.value,
            "strategy_mode": self.cfg.strategy_mode,
            "running": self.running,
            "entry": {"min_score": self.entry.min_score},
            "risk": {
                "max_entry_size_sol": r.max_entry_size_sol,
                "max_deposit_pct_per_trade": r.max_deposit_pct_per_trade,
                "max_concurrent_positions": r.max_concurrent_positions,
                "daily_loss_limit_pct": r.daily_loss_limit_pct,
                "max_loss_streak": r.max_loss_streak,
                "cooldown_seconds": r.cooldown_seconds,
            },
            "filters": {
                "min_age_seconds": f.min_age_seconds,
                "max_age_seconds": f.max_age_seconds,
                "min_liquidity_sol": f.min_liquidity_sol,
                "min_unique_buyers_60s": f.min_unique_buyers_60s,
                "min_buy_velocity": f.min_buy_velocity,
                "min_volume_60s_sol": f.min_volume_60s_sol,
                "max_initial_market_cap_sol": f.max_initial_market_cap_sol,
                "max_slippage_pct": f.max_slippage_pct,
                "max_wash_trade_score": f.max_wash_trade_score,
                "max_bot_activity_score": f.max_bot_activity_score,
                "min_momentum_30s_pct": f.min_momentum_30s_pct,
            },
            "exits": {
                "stop_loss_pct": e.stop_loss_pct,
                "time_exit_seconds": e.time_exit_seconds,
                "trailing_stop_pct": e.trailing_stop_pct,
                "emergency_liquidity_drop_pct": e.emergency_liquidity_drop_pct,
                "emergency_whale_dump_pct": e.emergency_whale_dump_pct,
            },
        }

    def update_settings(self, payload: dict) -> dict:
        for key, value in payload.get("risk", {}).items():
            if hasattr(self.cfg.risk, key):
                setattr(self.cfg.risk, key, _coerce_setting(key, value))
        for key, value in payload.get("filters", {}).items():
            if hasattr(self.cfg.active_filter, key):
                setattr(self.cfg.active_filter, key, _coerce_setting(key, value))
        for key, value in payload.get("exits", {}).items():
            if hasattr(self.cfg.active_exit, key):
                setattr(self.cfg.active_exit, key, _coerce_setting(key, value))
        if "entry" in payload and "min_score" in payload["entry"]:
            self.entry.min_score = float(payload["entry"]["min_score"])
        if "running" in payload:
            self.running = bool(payload["running"])
        return self.settings_snapshot()

    async def manual_buy(self, mint: str, size_sol: float | None = None) -> dict:
        meta = self.aggregator.metadata.get(mint)
        metrics = self.aggregator.metrics(mint, datetime.now(timezone.utc))
        if not meta or not metrics or metrics.price_sol <= 0:
            return {"ok": False, "error": "token has no live price/metadata yet"}
        size = size_sol if size_sol and size_sol > 0 else min(self.cfg.risk.max_entry_size_sol, self.risk.current_balance_sol * self.cfg.risk.max_deposit_pct_per_trade)
        await self._enter(meta.symbol, mint, metrics.price_sol, size, "manual paper entry")
        return {"ok": mint in self.positions, "mint": mint, "size_sol": size}

    async def manual_sell(self, mint: str, sell_pct: float = 1.0) -> dict:
        position = self.positions.get(mint)
        if not position:
            return {"ok": False, "error": "position not found"}
        metrics = self.aggregator.metrics(mint, datetime.now(timezone.utc))
        if not metrics or metrics.price_sol <= 0:
            return {"ok": False, "error": "token has no live price"}
        result = await self.broker.sell(position, metrics.price_sol, sell_pct, self.cfg.active_filter.max_slippage_pct)
        if not result.ok:
            return {"ok": False, "error": result.error}
        cost_basis = position.size_sol * sell_pct
        pnl = result.size_sol - cost_basis
        position.realized_pnl_sol += pnl
        position.remaining_pct -= sell_pct
        self.risk.record_exit(pnl, result.size_sol)
        self.repo.save_trade(result, "manual paper exit", pnl_sol=pnl, paper=self.cfg.mode != TradingMode.LIVE)
        if position.remaining_pct <= 0.0001:
            self.positions.pop(mint, None)
        return {"ok": True, "mint": mint, "pnl_sol": pnl}

    async def run(self) -> None:
        log.info("starting sniper bot mode=%s strategy=%s", self.cfg.mode.value, self.cfg.strategy_mode)
        await self.notifier.send(f"Sniper bot started: mode={self.cfg.mode.value}, strategy={self.cfg.strategy_mode}")
        asyncio.create_task(self.notifier.poll_commands(self.handle_command))
        async for event in self.scanner.events():
            if not self.running:
                await asyncio.sleep(1)
                continue
            self.repo.save_event(event)
            if event.event_type == "create":
                self.aggregator.add_new_token(event)
                continue
            if is_trade_event(event):
                metrics = self.aggregator.add_trade(event)
                metadata = self.aggregator.metadata.get(event.mint)
                if not metrics or not metadata:
                    continue
            else:
                metadata = event_to_metadata(event)
                metrics = event_to_metrics(event)
            await self._manage_existing(metrics)
            if metrics.mint in self.positions:
                continue
            signal = self.entry.evaluate(metadata, metrics, self.cfg.strategy_mode)
            self.repo.upsert_token(metadata, signal.score)
            self.repo.save_signal(signal)
            if not signal.passed:
                log.info("skip token mint=%s score=%.2f reasons=%s", signal.mint, signal.score, "; ".join(signal.reasons))
                continue
            risk = self.risk.evaluate_entry(signal, self.positions)
            if not risk.allowed:
                log.info("risk rejected mint=%s reasons=%s", signal.mint, "; ".join(risk.reasons))
                continue
            await self._enter(metadata.symbol, signal.mint, metrics.price_sol, risk.size_sol, "; ".join(signal.reasons))

    async def _enter(self, symbol: str, mint: str, price_sol: float, size_sol: float, reason: str) -> None:
        result = await self.broker.buy(mint, symbol, price_sol, size_sol, self.cfg.active_filter.max_slippage_pct)
        if not result.ok:
            log.warning("buy failed mint=%s error=%s", mint, result.error)
            return
        stop = result.price_sol * (1 - self.cfg.active_exit.stop_loss_pct)
        self.positions[mint] = Position(
            mint=mint,
            symbol=symbol,
            entry_price=result.price_sol,
            size_sol=size_sol,
            token_amount=result.token_amount,
            opened_at=datetime.now(timezone.utc),
            stop_loss_price=stop,
            highest_price=result.price_sol,
        )
        self.risk.record_entry(mint, size_sol)
        self.repo.save_trade(result, reason, paper=self.cfg.mode != TradingMode.LIVE)
        log.info("entered mint=%s size=%.4f price=%.10f reason=%s", mint, size_sol, result.price_sol, reason)
        await self.notifier.send(f"ENTRY {symbol} {mint}\nsize={size_sol:.4f} SOL price={result.price_sol:.10f}")

    async def _manage_existing(self, metrics) -> None:
        position = self.positions.get(metrics.mint)
        if not position:
            return
        decision = self.exit.evaluate(position, metrics)
        if decision.update_stop_to:
            position.stop_loss_price = max(position.stop_loss_price, decision.update_stop_to)
        if not decision.should_exit:
            return
        result = await self.broker.sell(position, metrics.price_sol, decision.sell_pct, self.cfg.active_filter.max_slippage_pct)
        if not result.ok:
            log.warning("sell failed mint=%s error=%s", position.mint, result.error)
            return
        cost_basis = position.size_sol * decision.sell_pct
        pnl = result.size_sol - cost_basis
        position.realized_pnl_sol += pnl
        position.remaining_pct -= decision.sell_pct
        if decision.reason.startswith("take profit"):
            position.take_profit_hits.add(len(position.take_profit_hits))
        self.risk.record_exit(pnl, result.size_sol)
        self.repo.save_trade(result, decision.reason, pnl_sol=pnl, paper=self.cfg.mode != TradingMode.LIVE)
        log.info("exit mint=%s pct=%.2f pnl=%.5f reason=%s", position.mint, decision.sell_pct, pnl, decision.reason)
        await self.notifier.send(f"EXIT {position.symbol} {position.mint}\nreason={decision.reason} pnl={pnl:.5f} SOL")
        if position.remaining_pct <= 0.0001:
            self.positions.pop(position.mint, None)

    def stop(self) -> None:
        self.running = False

    def start(self) -> None:
        self.running = True

    async def handle_command(self, command: str) -> str:
        if command == "/start":
            self.start()
            return "Bot resumed"
        if command == "/stop":
            self.stop()
            return "Bot paused"
        if command == "/status":
            perf = self.repo.performance_snapshot()
            return f"running={self.running} mode={self.cfg.mode.value} strategy={self.cfg.strategy_mode} positions={len(self.positions)} pnl={perf['pnl_sol']:.5f}"
        if command == "/balance":
            return f"balance={await self.broker.balance_sol():.5f} SOL"
        if command == "/positions":
            if not self.positions:
                return "No open positions"
            return "\n".join(f"{p.symbol} {p.mint} entry={p.entry_price:.10f} remaining={p.remaining_pct:.2f}" for p in self.positions.values())
        if command == "/pnl":
            perf = self.repo.performance_snapshot()
            return f"pnl={perf['pnl_sol']:.5f} SOL winrate={perf['winrate']:.2%}"
        if command == "/last_trades":
            trades = self.repo.last_trades(10)
            return "\n".join(f"{t.side} {t.mint} pnl={t.pnl_sol:.5f} {t.reason}" for t in trades) or "No trades"
        if command == "/blacklist":
            return "Blacklist is managed in config.yaml and database table blacklist"
        if command == "/config":
            return f"mode={self.cfg.mode.value} strategy={self.cfg.strategy_mode} max_entry={self.cfg.risk.max_entry_size_sol} SOL"
        if command == "/paper_on":
            return "Paper mode requires TRADING_MODE=paper and restart if currently live"
        if command == "/paper_off":
            return "Live mode is disabled until live adapter/keypair/RPC are configured and process is restarted with TRADING_MODE=live"
        return "Unknown command"


def _coerce_setting(key: str, value):
    if key in {"max_concurrent_positions", "max_loss_streak", "cooldown_seconds", "min_age_seconds", "max_age_seconds", "time_exit_seconds"}:
        return int(value)
    return float(value)
