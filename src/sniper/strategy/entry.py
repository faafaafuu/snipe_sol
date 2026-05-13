from __future__ import annotations

from sniper.analysis.filters import TokenAnalyzer
from sniper.core.models import Signal, TokenMetadata, TokenMetrics


class EntryStrategy:
    def __init__(self, analyzer: TokenAnalyzer, min_score: float) -> None:
        self.analyzer = analyzer
        self.min_score = min_score

    def evaluate(self, metadata: TokenMetadata, metrics: TokenMetrics, mode: str) -> Signal:
        signal = self.analyzer.analyze(metadata, metrics, mode)
        if signal.passed and signal.score < self.min_score:
            signal.passed = False
            signal.reasons = [f"score below threshold: {signal.score:.2f} < {self.min_score:.2f}"]
        return signal
