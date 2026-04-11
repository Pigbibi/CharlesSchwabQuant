"""Application orchestration for CharlesSchwabPlatform."""

from __future__ import annotations

import time

from quant_platform_kit.common.models import OrderIntent

_ZH_REASON_REPLACEMENTS = (
    ("feature snapshot guard blocked execution", "特征快照校验阻止执行"),
    ("feature snapshot required", "需要特征快照"),
    ("feature snapshot compute failed", "特征快照计算失败"),
    ("feature_snapshot_download_failed", "特征快照下载失败"),
    ("feature_snapshot_compute_failed", "特征快照计算失败"),
    ("feature_snapshot_path_missing", "缺少特征快照路径"),
    ("feature_snapshot_missing", "特征快照不存在"),
    ("feature_snapshot_stale", "特征快照过旧"),
    ("feature_snapshot_manifest_missing", "缺少快照清单"),
    ("feature_snapshot_profile_mismatch", "快照策略名不匹配"),
    ("feature_snapshot_config_name_mismatch", "快照配置名不匹配"),
    ("feature_snapshot_config_path_mismatch", "快照配置路径不匹配"),
    ("feature_snapshot_contract_version_mismatch", "快照契约版本不匹配"),
    ("regime=hard_defense", "市场阶段=强防御"),
    ("regime=soft_defense", "市场阶段=软防御"),
    ("regime=risk_on", "市场阶段=进攻"),
    ("benchmark_trend=down", "基准趋势=向下"),
    ("benchmark_trend=up", "基准趋势=向上"),
    ("benchmark=down", "基准趋势=向下"),
    ("benchmark=up", "基准趋势=向上"),
    ("breadth=", "市场宽度="),
    ("target_stock=", "目标股票仓位="),
    ("realized_stock=", "实际股票仓位="),
    ("stock_exposure=", "股票目标仓位="),
    ("safe_haven=", "避险仓位="),
    ("selected=", "入选标的数="),
    ("top=", "前排标的="),
    ("no_selection", "无入选标的"),
    ("outside_execution_window", "当前不在执行窗口"),
    ("insufficient_buying_power", "购买力不足"),
    ("missing_price", "缺少报价"),
    ("no_equity", "无净值"),
    ("fail_closed", "关闭执行"),
    ("reason=", "原因="),
)


def _plan_portfolio(plan):
    return dict(plan.get("portfolio") or {})


def _plan_execution(plan):
    return dict(plan.get("execution") or {})


def _plan_allocation(plan):
    return dict(plan.get("allocation") or {})


def _has_benchmark_context(execution):
    return any(
        float(execution.get(key) or 0.0) > 0.0
        for key in ("benchmark_price", "long_trend_value", "exit_line")
    )


def _translator_uses_zh(translator) -> bool:
    sample = str(translator("no_trades"))
    return any("\u4e00" <= ch <= "\u9fff" for ch in sample)


def _localize_notification_text(text, *, translator):
    value = str(text or "").strip()
    if not value or not _translator_uses_zh(translator):
        return value
    localized = value
    for source, target in _ZH_REASON_REPLACEMENTS:
        localized = localized.replace(source, target)
    return localized


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
    strategy_display_name,
    limit_buy_premium,
    sell_settle_delay_sec,
    dry_run_only=False,
):
    del now_ny

    snapshot = fetch_managed_snapshot(client)
    plan = resolve_rebalance_plan(
        qqq_history=fetch_reference_history(client),
        snapshot=snapshot,
    )
    portfolio = _plan_portfolio(plan)
    execution = _plan_execution(plan)
    allocation = _plan_allocation(plan)
    if allocation.get("target_mode") != "value":
        raise ValueError("CharlesSchwabPlatform requires allocation.target_mode=value")
    strategy_symbols = tuple(allocation["strategy_symbols"])

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

            report = submit_equity_order(client, plan["account_hash"], order_intent)
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
            send_tg_message(message)
            return False
        except Exception as exc:
            message = f"🚨 {symbol} {translator('buy_label')} {quantity}{translator('shares')} {translator('exception')}: {exc}"
            trade_logs.append(message)
            send_tg_message(message)
            return False

    market_values = dict(portfolio["market_values"])
    target_values = dict(allocation["targets"])
    threshold = float(execution["trade_threshold_value"])
    sell_order_symbols = tuple(
        allocation.get("risk_symbols", ())
        + allocation.get("income_symbols", ())
        + allocation.get("safe_haven_symbols", ())
    )
    sell_executed = False
    for symbol in sell_order_symbols:
        current = market_values[symbol]
        target = target_values[symbol]
        if current > (target + threshold):
            quantity = int((current - target) // quotes[symbol]["lastPrice"])
            execute_fire_forget(symbol, "SELL", quantity)
            sell_executed = True

    if sell_executed:
        time.sleep(sell_settle_delay_sec)

    liquid_cash = float(portfolio["liquid_cash"])
    reserved_cash = float(execution["reserved_cash"])
    estimated_buying_power = max(0, liquid_cash - reserved_cash)
    buy_order_symbols = tuple(
        allocation.get("income_symbols", ()) + allocation.get("risk_symbols", ())
    )
    for symbol in buy_order_symbols:
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

    cash_sweep_symbol = str(portfolio["cash_sweep_symbol"])
    if estimated_buying_power > quotes[cash_sweep_symbol]["lastPrice"] * 2:
        quantity = int(estimated_buying_power // quotes[cash_sweep_symbol]["lastPrice"])
        if quantity > 0:
            execute_fire_forget(cash_sweep_symbol, "BUY_MARKET", quantity)

    signal_display = _localize_notification_text(execution["signal_display"], translator=translator)
    status_display = _localize_notification_text(execution.get("status_display"), translator=translator)
    dashboard_text = str(execution["dashboard_text"])
    separator = str(execution["separator"])
    total_equity = float(portfolio["total_equity"])
    portfolio_rows = tuple(portfolio["portfolio_rows"])
    benchmark_symbol = str(execution["benchmark_symbol"])
    benchmark_price = float(execution["benchmark_price"])
    long_trend_value = float(execution["long_trend_value"])
    exit_line = float(execution["exit_line"])
    status_line = f"📊 {status_display}\n" if status_display else ""
    dashboard_block = f"{dashboard_text}\n{separator}\n" if dashboard_text else ""
    benchmark_line = ""
    if _has_benchmark_context(execution):
        benchmark_line = f"{benchmark_symbol}: {benchmark_price:.2f} | MA200: {long_trend_value:.2f} | Exit: {exit_line:.2f}\n"

    if trade_logs:
        dry_run_line = f"{translator('dry_run_banner')}\n" if dry_run_only else ""
        trade_message = (
            f"{translator('trade_header')}\n"
            f"{translator('strategy_label', name=strategy_display_name)}\n"
            f"{dry_run_line}"
            f"{status_line}"
            f"📊 {translator('signal_label')}: {signal_display}\n\n"
            f"{dashboard_block}"
            + "\n".join(trade_logs)
        )
        send_tg_message(trade_message)
    else:
        holdings_lines = [
            "  ".join(
                f"{symbol}: ${market_values[symbol]:,.2f}"
                for symbol in row
            )
            for row in portfolio_rows
        ]
        no_trade_message = (
            f"{translator('heartbeat_header')}\n"
            f"{translator('strategy_label', name=strategy_display_name)}\n"
            f"💰 {translator('equity')}: ${total_equity:,.2f}\n"
            f"{separator}\n"
            + "\n".join(holdings_lines) + "\n"
            f"{separator}\n"
            f"{status_line}"
            f"🎯 {translator('signal_label')}: {signal_display}\n"
            f"{benchmark_line}"
            f"{separator}\n"
            f"{translator('no_trades')}"
        )
        print(no_trade_message, flush=True)
        send_tg_message(no_trade_message)
