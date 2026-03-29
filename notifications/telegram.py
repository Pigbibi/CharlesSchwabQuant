"""Telegram notification and i18n helpers for CharlesSchwabQuant."""

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
        "signal_label": "信号",
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
    },
    "en": {
        "trade_header": "🔔 【Trade Execution Report】",
        "heartbeat_header": "💓 【Heartbeat】",
        "error_header": "🚨 【Strategy Error】",
        "signal_label": "Signal",
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
