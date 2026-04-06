"""Application orchestration for CharlesSchwabPlatform."""

from __future__ import annotations

import time

from quant_platform_kit.common.models import OrderIntent


def run_strategy_core(
    client,
    now_ny,
    *,
    fetch_reference_history,
    fetch_managed_snapshot,
    fetch_managed_quotes,
    resolve_rebalance_plan,
    submit_equity_order,
    send_tg_message,
    translator,
    limit_buy_premium,
    sell_settle_delay_sec,
):
    del now_ny

    snapshot = fetch_managed_snapshot(client)
    plan = resolve_rebalance_plan(
        qqq_history=fetch_reference_history(client),
        snapshot=snapshot,
    )
    strategy_symbols = plan["strategy_symbols"]

    quote_snapshots = fetch_managed_quotes(client)
    quotes = {
        symbol: {
            "lastPrice": quote_snapshots[symbol].last_price,
            "askPrice": quote_snapshots[symbol].ask_price or quote_snapshots[symbol].last_price,
        }
        for symbol in strategy_symbols
    }
    trade_logs = []

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

            report = submit_equity_order(client, plan["account_hash"], order_intent)
            success = report.status == "accepted"
            info = report.broker_order_id if success else report.raw_payload.get("detail", report.status)
            if success:
                if action_type == "SELL":
                    trade_logs.append(
                        f"✅ 📉 {translator('market_sell_cmd')} {symbol}: {quantity}{translator('shares')} (ID: {info})"
                    )
                elif action_type == "BUY_LIMIT":
                    trade_logs.append(
                        f"✅ 💰 {translator('limit_buy_cmd')} {symbol} (${price_text}): {quantity}{translator('shares')} {translator('submitted')} (ID: {info})"
                    )
                elif action_type == "BUY_MARKET":
                    trade_logs.append(
                        f"✅ 📈 {translator('market_buy_cmd')} {symbol}: {quantity}{translator('shares')} (ID: {info})"
                    )
                return True

            if action_type == "SELL":
                message = f"❌ {translator('market_sell')} {symbol}: {quantity}{translator('shares')} {translator('failed')} - {info}"
            elif action_type == "BUY_LIMIT":
                message = f"❌ {translator('limit_buy')} {symbol}: {quantity}{translator('shares')} {translator('failed')} - {info}"
            else:
                message = f"❌ {translator('market_buy')} {symbol}: {quantity}{translator('shares')} {translator('failed')} - {info}"
            trade_logs.append(message)
            send_tg_message(message)
            return False
        except Exception as exc:
            message = f"🚨 {symbol} {translator('buy_label')} {quantity}{translator('shares')} {translator('exception')}: {exc}"
            trade_logs.append(message)
            send_tg_message(message)
            return False

    market_values = plan["market_values"]
    target_values = plan["target_values"]
    threshold = plan["threshold"]
    sell_executed = False
    for symbol in plan["sell_order_symbols"]:
        current = market_values[symbol]
        target = target_values[symbol]
        if current > (target + threshold):
            quantity = int((current - target) // quotes[symbol]["lastPrice"])
            execute_fire_forget(symbol, "SELL", quantity)
            sell_executed = True

    if sell_executed:
        time.sleep(sell_settle_delay_sec)

    estimated_buying_power = max(0, plan["real_buying_power"] - plan["reserved"])
    for symbol in plan["buy_order_symbols"]:
        target_val = target_values[symbol]
        if market_values[symbol] < (target_val - threshold):
            amount_to_spend = min(target_val - market_values[symbol], estimated_buying_power)
            if amount_to_spend > 0:
                ask = quotes[symbol]["askPrice"]
                quantity = int(amount_to_spend // ask)
                if quantity > 0:
                    limit_price = round(ask * limit_buy_premium, 2)
                    execute_fire_forget(symbol, "BUY_LIMIT", quantity, limit_price)
                    estimated_buying_power -= quantity * limit_price

    cash_sweep_symbol = plan["cash_sweep_symbol"]
    if estimated_buying_power > quotes[cash_sweep_symbol]["lastPrice"] * 2:
        quantity = int(estimated_buying_power // quotes[cash_sweep_symbol]["lastPrice"])
        if quantity > 0:
            execute_fire_forget(cash_sweep_symbol, "BUY_MARKET", quantity)

    if trade_logs:
        trade_message = (
            f"{translator('trade_header')}\n"
            f"📊 {translator('signal_label')}: {plan['sig_display']}\n\n"
            f"{plan['dashboard']}\n"
            f"{plan['separator']}\n"
            + "\n".join(trade_logs)
        )
        send_tg_message(trade_message)
    else:
        holdings_lines = [
            "  ".join(
                f"{symbol}: ${market_values[symbol]:,.2f}"
                for symbol in row
            )
            for row in plan["portfolio_rows"]
        ]
        no_trade_message = (
            f"{translator('heartbeat_header')}\n"
            f"💰 {translator('equity')}: ${plan['total_equity']:,.2f}\n"
            f"{plan['separator']}\n"
            + "\n".join(holdings_lines) + "\n"
            f"{plan['separator']}\n"
            f"🎯 {translator('signal_label')}: {plan['sig_display']}\n"
            f"QQQ: {plan['qqq_p']:.2f} | MA200: {plan['ma200']:.2f} | Exit: {plan['exit_line']:.2f}\n"
            f"{plan['separator']}\n"
            f"{translator('no_trades')}"
        )
        print(no_trade_message, flush=True)
        send_tg_message(no_trade_message)
