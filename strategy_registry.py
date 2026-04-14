from __future__ import annotations

from us_equity_strategies import get_platform_runtime_adapter, get_strategy_catalog

from quant_platform_kit.common.strategies import (
    PlatformCapabilityMatrix,
    PlatformStrategyPolicy,
    StrategyDefinition,
    US_EQUITY_DOMAIN,
    build_platform_profile_matrix,
    build_platform_profile_status_matrix,
    derive_enabled_profiles_for_platform,
    derive_eligible_profiles_for_platform,
    get_enabled_profiles_for_platform,
    get_catalog_strategy_metadata,
    resolve_platform_strategy_definition,
)

SCHWAB_PLATFORM = "schwab"

DEFAULT_STRATEGY_PROFILE = "tqqq_growth_income"
ROLLBACK_STRATEGY_PROFILE = DEFAULT_STRATEGY_PROFILE

SCHWAB_ROLLOUT_ALLOWLIST = frozenset({
    "global_etf_rotation",
    "mega_cap_leader_rotation_dynamic_top20",
    "russell_1000_multi_factor_defensive",
    "tqqq_growth_income",
    "soxl_soxx_trend_income",
    "tech_communication_pullback_enhancement",
    "qqq_tech_enhancement",
})

PLATFORM_SUPPORTED_DOMAINS: dict[str, frozenset[str]] = {
    SCHWAB_PLATFORM: frozenset({US_EQUITY_DOMAIN}),
}
STRATEGY_CATALOG = get_strategy_catalog()
PLATFORM_CAPABILITY_MATRIX = PlatformCapabilityMatrix(
    platform_id=SCHWAB_PLATFORM,
    supported_domains=PLATFORM_SUPPORTED_DOMAINS[SCHWAB_PLATFORM],
    supported_target_modes=frozenset({"weight", "value"}),
    supported_inputs=frozenset(
        {
            "benchmark_history",
            "market_history",
            "portfolio_snapshot",
            "feature_snapshot",
            "derived_indicators",
            "indicators",
            "account_state",
            "snapshot",
        }
    ),
    supported_capabilities=frozenset(),
)
ELIGIBLE_STRATEGY_PROFILES = derive_eligible_profiles_for_platform(
    STRATEGY_CATALOG,
    capability_matrix=PLATFORM_CAPABILITY_MATRIX,
    runtime_adapter_loader=lambda profile: get_platform_runtime_adapter(
        profile,
        platform_id=SCHWAB_PLATFORM,
    ),
)
SCHWAB_ENABLED_PROFILES = derive_enabled_profiles_for_platform(
    STRATEGY_CATALOG,
    capability_matrix=PLATFORM_CAPABILITY_MATRIX,
    runtime_adapter_loader=lambda profile: get_platform_runtime_adapter(
        profile,
        platform_id=SCHWAB_PLATFORM,
    ),
    rollout_allowlist=SCHWAB_ROLLOUT_ALLOWLIST,
)
PLATFORM_POLICY = PlatformStrategyPolicy(
    platform_id=SCHWAB_PLATFORM,
    supported_domains=PLATFORM_SUPPORTED_DOMAINS[SCHWAB_PLATFORM],
    enabled_profiles=SCHWAB_ENABLED_PROFILES,
    default_profile=DEFAULT_STRATEGY_PROFILE,
    rollback_profile=ROLLBACK_STRATEGY_PROFILE,
)

SUPPORTED_STRATEGY_PROFILES = SCHWAB_ENABLED_PROFILES


def get_eligible_profiles_for_platform(platform_id: str) -> frozenset[str]:
    if platform_id != SCHWAB_PLATFORM:
        return frozenset()
    return ELIGIBLE_STRATEGY_PROFILES


def get_supported_profiles_for_platform(platform_id: str) -> frozenset[str]:
    return get_enabled_profiles_for_platform(platform_id, policy=PLATFORM_POLICY)


def get_platform_profile_matrix() -> list[dict[str, object]]:
    return build_platform_profile_matrix(STRATEGY_CATALOG, policy=PLATFORM_POLICY)


def get_platform_profile_status_matrix() -> list[dict[str, object]]:
    return build_platform_profile_status_matrix(
        STRATEGY_CATALOG,
        policy=PLATFORM_POLICY,
        eligible_profiles=ELIGIBLE_STRATEGY_PROFILES,
    )


def resolve_strategy_definition(
    raw_value: str | None,
    *,
    platform_id: str,
) -> StrategyDefinition:
    return resolve_platform_strategy_definition(
        raw_value,
        platform_id=platform_id,
        strategy_catalog=STRATEGY_CATALOG,
        policy=PLATFORM_POLICY,
    )


def resolve_strategy_metadata(
    raw_value: str | None,
    *,
    platform_id: str,
):
    definition = resolve_strategy_definition(raw_value, platform_id=platform_id)
    return get_catalog_strategy_metadata(STRATEGY_CATALOG, definition.profile)
