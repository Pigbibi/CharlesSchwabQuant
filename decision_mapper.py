from __future__ import annotations

from typing import Any

from quant_platform_kit.strategy_contracts import StrategyDecision


def _target_values(decision: StrategyDecision) -> dict[str, float]:
    target_values: dict[str, float] = {}
    for position in decision.positions:
        if position.target_value is None:
            raise ValueError(
                "Schwab decision mapper requires target_value positions; "
                f"position {position.symbol!r} is missing target_value"
            )
        target_values[position.symbol] = float(position.target_value)
    return target_values


def _symbols_by_role(decision: StrategyDecision) -> tuple[list[str], list[str], list[str]]:
    target_values = _target_values(decision)
    risk_symbols: list[str] = []
    income_symbols: list[str] = []
    safe_haven_symbols: list[str] = []
    for position in decision.positions:
        if position.role == "safe_haven":
            safe_haven_symbols.append(position.symbol)
        elif position.role == "income":
            income_symbols.append(position.symbol)
        else:
            risk_symbols.append(position.symbol)
    risk_symbols = sorted(dict.fromkeys(risk_symbols))
    income_symbols = sorted(
        dict.fromkeys(income_symbols),
        key=lambda symbol: (-target_values.get(symbol, 0.0), symbol),
    )
    safe_haven_symbols = sorted(dict.fromkeys(safe_haven_symbols))
    return risk_symbols, income_symbols, safe_haven_symbols


def _extract_snapshot_positions(snapshot) -> tuple[dict[str, float], dict[str, int]]:
    market_values: dict[str, float] = {}
    quantities: dict[str, int] = {}
    for position in snapshot.positions:
        market_values[position.symbol] = float(position.market_value)
        quantities[position.symbol] = int(position.quantity)
    return market_values, quantities


def map_strategy_decision_to_plan(
    decision: StrategyDecision,
    *,
    snapshot,
    strategy_profile: str,
) -> dict[str, Any]:
    diagnostics = dict(decision.diagnostics)
    target_values = _target_values(decision)
    risk_symbols, income_symbols, safe_haven_symbols = _symbols_by_role(decision)
    strategy_symbols = tuple(risk_symbols + safe_haven_symbols + income_symbols)
    market_values, quantities = _extract_snapshot_positions(snapshot)
    for symbol in strategy_symbols:
        market_values.setdefault(symbol, 0.0)
        quantities.setdefault(symbol, 0)

    safe_haven_symbol = safe_haven_symbols[0] if safe_haven_symbols else None
    return {
        "strategy_profile": strategy_profile,
        "strategy_symbols": strategy_symbols,
        "sell_order_symbols": tuple(risk_symbols + income_symbols + safe_haven_symbols),
        "buy_order_symbols": tuple(income_symbols + risk_symbols),
        "cash_sweep_symbol": safe_haven_symbol,
        "portfolio_rows": (
            tuple(risk_symbols + safe_haven_symbols),
            tuple(income_symbols),
        ),
        "account_hash": snapshot.metadata["account_hash"],
        "market_values": market_values,
        "quantities": quantities,
        "total_equity": float(snapshot.total_equity),
        "real_buying_power": float(snapshot.buying_power or 0.0),
        "reserved": float(diagnostics["reserved"]),
        "threshold": float(diagnostics["threshold"]),
        "target_values": target_values,
        "sig_display": diagnostics["signal_display"],
        "dashboard": diagnostics["dashboard"],
        "qqq_p": float(diagnostics["qqq_price"]),
        "ma200": float(diagnostics["ma200"]),
        "exit_line": float(diagnostics["exit_line"]),
        "separator": diagnostics.get("separator", "━━━━━━━━━━━━━━━━━━"),
    }
