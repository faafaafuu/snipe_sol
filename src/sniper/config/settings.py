from __future__ import annotations

import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sniper.core.models import TradingMode


@dataclass(slots=True)
class RpcConfig:
    endpoints: list[str]
    commitment: str = "confirmed"
    max_retries: int = 3
    priority_fee_micro_lamports: int = 20_000
    compute_unit_limit: int = 120_000


@dataclass(slots=True)
class RiskConfig:
    max_entry_size_sol: float
    max_deposit_pct_per_trade: float
    max_concurrent_positions: int
    daily_loss_limit_pct: float
    max_loss_streak: int
    cooldown_seconds: int
    min_sol_balance: float
    max_priority_fee_sol: float


@dataclass(slots=True)
class FilterConfig:
    min_age_seconds: int
    max_age_seconds: int
    min_liquidity_sol: float
    min_unique_buyers_60s: int
    min_buy_velocity: float
    min_volume_60s_sol: float
    max_top10_holder_pct: float
    max_top1_holder_pct: float
    max_creator_allocation_pct: float
    max_creator_holder_pct: float
    max_initial_market_cap_sol: float
    max_slippage_pct: float
    max_wash_trade_score: float
    max_bot_activity_score: float
    min_momentum_30s_pct: float


@dataclass(slots=True)
class ExitConfig:
    stop_loss_pct: float
    time_exit_seconds: int
    emergency_liquidity_drop_pct: float
    emergency_whale_dump_pct: float
    break_even_after_tp1: bool
    trailing_stop_pct: float
    take_profit_ladder: list[dict[str, float]]


@dataclass(slots=True)
class AppConfig:
    mode: TradingMode
    strategy_mode: str
    database_url: str
    log_level: str
    raw_event_retention_days: int
    scanner: dict[str, Any]
    rpc: RpcConfig
    risk: RiskConfig
    filters: dict[str, FilterConfig]
    exits: dict[str, ExitConfig]
    telegram_enabled: bool
    dashboard_host: str
    dashboard_port: int
    blacklist_wallets: set[str] = field(default_factory=set)
    whitelist_wallets: set[str] = field(default_factory=set)

    @property
    def active_filter(self) -> FilterConfig:
        return self.filters[self.strategy_mode]

    @property
    def active_exit(self) -> ExitConfig:
        return self.exits[self.strategy_mode]


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    import yaml
    from dotenv import load_dotenv

    load_dotenv()
    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    mode = TradingMode(_env("TRADING_MODE", raw.get("mode", "paper")))
    strategy_mode = _env("STRATEGY_MODE", raw.get("strategy_mode", "balanced"))
    database_url = _env("DATABASE_URL", raw["storage"]["database_url"])

    rpc = RpcConfig(
        endpoints=[x for x in _env("SOLANA_RPC_ENDPOINTS", ",".join(raw["rpc"]["endpoints"])).split(",") if x],
        commitment=raw["rpc"].get("commitment", "confirmed"),
        max_retries=int(raw["rpc"].get("max_retries", 3)),
        priority_fee_micro_lamports=int(raw["rpc"].get("priority_fee_micro_lamports", 20_000)),
        compute_unit_limit=int(raw["rpc"].get("compute_unit_limit", 120_000)),
    )
    risk = RiskConfig(**raw["risk"])
    filters = {name: FilterConfig(**cfg) for name, cfg in raw["filters"].items()}
    exits = {name: ExitConfig(**cfg) for name, cfg in raw["exits"].items()}

    scanner = dict(raw["scanner"])
    api_key = _env("PUMPPORTAL_API_KEY", "")
    if api_key and scanner.get("websocket_url") and "pumpportal.fun" in scanner["websocket_url"]:
        scanner["websocket_url"] = _with_query_param(scanner["websocket_url"], "api-key", api_key)

    return AppConfig(
        mode=mode,
        strategy_mode=strategy_mode,
        database_url=database_url,
        log_level=_env("LOG_LEVEL", raw.get("log_level", "INFO")),
        raw_event_retention_days=int(raw["storage"].get("raw_event_retention_days", 14)),
        scanner=scanner,
        rpc=rpc,
        risk=risk,
        filters=filters,
        exits=exits,
        telegram_enabled=_env("TELEGRAM_ENABLED", str(raw["telegram"].get("enabled", False))).lower() == "true",
        dashboard_host=_env("DASHBOARD_HOST", raw["dashboard"].get("host", "0.0.0.0")),
        dashboard_port=int(_env("DASHBOARD_PORT", str(raw["dashboard"].get("port", 8080)))),
        blacklist_wallets=set(raw.get("blacklist_wallets", [])),
        whitelist_wallets=set(raw.get("whitelist_wallets", [])),
    )


def _with_query_param(url: str, key: str, value: str) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    query[key] = value
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
