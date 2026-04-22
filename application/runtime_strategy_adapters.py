"""Builder helpers for Schwab strategy evaluation adapters."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Callable
from dataclasses import dataclass
from typing import Any

from quant_platform_kit.strategy_contracts import build_account_state_from_portfolio_snapshot


@dataclass(frozen=True)
class SchwabRuntimeStrategyAdapters:
    strategy_runtime: Any
    strategy_profile: str
    strategy_runtime_config: Mapping[str, Any]
    available_inputs: Collection[str]
    benchmark_symbol: str
    managed_symbols: tuple[str, ...]
    signal_text_fn: Callable[[str], str]
    translator: Callable[..., str]
    broker_adapters: Any
    build_strategy_evaluation_inputs_fn: Callable[..., dict[str, Any]]
    map_strategy_decision_to_plan_fn: Callable[..., dict[str, Any]]
    build_strategy_plugin_report_payload_fn: Callable[..., dict[str, Any]]
    load_configured_strategy_plugin_signals_fn: Callable[..., Any]
    parse_strategy_plugin_mounts_fn: Callable[..., Any]
    reserved_cash_floor_usd: float = 0.0
    reserved_cash_ratio: float = 0.0

    def load_strategy_plugin_signals(self, raw_mounts):
        if not raw_mounts:
            return (), None
        try:
            mounts = self.parse_strategy_plugin_mounts_fn(raw_mounts)
            if not mounts:
                return (), None
            return (
                self.load_configured_strategy_plugin_signals_fn(
                    mounts,
                    strategy_profile=self.strategy_profile,
                ),
                None,
            )
        except Exception as exc:
            return (), f"{type(exc).__name__}: {exc}"

    def attach_strategy_plugin_report(self, report, *, signals, error: str | None = None):
        if signals:
            report.setdefault("summary", {}).update(self.build_strategy_plugin_report_payload_fn(signals))
        if error:
            report.setdefault("diagnostics", {})["strategy_plugin_error"] = error

    def translate_strategy_plugin_value(self, category: str, raw_value: str | None) -> str:
        value = str(raw_value or "").strip() or "unknown"
        key = f"strategy_plugin_{category}_{value}"
        translated = self.translator(key)
        return translated if translated != key else value

    def build_strategy_plugin_notification_lines(self, signals) -> tuple[str, ...]:
        lines = []
        for signal in signals:
            route = signal.canonical_route or "unknown_route"
            action = signal.suggested_action or "unknown_action"
            lines.append(
                self.translator(
                    "strategy_plugin_line",
                    plugin=self.translate_strategy_plugin_value("name", signal.plugin),
                    mode=self.translate_strategy_plugin_value("mode", signal.effective_mode),
                    route=self.translate_strategy_plugin_value("route", route),
                    action=self.translate_strategy_plugin_value("action", action),
                )
            )
        return tuple(lines)

    def fetch_reference_history(self, market_data_port):
        available_inputs = set(self.available_inputs)
        if "feature_snapshot" in available_inputs and not (
            {"market_history", "benchmark_history", "qqq_history", "derived_indicators", "indicators"}
            & available_inputs
        ):
            return {}
        if "market_history" in available_inputs:
            market_inputs = {
                "market_history": self.broker_adapters.build_market_history_loader(market_data_port),
            }
            if "benchmark_history" in available_inputs:
                market_inputs["benchmark_history"] = self.broker_adapters.build_price_history(
                    market_data_port,
                    self.benchmark_symbol,
                )
            if "qqq_history" in available_inputs:
                market_inputs["qqq_history"] = self.broker_adapters.build_price_history(
                    market_data_port,
                    self.benchmark_symbol,
                )
            return market_inputs
        if "benchmark_history" in available_inputs or "qqq_history" in available_inputs:
            return self.broker_adapters.build_price_history(market_data_port, self.benchmark_symbol)
        if "derived_indicators" in available_inputs or "indicators" in available_inputs:
            return self.build_semiconductor_indicators(
                market_data_port,
                trend_window=int(self.strategy_runtime_config.get("trend_ma_window", 150)),
            )
        raise ValueError(
            f"Unsupported Schwab runtime inputs for {self.strategy_profile}: {sorted(available_inputs)}"
        )

    def build_semiconductor_indicators(self, market_data_source, *, trend_window: int) -> dict[str, dict[str, float]]:
        market_data_port = (
            market_data_source
            if hasattr(market_data_source, "get_price_series")
            else self.broker_adapters.build_market_data_port(market_data_source)
        )
        soxl_history = self.broker_adapters.build_price_history(market_data_port, "SOXL")
        soxx_history = self.broker_adapters.build_price_history(market_data_port, "SOXX")
        if len(soxl_history) < trend_window:
            raise RuntimeError(f"SOXL history has {len(soxl_history)} candles; need at least {trend_window}")
        if len(soxx_history) < trend_window:
            raise RuntimeError(f"SOXX history has {len(soxx_history)} candles; need at least {trend_window}")

        soxl_closes = [float(candle["close"]) for candle in soxl_history[-trend_window:]]
        soxx_all_closes = [float(candle["close"]) for candle in soxx_history]
        soxx_trend_closes = soxx_all_closes[-trend_window:]
        soxx_ma20_closes = soxx_all_closes[-20:]
        previous_soxx_ma20_closes = soxx_all_closes[-21:-1]
        soxx_ma20 = sum(soxx_ma20_closes) / 20
        previous_soxx_ma20 = (
            sum(previous_soxx_ma20_closes) / 20
            if len(previous_soxx_ma20_closes) == 20
            else soxx_ma20
        )
        return {
            "soxl": {
                "price": soxl_closes[-1],
                "ma_trend": sum(soxl_closes) / trend_window,
            },
            "soxx": {
                "price": soxx_all_closes[-1],
                "ma_trend": sum(soxx_trend_closes) / trend_window,
                "ma20": soxx_ma20,
                "ma20_slope": soxx_ma20 - previous_soxx_ma20,
            },
        }

    def build_account_state_from_snapshot(self, snapshot) -> dict[str, object]:
        return build_account_state_from_portfolio_snapshot(
            snapshot,
            strategy_symbols=self.managed_symbols,
        )

    def resolve_rebalance_plan(self, *, qqq_history, snapshot):
        account_state = None
        if "account_state" in self.available_inputs:
            account_state = self.build_account_state_from_snapshot(snapshot)
        market_inputs = {
            "market_history": qqq_history,
            "benchmark_history": qqq_history,
            "qqq_history": qqq_history,
            "derived_indicators": qqq_history,
            "indicators": qqq_history,
        }
        if isinstance(qqq_history, dict) and any(
            key in qqq_history for key in ("market_history", "benchmark_history", "qqq_history")
        ):
            market_inputs.update(qqq_history)
        evaluation_inputs = self.build_strategy_evaluation_inputs_fn(
            available_inputs=self.available_inputs,
            market_inputs=market_inputs,
            portfolio_snapshot=snapshot,
            account_state=account_state,
            translator=self.translator,
            signal_text_fn=self.signal_text_fn,
        )
        evaluation = self.strategy_runtime.evaluate(**evaluation_inputs)
        runtime_metadata = dict(getattr(evaluation, "metadata", None) or {})
        runtime_metadata["schwab_execution_policy"] = {
            "reserved_cash_floor_usd": float(self.reserved_cash_floor_usd or 0.0),
            "reserved_cash_ratio": float(self.reserved_cash_ratio or 0.0),
        }
        return self.map_strategy_decision_to_plan_fn(
            evaluation.decision,
            snapshot=snapshot,
            strategy_profile=self.strategy_profile,
            runtime_metadata=runtime_metadata,
        )


def build_runtime_strategy_adapters(
    *,
    strategy_runtime: Any,
    strategy_profile: str,
    strategy_runtime_config: Mapping[str, Any],
    available_inputs: Collection[str],
    benchmark_symbol: str,
    managed_symbols: tuple[str, ...],
    signal_text_fn: Callable[[str], str],
    translator: Callable[..., str],
    broker_adapters: Any,
    build_strategy_evaluation_inputs_fn: Callable[..., dict[str, Any]],
    map_strategy_decision_to_plan_fn: Callable[..., dict[str, Any]],
    build_strategy_plugin_report_payload_fn: Callable[..., dict[str, Any]],
    load_configured_strategy_plugin_signals_fn: Callable[..., Any],
    parse_strategy_plugin_mounts_fn: Callable[..., Any],
    reserved_cash_floor_usd: float = 0.0,
    reserved_cash_ratio: float = 0.0,
) -> SchwabRuntimeStrategyAdapters:
    return SchwabRuntimeStrategyAdapters(
        strategy_runtime=strategy_runtime,
        strategy_profile=str(strategy_profile),
        strategy_runtime_config=dict(strategy_runtime_config),
        available_inputs=frozenset(available_inputs),
        benchmark_symbol=str(benchmark_symbol or ""),
        managed_symbols=tuple(managed_symbols),
        signal_text_fn=signal_text_fn,
        translator=translator,
        broker_adapters=broker_adapters,
        build_strategy_evaluation_inputs_fn=build_strategy_evaluation_inputs_fn,
        map_strategy_decision_to_plan_fn=map_strategy_decision_to_plan_fn,
        build_strategy_plugin_report_payload_fn=build_strategy_plugin_report_payload_fn,
        load_configured_strategy_plugin_signals_fn=load_configured_strategy_plugin_signals_fn,
        parse_strategy_plugin_mounts_fn=parse_strategy_plugin_mounts_fn,
        reserved_cash_floor_usd=float(reserved_cash_floor_usd or 0.0),
        reserved_cash_ratio=float(reserved_cash_ratio or 0.0),
    )
