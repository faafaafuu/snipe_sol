from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable

import httpx

log = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, enabled: bool) -> None:
        self.token = token
        self.chat_id = chat_id
        self.enabled = enabled and bool(token and chat_id)

    @classmethod
    def from_env(cls, enabled: bool) -> "TelegramNotifier":
        return cls(os.getenv("TELEGRAM_BOT_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", ""), enabled)

    async def send(self, text: str) -> None:
        if not self.enabled:
            return
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(
                    f"https://api.telegram.org/bot{self.token}/sendMessage",
                    json={"chat_id": self.chat_id, "text": text[:3900]},
                )
        except Exception as exc:
            log.warning("telegram notification failed: %s", exc)

    async def poll_commands(self, handler: Callable[[str], Awaitable[str]]) -> None:
        if not self.enabled:
            return
        offset = 0
        async with httpx.AsyncClient(timeout=20) as client:
            while True:
                try:
                    response = await client.get(
                        f"https://api.telegram.org/bot{self.token}/getUpdates",
                        params={"timeout": 20, "offset": offset, "allowed_updates": ["message"]},
                    )
                    response.raise_for_status()
                    for update in response.json().get("result", []):
                        offset = update["update_id"] + 1
                        message = update.get("message", {})
                        if str(message.get("chat", {}).get("id")) != str(self.chat_id):
                            continue
                        text = str(message.get("text", "")).strip()
                        if text.startswith("/"):
                            await self.send(await handler(text.split()[0]))
                except Exception as exc:
                    log.warning("telegram command polling failed: %s", exc)


COMMANDS = {
    "/start": "resume scanner/execution",
    "/stop": "pause scanner/execution",
    "/status": "show runtime state",
    "/balance": "show SOL balance",
    "/positions": "show open positions",
    "/pnl": "show realized PnL",
    "/last_trades": "show recent trades",
    "/blacklist": "show/update blacklist",
    "/config": "show active strategy config",
    "/paper_on": "switch to paper mode",
    "/paper_off": "requires explicit live mode restart",
}
