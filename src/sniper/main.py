from __future__ import annotations

import argparse
import asyncio
import logging

import uvicorn

from sniper.config.settings import load_config
from sniper.core.app import SniperBot
from sniper.dashboard.server import create_dashboard
from sniper.storage.db import Database
from sniper.storage.repository import Repository
from sniper.utils.logging import setup_logging


async def run_bot(config_path: str) -> None:
    cfg = load_config(config_path)
    setup_logging(cfg.log_level)
    db = Database(cfg.database_url)
    db.create_all()
    repo = Repository(db)
    bot = SniperBot(cfg, repo)
    dashboard = create_dashboard(repo, bot)
    server = uvicorn.Server(uvicorn.Config(dashboard, host=cfg.dashboard_host, port=cfg.dashboard_port, log_level="info"))
    await asyncio.gather(bot.run(), server.serve())


def init_db(config_path: str) -> None:
    cfg = load_config(config_path)
    setup_logging(cfg.log_level)
    db = Database(cfg.database_url)
    db.create_all()
    logging.getLogger(__name__).info("database initialized: %s", cfg.database_url)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("command", choices=["run", "init-db"], default="run", nargs="?")
    args = parser.parse_args()
    if args.command == "init-db":
        init_db(args.config)
        return
    asyncio.run(run_bot(args.config))


if __name__ == "__main__":
    main()
