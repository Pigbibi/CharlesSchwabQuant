import os
import traceback
from datetime import datetime, timezone
from flask import Flask
import google.auth

from application.rebalance_service import run_strategy_core as run_rebalance_cycle
from decision_mapper import map_strategy_decision_to_plan
from entrypoints.cloud_run import is_market_open_today
from notifications.telegram import (
    build_sender,
    build_signal_text,
    build_strategy_display_name,
    build_translator,
)
from quant_platform_kit.schwab import (
    fetch_account_snapshot,
    fetch_default_daily_price_history_candles,
    fetch_quotes,
    get_client_from_secret,
    submit_equity_order,
)
from quant_platform_kit.common.runtime_reports import (
    append_runtime_report_error,
    build_runtime_report_base,
    finalize_runtime_report,
    persist_runtime_report,
)
from runtime_config_support import load_platform_runtime_settings
from runtime_logging import RuntimeLogContext, build_run_id, emit_runtime_log
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
SERVICE_NAME = os.getenv("SERVICE_NAME") or os.getenv("K_SERVICE") or "charles-schwab-platform"
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
STRATEGY_DISPLAY_NAME = RUNTIME_SETTINGS.strategy_display_name
NOTIFY_LANG = RUNTIME_SETTINGS.notify_lang
t = build_translator(NOTIFY_LANG)
signal_text = build_signal_text(t)
strategy_display_name = build_strategy_display_name(t)(
    STRATEGY_PROFILE,
    fallback_name=STRATEGY_DISPLAY_NAME,
)


def build_strategy_runtime_overrides(profile: str) -> dict[str, float]:
    if profile == "hybrid_growth_income":
        return {
            "income_threshold_usd": INCOME_THRESHOLD_USD,
            "qqqi_income_ratio": QQQI_INCOME_RATIO,
        }
    return {}


STRATEGY_RUNTIME = load_strategy_runtime(
    STRATEGY_PROFILE,
    runtime_overrides=build_strategy_runtime_overrides(STRATEGY_PROFILE),
)
STRATEGY_RUNTIME_CONFIG = dict(STRATEGY_RUNTIME.merged_runtime_config)
MANAGED_SYMBOLS = STRATEGY_RUNTIME.managed_symbols
BENCHMARK_SYMBOL = STRATEGY_RUNTIME.benchmark_symbol
AVAILABLE_INPUTS = frozenset(STRATEGY_RUNTIME.runtime_adapter.available_inputs)
RUNTIME_LOG_CONTEXT = RuntimeLogContext(
    platform="charles_schwab",
    deploy_target="cloud_run",
    service_name=SERVICE_NAME,
    strategy_profile=STRATEGY_PROFILE,
    project_id=PROJECT_ID,
    extra_fields={
        "strategy_display_name": STRATEGY_DISPLAY_NAME,
        "strategy_display_name_localized": strategy_display_name,
    },
)


def validate_config():
    """Fail loudly at startup if required config is missing or invalid."""
    missing = [v for v in ("SCHWAB_API_KEY", "SCHWAB_APP_SECRET") if not os.getenv(v)]
    if missing:
        raise EnvironmentError(f"Missing required env vars: {', '.join(missing)}")
    if not (0.0 <= QQQI_INCOME_RATIO <= 1.0):
        raise ValueError(f"QQQI_INCOME_RATIO must be in [0,1], got {QQQI_INCOME_RATIO}")


validate_config()


send_tg_message = build_sender(TG_TOKEN, TG_CHAT_ID)


def log_runtime_event(log_context, event, **fields):
    return emit_runtime_log(
        log_context,
        event,
        printer=lambda line: print(line, flush=True),
        **fields,
    )


def build_execution_report(log_context):
    return build_runtime_report_base(
        platform=log_context.platform,
        deploy_target=log_context.deploy_target,
        service_name=log_context.service_name,
        strategy_profile=STRATEGY_PROFILE,
        strategy_domain=RUNTIME_SETTINGS.strategy_domain,
        run_id=log_context.run_id,
        run_source="cloud_run",
        dry_run=RUNTIME_SETTINGS.dry_run_only,
        started_at=datetime.now(timezone.utc),
        summary={
            "managed_symbols": list(MANAGED_SYMBOLS),
            "benchmark_symbol": BENCHMARK_SYMBOL,
            "strategy_display_name": STRATEGY_DISPLAY_NAME,
            "strategy_display_name_localized": strategy_display_name,
        },
    )


def persist_execution_report(report):
    persisted = persist_runtime_report(
        report,
        base_dir=os.getenv("EXECUTION_REPORT_OUTPUT_DIR"),
        gcs_prefix_uri=os.getenv("EXECUTION_REPORT_GCS_URI"),
        gcp_project_id=PROJECT_ID,
    )
    return persisted.gcs_uri or persisted.local_path


# ---------------------------------------------------------------------------
# Strategy execution
# ---------------------------------------------------------------------------
def fetch_reference_history(client):
    if "qqq_history" in AVAILABLE_INPUTS:
        return fetch_default_daily_price_history_candles(client, BENCHMARK_SYMBOL)
    if "indicators" in AVAILABLE_INPUTS:
        return build_semiconductor_indicators(
            client,
            trend_window=int(STRATEGY_RUNTIME_CONFIG.get("trend_ma_window", 150)),
        )
    raise ValueError(f"Unsupported Schwab runtime inputs for {STRATEGY_PROFILE}: {sorted(AVAILABLE_INPUTS)}")


def fetch_managed_snapshot(client):
    return fetch_account_snapshot(client, strategy_symbols=list(MANAGED_SYMBOLS))


def fetch_managed_quotes(client):
    return fetch_quotes(client, list(MANAGED_SYMBOLS))


def build_semiconductor_indicators(client, *, trend_window: int) -> dict[str, dict[str, float]]:
    soxl_history = fetch_default_daily_price_history_candles(client, "SOXL")
    soxx_history = fetch_default_daily_price_history_candles(client, "SOXX")
    if len(soxl_history) < trend_window:
        raise RuntimeError(
            f"SOXL history has {len(soxl_history)} candles; need at least {trend_window}"
        )
    if not soxx_history:
        raise RuntimeError("SOXX history response is empty")

    soxl_closes = [float(candle["close"]) for candle in soxl_history[-trend_window:]]
    soxx_close = float(soxx_history[-1]["close"])
    return {
        "soxl": {
            "price": soxl_closes[-1],
            "ma_trend": sum(soxl_closes) / trend_window,
        },
        "soxx": {
            "price": soxx_close,
        },
    }


def build_account_state_from_snapshot(snapshot) -> dict[str, object]:
    available_cash = float(
        snapshot.metadata.get("cash_available_for_trading", snapshot.buying_power or 0.0) or 0.0
    )
    market_values = {symbol: 0.0 for symbol in MANAGED_SYMBOLS}
    quantities = {symbol: 0 for symbol in MANAGED_SYMBOLS}
    sellable_quantities = {symbol: 0 for symbol in MANAGED_SYMBOLS}
    for position in snapshot.positions:
        if position.symbol not in market_values:
            continue
        market_values[position.symbol] = float(position.market_value)
        quantity = int(position.quantity)
        quantities[position.symbol] = quantity
        sellable_quantities[position.symbol] = quantity
    return {
        "available_cash": available_cash,
        "market_values": market_values,
        "quantities": quantities,
        "sellable_quantities": sellable_quantities,
        "total_strategy_equity": float(snapshot.total_equity),
    }


def resolve_rebalance_plan(*, qqq_history, snapshot):
    evaluation_inputs = {
        "signal_text_fn": signal_text,
        "translator": t,
    }
    if "qqq_history" in AVAILABLE_INPUTS:
        evaluation_inputs["qqq_history"] = qqq_history
    if "indicators" in AVAILABLE_INPUTS:
        evaluation_inputs["indicators"] = qqq_history
    if "snapshot" in AVAILABLE_INPUTS:
        evaluation_inputs["snapshot"] = snapshot
    if "account_state" in AVAILABLE_INPUTS:
        evaluation_inputs["account_state"] = build_account_state_from_snapshot(snapshot)
    evaluation = STRATEGY_RUNTIME.evaluate(**evaluation_inputs)
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
        strategy_display_name=strategy_display_name,
        limit_buy_premium=LIMIT_BUY_PREMIUM,
        sell_settle_delay_sec=SELL_SETTLE_DELAY_SEC,
        dry_run_only=RUNTIME_SETTINGS.dry_run_only,
    )


@app.route("/", methods=["POST", "GET"])
def handle_schwab():
    log_context = RUNTIME_LOG_CONTEXT.with_run(build_run_id())
    report = build_execution_report(log_context)
    try:
        log_runtime_event(
            log_context,
            "strategy_cycle_received",
            message="Received strategy execution request",
        )
        c = get_client_from_secret(PROJECT_ID, SECRET_ID, APP_KEY, APP_SECRET, token_path=TOKEN_PATH)
        if not is_market_open_today():
            log_runtime_event(
                log_context,
                "market_closed",
                message="Market closed; skip strategy execution",
            )
            finalize_runtime_report(
                report,
                status="skipped",
                diagnostics={"skip_reason": "market_closed"},
            )
            return "Market Closed", 200
        log_runtime_event(
            log_context,
            "strategy_cycle_started",
            message="Starting strategy execution",
        )
        run_strategy_core(c, None)
        finalize_runtime_report(report, status="ok")
        log_runtime_event(
            log_context,
            "strategy_cycle_completed",
            message="Strategy execution completed",
        )
        return "OK", 200
    except Exception as exc:
        append_runtime_report_error(
            report,
            stage="strategy_cycle",
            message=str(exc),
            error_type=type(exc).__name__,
        )
        finalize_runtime_report(report, status="error")
        log_runtime_event(
            log_context,
            "strategy_cycle_failed",
            message="Strategy execution failed",
            severity="ERROR",
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        send_tg_message(f"{t('error_header')}\n{traceback.format_exc()}")
        return "Error", 500
    finally:
        try:
            report_path = persist_execution_report(report)
            print(f"execution_report {report_path}", flush=True)
        except Exception as persist_exc:
            print(f"failed to persist execution report: {persist_exc}", flush=True)


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
