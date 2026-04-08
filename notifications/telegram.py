"""Telegram notification and i18n helpers for CharlesSchwabPlatform."""

from __future__ import annotations

import requests


SIGNAL_ICONS = {
    "hold": "💎",
    "entry": "🚀",
    "reduce": "⚠️",
    "exit": "🔴",
    "idle": "💤",
}


I18N = {
    "zh": {
        "trade_header": "🔔 【交易执行报告】",
        "heartbeat_header": "💓 【心跳检测】",
        "error_header": "🚨 【策略异常】",
        "strategy_label": "🧭 策略: {name}",
        "signal_label": "信号",
        "dry_run_banner": "🧪 仅 dry-run，本轮不提交真实订单",
        "dashboard_label": "📊 资产看板",
        "equity": "净值",
        "buying_power": "购买力",
        "no_trades": "✅ 无需调仓",
        "separator": "━━━━━━━━━━━━━━━━━━",
        "signal_hold": "趋势持有",
        "signal_entry": "入场信号",
        "signal_reduce": "减仓信号",
        "signal_exit": "离场信号",
        "signal_idle": "等待信号",
        "signal_risk_on": "SOXL 站上 {window} 日均线，持有 SOXL，交易层风险仓位 {ratio}",
        "signal_delever": "SOXL 跌破 {window} 日均线，切换至 SOXX，交易层风险仓位 {ratio}",
        "limit_buy": "限价买入",
        "market_buy": "市价买入",
        "market_sell": "市价卖出",
        "shares": "股",
        "submitted": "已下发",
        "failed": "失败",
        "exception": "异常",
        "buy_label": "买入",
        "limit_buy_cmd": "限价买入指令",
        "market_buy_cmd": "市价买入指令",
        "market_sell_cmd": "市价卖出指令",
        "strategy_name_hybrid_growth_income": "QQQ/TQQQ 增长收益",
        "strategy_name_semiconductor_rotation_income": "芯片趋势收益",
        "strategy_name_global_etf_rotation": "全球 ETF 轮动防御",
        "strategy_name_russell_1000_multi_factor_defensive": "罗素1000多因子防御",
        "strategy_name_tech_pullback_cash_buffer": "科技回撤现金缓冲",
    },
    "en": {
        "trade_header": "🔔 【Trade Execution Report】",
        "heartbeat_header": "💓 【Heartbeat】",
        "error_header": "🚨 【Strategy Error】",
        "strategy_label": "🧭 Strategy: {name}",
        "signal_label": "Signal",
        "dry_run_banner": "🧪 Dry run only; no live orders submitted",
        "dashboard_label": "📊 Dashboard",
        "equity": "Equity",
        "buying_power": "Buying Power",
        "no_trades": "✅ No rebalance needed",
        "separator": "━━━━━━━━━━━━━━━━━━",
        "signal_hold": "Trend Hold",
        "signal_entry": "Entry Signal",
        "signal_reduce": "Reduce Signal",
        "signal_exit": "Exit Signal",
        "signal_idle": "Idle",
        "signal_risk_on": "SOXL above {window}d MA, hold SOXL, risk {ratio}",
        "signal_delever": "SOXL below {window}d MA, switch to SOXX, risk {ratio}",
        "limit_buy": "Limit Buy",
        "market_buy": "Market Buy",
        "market_sell": "Market Sell",
        "shares": " shares",
        "submitted": "submitted",
        "failed": "failed",
        "exception": "error",
        "buy_label": "Buy",
        "limit_buy_cmd": "Limit Buy",
        "market_buy_cmd": "Market Buy",
        "market_sell_cmd": "Market Sell",
        "strategy_name_hybrid_growth_income": "QQQ/TQQQ Growth Income",
        "strategy_name_semiconductor_rotation_income": "Semiconductor Trend Income",
        "strategy_name_global_etf_rotation": "Global ETF Rotation Defense",
        "strategy_name_russell_1000_multi_factor_defensive": "Russell 1000 Multi-Factor Defensive",
        "strategy_name_tech_pullback_cash_buffer": "Tech Pullback Cash Buffer",
    },
}


def build_translator(lang):
    def translate(key, **kwargs):
        active_lang = lang if lang in I18N else "en"
        template = I18N[active_lang].get(key, key)
        return template.format(**kwargs) if kwargs else template

    return translate


def build_signal_text(translate_fn):
    def signal_text(icon_key):
        emoji = SIGNAL_ICONS.get(icon_key, "❓")
        name = translate_fn(f"signal_{icon_key}")
        return f"{emoji} {name}"

    return signal_text


def build_strategy_display_name(translate_fn):
    def strategy_display_name(profile: str, *, fallback_name: str | None = None) -> str:
        key = f"strategy_name_{str(profile or '').strip()}"
        translated = translate_fn(key)
        if translated != key:
            return translated
        fallback = str(fallback_name or "").strip()
        if fallback:
            return fallback
        return str(profile or "").strip()

    return strategy_display_name


def build_sender(token, chat_id, *, requests_module=requests):
    def send_tg_message(message):
        if not token or not chat_id:
            return
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        try:
            requests_module.post(url, json={"chat_id": chat_id, "text": message}, timeout=15)
        except Exception as exc:
            print(f"Telegram send failed: {exc}", flush=True)

    return send_tg_message
