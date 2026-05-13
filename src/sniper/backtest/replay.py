from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from sniper.core.models import RawEvent
from sniper.listener.scanner import event_to_metadata, event_to_metrics
from sniper.strategy.entry import EntryStrategy


@dataclass(slots=True)
class ReplayStats:
    signals: int
    accepted: int
    rejected: int
    winrate: float
    avg_return: float
    max_drawdown: float
    expectancy: float
    profit_factor: float


class HistoricalReplay:
    def __init__(self, entry: EntryStrategy) -> None:
        self.entry = entry

    def load_jsonl(self, path: str | Path) -> list[RawEvent]:
        events: list[RawEvent] = []
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            raw = json.loads(line)
            events.append(RawEvent(**raw))
        return events

    def evaluate_signals(self, events: list[RawEvent], mode: str) -> ReplayStats:
        accepted = 0
        rejected = 0
        returns: list[float] = []
        equity = 1.0
        peak = 1.0
        max_dd = 0.0
        for event in events:
            signal = self.entry.evaluate(event_to_metadata(event), event_to_metrics(event), mode)
            if signal.passed:
                accepted += 1
                simulated_return = float(event.payload.get("future_return_pct", 0.0))
                returns.append(simulated_return)
                equity *= 1 + simulated_return
                peak = max(peak, equity)
                max_dd = max(max_dd, (peak - equity) / peak)
            else:
                rejected += 1
        wins = [x for x in returns if x > 0]
        losses = [abs(x) for x in returns if x < 0]
        gross_win = sum(wins)
        gross_loss = sum(losses)
        total = len(returns)
        return ReplayStats(
            signals=accepted + rejected,
            accepted=accepted,
            rejected=rejected,
            winrate=len(wins) / max(total, 1),
            avg_return=sum(returns) / max(total, 1),
            max_drawdown=max_dd,
            expectancy=(sum(returns) / max(total, 1)),
            profit_factor=gross_win / gross_loss if gross_loss else float("inf") if gross_win else 0.0,
        )
