from __future__ import annotations

from typing import Any

from quant_platform_kit.strategy_contracts import (
    StrategyDecision,
    ValueTargetExecutionAnnotations,
    build_value_target_portfolio_inputs_from_snapshot,
    build_value_target_runtime_plan,
    translate_decision_to_target_mode,
)


def map_strategy_decision_to_plan(
    decision: StrategyDecision,
    *,
    snapshot,
    strategy_profile: str,
    runtime_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    runtime_metadata = dict(runtime_metadata or {})
    normalized_decision = translate_decision_to_target_mode(
        decision,
        target_mode="value",
        total_equity=float(snapshot.total_equity),
    )
    diagnostics = {**runtime_metadata, **dict(decision.diagnostics)}
    execution_annotations: dict[str, Any] = {}
    raw_runtime_annotations = runtime_metadata.get("execution_annotations")
    if isinstance(raw_runtime_annotations, dict):
        execution_annotations.update(raw_runtime_annotations)
    raw_annotations = diagnostics.get("execution_annotations")
    if isinstance(raw_annotations, dict):
        execution_annotations.update(raw_annotations)
    portfolio_inputs = build_value_target_portfolio_inputs_from_snapshot(snapshot)
    plan = build_value_target_runtime_plan(
        normalized_decision,
        strategy_profile=strategy_profile,
        portfolio_inputs=portfolio_inputs,
        strategy_symbols_order="risk_safe_income",
        portfolio_rows_layout=("risk_safe", "income"),
        execution_fields=(
            "trade_threshold_value",
            "reserved_cash",
            "signal_display",
            "status_display",
            "dashboard_text",
            "signal_date",
            "effective_date",
            "execution_timing_contract",
            "execution_calendar_source",
            "signal_effective_after_trading_days",
            "separator",
            "benchmark_symbol",
            "benchmark_price",
            "long_trend_value",
            "exit_line",
            "deploy_ratio_text",
            "income_ratio_text",
            "income_locked_ratio_text",
            "active_risk_asset",
            "current_min_trade",
            "investable_cash",
        ),
        execution_defaults={
            "reserved_cash": 0.0,
            "signal_display": "",
            "status_display": "",
            "dashboard_text": "",
            "signal_date": "",
            "effective_date": "",
            "execution_timing_contract": "",
            "execution_calendar_source": "",
            "signal_effective_after_trading_days": None,
            "separator": "━━━━━━━━━━━━━━━━━━",
            "benchmark_symbol": "QQQ",
            "benchmark_price": 0.0,
            "long_trend_value": 0.0,
            "exit_line": 0.0,
            "deploy_ratio_text": "",
            "income_ratio_text": "",
            "income_locked_ratio_text": "",
            "active_risk_asset": "",
            "current_min_trade": 0.0,
            "investable_cash": portfolio_inputs.liquid_cash,
        },
        annotations=ValueTargetExecutionAnnotations(
            trade_threshold_value=float(
                execution_annotations.get("trade_threshold_value", diagnostics.get("threshold", 0.0)) or 0.0
            ),
            reserved_cash=float(execution_annotations.get("reserved_cash", diagnostics.get("reserved", 0.0)) or 0.0),
            signal_display=str(
                execution_annotations.get("signal_display")
                or diagnostics.get("signal_display")
                or diagnostics.get("signal_description")
                or ""
            ),
            status_display=str(
                execution_annotations.get("status_display")
                or diagnostics.get("status_display")
                or diagnostics.get("status_description")
                or diagnostics.get("canary_status")
                or ""
            ),
            dashboard_text=str(
                execution_annotations.get("dashboard_text")
                or diagnostics.get("dashboard")
                or ""
            ),
            signal_date=str(execution_annotations.get("signal_date") or diagnostics.get("signal_date") or "") or None,
            effective_date=str(
                execution_annotations.get("effective_date") or diagnostics.get("effective_date") or ""
            )
            or None,
            execution_timing_contract=str(
                execution_annotations.get("execution_timing_contract")
                or diagnostics.get("execution_timing_contract")
                or ""
            )
            or None,
            execution_calendar_source=str(
                execution_annotations.get("execution_calendar_source")
                or diagnostics.get("execution_calendar_source")
                or ""
            )
            or None,
            signal_effective_after_trading_days=(
                int(signal_delay)
                if (
                    signal_delay := execution_annotations.get(
                        "signal_effective_after_trading_days",
                        diagnostics.get("signal_effective_after_trading_days"),
                    )
                )
                is not None
                else None
            ),
            separator=str(execution_annotations.get("separator") or "━━━━━━━━━━━━━━━━━━"),
            benchmark_symbol=str(execution_annotations.get("benchmark_symbol") or "QQQ"),
            benchmark_price=float(execution_annotations.get("benchmark_price", diagnostics.get("qqq_price", 0.0)) or 0.0),
            long_trend_value=float(execution_annotations.get("long_trend_value", diagnostics.get("ma200", 0.0)) or 0.0),
            exit_line=float(execution_annotations.get("exit_line", diagnostics.get("exit_line", 0.0)) or 0.0),
            deploy_ratio_text=str(execution_annotations.get("deploy_ratio_text") or ""),
            income_ratio_text=str(execution_annotations.get("income_ratio_text") or ""),
            income_locked_ratio_text=str(execution_annotations.get("income_locked_ratio_text") or ""),
            active_risk_asset=str(execution_annotations.get("active_risk_asset") or ""),
            current_min_trade=float(execution_annotations.get("current_min_trade", 0.0) or 0.0),
            investable_cash=float(execution_annotations.get("investable_cash", portfolio_inputs.liquid_cash) or 0.0),
        ),
    )
    plan["account_hash"] = snapshot.metadata["account_hash"]
    return plan
