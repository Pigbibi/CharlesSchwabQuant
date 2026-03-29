import os
import traceback
from flask import Flask
import google.auth

from application.rebalance_service import run_strategy_core as run_rebalance_cycle
from entrypoints.cloud_run import is_market_open_today
from notifications.telegram import build_sender, build_signal_text, build_translator
from quant_platform_kit.schwab import (
    fetch_account_snapshot,
    fetch_default_daily_price_history_candles,
    fetch_quotes,
    get_client_from_secret,
    submit_equity_order,
)
from runtime_config_support import load_platform_runtime_settings
from strategy.allocation import (
    get_hybrid_allocation as strategy_get_hybrid_allocation,
    get_income_ratio as strategy_get_income_ratio,
)

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
TG_CHAT_ID = os.getenv("GLOBAL_TELEGRAM_CHAT_ID")
SECRET_ID = "schwab_token"
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
# Runtime / i18n
# ---------------------------------------------------------------------------
RUNTIME_SETTINGS = load_platform_runtime_settings()
STRATEGY_PROFILE = RUNTIME_SETTINGS.strategy_profile
NOTIFY_LANG = RUNTIME_SETTINGS.notify_lang
t = build_translator(NOTIFY_LANG)
signal_text = build_signal_text(t)


def validate_config():
    """Fail loudly at startup if required config is missing or invalid."""
    missing = [v for v in ("SCHWAB_API_KEY", "SCHWAB_APP_SECRET") if not os.getenv(v)]
    if missing:
        raise EnvironmentError(f"Missing required env vars: {', '.join(missing)}")
    if not (0.0 <= QQQI_INCOME_RATIO <= 1.0):
        raise ValueError(f"QQQI_INCOME_RATIO must be in [0,1], got {QQQI_INCOME_RATIO}")


validate_config()


send_tg_message = build_sender(TG_TOKEN, TG_CHAT_ID)


def get_hybrid_allocation(total_equity_usd, qqq_p, stop_line):
    return strategy_get_hybrid_allocation(
        total_equity_usd,
        qqq_p,
        stop_line,
        alloc_tier1_breakpoints=ALLOC_TIER1_BREAKPOINTS,
        alloc_tier1_values=ALLOC_TIER1_VALUES,
        alloc_tier2_breakpoints=ALLOC_TIER2_BREAKPOINTS,
        alloc_tier2_values=ALLOC_TIER2_VALUES,
        risk_leverage_factor=RISK_LEVERAGE_FACTOR,
        risk_agg_cap=RISK_AGG_CAP,
        risk_numerator=RISK_NUMERATOR,
    )


def get_income_ratio(total_equity_usd: float) -> float:
    return strategy_get_income_ratio(
        total_equity_usd,
        income_threshold_usd=INCOME_THRESHOLD_USD,
    )


# ---------------------------------------------------------------------------
# Strategy execution
# ---------------------------------------------------------------------------
def run_strategy_core(c, now_ny):
    return run_rebalance_cycle(
        c,
        now_ny,
        fetch_default_daily_price_history_candles=fetch_default_daily_price_history_candles,
        fetch_account_snapshot=fetch_account_snapshot,
        fetch_quotes=fetch_quotes,
        submit_equity_order=submit_equity_order,
        send_tg_message=send_tg_message,
        signal_text=signal_text,
        translator=t,
        income_threshold_usd=INCOME_THRESHOLD_USD,
        qqqi_income_ratio=QQQI_INCOME_RATIO,
        cash_reserve_ratio=CASH_RESERVE_RATIO,
        rebalance_threshold_ratio=REBALANCE_THRESHOLD_RATIO,
        limit_buy_premium=LIMIT_BUY_PREMIUM,
        sell_settle_delay_sec=SELL_SETTLE_DELAY_SEC,
        alloc_tier1_breakpoints=ALLOC_TIER1_BREAKPOINTS,
        alloc_tier1_values=ALLOC_TIER1_VALUES,
        alloc_tier2_breakpoints=ALLOC_TIER2_BREAKPOINTS,
        alloc_tier2_values=ALLOC_TIER2_VALUES,
        risk_leverage_factor=RISK_LEVERAGE_FACTOR,
        risk_agg_cap=RISK_AGG_CAP,
        risk_numerator=RISK_NUMERATOR,
        atr_exit_scale=ATR_EXIT_SCALE,
        atr_entry_scale=ATR_ENTRY_SCALE,
        exit_line_floor=EXIT_LINE_FLOOR,
        exit_line_cap=EXIT_LINE_CAP,
        entry_line_floor=ENTRY_LINE_FLOOR,
        entry_line_cap=ENTRY_LINE_CAP,
    )


@app.route("/", methods=["POST", "GET"])
def handle_schwab():
    try:
        c = get_client_from_secret(PROJECT_ID, SECRET_ID, APP_KEY, APP_SECRET, token_path=TOKEN_PATH)
        if not is_market_open_today():
            return "Market Closed", 200
        run_strategy_core(c, None)
        return "OK", 200
    except Exception:
        send_tg_message(f"{t('error_header')}\n{traceback.format_exc()}")
        return "Error", 500


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
