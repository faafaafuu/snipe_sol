from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import uuid4

from sniper.config.settings import RpcConfig
from sniper.core.models import OrderResult, Position, TradeSide, utc_now


class Broker(ABC):
    @abstractmethod
    async def buy(self, mint: str, symbol: str, price_sol: float, size_sol: float, max_slippage_pct: float) -> OrderResult:
        raise NotImplementedError

    @abstractmethod
    async def sell(self, position: Position, price_sol: float, sell_pct: float, max_slippage_pct: float) -> OrderResult:
        raise NotImplementedError

    @abstractmethod
    async def balance_sol(self) -> float:
        raise NotImplementedError


class PaperBroker(Broker):
    def __init__(self, starting_balance_sol: float, fee_pct: float = 0.002) -> None:
        self.balance = starting_balance_sol
        self.fee_pct = fee_pct

    async def buy(self, mint: str, symbol: str, price_sol: float, size_sol: float, max_slippage_pct: float) -> OrderResult:
        if size_sol > self.balance:
            return OrderResult(False, None, TradeSide.BUY, mint, price_sol, size_sol, 0.0, "insufficient paper balance")
        executed_price = price_sol * (1 + min(max_slippage_pct / 2, max_slippage_pct))
        token_amount = (size_sol * (1 - self.fee_pct)) / executed_price
        self.balance -= size_sol
        return OrderResult(True, f"paper-{uuid4()}", TradeSide.BUY, mint, executed_price, size_sol, token_amount)

    async def sell(self, position: Position, price_sol: float, sell_pct: float, max_slippage_pct: float) -> OrderResult:
        sell_pct = min(max(sell_pct, 0.0), position.remaining_pct)
        token_amount = position.token_amount * sell_pct
        executed_price = price_sol * (1 - min(max_slippage_pct / 2, max_slippage_pct))
        proceeds = token_amount * executed_price * (1 - self.fee_pct)
        self.balance += proceeds
        return OrderResult(True, f"paper-{uuid4()}", TradeSide.SELL, position.mint, executed_price, proceeds, token_amount)

    async def balance_sol(self) -> float:
        return self.balance


class LiveSolanaBroker(Broker):
    def __init__(self, rpc: RpcConfig, keypair_path: str | None) -> None:
        self.rpc = rpc
        self.keypair_path = keypair_path

    async def buy(self, mint: str, symbol: str, price_sol: float, size_sol: float, max_slippage_pct: float) -> OrderResult:
        return OrderResult(False, None, TradeSide.BUY, mint, price_sol, size_sol, 0.0, "live execution adapter not configured")

    async def sell(self, position: Position, price_sol: float, sell_pct: float, max_slippage_pct: float) -> OrderResult:
        return OrderResult(False, None, TradeSide.SELL, position.mint, price_sol, 0.0, 0.0, "live execution adapter not configured")

    async def balance_sol(self) -> float:
        return 0.0
