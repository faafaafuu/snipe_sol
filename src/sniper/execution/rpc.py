from __future__ import annotations

import itertools
import logging
from typing import Any

import httpx

from sniper.config.settings import RpcConfig

log = logging.getLogger(__name__)


class RpcManager:
    def __init__(self, cfg: RpcConfig) -> None:
        self.cfg = cfg
        self._cycle = itertools.cycle(cfg.endpoints)

    async def call(self, method: str, params: list[Any] | None = None) -> Any:
        last_error: Exception | None = None
        for _ in range(max(1, self.cfg.max_retries * len(self.cfg.endpoints))):
            endpoint = next(self._cycle)
            try:
                async with httpx.AsyncClient(timeout=8) as client:
                    response = await client.post(
                        endpoint,
                        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []},
                    )
                    response.raise_for_status()
                    payload = response.json()
                    if "error" in payload:
                        raise RuntimeError(payload["error"])
                    return payload["result"]
            except Exception as exc:
                last_error = exc
                log.warning("rpc endpoint failed endpoint=%s method=%s error=%s", endpoint, method, exc)
        raise RuntimeError(f"all rpc endpoints failed for {method}: {last_error}")
