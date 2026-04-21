import os
import time
import traceback

from flask import Flask
import google.auth

from application.runtime_broker_adapters import build_runtime_broker_adapters
from application.runtime_composer import build_runtime_composer
from application.runtime_strategy_adapters import build_runtime_strategy_adapters
from application.rebalance_service import run_strategy_core as run_rebalance_cycle
from decision_mapper import map_strategy_decision_to_plan
from entrypoints.cloud_run import is_market_open_today
from notifications.telegram import (
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
from quant_platform_kit.common.strategy_plugins import (
    build_strategy_plugin_report_payload,
    load_configured_strategy_plugin_signals,
    parse_strategy_plugin_mounts,
)
from quant_platform_kit.strategy_contracts import build_strategy_evaluation_inputs
from runtime_config_support import load_platform_runtime_settings
from runtime_logging import build_run_id, emit_runtime_log
from strategy_runtime import load_strategy_runtime

app = Flask(__name__)


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
TOKEN_PATH = "/tmp/token.json"


def _optional_float_env(name: str) -> float | None:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return None
    return float(value)


def _optional_symbol_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return None
    return value.strip().upper()


INCOME_THRESHOLD_USD = _optional_float_env("INCOME_THRESHOLD_USD")
QQQI_INCOME_RATIO = _optional_float_env("QQQI_INCOME_RATIO")
DUAL_DRIVE_UNLEVERED_SYMBOL = _optional_symbol_env("DUAL_DRIVE_UNLEVERED_SYMBOL")

LIMIT_BUY_PREMIUM = 1.005
SELL_SETTLE_DELAY_SEC = 3
POST_SELL_REFRESH_ATTEMPTS = 5
POST_SELL_REFRESH_INTERVAL_SEC = 1

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


def build_tqqq_managed_symbols(unlevered_symbol: str) -> tuple[str, ...]:
    symbol = str(unlevered_symbol or "QQQ").strip().upper()
    if not symbol:
        raise ValueError("DUAL_DRIVE_UNLEVERED_SYMBOL must be a non-empty ticker")
    if symbol in {"TQQQ", "BOXX", "SPYI", "QQQI"}:
        raise ValueError("DUAL_DRIVE_UNLEVERED_SYMBOL must not overlap another TQQQ profile sleeve")
    return ("TQQQ", symbol, "BOXX", "SPYI", "QQQI")


def build_strategy_runtime_overrides(profile: str) -> dict[str, object]:
    overrides: dict[str, object] = {}
    if profile == "tqqq_growth_income":
        if INCOME_THRESHOLD_USD is not None:
            overrides["income_threshold_usd"] = INCOME_THRESHOLD_USD
        if QQQI_INCOME_RATIO is not None:
            overrides["qqqi_income_ratio"] = QQQI_INCOME_RATIO
        if DUAL_DRIVE_UNLEVERED_SYMBOL is not None:
            overrides["dual_drive_unlevered_symbol"] = DUAL_DRIVE_UNLEVERED_SYMBOL
            overrides["managed_symbols"] = build_tqqq_managed_symbols(DUAL_DRIVE_UNLEVERED_SYMBOL)
    return overrides


STRATEGY_RUNTIME = load_strategy_runtime(
    STRATEGY_PROFILE,
    runtime_settings=RUNTIME_SETTINGS,
    runtime_overrides=build_strategy_runtime_overrides(STRATEGY_PROFILE),
    logger=lambda message: print(message, flush=True),
)
STRATEGY_RUNTIME_CONFIG = dict(STRATEGY_RUNTIME.merged_runtime_config)
MANAGED_SYMBOLS = STRATEGY_RUNTIME.managed_symbols
BENCHMARK_SYMBOL = STRATEGY_RUNTIME.benchmark_symbol
SIGNAL_EFFECTIVE_AFTER_TRADING_DAYS = getattr(
    getattr(STRATEGY_RUNTIME.runtime_adapter, "runtime_policy", None),
    "signal_effective_after_trading_days",
    None,
)
AVAILABLE_INPUTS = frozenset(STRATEGY_RUNTIME.runtime_adapter.available_inputs)


def validate_config():
    missing = [v for v in ("SCHWAB_API_KEY", "SCHWAB_APP_SECRET") if not os.getenv(v)]
    if missing:
        raise EnvironmentError(f"Missing required env vars: {', '.join(missing)}")
    if QQQI_INCOME_RATIO is not None and not (0.0 <= QQQI_INCOME_RATIO <= 1.0):
        raise ValueError(f"QQQI_INCOME_RATIO must be in [0,1], got {QQQI_INCOME_RATIO}")


validate_config()


def build_broker_adapters():
    return build_runtime_broker_adapters(
        managed_symbols=MANAGED_SYMBOLS,
        fetch_account_snapshot_fn=fetch_account_snapshot,
        fetch_quotes_fn=fetch_quotes,
        fetch_daily_price_history_fn=fetch_default_daily_price_history_candles,
        submit_equity_order_fn=submit_equity_order,
    )


def build_strategy_adapters():
    return build_runtime_strategy_adapters(
        strategy_runtime=STRATEGY_RUNTIME,
        strategy_profile=STRATEGY_PROFILE,
        strategy_runtime_config=STRATEGY_RUNTIME_CONFIG,
        available_inputs=AVAILABLE_INPUTS,
        benchmark_symbol=BENCHMARK_SYMBOL,
        managed_symbols=MANAGED_SYMBOLS,
        signal_text_fn=signal_text,
        translator=t,
        broker_adapters=build_broker_adapters(),
        build_strategy_evaluation_inputs_fn=build_strategy_evaluation_inputs,
        map_strategy_decision_to_plan_fn=map_strategy_decision_to_plan,
        build_strategy_plugin_report_payload_fn=build_strategy_plugin_report_payload,
        load_configured_strategy_plugin_signals_fn=load_configured_strategy_plugin_signals,
        parse_strategy_plugin_mounts_fn=parse_strategy_plugin_mounts,
    )


def build_composer():
    return build_runtime_composer(
        project_id=PROJECT_ID,
        service_name=SERVICE_NAME,
        secret_id=SECRET_ID,
        app_key=APP_KEY,
        app_secret=APP_SECRET,
        token_path=TOKEN_PATH,
        strategy_profile=STRATEGY_PROFILE,
        strategy_domain=RUNTIME_SETTINGS.strategy_domain,
        strategy_display_name=STRATEGY_DISPLAY_NAME,
        strategy_display_name_localized=strategy_display_name,
        notify_lang=NOTIFY_LANG,
        tg_token=TG_TOKEN,
        tg_chat_id=TG_CHAT_ID,
        managed_symbols=MANAGED_SYMBOLS,
        benchmark_symbol=BENCHMARK_SYMBOL,
        signal_effective_after_trading_days=SIGNAL_EFFECTIVE_AFTER_TRADING_DAYS,
        dry_run_only=RUNTIME_SETTINGS.dry_run_only,
        limit_buy_premium=LIMIT_BUY_PREMIUM,
        sell_settle_delay_sec=SELL_SETTLE_DELAY_SEC,
        post_sell_refresh_attempts=POST_SELL_REFRESH_ATTEMPTS,
        post_sell_refresh_interval_sec=POST_SELL_REFRESH_INTERVAL_SEC,
        broker_adapters=build_broker_adapters(),
        strategy_adapters=build_strategy_adapters(),
        client_builder=get_client_from_secret,
        run_id_builder=build_run_id,
        event_logger=emit_runtime_log,
        report_builder=build_runtime_report_base,
        report_persister=persist_runtime_report,
        env_reader=os.getenv,
        sleeper=time.sleep,
        printer=print,
    )


def send_tg_message(message):
    return build_composer().send_tg_message(message)


def publish_notification(*, detailed_text, compact_text):
    build_composer().build_notification_adapters().publish_cycle_notification(
        detailed_text=detailed_text,
        compact_text=compact_text,
    )


def log_runtime_event(log_context, event, **fields):
    return build_composer().build_reporting_adapters().log_event(log_context, event, **fields)


def build_execution_report(log_context):
    return build_composer().build_reporting_adapters().build_report(log_context)


def load_strategy_plugin_signals():
    return build_composer().load_strategy_plugin_signals(
        getattr(RUNTIME_SETTINGS, "strategy_plugin_mounts_json", None)
    )


def attach_strategy_plugin_report(report, *, signals, error: str | None = None):
    build_composer().attach_strategy_plugin_report(
        report,
        signals=signals,
        error=error,
    )


def translate_strategy_plugin_value(category: str, raw_value: str | None) -> str:
    return build_strategy_adapters().translate_strategy_plugin_value(category, raw_value)


def build_strategy_plugin_notification_lines(signals) -> tuple[str, ...]:
    return build_strategy_adapters().build_strategy_plugin_notification_lines(signals)


def persist_execution_report(report):
    return build_composer().build_reporting_adapters().persist_execution_report(report)


def fetch_reference_history(market_data_port):
    return build_strategy_adapters().fetch_reference_history(market_data_port)


def build_price_history(market_data_port, symbol: str):
    return build_broker_adapters().build_price_history(market_data_port, symbol)


def build_market_history_loader(market_data_port):
    return build_broker_adapters().build_market_history_loader(market_data_port)


def fetch_managed_snapshot(client):
    return build_broker_adapters().fetch_managed_snapshot(client)


def build_market_data_port(client):
    return build_broker_adapters().build_market_data_port(client)


def build_semiconductor_indicators(market_data_source, *, trend_window: int) -> dict[str, dict[str, float]]:
    return build_strategy_adapters().build_semiconductor_indicators(
        market_data_source,
        trend_window=trend_window,
    )


def build_account_state_from_snapshot(snapshot) -> dict[str, object]:
    return build_strategy_adapters().build_account_state_from_snapshot(snapshot)


def resolve_rebalance_plan(*, qqq_history, snapshot):
    return build_strategy_adapters().resolve_rebalance_plan(
        qqq_history=qqq_history,
        snapshot=snapshot,
    )


def run_strategy_core(c, now_ny, *, strategy_plugin_signals=()):
    composer = build_composer()
    return run_rebalance_cycle(
        c,
        now_ny,
        runtime=composer.build_rebalance_runtime(c),
        config=composer.build_rebalance_config(strategy_plugin_signals=strategy_plugin_signals),
    )


@app.route("/", methods=["POST", "GET"])
def handle_schwab():
    log_context = build_composer().build_reporting_adapters().build_log_context()
    report = build_execution_report(log_context)
    strategy_plugin_signals, strategy_plugin_error = load_strategy_plugin_signals()
    attach_strategy_plugin_report(
        report,
        signals=strategy_plugin_signals,
        error=strategy_plugin_error,
    )
    try:
        log_runtime_event(
            log_context,
            "strategy_cycle_received",
            message="Received strategy execution request",
        )
        client = build_composer().build_client()
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
        run_strategy_core(client, None, strategy_plugin_signals=strategy_plugin_signals)
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
        error_message = f"{t('error_header')}\n{traceback.format_exc()}"
        publish_notification(detailed_text=error_message, compact_text=error_message)
        return "Error", 500
    finally:
        try:
            report_path = persist_execution_report(report)
            print(f"execution_report {report_path}", flush=True)
        except Exception as persist_exc:
            print(f"failed to persist execution report: {persist_exc}", flush=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
