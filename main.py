import os
import stat
import time
import traceback
import requests
import json
import numpy as np
import pandas as pd
import pytz
import pandas_market_calendars as mcal
from datetime import datetime
from flask import Flask
import google.auth

from schwab import auth, client
from schwab.orders.equities import equity_buy_market, equity_sell_market, equity_buy_limit

try:
    import google.cloud.secretmanager_v1 as secret_manager
except ImportError:
    from google.cloud import secret_manager

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
def get_project_id():
    try:
        _, project_id = google.auth.default()
        return project_id if project_id else os.getenv("GOOGLE_CLOUD_PROJECT")
    except Exception:
        return os.getenv("GOOGLE_CLOUD_PROJECT")

PROJECT_ID = get_project_id()
APP_KEY = os.getenv("SCHWAB_API_KEY")
APP_SECRET = os.getenv("SCHWAB_APP_SECRET")
TG_TOKEN = os.getenv("TELEGRAM_TOKEN")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SECRET_ID = "SCHWAB_TOKENS"
TOKEN_PATH = '/tmp/token.json'

CASH_RESERVE_RATIO = 0.05
INCOME_THRESHOLD_USD = float(os.getenv("INCOME_THRESHOLD_USD", "100000"))
QQQI_INCOME_RATIO = float(os.getenv("QQQI_INCOME_RATIO", "0.5"))

# Rebalance: minimum deviation (fraction of equity) to trigger trades
REBALANCE_THRESHOLD_RATIO = 0.01

# Order pricing: limit buy premium above ask price
LIMIT_BUY_PREMIUM = 1.005

# Sell-to-buy delay: seconds to wait after sells before buying
SELL_SETTLE_DELAY_SEC = 3

# Allocation breakpoints by account size tier
ALLOC_TIER1_BREAKPOINTS = [0, 15000, 30000, 70000]
ALLOC_TIER1_VALUES = [1.0, 0.95, 0.85, 0.70]
ALLOC_TIER2_BREAKPOINTS = [70000, 140000]
ALLOC_TIER2_VALUES = [0.70, 0.50]

# Risk parameters for large accounts (>140k)
RISK_LEVERAGE_FACTOR = 3.0
RISK_NUMERATOR = 0.30
RISK_AGG_CAP = 0.50

# ATR band scaling for entry/exit lines
ATR_EXIT_SCALE = 2.0
ATR_ENTRY_SCALE = 2.5
EXIT_LINE_FLOOR = 0.92
EXIT_LINE_CAP = 0.98
ENTRY_LINE_FLOOR = 1.02
ENTRY_LINE_CAP = 1.08

# ---------------------------------------------------------------------------
# Language / i18n
# ---------------------------------------------------------------------------
NOTIFY_LANG = os.getenv("NOTIFY_LANG", "en")

SIGNAL_ICONS = {
    "hold":   "💎",
    "entry":  "🚀",
    "reduce": "⚠️",
    "exit":   "🔴",
    "idle":   "💤",
}

I18N = {
    "zh": {
        "trade_header":      "🔔 【交易执行报告】",
        "heartbeat_header":  "💓 【心跳检测】",
        "error_header":      "🚨 【策略异常】",
        "signal_label":      "信号",
        "dashboard_label":   "📊 资产看板",
        "equity":            "净值",
        "buying_power":      "购买力",
        "no_trades":         "✅ 无需调仓",
        "separator":         "━━━━━━━━━━━━━━━━━━",
        "signal_hold":       "趋势持有",
        "signal_entry":      "入场信号",
        "signal_reduce":     "减仓信号",
        "signal_exit":       "离场信号",
        "signal_idle":       "等待信号",
        "limit_buy":         "限价买入",
        "market_buy":        "市价买入",
        "market_sell":       "市价卖出",
        "shares":            "股",
        "submitted":         "已下发",
        "failed":            "失败",
        "exception":         "异常",
        "buy_label":         "买入",
        "limit_buy_cmd":     "限价买入指令",
        "market_buy_cmd":    "市价买入指令",
        "market_sell_cmd":   "市价卖出指令",
    },
    "en": {
        "trade_header":      "🔔 【Trade Execution Report】",
        "heartbeat_header":  "💓 【Heartbeat】",
        "error_header":      "🚨 【Strategy Error】",
        "signal_label":      "Signal",
        "dashboard_label":   "📊 Dashboard",
        "equity":            "Equity",
        "buying_power":      "Buying Power",
        "no_trades":         "✅ No rebalance needed",
        "separator":         "━━━━━━━━━━━━━━━━━━",
        "signal_hold":       "Trend Hold",
        "signal_entry":      "Entry Signal",
        "signal_reduce":     "Reduce Signal",
        "signal_exit":       "Exit Signal",
        "signal_idle":       "Idle",
        "limit_buy":         "Limit Buy",
        "market_buy":        "Market Buy",
        "market_sell":       "Market Sell",
        "shares":            " shares",
        "submitted":         "submitted",
        "failed":            "failed",
        "exception":         "error",
        "buy_label":         "Buy",
        "limit_buy_cmd":     "Limit Buy",
        "market_buy_cmd":    "Market Buy",
        "market_sell_cmd":   "Market Sell",
    },
}


def t(key, **kwargs):
    """Return translated string for the current LANG setting."""
    lang = NOTIFY_LANG if NOTIFY_LANG in I18N else "en"
    template = I18N[lang].get(key, key)
    return template.format(**kwargs) if kwargs else template


def signal_text(icon_key):
    """Return the emoji + translated signal name, e.g. '💎 趋势持有'."""
    emoji = SIGNAL_ICONS.get(icon_key, "❓")
    name = t(f"signal_{icon_key}")
    return f"{emoji} {name}"


def validate_config():
    """Fail loudly at startup if required config is missing or invalid."""
    missing = [v for v in ("SCHWAB_API_KEY", "SCHWAB_APP_SECRET") if not os.getenv(v)]
    if missing:
        raise EnvironmentError(f"Missing required env vars: {', '.join(missing)}")
    if not (0.0 <= QQQI_INCOME_RATIO <= 1.0):
        raise ValueError(f"QQQI_INCOME_RATIO must be in [0,1], got {QQQI_INCOME_RATIO}")


validate_config()


def send_tg_message(message):
    if not TG_TOKEN or not TG_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TG_CHAT_ID, "text": message}, timeout=15)
    except Exception as e:
        print(f"Telegram send failed: {e}", flush=True)


# ---------------------------------------------------------------------------
# GCP Secret Manager and Schwab client
# ---------------------------------------------------------------------------
def get_secret_from_gcp():
    client_sm = secret_manager.SecretManagerServiceClient()
    name = f"projects/{PROJECT_ID}/secrets/{SECRET_ID}/versions/latest"
    response = client_sm.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")


def get_schwab_client_init():
    raw_data = get_secret_from_gcp()
    with open(TOKEN_PATH, 'w') as f:
        f.write(raw_data)
    os.chmod(TOKEN_PATH, stat.S_IRUSR | stat.S_IWUSR)  # 0o600: owner read/write only
    return auth.client_from_token_file(TOKEN_PATH, APP_KEY, APP_SECRET)


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------
def check_submission(resp, symbol):
    if resp.status_code in [200, 201]:
        location = resp.headers.get('Location', '')
        order_id = location.split('/')[-1] if location else None
        return True, order_id
    return False, f"{resp.status_code} {resp.text}"


def safe_api_call(response, context="API"):
    if response.status_code not in (200, 201):
        raise Exception(f"{context} failed: {response.status_code} {response.text}")
    try:
        return response.json()
    except json.JSONDecodeError:
        raise Exception(f"{context} invalid JSON: {response.text}")


def get_hybrid_allocation(total_equity_usd, qqq_p, stop_line):
    if total_equity_usd <= ALLOC_TIER2_BREAKPOINTS[0]:
        target_agg = float(np.interp(total_equity_usd, ALLOC_TIER1_BREAKPOINTS, ALLOC_TIER1_VALUES))
    elif total_equity_usd <= ALLOC_TIER2_BREAKPOINTS[1]:
        target_agg = float(np.interp(total_equity_usd, ALLOC_TIER2_BREAKPOINTS, ALLOC_TIER2_VALUES))
    else:
        if qqq_p <= stop_line:
            target_agg = 0.0
        else:
            risk = max(0.01, (qqq_p - stop_line) / qqq_p * RISK_LEVERAGE_FACTOR)
            target_agg = min(RISK_AGG_CAP, RISK_NUMERATOR / risk)
    target_yield = max(0.0, 1.0 - target_agg)
    return target_agg, target_yield


def get_income_ratio(total_equity_usd: float) -> float:
    """
    Income layer target as fraction of total equity. Not used for strategy-layer sizing.
    Below INCOME_THRESHOLD_USD: 0. Between threshold and 2x: linear to 40%. Above 2x: 60% cap.
    """
    if total_equity_usd < INCOME_THRESHOLD_USD:
        return 0.0
    if total_equity_usd <= 2 * INCOME_THRESHOLD_USD:
        return float(np.interp(
            total_equity_usd,
            [INCOME_THRESHOLD_USD, 2 * INCOME_THRESHOLD_USD],
            [0.0, 0.40],
        ))
    return 0.60


# ---------------------------------------------------------------------------
# Strategy execution
# ---------------------------------------------------------------------------
def run_strategy_core(c, now_ny):
    # Fetch QQQ history
    raw_resp_qqq = c.get_price_history('QQQ',
        period_type=client.Client.PriceHistory.PeriodType.YEAR,
        period=client.Client.PriceHistory.Period.TWO_YEARS,
        frequency_type=client.Client.PriceHistory.FrequencyType.DAILY,
        frequency=client.Client.PriceHistory.Frequency.DAILY)
    resp_qqq = safe_api_call(raw_resp_qqq, "QQQ history")
    if 'candles' not in resp_qqq:
        raise Exception(f"QQQ response missing candles: {resp_qqq}")

    df_qqq = pd.DataFrame(resp_qqq['candles'])
    qqq_p = df_qqq['close'].iloc[-1]
    ma200 = df_qqq['close'].rolling(200).mean().iloc[-1]

    tr = pd.concat([
        df_qqq['high'] - df_qqq['low'],
        abs(df_qqq['high'] - df_qqq['close'].shift(1)),
        abs(df_qqq['low'] - df_qqq['close'].shift(1))
    ], axis=1).max(axis=1)
    atr_pct = tr.rolling(14).mean().iloc[-1] / qqq_p
    exit_line = ma200 * max(EXIT_LINE_FLOOR, min(EXIT_LINE_CAP, 1.0 - (atr_pct * ATR_EXIT_SCALE)))
    entry_line = ma200 * max(ENTRY_LINE_FLOOR, min(ENTRY_LINE_CAP, 1.0 + (atr_pct * ATR_ENTRY_SCALE)))

    # Account snapshot (strategy symbols only)
    raw_acct_nums = c.get_account_numbers()
    acct_hash = safe_api_call(raw_acct_nums, "Account numbers")[0]['hashValue']
    strategy_symbols = ["TQQQ", "BOXX", "SPYI", "QQQI"]

    raw_acc_resp = c.get_account(acct_hash, fields=client.Client.Account.Fields.POSITIONS)
    acc_resp = safe_api_call(raw_acc_resp, "Account positions")
    acc = acc_resp['securitiesAccount']
    current_bal = acc.get('currentBalances', {})

    cash_for_equity = float(current_bal.get('cashAvailableForTrading', 0.0))
    raw_withdrawable = float(current_bal.get('cashAvailableForWithdrawal', 0.0))
    real_buying_power = max(0.0, raw_withdrawable)

    mv = {s: 0.0 for s in strategy_symbols}
    qty = {s: 0 for s in strategy_symbols}
    if 'positions' in acc:
        for p in acc['positions']:
            s = p['instrument']['symbol']
            if s in mv:
                mv[s] = float(p['marketValue'])
                qty[s] = int(p['longQuantity'])

    total_equity = cash_for_equity + sum(mv.values())

    # Income layer: target size from total equity only
    income_ratio = get_income_ratio(total_equity)
    target_income_val = total_equity * income_ratio
    target_spyi_val = target_income_val * (1.0 - QQQI_INCOME_RATIO)
    target_qqqi_val = target_income_val * QQQI_INCOME_RATIO

    # Strategy layer: remainder allocated to TQQQ + BOXX
    strategy_equity = max(0.0, total_equity - target_income_val)
    reserved = strategy_equity * CASH_RESERVE_RATIO
    agg_ratio, _ = get_hybrid_allocation(strategy_equity, qqq_p, exit_line)

    # TQQQ signal: staged exit when between MA200 and exit_line, full exit below exit_line
    target_tqqq_ratio, icon, reason = 0.0, "idle", "no signal"
    if qty["TQQQ"] > 0:
        if qqq_p < exit_line:
            target_tqqq_ratio, icon, reason = 0.0, "exit", "below exit line"
        elif qqq_p < ma200:
            target_tqqq_ratio, icon, reason = agg_ratio * 0.33, "reduce", "between MA200 and exit"
        else:
            target_tqqq_ratio, icon, reason = agg_ratio, "hold", "above MA200"
    elif qqq_p > entry_line:
        target_tqqq_ratio, icon, reason = agg_ratio, "entry", "above entry line"

    target_tqqq_val = strategy_equity * target_tqqq_ratio
    target_boxx_val = max(0.0, (strategy_equity - reserved) - target_tqqq_val)
    threshold = total_equity * REBALANCE_THRESHOLD_RATIO

    sig_display = signal_text(icon)
    sep = t("separator")
    dashboard = (
        f"{t('dashboard_label')} | {t('equity')}: ${total_equity:,.2f}\n"
        f"TQQQ: ${mv['TQQQ']:,.2f} | SPYI: ${mv['SPYI']:,.2f} | QQQI: ${mv['QQQI']:,.2f} | BOXX: ${mv['BOXX']:,.2f}\n"
        f"{t('buying_power')}: ${real_buying_power:,.2f} | {t('signal_label')}: {sig_display}\n"
        f"QQQ: {qqq_p:.2f} | MA200: {ma200:.2f} | Exit: {exit_line:.2f}"
    )

    # Quotes and order execution
    raw_quotes = c.get_quotes(strategy_symbols)
    quotes_data = safe_api_call(raw_quotes, "Quotes")
    quotes = {}
    for sym in strategy_symbols:
        if sym not in quotes_data or 'quote' not in quotes_data[sym]:
            raise Exception(f"Missing quote data for {sym}")
        q = quotes_data[sym]['quote']
        if 'lastPrice' not in q or 'askPrice' not in q:
            raise Exception(f"Incomplete quote for {sym}: missing lastPrice or askPrice")
        quotes[sym] = q
    trade_logs = []

    def execute_fire_forget(symbol, action_type, quantity, price=None):
        if quantity <= 0:
            return False
        try:
            p_str = "{:.2f}".format(price) if price else None
            if action_type == 'SELL':
                order = equity_sell_market(symbol, quantity)
            elif action_type == 'BUY_LIMIT':
                order = equity_buy_limit(symbol, quantity, p_str)
            elif action_type == 'BUY_MARKET':
                order = equity_buy_market(symbol, quantity)
            else:
                return False
            resp = c.place_order(acct_hash, order)
            success, info = check_submission(resp, symbol)
            if success:
                if action_type == 'SELL':
                    trade_logs.append(
                        f"✅ 📉 {t('market_sell_cmd')} {symbol}: {quantity}{t('shares')} (ID: {info})"
                    )
                elif action_type == 'BUY_LIMIT':
                    trade_logs.append(
                        f"✅ 💰 {t('limit_buy_cmd')} {symbol} (${p_str}): {quantity}{t('shares')} {t('submitted')} (ID: {info})"
                    )
                elif action_type == 'BUY_MARKET':
                    trade_logs.append(
                        f"✅ 📈 {t('market_buy_cmd')} {symbol}: {quantity}{t('shares')} (ID: {info})"
                    )
                return True
            else:
                if action_type == 'SELL':
                    msg = f"❌ {t('market_sell')} {symbol}: {quantity}{t('shares')} {t('failed')} - {info}"
                elif action_type == 'BUY_LIMIT':
                    msg = f"❌ {t('limit_buy')} {symbol}: {quantity}{t('shares')} {t('failed')} - {info}"
                else:
                    msg = f"❌ {t('market_buy')} {symbol}: {quantity}{t('shares')} {t('failed')} - {info}"
                trade_logs.append(msg)
                send_tg_message(msg)
                return False
        except Exception as e:
            msg = f"🚨 {symbol} {t('buy_label')} {quantity}{t('shares')} {t('exception')}: {e}"
            trade_logs.append(msg)
            send_tg_message(msg)
            return False

    # Sell phase
    sell_executed = False
    if mv["TQQQ"] > (target_tqqq_val + threshold):
        q = int((mv["TQQQ"] - target_tqqq_val) // quotes["TQQQ"]['lastPrice'])
        execute_fire_forget('TQQQ', 'SELL', q)
        sell_executed = True
    if mv["SPYI"] > (target_spyi_val + threshold):
        q = int((mv["SPYI"] - target_spyi_val) // quotes["SPYI"]['lastPrice'])
        execute_fire_forget('SPYI', 'SELL', q)
        sell_executed = True
    if mv["QQQI"] > (target_qqqi_val + threshold):
        q = int((mv["QQQI"] - target_qqqi_val) // quotes["QQQI"]['lastPrice'])
        execute_fire_forget('QQQI', 'SELL', q)
        sell_executed = True
    if mv["BOXX"] > (target_boxx_val + threshold):
        q = int((mv["BOXX"] - target_boxx_val) // quotes["BOXX"]['lastPrice'])
        execute_fire_forget('BOXX', 'SELL', q)
        sell_executed = True

    if sell_executed:
        time.sleep(SELL_SETTLE_DELAY_SEC)

    # Buy phase
    est_buying_power = max(0, real_buying_power - reserved)
    for sym, target_val in [('SPYI', target_spyi_val), ('QQQI', target_qqqi_val), ('TQQQ', target_tqqq_val)]:
        if mv[sym] < (target_val - threshold):
            amt_to_spend = min(target_val - mv[sym], est_buying_power)
            if amt_to_spend > 0:
                ask = quotes[sym]['askPrice']
                q = int(amt_to_spend // ask)
                if q > 0:
                    limit_p = round(ask * LIMIT_BUY_PREMIUM, 2)
                    execute_fire_forget(sym, 'BUY_LIMIT', q, limit_p)
                    est_buying_power -= (q * limit_p)

    if est_buying_power > quotes["BOXX"]['lastPrice'] * 2:
        q = int(est_buying_power // quotes["BOXX"]['lastPrice'])
        if q > 0:
            execute_fire_forget('BOXX', 'BUY_MARKET', q)

    if trade_logs:
        trade_msg = (
            f"{t('trade_header')}\n"
            f"📊 {t('signal_label')}: {sig_display}\n\n"
            f"{dashboard}\n"
            f"{sep}\n"
            + "\n".join(trade_logs)
        )
        send_tg_message(trade_msg)
    else:
        no_trade_msg = (
            f"{t('heartbeat_header')}\n"
            f"💰 {t('equity')}: ${total_equity:,.2f}\n"
            f"{sep}\n"
            f"TQQQ: ${mv['TQQQ']:,.2f}  BOXX: ${mv['BOXX']:,.2f}\n"
            f"QQQI: ${mv['QQQI']:,.2f}  SPYI: ${mv['SPYI']:,.2f}\n"
            f"{sep}\n"
            f"🎯 {t('signal_label')}: {sig_display}\n"
            f"QQQ: {qqq_p:.2f} | MA200: {ma200:.2f} | Exit: {exit_line:.2f}\n"
            f"{sep}\n"
            f"{t('no_trades')}"
        )
        print(no_trade_msg, flush=True)
        send_tg_message(no_trade_msg)


@app.route("/", methods=["POST", "GET"])
def handle_schwab():
    try:
        c = get_schwab_client_init()
        tz_ny = pytz.timezone('America/New_York')
        now_ny = datetime.now(tz_ny)
        nyse = mcal.get_calendar('NASDAQ')
        schedule = nyse.schedule(start_date=now_ny.date(), end_date=now_ny.date())
        if schedule.empty:
            return "Market Closed", 200
        run_strategy_core(c, now_ny)
        return "OK", 200
    except Exception:
        send_tg_message(f"{t('error_header')}\n{traceback.format_exc()}")
        return "Error", 500


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
