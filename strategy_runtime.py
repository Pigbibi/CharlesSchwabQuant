from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from quant_platform_kit.common.feature_snapshot import load_feature_snapshot_guarded
from quant_platform_kit.strategy_contracts import (
    StrategyDecision,
    StrategyEntrypoint,
    StrategyRuntimeAdapter,
    build_strategy_context_from_available_inputs,
)
from runtime_config_support import PlatformRuntimeSettings

from strategy_loader import (
    load_strategy_entrypoint_for_profile,
    load_strategy_runtime_adapter_for_profile,
)

_FEATURE_SNAPSHOT_INPUT = "feature_snapshot"


@dataclass(frozen=True)
class StrategyEvaluationResult:
    decision: StrategyDecision
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LoadedStrategyRuntime:
    entrypoint: StrategyEntrypoint
    runtime_adapter: StrategyRuntimeAdapter
    runtime_settings: PlatformRuntimeSettings
    runtime_overrides: Mapping[str, Any] = field(default_factory=dict)
    runtime_config: Mapping[str, Any] = field(default_factory=dict)
    merged_runtime_config: Mapping[str, Any] = field(default_factory=dict)
    logger: Callable[[str], None] = print

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
        signal_text_fn: Callable[[str], str],
        translator: Callable[[str], str],
        **available_inputs,
    ) -> StrategyEvaluationResult:
        runtime_config = dict(self.runtime_overrides)
        runtime_config.setdefault("signal_text_fn", signal_text_fn)
        runtime_config.setdefault("translator", translator)
        if _FEATURE_SNAPSHOT_INPUT in frozenset(self.entrypoint.manifest.required_inputs):
            return self._evaluate_feature_snapshot_strategy(
                runtime_config=runtime_config,
                available_inputs=available_inputs,
            )
        ctx = build_strategy_context_from_available_inputs(
            entrypoint=self.entrypoint,
            runtime_adapter=self.runtime_adapter,
            as_of=datetime.now(timezone.utc),
            available_inputs=available_inputs,
            runtime_config=runtime_config,
        )
        decision = self.entrypoint.evaluate(ctx)
        return StrategyEvaluationResult(
            decision=decision,
            metadata={"strategy_profile": self.profile},
        )

    def _evaluate_feature_snapshot_strategy(
        self,
        *,
        runtime_config: Mapping[str, Any],
        available_inputs: Mapping[str, Any],
    ) -> StrategyEvaluationResult:
        feature_snapshot_path = self.runtime_settings.feature_snapshot_path
        runtime_config_name = str(
            self.merged_runtime_config.get("runtime_config_name")
            or self.runtime_settings.strategy_profile
        )
        runtime_config_path = (
            self.merged_runtime_config.get("runtime_config_path")
            or self.runtime_settings.strategy_config_path
        )
        runtime_config_source = (
            self.merged_runtime_config.get("runtime_config_source")
            or self.runtime_settings.strategy_config_source
        )
        safe_haven_symbol = str(self.merged_runtime_config.get("safe_haven") or "BOXX").strip().upper() or None

        if not feature_snapshot_path:
            metadata = {
                "strategy_profile": self.profile,
                "feature_snapshot_path": None,
                "strategy_config_path": runtime_config_path,
                "strategy_config_source": runtime_config_source,
                "dry_run_only": self.runtime_settings.dry_run_only,
                "snapshot_guard_decision": "fail_closed",
                "fail_reason": "feature_snapshot_path_missing",
                "managed_symbols": self.managed_symbols,
                "safe_haven_symbol": safe_haven_symbol,
                "status_icon": "🛑",
            }
            decision = StrategyDecision(
                risk_flags=("no_execute",),
                diagnostics={
                    "signal_description": "feature snapshot required",
                    "status_description": "fail_closed | reason=feature_snapshot_path_missing",
                    "actionable": False,
                    "snapshot_guard_decision": "fail_closed",
                    "fail_reason": "feature_snapshot_path_missing",
                },
            )
            return StrategyEvaluationResult(decision=decision, metadata=metadata)

        guard_result = load_feature_snapshot_guarded(
            feature_snapshot_path,
            run_as_of=datetime.now(timezone.utc),
            required_columns=self.runtime_adapter.required_feature_columns,
            snapshot_date_columns=tuple(self.runtime_adapter.snapshot_date_columns),
            max_snapshot_month_lag=int(self.runtime_adapter.max_snapshot_month_lag),
            manifest_path=self.runtime_settings.feature_snapshot_manifest_path,
            require_manifest=bool(self.runtime_adapter.require_snapshot_manifest),
            expected_strategy_profile=self.profile,
            expected_config_name=runtime_config_name,
            expected_config_path=runtime_config_path,
            expected_contract_version=self.runtime_adapter.snapshot_contract_version,
        )
        guard_metadata = dict(guard_result.metadata)
        if guard_metadata.get("snapshot_guard_decision") != "proceed":
            decision_text = str(guard_metadata.get("snapshot_guard_decision") or "fail_closed")
            reason = guard_metadata.get("fail_reason") or guard_metadata.get("no_op_reason")
            metadata = {
                "strategy_profile": self.profile,
                "strategy_config_path": runtime_config_path,
                "strategy_config_source": runtime_config_source,
                "dry_run_only": self.runtime_settings.dry_run_only,
                "managed_symbols": self.managed_symbols,
                "safe_haven_symbol": safe_haven_symbol,
                "status_icon": "🛑",
                **guard_metadata,
            }
            decision = StrategyDecision(
                risk_flags=("no_execute",),
                diagnostics={
                    "signal_description": "feature snapshot guard blocked execution",
                    "status_description": f"{decision_text} | reason={reason}",
                    "actionable": False,
                    "snapshot_guard_decision": decision_text,
                    "fail_reason": guard_metadata.get("fail_reason"),
                    "no_op_reason": guard_metadata.get("no_op_reason"),
                },
            )
            return StrategyEvaluationResult(decision=decision, metadata=metadata)

        evaluation_inputs = dict(available_inputs)
        evaluation_inputs[_FEATURE_SNAPSHOT_INPUT] = guard_result.frame
        ctx = build_strategy_context_from_available_inputs(
            entrypoint=self.entrypoint,
            runtime_adapter=self.runtime_adapter,
            as_of=datetime.now(timezone.utc),
            available_inputs=evaluation_inputs,
            runtime_config=runtime_config,
        )
        decision = self.entrypoint.evaluate(ctx)
        managed_symbols = self._extract_managed_symbols(guard_result.frame, safe_haven_symbol=safe_haven_symbol)
        return StrategyEvaluationResult(
            decision=decision,
            metadata={
                "strategy_profile": self.profile,
                "strategy_config_path": runtime_config_path,
                "strategy_config_source": runtime_config_source,
                "feature_snapshot_path": feature_snapshot_path,
                "dry_run_only": self.runtime_settings.dry_run_only,
                "managed_symbols": managed_symbols,
                "safe_haven_symbol": safe_haven_symbol,
                "status_icon": self.runtime_adapter.status_icon,
                **guard_metadata,
            },
        )

    def _extract_managed_symbols(
        self,
        feature_snapshot,
        *,
        safe_haven_symbol: str | None,
    ) -> tuple[str, ...]:
        extractor = self.runtime_adapter.managed_symbols_extractor
        if callable(extractor):
            return tuple(
                extractor(
                    feature_snapshot,
                    benchmark_symbol=str(self.merged_runtime_config.get("benchmark_symbol") or "QQQ"),
                    safe_haven=safe_haven_symbol,
                )
            )
        if safe_haven_symbol:
            return (safe_haven_symbol,)
        return self.managed_symbols

    def load_runtime_parameters(self) -> dict[str, Any]:
        runtime_loader = self.runtime_adapter.runtime_parameter_loader
        if not callable(runtime_loader):
            return {}
        return dict(
            runtime_loader(
                config_path=self.runtime_settings.strategy_config_path,
                logger=self.logger,
            )
            or {}
        )


def load_strategy_runtime(
    raw_profile: str | None,
    *,
    runtime_settings: PlatformRuntimeSettings,
    runtime_overrides: Mapping[str, Any] | None = None,
    logger: Callable[[str], None] = print,
) -> LoadedStrategyRuntime:
    entrypoint = load_strategy_entrypoint_for_profile(raw_profile)
    runtime_adapter = load_strategy_runtime_adapter_for_profile(raw_profile)
    overrides = dict(runtime_overrides or {})
    runtime = LoadedStrategyRuntime(
        entrypoint=entrypoint,
        runtime_adapter=runtime_adapter,
        runtime_settings=runtime_settings,
        runtime_overrides=overrides,
        logger=logger,
    )
    runtime_config = runtime.load_runtime_parameters()
    merged_runtime_config = dict(entrypoint.manifest.default_config)
    merged_runtime_config.update(runtime_config)
    merged_runtime_config.update(overrides)
    return LoadedStrategyRuntime(
        entrypoint=entrypoint,
        runtime_adapter=runtime_adapter,
        runtime_settings=runtime_settings,
        runtime_overrides=overrides,
        runtime_config=runtime_config,
        merged_runtime_config=merged_runtime_config,
        logger=logger,
    )
