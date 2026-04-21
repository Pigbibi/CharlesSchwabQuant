import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from application.runtime_composer import SchwabRuntimeComposer


def test_runtime_composer_builds_runtime_and_config_from_local_builders():
    observed = {}

    def fake_notification_builder(**kwargs):
        observed["notification_builder"] = kwargs
        return SimpleNamespace(notification_port="notification-port")

    def fake_reporting_builder(**kwargs):
        observed["reporting_builder"] = kwargs
        return "reporting-adapters"

    composer = SchwabRuntimeComposer(
        project_id="project-1",
        service_name="charles-schwab-platform",
        secret_id="schwab_token",
        app_key="app-key",
        app_secret="app-secret",
        token_path="/tmp/token.json",
        strategy_profile="tqqq_growth_income",
        strategy_domain="us_equity",
        strategy_display_name="TQQQ Growth Income",
        strategy_display_name_localized="TQQQ 增长收益",
        notify_lang="en",
        tg_token="tg-token",
        tg_chat_id="chat-id",
        managed_symbols=("TQQQ", "BOXX", "SPYI", "QQQI"),
        benchmark_symbol="QQQ",
        signal_effective_after_trading_days=1,
        dry_run_only=True,
        limit_buy_premium=1.005,
        sell_settle_delay_sec=3.0,
        post_sell_refresh_attempts=5,
        post_sell_refresh_interval_sec=1.0,
        broker_adapters=SimpleNamespace(
            build_market_data_port=lambda client: ("market-data-port", client),
            build_portfolio_port=lambda client: ("portfolio-port", client),
            build_execution_port=lambda client, account_hash: ("execution-port", client, account_hash),
        ),
        strategy_adapters=SimpleNamespace(
            translator=lambda key, **_kwargs: key,
            fetch_reference_history=lambda port: ("reference-history", port),
            resolve_rebalance_plan="resolve-plan",
            build_strategy_plugin_notification_lines=lambda signals: tuple(signals),
            load_strategy_plugin_signals=lambda raw_mounts: (tuple(raw_mounts or ()), None),
            attach_strategy_plugin_report=lambda report, *, signals, error=None: report.setdefault(
                "strategy_plugins",
                [list(signals), error],
            ),
        ),
        client_builder=lambda *args, **kwargs: (args, kwargs),
        run_id_builder=lambda: "run-001",
        event_logger="event-logger",
        report_builder="report-builder",
        report_persister="report-persister",
        env_reader=lambda name, default="": {
            "EXECUTION_REPORT_OUTPUT_DIR": "/tmp/runtime-reports",
            "EXECUTION_REPORT_GCS_URI": "gs://bucket/runtime-reports",
        }.get(name, default),
        sleeper=lambda _seconds: None,
        printer=lambda *_args, **_kwargs: None,
        sender_builder=lambda token, chat_id: lambda message: observed.setdefault(
            "sent_message",
            (token, chat_id, message),
        ),
        notification_builder=fake_notification_builder,
        reporting_builder=fake_reporting_builder,
    )

    composer.send_tg_message("hello")
    runtime = composer.build_rebalance_runtime("client")
    config = composer.build_rebalance_config(strategy_plugin_signals=("plugin-line",))
    reporting_adapters = composer.build_reporting_adapters()
    built_client = composer.build_client()

    assert observed["sent_message"] == ("tg-token", "chat-id", "hello")
    assert observed["notification_builder"]["send_message"]
    assert observed["reporting_builder"]["managed_symbols"] == ("TQQQ", "BOXX", "SPYI", "QQQI")
    assert observed["reporting_builder"]["signal_effective_after_trading_days"] == 1
    assert runtime.fetch_reference_history() == ("reference-history", ("market-data-port", "client"))
    assert runtime.portfolio_port == ("portfolio-port", "client")
    assert runtime.execution_port_factory("hash-1") == ("execution-port", "client", "hash-1")
    assert runtime.notifications == "notification-port"
    assert config.extra_notification_lines == ("plugin-line",)
    assert config.strategy_display_name == "TQQQ 增长收益"
    assert config.dry_run_only is True
    assert reporting_adapters == "reporting-adapters"
    assert built_client[0][:4] == ("project-1", "schwab_token", "app-key", "app-secret")
