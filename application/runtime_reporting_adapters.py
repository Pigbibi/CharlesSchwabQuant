"""Builder helpers for Schwab runtime reporting and structured logging."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from quant_platform_kit.strategy_contracts import build_execution_timing_metadata
from runtime_logging import RuntimeLogContext


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class SchwabRuntimeReportingAdapters:
    platform: str
    deploy_target: str
    service_name: str
    strategy_profile: str
    strategy_domain: str | None
    project_id: str | None
    extra_context_fields: Mapping[str, Any] = field(default_factory=dict)
    managed_symbols: tuple[str, ...] = ()
    benchmark_symbol: str = ""
    strategy_display_name: str = ""
    strategy_display_name_localized: str = ""
    dry_run: bool = False
    signal_effective_after_trading_days: int | None = None
    report_base_dir: str | None = None
    report_gcs_prefix_uri: str | None = None
    run_id_builder: Callable[[], str] | None = None
    event_logger: Callable[..., dict[str, Any]] | None = None
    report_builder: Callable[..., dict[str, Any]] | None = None
    report_persister: Callable[..., Any] | None = None
    printer: Callable[..., Any] = print
    clock: Callable[[], datetime] = _utcnow

    def __post_init__(self) -> None:
        required = {
            "run_id_builder": self.run_id_builder,
            "event_logger": self.event_logger,
            "report_builder": self.report_builder,
            "report_persister": self.report_persister,
        }
        missing = [name for name, value in required.items() if value is None]
        if missing:
            raise ValueError(f"Missing reporting adapter dependencies: {', '.join(missing)}")

    def build_log_context(self) -> RuntimeLogContext:
        return RuntimeLogContext(
            platform=self.platform,
            deploy_target=self.deploy_target,
            service_name=self.service_name,
            strategy_profile=self.strategy_profile,
            project_id=self.project_id,
            extra_fields=dict(self.extra_context_fields),
        ).with_run(self.run_id_builder())

    def build_report(self, log_context: RuntimeLogContext) -> dict[str, Any]:
        started_at = self.clock()
        timing_summary = build_execution_timing_metadata(
            signal_date=started_at,
            signal_effective_after_trading_days=self.signal_effective_after_trading_days,
        )
        return self.report_builder(
            platform=log_context.platform,
            deploy_target=log_context.deploy_target,
            service_name=log_context.service_name,
            strategy_profile=self.strategy_profile,
            strategy_domain=self.strategy_domain,
            run_id=log_context.run_id,
            run_source="cloud_run",
            dry_run=self.dry_run,
            started_at=started_at,
            summary={
                "managed_symbols": list(self.managed_symbols),
                "benchmark_symbol": self.benchmark_symbol,
                "strategy_display_name": self.strategy_display_name,
                "strategy_display_name_localized": self.strategy_display_name_localized,
                **timing_summary,
            },
        )

    def start_run(self) -> tuple[RuntimeLogContext, dict[str, Any]]:
        log_context = self.build_log_context()
        return log_context, self.build_report(log_context)

    def log_event(self, log_context: RuntimeLogContext, event: str, **fields: Any) -> dict[str, Any]:
        return self.event_logger(
            log_context,
            event,
            printer=self.printer,
            **fields,
        )

    def persist_execution_report(self, report: dict[str, Any]) -> str | None:
        persisted = self.report_persister(
            report,
            base_dir=self.report_base_dir,
            gcs_prefix_uri=self.report_gcs_prefix_uri,
            gcp_project_id=self.project_id,
        )
        if isinstance(persisted, str):
            return persisted
        return getattr(persisted, "gcs_uri", None) or getattr(persisted, "local_path", None)


def build_runtime_reporting_adapters(
    *,
    platform: str,
    deploy_target: str,
    service_name: str,
    strategy_profile: str,
    strategy_domain: str | None,
    project_id: str | None,
    extra_context_fields: Mapping[str, Any] | None = None,
    managed_symbols: tuple[str, ...],
    benchmark_symbol: str,
    strategy_display_name: str,
    strategy_display_name_localized: str,
    dry_run: bool,
    signal_effective_after_trading_days: int | None,
    report_base_dir: str | None,
    report_gcs_prefix_uri: str | None,
    run_id_builder: Callable[[], str],
    event_logger: Callable[..., dict[str, Any]],
    report_builder: Callable[..., dict[str, Any]],
    report_persister: Callable[..., Any],
    printer: Callable[..., Any] = print,
    clock: Callable[[], datetime] = _utcnow,
) -> SchwabRuntimeReportingAdapters:
    return SchwabRuntimeReportingAdapters(
        platform=platform,
        deploy_target=deploy_target,
        service_name=service_name,
        strategy_profile=strategy_profile,
        strategy_domain=strategy_domain,
        project_id=project_id,
        extra_context_fields=dict(extra_context_fields or {}),
        managed_symbols=tuple(managed_symbols),
        benchmark_symbol=str(benchmark_symbol or ""),
        strategy_display_name=str(strategy_display_name or ""),
        strategy_display_name_localized=str(strategy_display_name_localized or ""),
        dry_run=bool(dry_run),
        signal_effective_after_trading_days=signal_effective_after_trading_days,
        report_base_dir=report_base_dir,
        report_gcs_prefix_uri=report_gcs_prefix_uri,
        run_id_builder=run_id_builder,
        event_logger=event_logger,
        report_builder=report_builder,
        report_persister=report_persister,
        printer=printer,
        clock=clock,
    )
