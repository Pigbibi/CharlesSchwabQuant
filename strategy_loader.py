from __future__ import annotations

from quant_platform_kit.common.strategies import (
    StrategyDefinition,
    load_strategy_entrypoint,
)
from quant_platform_kit.strategy_contracts import StrategyEntrypoint

from strategy_registry import SCHWAB_PLATFORM, resolve_strategy_definition


def load_strategy_definition(raw_profile: str | None) -> StrategyDefinition:
    return resolve_strategy_definition(
        raw_profile,
        platform_id=SCHWAB_PLATFORM,
    )


def load_strategy_entrypoint_for_profile(raw_profile: str | None) -> StrategyEntrypoint:
    definition = load_strategy_definition(raw_profile)
    return load_strategy_entrypoint(
        definition,
        platform_id=SCHWAB_PLATFORM,
        available_inputs=("qqq_history",),
    )
