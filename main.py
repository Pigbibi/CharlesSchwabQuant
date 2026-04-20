import os
import time
import traceback
from datetime import datetime, timezone
from flask import Flask
import google.auth
import pandas as pd

from application.rebalance_service import run_strategy_core as run_rebalance_cycle
from decision_mapper import map_strategy_decision_to_plan
from entrypoints.cloud_run import is_market_open_today
from notifications.events import NotificationPublisher, RenderedNotification
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
from quant_platform_kit.common.strategy_plugins import (
    build_strategy_plugin_report_payload,
    load_configured_strategy_plugin_signals,
    parse_strategy_plugin_mounts,
)
from quant_platform_kit.strategy_contracts import (
    build_account_state_from_portfolio_snapshot,
    build_strategy_evaluation_inputs,
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

# Order pricing: limit buy premium above ask price
LIMIT_BUY_PREMIUM = 1.005

# Sell-to-buy delay: seconds to wait after sells before buying
SELL_SETTLE_DELAY_SEC = 3
POST_SELL_REFRESH_ATTEMPTS = 5
POST_SELL_REFRESH_INTERVAL_SEC = 1

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
LATEST_PLAN_STRATEGY_SYMBOLS: tuple[str, ...] = ()


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
    if QQQI_INCOME_RATIO is not None and not (0.0 <= QQQI_INCOME_RATIO <= 1.0):
        raise ValueError(f"QQQI_INCOME_RATIO must be in [0,1], got {QQQI_INCOME_RATIO}")


validate_config()


send_tg_message = build_sender(TG_TOKEN, TG_CHAT_ID)


def publish_notification(*, detailed_text, compact_text):
    publisher = NotificationPublisher(
        log_message=lambda message: print(message, flush=True),
        send_message=send_tg_message,
    )
    publisher.publish(
        RenderedNotification(
            detailed_text=detailed_text,
            compact_text=compact_text,
        )
    )


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


def load_strategy_plugin_signals():
    raw_mounts = getattr(RUNTIME_SETTINGS, "strategy_plugin_mounts_json", None)
    if not raw_mounts:
        return (), None
    try:
        mounts = parse_strategy_plugin_mounts(raw_mounts)
        if not mounts:
            return (), None
        return (
            load_configured_strategy_plugin_signals(
                mounts,
                strategy_profile=STRATEGY_PROFILE,
            ),
            None,
        )
    except Exception as exc:
        return (), f"{type(exc).__name__}: {exc}"


def attach_strategy_plugin_report(report, *, signals, error: str | None = None):
    if signals:
        report.setdefault("summary", {}).update(build_strategy_plugin_report_payload(signals))
    if error:
        report.setdefault("diagnostics", {})["strategy_plugin_error"] = error


def translate_strategy_plugin_value(category: str, raw_value: str | None) -> str:
    value = str(raw_value or "").strip() or "unknown"
    key = f"strategy_plugin_{category}_{value}"
    translated = t(key)
    return translated if translated != key else value


def build_strategy_plugin_notification_lines(signals) -> tuple[str, ...]:
    lines = []
    for signal in signals:
        route = signal.canonical_route or "unknown_route"
        action = signal.suggested_action or "unknown_action"
        lines.append(
            t(
                "strategy_plugin_line",
                plugin=translate_strategy_plugin_value("name", signal.plugin),
                mode=translate_strategy_plugin_value("mode", signal.effective_mode),
                route=translate_strategy_plugin_value("route", route),
                action=translate_strategy_plugin_value("action", action),
            )
        )
    return tuple(lines)


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
    if "feature_snapshot" in AVAILABLE_INPUTS and not (
        {"market_history", "benchmark_history", "qqq_history", "derived_indicators", "indicators"}
        & AVAILABLE_INPUTS
    ):
        return {}
    if "market_history" in AVAILABLE_INPUTS:
        market_inputs = {"market_history": build_market_history_loader(client)}
        if "benchmark_history" in AVAILABLE_INPUTS:
            market_inputs["benchmark_history"] = fetch_default_daily_price_history_candles(
                client,
                BENCHMARK_SYMBOL,
            )
        if "qqq_history" in AVAILABLE_INPUTS:
            market_inputs["qqq_history"] = fetch_default_daily_price_history_candles(
                client,
                BENCHMARK_SYMBOL,
            )
        return market_inputs
    if "benchmark_history" in AVAILABLE_INPUTS or "qqq_history" in AVAILABLE_INPUTS:
        return fetch_default_daily_price_history_candles(client, BENCHMARK_SYMBOL)
    if "derived_indicators" in AVAILABLE_INPUTS or "indicators" in AVAILABLE_INPUTS:
        return build_semiconductor_indicators(
            client,
            trend_window=int(STRATEGY_RUNTIME_CONFIG.get("trend_ma_window", 150)),
        )
    raise ValueError(f"Unsupported Schwab runtime inputs for {STRATEGY_PROFILE}: {sorted(AVAILABLE_INPUTS)}")


def build_market_history_loader(client):
    def load_market_history(_broker_client, symbol, *_args, **_kwargs):
        candles = fetch_default_daily_price_history_candles(client, str(symbol).strip().upper())
        if not candles:
            return pd.Series(dtype=float)
        closes = []
        index = []
        for candle in candles:
            if candle.get("datetime") is None:
                raise ValueError(f"Missing candle datetime for {symbol}: {candle}")
            closes.append(float(candle["close"]))
            index.append(pd.to_datetime(int(candle["datetime"]), unit="ms", utc=True))
        return pd.Series(closes, index=pd.DatetimeIndex(index), dtype=float)

    return load_market_history


def fetch_managed_snapshot(client):
    return fetch_account_snapshot(client, strategy_symbols=list(MANAGED_SYMBOLS))


def fetch_managed_quotes(client):
    symbols = tuple(LATEST_PLAN_STRATEGY_SYMBOLS or MANAGED_SYMBOLS)
    return fetch_quotes(client, list(symbols))


def build_semiconductor_indicators(client, *, trend_window: int) -> dict[str, dict[str, float]]:
    soxl_history = fetch_default_daily_price_history_candles(client, "SOXL")
    soxx_history = fetch_default_daily_price_history_candles(client, "SOXX")
    if len(soxl_history) < trend_window:
        raise RuntimeError(
            f"SOXL history has {len(soxl_history)} candles; need at least {trend_window}"
        )
    if len(soxx_history) < trend_window:
        raise RuntimeError(
            f"SOXX history has {len(soxx_history)} candles; need at least {trend_window}"
        )

    soxl_closes = [float(candle["close"]) for candle in soxl_history[-trend_window:]]
    soxx_all_closes = [float(candle["close"]) for candle in soxx_history]
    soxx_trend_closes = soxx_all_closes[-trend_window:]
    soxx_ma20_closes = soxx_all_closes[-20:]
    previous_soxx_ma20_closes = soxx_all_closes[-21:-1]
    soxx_ma20 = sum(soxx_ma20_closes) / 20
    previous_soxx_ma20 = sum(previous_soxx_ma20_closes) / 20 if len(previous_soxx_ma20_closes) == 20 else soxx_ma20
    return {
        "soxl": {
            "price": soxl_closes[-1],
            "ma_trend": sum(soxl_closes) / trend_window,
        },
        "soxx": {
            "price": soxx_all_closes[-1],
            "ma_trend": sum(soxx_trend_closes) / trend_window,
            "ma20": soxx_ma20,
            "ma20_slope": soxx_ma20 - previous_soxx_ma20,
        },
    }


def build_account_state_from_snapshot(snapshot) -> dict[str, object]:
    return build_account_state_from_portfolio_snapshot(
        snapshot,
        strategy_symbols=MANAGED_SYMBOLS,
    )


def resolve_rebalance_plan(*, qqq_history, snapshot):
    global LATEST_PLAN_STRATEGY_SYMBOLS
    account_state = None
    if "account_state" in AVAILABLE_INPUTS:
        account_state = build_account_state_from_snapshot(snapshot)
    market_inputs = {
        "market_history": qqq_history,
        "benchmark_history": qqq_history,
        "qqq_history": qqq_history,
        "derived_indicators": qqq_history,
        "indicators": qqq_history,
    }
    if isinstance(qqq_history, dict) and any(
        key in qqq_history for key in ("market_history", "benchmark_history", "qqq_history")
    ):
        market_inputs.update(qqq_history)
    evaluation_inputs = build_strategy_evaluation_inputs(
        available_inputs=AVAILABLE_INPUTS,
        market_inputs=market_inputs,
        portfolio_snapshot=snapshot,
        account_state=account_state,
        translator=t,
        signal_text_fn=signal_text,
    )
    evaluation = STRATEGY_RUNTIME.evaluate(**evaluation_inputs)
    plan = map_strategy_decision_to_plan(
        evaluation.decision,
        snapshot=snapshot,
        strategy_profile=STRATEGY_PROFILE,
    )
    LATEST_PLAN_STRATEGY_SYMBOLS = tuple(plan["allocation"]["strategy_symbols"])
    return plan


def run_strategy_core(c, now_ny, *, strategy_plugin_signals=()):
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
        post_sell_refresh_attempts=POST_SELL_REFRESH_ATTEMPTS,
        post_sell_refresh_interval_sec=POST_SELL_REFRESH_INTERVAL_SEC,
        sleeper=time.sleep,
        extra_notification_lines=build_strategy_plugin_notification_lines(strategy_plugin_signals),
    )


@app.route("/", methods=["POST", "GET"])
def handle_schwab():
    log_context = RUNTIME_LOG_CONTEXT.with_run(build_run_id())
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
        run_strategy_core(c, None, strategy_plugin_signals=strategy_plugin_signals)
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
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))
