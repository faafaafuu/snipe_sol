# Solana Pump.fun Risk-First Sniper Bot

Production-oriented Python MVP for monitoring pump.fun-style meme-token launches on Solana, filtering scammy launches, paper trading entries/exits, recording raw events, and exposing Telegram notifications plus a small dashboard.

This project does not promise profit. Meme-token sniping is adversarial, latency-sensitive, and often dominated by insiders, MEV, fake volume, and deployer rugs. The default mode is `paper`.

## What Is Implemented

- Modular Python codebase under `src/sniper`
- `.env` plus YAML config
- SQLite by default, Postgres-compatible SQLAlchemy models
- Console and rotating file logs
- Websocket scanner with polling fallback
- Raw event persistence for replay
- Anti-scam filter with explicit skip reasons
- Entry gate with Ultra Safe / Balanced / Aggressive modes
- Paper execution engine
- Risk manager: per-trade cap, daily loss cap, cooldown, max positions, loss-streak pause, no re-entry
- Exit strategy: take-profit ladder, stop-loss, time exit, emergency liquidity and whale-dump exits, break-even and trailing behavior
- Telegram notifications and control commands
- FastAPI dashboard
- Unit tests for filter, risk, and exit logic

Live Solana execution is intentionally a guarded adapter stub. Wire it only after paper/replay results are acceptable and after you configure a private low-latency RPC, key management, transaction simulation, priority fees, and confirmation monitoring.

## Project Structure

```text
solana-pumpfun-sniper/
  src/sniper/
    analysis/filters.py        # anti-scam and momentum filter
    backtest/replay.py         # historical replay metrics
    config/settings.py         # env + yaml settings
    core/app.py                # orchestration loop
    core/models.py             # domain dataclasses
    dashboard/server.py        # FastAPI dashboard
    execution/broker.py        # paper broker + live adapter boundary
    execution/rpc.py           # RPC fallback manager
    listener/scanner.py        # websocket/polling scanner
    risk/manager.py            # portfolio and loss limits
    storage/db.py              # SQLAlchemy tables
    storage/repository.py      # persistence API
    strategy/entry.py          # entry scoring
    strategy/exit.py           # exits and emergency exits
    telegram/bot.py            # notifications and commands
    utils/logging.py
  tests/
  config.example.yaml
  .env.example
  Dockerfile
  docker-compose.yml
```

## Quick Start

```bash
cd /root/solana-pumpfun-sniper
cp .env.example .env
cp config.example.yaml config.yaml
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m sniper.main --config config.yaml init-db
python -m sniper.main --config config.yaml run
```

Dashboard:

```text
http://localhost:8080
```

Docker:

```bash
cp .env.example .env
cp config.example.yaml config.yaml
docker compose up --build
```

## Scanner Setup

Set scanner endpoints in `config.yaml`:

```yaml
scanner:
  websocket_url: "wss://your-pumpfun-feed.example/ws"
  polling_url: "https://your-pumpfun-feed.example/new-tokens"
  polling_interval_seconds: 2
```

Expected event fields are normalized in `listener/scanner.py`. Your provider should include fields such as `mint`, `symbol`, `creator/deployer`, `created_at`, `price_sol`, `liquidity_sol`, `market_cap_sol`, `unique_buyers_60s`, holder concentration, slippage, wash-trade score, and bot-activity score. If your feed has different names, adapt `event_to_metadata()` and `event_to_metrics()`.

## Strategy Modes

`ultra_safe`: strict concentration, liquidity, buyer-count, wash-trade, and bot-activity limits. Fewer trades, lower expected rug exposure.

`balanced`: default. Moderate filters with still-strict risk caps.

`aggressive`: more entries and wider thresholds, but still uses stop-loss, daily loss, cooldown, max positions, and no averaging down.

Select with:

```env
STRATEGY_MODE=balanced
```

## Telegram Setup

1. Create a bot with BotFather and copy the token.
2. Send a message to your bot.
3. Get your chat id via `https://api.telegram.org/bot<TOKEN>/getUpdates`.
4. Set:

```env
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=123:abc
TELEGRAM_CHAT_ID=123456789
```

Supported commands:

```text
/start /stop /status /balance /positions /pnl /last_trades /blacklist /config /paper_on /paper_off
```

## Live Trading Boundary

Default execution is paper. To move toward live mode, implement `LiveSolanaBroker` in `src/sniper/execution/broker.py` with:

- Solana keypair loading from `SOLANA_KEYPAIR_PATH`
- Pump.fun/Jupiter/swap route construction as appropriate
- Preflight simulation
- Balance and rent checks
- Compute-unit limit and priority-fee caps
- Slippage cap enforcement
- Confirmation polling with retry and stuck-transaction handling
- Refusal when fees or slippage exceed config

Do not run live mode until replay and paper logs show that skip/buy/exit reasons are sane.

## Tests

```bash
pytest -q
```

Current tests cover the highest-risk pure logic: scam filters, risk manager, and exit decisions.

## Replay Testing

Raw events are stored in `raw_events`. You can export them to JSONL and feed them into `HistoricalReplay`. Include a `future_return_pct` field when you have labeled historical outcomes to compute winrate, average return, max drawdown, expectancy, and profit factor.

## Roadmap

1. MVP: scanner normalization, paper broker, risk/filter/exit logic, dashboard, Telegram, SQLite.
2. Paper trading: connect a real pump.fun event feed, record all raw events, tune thresholds from skip/buy logs.
3. Replay testing: label event windows, replay strategy variants, reject overfit configs.
4. Limited live trading: tiny size, private RPC, live broker, strict fee/slippage caps, kill switch.
5. Production hardening: deployer reputation DB, holder graph features, bot-cluster detection, MEV-aware routing, alerting, and automated daily risk reports.
