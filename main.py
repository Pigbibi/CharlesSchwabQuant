import os
import traceback
from flask import Flask
import google.auth

from application.rebalance_service import run_strategy_core as run_rebalance_cycle
from decision_mapper import map_strategy_decision_to_plan
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
from strategy_runtime import load_strategy_runtime

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

INCOME_THRESHOLD_USD = float(os.getenv("INCOME_THRESHOLD_USD", "100000"))
QQQI_INCOME_RATIO = float(os.getenv("QQQI_INCOME_RATIO", "0.5"))

# Order pricing: limit buy premium above ask price
LIMIT_BUY_PREMIUM = 1.005

# Sell-to-buy delay: seconds to wait after sells before buying
SELL_SETTLE_DELAY_SEC = 3

# ---------------------------------------------------------------------------
# Runtime / i18n
# ---------------------------------------------------------------------------
RUNTIME_SETTINGS = load_platform_runtime_settings()
STRATEGY_PROFILE = RUNTIME_SETTINGS.strategy_profile
NOTIFY_LANG = RUNTIME_SETTINGS.notify_lang
t = build_translator(NOTIFY_LANG)
signal_text = build_signal_text(t)
STRATEGY_RUNTIME = load_strategy_runtime(
    STRATEGY_PROFILE,
    runtime_overrides={
        "income_threshold_usd": INCOME_THRESHOLD_USD,
        "qqqi_income_ratio": QQQI_INCOME_RATIO,
    },
)
STRATEGY_RUNTIME_CONFIG = dict(STRATEGY_RUNTIME.merged_runtime_config)
MANAGED_SYMBOLS = STRATEGY_RUNTIME.managed_symbols
BENCHMARK_SYMBOL = STRATEGY_RUNTIME.benchmark_symbol


def validate_config():
    """Fail loudly at startup if required config is missing or invalid."""
    missing = [v for v in ("SCHWAB_API_KEY", "SCHWAB_APP_SECRET") if not os.getenv(v)]
    if missing:
        raise EnvironmentError(f"Missing required env vars: {', '.join(missing)}")
    if not (0.0 <= QQQI_INCOME_RATIO <= 1.0):
        raise ValueError(f"QQQI_INCOME_RATIO must be in [0,1], got {QQQI_INCOME_RATIO}")


validate_config()


send_tg_message = build_sender(TG_TOKEN, TG_CHAT_ID)


# ---------------------------------------------------------------------------
# Strategy execution
# ---------------------------------------------------------------------------
def fetch_reference_history(client):
    return fetch_default_daily_price_history_candles(client, BENCHMARK_SYMBOL)


def fetch_managed_snapshot(client):
    return fetch_account_snapshot(client, strategy_symbols=list(MANAGED_SYMBOLS))


def fetch_managed_quotes(client):
    return fetch_quotes(client, list(MANAGED_SYMBOLS))


def resolve_rebalance_plan(*, qqq_history, snapshot):
    evaluation = STRATEGY_RUNTIME.evaluate(
        qqq_history=qqq_history,
        snapshot=snapshot,
        signal_text_fn=signal_text,
        translator=t,
    )
    return map_strategy_decision_to_plan(
        evaluation.decision,
        snapshot=snapshot,
        strategy_profile=STRATEGY_PROFILE,
    )


def run_strategy_core(c, now_ny):
    return run_rebalance_cycle(
        c,
        now_ny,
        fetch_reference_history=fetch_reference_history,
        fetch_managed_snapshot=fetch_managed_snapshot,
        fetch_managed_quotes=fetch_managed_quotes,
        resolve_rebalance_plan=resolve_rebalance_plan,
        submit_equity_order=submit_equity_order,
        send_tg_message=send_tg_message,
        translator=t,
        limit_buy_premium=LIMIT_BUY_PREMIUM,
        sell_settle_delay_sec=SELL_SETTLE_DELAY_SEC,
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
