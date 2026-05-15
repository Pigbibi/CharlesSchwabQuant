"""Order execution helpers for CharlesSchwabPlatform."""

from __future__ import annotations

from dataclasses import dataclass

from quant_platform_kit.common.cash_sweep import (
    estimate_cash_sweep_sale_quantity_to_fund_buy,
)
from quant_platform_kit.common.models import OrderIntent
from quant_platform_kit.common.quantity import format_quantity


@dataclass(frozen=True)
class ExecutionCycleResult:
    plan: dict
    portfolio: dict
    execution: dict
    allocation: dict
    trade_logs: tuple[str, ...]


def _noop_sleep(_seconds):
    return None


def execute_rebalance_cycle(
    *,
    client,
    plan,
    portfolio,
    execution,
    allocation,
    fetch_managed_snapshot,
    market_data_port,
    load_plan,
    execution_port=None,
    submit_equity_order=None,
    translator,
    limit_buy_premium,
    sell_settle_delay_sec,
    dry_run_only=False,
    post_sell_refresh_attempts=1,
    post_sell_refresh_interval_sec=0.0,
    sleeper=_noop_sleep,
    publish_order_issue,
) -> ExecutionCycleResult:
    def load_quotes(symbols):
        quotes = {}
        for symbol in symbols:
            snapshot = market_data_port.get_quote(symbol)
            quotes[symbol] = {
                "lastPrice": snapshot.last_price,
                "askPrice": snapshot.ask_price or snapshot.last_price,
            }
        return quotes

    def buying_power_from_plan(current_portfolio, current_execution):
        current_liquid_cash = float(current_portfolio["liquid_cash"])
        current_reserved_cash = float(current_execution["reserved_cash"])
        return max(0.0, current_liquid_cash - current_reserved_cash)

    strategy_symbols = tuple(allocation["strategy_symbols"])
    quotes = load_quotes(strategy_symbols)
    trade_logs: list[str] = []

    def execute_fire_forget(symbol, action_type, quantity, price=None):
        if quantity <= 0:
            return False
        try:
            price_text = "{:.2f}".format(price) if price else None
            if action_type == "SELL":
                order_intent = OrderIntent(symbol=symbol, side="sell", quantity=quantity)
            elif action_type == "BUY_LIMIT":
                order_intent = OrderIntent(
                    symbol=symbol,
                    side="buy",
                    quantity=quantity,
                    order_type="limit",
                    limit_price=float(price),
                )
            elif action_type == "BUY_MARKET":
                order_intent = OrderIntent(symbol=symbol, side="buy", quantity=quantity)
            else:
                return False

            if dry_run_only:
                if action_type == "SELL":
                    trade_logs.append(
                        translator(
                            "dry_run_trade_log",
                            command=translator("market_sell_cmd"),
                            symbol=symbol,
                            quantity=quantity,
                            shares=translator("shares"),
                        )
                    )
                elif action_type == "BUY_LIMIT":
                    trade_logs.append(
                        translator(
                            "dry_run_trade_log_with_price",
                            command=translator("limit_buy_cmd"),
                            symbol=symbol,
                            price=price_text,
                            quantity=quantity,
                            shares=translator("shares"),
                        )
                    )
                elif action_type == "BUY_MARKET":
                    trade_logs.append(
                        translator(
                            "dry_run_trade_log",
                            command=translator("market_buy_cmd"),
                            symbol=symbol,
                            quantity=quantity,
                            shares=translator("shares"),
                        )
                    )
                return True

            if execution_port is not None:
                report = execution_port.submit_order(order_intent)
            elif submit_equity_order is not None:
                report = submit_equity_order(client, plan["account_hash"], order_intent)
            else:
                raise ValueError("Schwab execution requires execution_port or submit_equity_order")
            success = report.status == "accepted"
            info = report.broker_order_id if success else report.raw_payload.get("detail", report.status)
            order_id_suffix = str(translator("order_id_suffix", order_id=info)).strip()
            if not order_id_suffix or order_id_suffix == "order_id_suffix":
                order_id_suffix = f"（订单号: {info}）"
            if success:
                if action_type == "SELL":
                    trade_logs.append(
                        f"✅ 📉 {translator('market_sell_cmd')} {symbol}: {quantity}{translator('shares')} {order_id_suffix}"
                    )
                elif action_type == "BUY_LIMIT":
                    trade_logs.append(
                        f"✅ 💰 {translator('limit_buy_cmd')} {symbol} (${price_text}): {quantity}{translator('shares')} {translator('submitted')} {order_id_suffix}"
                    )
                elif action_type == "BUY_MARKET":
                    trade_logs.append(
                        f"✅ 📈 {translator('market_buy_cmd')} {symbol}: {quantity}{translator('shares')} {order_id_suffix}"
                    )
                return True

            if action_type == "SELL":
                message = f"❌ {translator('market_sell')} {symbol}: {quantity}{translator('shares')} {translator('failed')} - {info}"
            elif action_type == "BUY_LIMIT":
                message = f"❌ {translator('limit_buy')} {symbol}: {quantity}{translator('shares')} {translator('failed')} - {info}"
            else:
                message = f"❌ {translator('market_buy')} {symbol}: {quantity}{translator('shares')} {translator('failed')} - {info}"
            trade_logs.append(message)
            publish_order_issue(message)
            return False
        except Exception as exc:
            message = f"🚨 {symbol} {translator('buy_label')} {quantity}{translator('shares')} {translator('exception')}: {exc}"
            trade_logs.append(message)
            publish_order_issue(message)
            return False

    market_values = dict(portfolio["market_values"])
    quantities = dict(portfolio["quantities"])
    target_values = dict(allocation["targets"])
    threshold = float(execution["trade_threshold_value"])
    cash_sweep_symbol = str(portfolio["cash_sweep_symbol"])
    dry_run_sale_events = []
    post_sell_buying_power_released = None
    buy_order_symbols = tuple(
        allocation.get("income_symbols", ()) + allocation.get("risk_symbols", ())
    )
    funding_buy_candidates = [
        symbol
        for symbol in buy_order_symbols
        if symbol != cash_sweep_symbol and (target_values[symbol] - market_values[symbol]) > threshold
    ]

    def cash_sweep_sale_quantity_to_fund_buy(max_quantity, candidate_symbols):
        if max_quantity <= 0 or not cash_sweep_symbol:
            return 0
        cash_sweep_price = quotes[cash_sweep_symbol]["lastPrice"]
        base_buying_power = buying_power_from_plan(portfolio, execution)
        funding_needs = (
            (
                target_values[buy_symbol] - market_values[buy_symbol],
                quotes[buy_symbol]["askPrice"],
            )
            for buy_symbol in candidate_symbols
        )
        return estimate_cash_sweep_sale_quantity_to_fund_buy(
            max_quantity,
            cash_sweep_price,
            base_buying_power,
            funding_needs,
        )

    sell_order_symbols = tuple(
        allocation.get("risk_symbols", ())
        + allocation.get("income_symbols", ())
        + allocation.get("safe_haven_symbols", ())
    )
    sell_executed = False
    cash_sweep_sold_this_cycle = False
    for symbol in sell_order_symbols:
        current = market_values[symbol]
        target = target_values[symbol]
        if current > (target + threshold):
            quantity = int((current - target) // quotes[symbol]["lastPrice"])
            if symbol == cash_sweep_symbol:
                quantity = cash_sweep_sale_quantity_to_fund_buy(quantity, funding_buy_candidates)
                if quantity <= 0:
                    continue
            if execute_fire_forget(symbol, "SELL", quantity):
                sell_executed = True
                if symbol == cash_sweep_symbol:
                    cash_sweep_sold_this_cycle = True
                if dry_run_only:
                    dry_run_sale_events.append(
                        (symbol, quantity, quantity * quotes[symbol]["lastPrice"])
                    )

    if (
        not cash_sweep_sold_this_cycle
        and funding_buy_candidates
        and cash_sweep_symbol
        and quantities.get(cash_sweep_symbol, 0.0) > 0.0
    ):
        sweep_quantity = cash_sweep_sale_quantity_to_fund_buy(
            int(quantities[cash_sweep_symbol]),
            funding_buy_candidates,
        )
        if sweep_quantity > 0:
            sweep_price = round(float(quotes[cash_sweep_symbol]["lastPrice"]), 2)
            if dry_run_only:
                submitted = execute_fire_forget(
                    cash_sweep_symbol,
                    "SELL",
                    sweep_quantity,
                    sweep_price,
                )
            else:
                submitted = execute_fire_forget(
                    cash_sweep_symbol,
                    "SELL",
                    sweep_quantity,
                    sweep_price,
                )
            if submitted:
                sell_executed = True
                cash_sweep_sold_this_cycle = True
                if dry_run_only:
                    dry_run_sale_events.append(
                        (
                            cash_sweep_symbol,
                            sweep_quantity,
                            sweep_quantity * sweep_price,
                        )
                    )

    if sell_executed:
        if dry_run_only:
            virtual_market_values = dict(portfolio["market_values"])
            virtual_quantities = dict(portfolio["quantities"])
            virtual_sale_proceeds = 0.0
            for symbol, quantity, sale_value in dry_run_sale_events:
                virtual_sale_proceeds += sale_value
                virtual_market_values[symbol] = max(
                    0.0,
                    float(virtual_market_values.get(symbol, 0.0)) - sale_value,
                )
                virtual_quantities[symbol] = max(
                    0,
                    int(virtual_quantities.get(symbol, 0)) - quantity,
                )
            portfolio = dict(portfolio)
            portfolio["market_values"] = virtual_market_values
            portfolio["quantities"] = virtual_quantities
            portfolio["liquid_cash"] = float(portfolio["liquid_cash"]) + virtual_sale_proceeds
            market_values = dict(portfolio["market_values"])
        else:
            previous_buying_power = buying_power_from_plan(portfolio, execution)
            refresh_attempts = max(1, int(post_sell_refresh_attempts or 1))
            refresh_interval = max(0.0, float(post_sell_refresh_interval_sec or 0.0))
            best_refreshed_state = None
            best_buying_power = previous_buying_power
            for attempt in range(refresh_attempts):
                sleeper(sell_settle_delay_sec if attempt == 0 else refresh_interval)
                snapshot = fetch_managed_snapshot(client)
                refreshed_state = load_plan(snapshot)
                refreshed_buying_power = buying_power_from_plan(
                    refreshed_state[1],
                    refreshed_state[2],
                )
                if best_refreshed_state is None or refreshed_buying_power > best_buying_power:
                    best_refreshed_state = refreshed_state
                    best_buying_power = refreshed_buying_power
                if refreshed_buying_power > previous_buying_power:
                    best_refreshed_state = refreshed_state
                    break
            post_sell_buying_power_released = best_buying_power > previous_buying_power
            plan, portfolio, execution, allocation = best_refreshed_state
            strategy_symbols = tuple(allocation["strategy_symbols"])
            quotes = load_quotes(strategy_symbols)
            market_values = dict(portfolio["market_values"])
            target_values = dict(allocation["targets"])
            threshold = float(execution["trade_threshold_value"])

    liquid_cash = float(portfolio["liquid_cash"])
    reserved_cash = float(execution["reserved_cash"])
    estimated_buying_power = max(0, liquid_cash - reserved_cash)
    buy_executed = False
    for symbol in buy_order_symbols:
        target_val = target_values[symbol]
        if market_values[symbol] < (target_val - threshold):
            amount_to_spend = min(target_val - market_values[symbol], estimated_buying_power)
            if amount_to_spend > 0:
                ask = quotes[symbol]["askPrice"]
                quantity = int(amount_to_spend // ask)
                if quantity > 0:
                    limit_price = round(ask * limit_buy_premium, 2)
                    if execute_fire_forget(symbol, "BUY_LIMIT", quantity, limit_price):
                        buy_executed = True
                        estimated_buying_power -= quantity * limit_price

    if (
        not cash_sweep_sold_this_cycle
        and estimated_buying_power > quotes[cash_sweep_symbol]["lastPrice"] * 2
    ):
        quantity = int(estimated_buying_power // quotes[cash_sweep_symbol]["lastPrice"])
        if quantity > 0:
            if execute_fire_forget(cash_sweep_symbol, "BUY_MARKET", quantity):
                trade_logs.append(
                    translator(
                        "cash_sweep_rebuy",
                        symbol=cash_sweep_symbol,
                        quantity=format_quantity(quantity),
                        shares=translator("shares"),
                        price=f"{quotes[cash_sweep_symbol]['lastPrice']:.2f}",
                    )
                )
                buy_executed = True

    if (
        sell_executed
        and not dry_run_only
        and post_sell_buying_power_released is False
        and not buy_executed
    ):
        trade_logs.append(translator("post_sell_buying_power_unreleased"))

    return ExecutionCycleResult(
        plan=dict(plan or {}),
        portfolio=dict(portfolio or {}),
        execution=dict(execution or {}),
        allocation=dict(allocation or {}),
        trade_logs=tuple(trade_logs),
    )
