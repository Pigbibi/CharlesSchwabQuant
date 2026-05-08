"""Top-level runtime composer for Schwab application wiring."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from application.runtime_dependencies import SchwabRebalanceConfig, SchwabRebalanceRuntime
from application.runtime_notification_adapters import build_runtime_notification_adapters
from application.runtime_reporting_adapters import build_runtime_reporting_adapters
from quant_platform_kit.common.runtime_assembly import build_runtime_assembly
from quant_platform_kit.common.runtime_target import build_runtime_context_fields
from quant_platform_kit.common.runtime_target import RuntimeTarget
from notifications.telegram import build_sender


@dataclass(frozen=True)
class SchwabRuntimeComposer:
    project_id: str | None
    service_name: str
    secret_id: str
    app_key: str | None
    app_secret: str | None
    token_path: str
    strategy_profile: str
    strategy_domain: str | None
    strategy_display_name: str
    strategy_display_name_localized: str
    notify_lang: str
    tg_token: str | None
    tg_chat_id: str | None
    managed_symbols: tuple[str, ...]
    benchmark_symbol: str
    signal_effective_after_trading_days: int | None
    dry_run_only: bool
    limit_buy_premium: float
    sell_settle_delay_sec: float
    post_sell_refresh_attempts: int
    post_sell_refresh_interval_sec: float
    broker_adapters: Any
    strategy_adapters: Any
    client_builder: Callable[..., Any]
    run_id_builder: Callable[[], str]
    event_logger: Callable[..., dict[str, Any]]
    report_builder: Callable[..., dict[str, Any]]
    report_persister: Callable[..., Any]
    env_reader: Callable[[str, str], str | None]
    sleeper: Callable[[float], None] | None = None
    printer: Callable[..., Any] = print
    sender_builder: Callable[..., Callable[[str], None]] = build_sender
    notification_builder: Callable[..., Any] = build_runtime_notification_adapters
    reporting_builder: Callable[..., Any] = build_runtime_reporting_adapters
    runtime_target: RuntimeTarget | None = None
    extra_reporting_fields: dict[str, Any] = field(default_factory=dict)

    def send_tg_message(self, message: str) -> None:
        sender = self.sender_builder(self.tg_token, self.tg_chat_id)
        sender(message)

    def build_notification_adapters(self):
        return self.notification_builder(
            send_message=self.send_tg_message,
            log_message=lambda message: self.printer(message, flush=True),
        )

    def build_reporting_adapters(self):
        runtime_assembly = build_runtime_assembly(
            platform="charles_schwab",
            deploy_target="cloud_run",
            service_name=self.service_name,
            strategy_profile=self.strategy_profile,
            runtime_target=self.runtime_target,
            project_id=self.project_id,
            extra_context_fields=build_runtime_context_fields(
                {
                    "strategy_display_name": self.strategy_display_name,
                    "strategy_display_name_localized": self.strategy_display_name_localized,
                    **dict(self.extra_reporting_fields),
                },
            ),
        )
        return self.reporting_builder(
            runtime_assembly=runtime_assembly,
            strategy_domain=self.strategy_domain,
            managed_symbols=self.managed_symbols,
            benchmark_symbol=self.benchmark_symbol,
            strategy_display_name=self.strategy_display_name,
            strategy_display_name_localized=self.strategy_display_name_localized,
            dry_run=self.dry_run_only,
            signal_effective_after_trading_days=self.signal_effective_after_trading_days,
            report_base_dir=self.env_reader("EXECUTION_REPORT_OUTPUT_DIR", ""),
            report_gcs_prefix_uri=self.env_reader("EXECUTION_REPORT_GCS_URI", ""),
            run_id_builder=self.run_id_builder,
            event_logger=self.event_logger,
            report_builder=self.report_builder,
            report_persister=self.report_persister,
            printer=lambda line: self.printer(line, flush=True),
        )

    def build_client(self):
        return self.client_builder(
            self.project_id,
            self.secret_id,
            self.app_key,
            self.app_secret,
            token_path=self.token_path,
        )

    def build_rebalance_runtime(self, client):
        notification_adapters = self.build_notification_adapters()
        market_data_port = self.broker_adapters.build_market_data_port(client)
        return SchwabRebalanceRuntime(
            fetch_reference_history=lambda: self.strategy_adapters.fetch_reference_history(market_data_port),
            portfolio_port=self.broker_adapters.build_portfolio_port(client),
            market_data_port=market_data_port,
            resolve_rebalance_plan=self.strategy_adapters.resolve_rebalance_plan,
            notifications=notification_adapters.notification_port,
            execution_port_factory=lambda account_hash: self.broker_adapters.build_execution_port(
                client,
                account_hash,
            ),
        )

    def build_rebalance_config(self, *, strategy_plugin_signals=()):
        return SchwabRebalanceConfig(
            translator=self.strategy_adapters.translator,
            strategy_display_name=self.strategy_display_name_localized,
            limit_buy_premium=self.limit_buy_premium,
            sell_settle_delay_sec=self.sell_settle_delay_sec,
            dry_run_only=self.dry_run_only,
            post_sell_refresh_attempts=self.post_sell_refresh_attempts,
            post_sell_refresh_interval_sec=self.post_sell_refresh_interval_sec,
            sleeper=self.sleeper,
            extra_notification_lines=self.strategy_adapters.build_strategy_plugin_notification_lines(
                strategy_plugin_signals
            ),
        )

    def load_strategy_plugin_signals(self, raw_mounts):
        return self.strategy_adapters.load_strategy_plugin_signals(raw_mounts)

    def attach_strategy_plugin_report(self, report, *, signals, error: str | None = None):
        self.strategy_adapters.attach_strategy_plugin_report(
            report,
            signals=signals,
            error=error,
        )


def build_runtime_composer(
    *,
    project_id: str | None,
    service_name: str,
    secret_id: str,
    app_key: str | None,
    app_secret: str | None,
    token_path: str,
    strategy_profile: str,
    strategy_domain: str | None,
    strategy_display_name: str,
    strategy_display_name_localized: str,
    notify_lang: str,
    tg_token: str | None,
    tg_chat_id: str | None,
    managed_symbols: tuple[str, ...],
    benchmark_symbol: str,
    signal_effective_after_trading_days: int | None,
    dry_run_only: bool,
    limit_buy_premium: float,
    sell_settle_delay_sec: float,
    post_sell_refresh_attempts: int,
    post_sell_refresh_interval_sec: float,
    broker_adapters: Any,
    strategy_adapters: Any,
    client_builder: Callable[..., Any],
    run_id_builder: Callable[[], str],
    event_logger: Callable[..., dict[str, Any]],
    report_builder: Callable[..., dict[str, Any]],
    report_persister: Callable[..., Any],
    env_reader: Callable[[str, str], str | None],
    sleeper: Callable[[float], None] | None = None,
    printer: Callable[..., Any] = print,
    extra_reporting_fields: dict[str, Any] | None = None,
    runtime_target: RuntimeTarget | None = None,
) -> SchwabRuntimeComposer:
    return SchwabRuntimeComposer(
        project_id=project_id,
        service_name=str(service_name or ""),
        secret_id=str(secret_id or ""),
        app_key=app_key,
        app_secret=app_secret,
        token_path=str(token_path or ""),
        strategy_profile=str(strategy_profile),
        strategy_domain=strategy_domain,
        strategy_display_name=str(strategy_display_name or ""),
        strategy_display_name_localized=str(strategy_display_name_localized or ""),
        notify_lang=str(notify_lang or ""),
        tg_token=tg_token,
        tg_chat_id=tg_chat_id,
        managed_symbols=tuple(managed_symbols),
        benchmark_symbol=str(benchmark_symbol or ""),
        signal_effective_after_trading_days=signal_effective_after_trading_days,
        dry_run_only=bool(dry_run_only),
        limit_buy_premium=float(limit_buy_premium),
        sell_settle_delay_sec=float(sell_settle_delay_sec),
        post_sell_refresh_attempts=int(post_sell_refresh_attempts),
        post_sell_refresh_interval_sec=float(post_sell_refresh_interval_sec),
        broker_adapters=broker_adapters,
        strategy_adapters=strategy_adapters,
        client_builder=client_builder,
        run_id_builder=run_id_builder,
        event_logger=event_logger,
        report_builder=report_builder,
        report_persister=report_persister,
        env_reader=env_reader,
        sleeper=sleeper,
        printer=printer,
        runtime_target=runtime_target,
        extra_reporting_fields=dict(extra_reporting_fields or {}),
    )
