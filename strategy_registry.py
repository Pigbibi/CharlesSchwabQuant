from __future__ import annotations

from quant_platform_kit.common.strategies import (
    US_EQUITY_DOMAIN,
    StrategyDefinition,
    get_supported_profiles_for_platform as qpk_get_supported_profiles_for_platform,
    resolve_strategy_definition as qpk_resolve_strategy_definition,
)

SCHWAB_PLATFORM = "schwab"


DEFAULT_STRATEGY_PROFILE = "hybrid_growth_income"

STRATEGY_DEFINITIONS: dict[str, StrategyDefinition] = {
    DEFAULT_STRATEGY_PROFILE: StrategyDefinition(
        profile=DEFAULT_STRATEGY_PROFILE,
        domain=US_EQUITY_DOMAIN,
        supported_platforms=frozenset({SCHWAB_PLATFORM}),
    ),
}

PLATFORM_SUPPORTED_DOMAINS: dict[str, frozenset[str]] = {
    SCHWAB_PLATFORM: frozenset({US_EQUITY_DOMAIN}),
}

SUPPORTED_STRATEGY_PROFILES = frozenset(STRATEGY_DEFINITIONS)


def get_supported_profiles_for_platform(platform_id: str) -> frozenset[str]:
    return qpk_get_supported_profiles_for_platform(
        STRATEGY_DEFINITIONS,
        PLATFORM_SUPPORTED_DOMAINS,
        platform_id=platform_id,
    )


def resolve_strategy_definition(
    raw_value: str | None,
    *,
    platform_id: str,
) -> StrategyDefinition:
    return qpk_resolve_strategy_definition(
        raw_value,
        platform_id=platform_id,
        strategy_definitions=STRATEGY_DEFINITIONS,
        platform_supported_domains=PLATFORM_SUPPORTED_DOMAINS,
        default_profile=DEFAULT_STRATEGY_PROFILE,
    )
