from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from quant_platform_kit.strategy_contracts import StrategyContext, StrategyDecision, StrategyEntrypoint

from strategy_loader import load_strategy_entrypoint_for_profile


@dataclass(frozen=True)
class StrategyEvaluationResult:
    decision: StrategyDecision
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LoadedStrategyRuntime:
    entrypoint: StrategyEntrypoint
    runtime_overrides: Mapping[str, Any] = field(default_factory=dict)
    merged_runtime_config: Mapping[str, Any] = field(default_factory=dict)

    @property
    def profile(self) -> str:
        return self.entrypoint.manifest.profile

    @property
    def managed_symbols(self) -> tuple[str, ...]:
        configured = self.merged_runtime_config.get("managed_symbols", ())
        return tuple(str(symbol) for symbol in configured)

    @property
    def benchmark_symbol(self) -> str:
        return str(self.merged_runtime_config.get("benchmark_symbol", "QQQ"))

    def evaluate(
        self,
        *,
        qqq_history,
        snapshot,
        signal_text_fn: Callable[[str], str],
        translator: Callable[[str], str],
    ) -> StrategyEvaluationResult:
        runtime_config = dict(self.runtime_overrides)
        runtime_config.setdefault("signal_text_fn", signal_text_fn)
        runtime_config.setdefault("translator", translator)
        ctx = StrategyContext(
            as_of=datetime.now(timezone.utc),
            market_data={"qqq_history": qqq_history},
            portfolio=snapshot,
            runtime_config=runtime_config,
        )
        decision = self.entrypoint.evaluate(ctx)
        return StrategyEvaluationResult(
            decision=decision,
            metadata={"strategy_profile": self.profile},
        )


def load_strategy_runtime(
    raw_profile: str | None,
    *,
    runtime_overrides: Mapping[str, Any] | None = None,
) -> LoadedStrategyRuntime:
    entrypoint = load_strategy_entrypoint_for_profile(raw_profile)
    merged_runtime_config = dict(entrypoint.manifest.default_config)
    overrides = dict(runtime_overrides or {})
    merged_runtime_config.update(overrides)
    return LoadedStrategyRuntime(
        entrypoint=entrypoint,
        runtime_overrides=overrides,
        merged_runtime_config=merged_runtime_config,
    )
