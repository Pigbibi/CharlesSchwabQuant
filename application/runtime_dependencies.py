"""Runtime dependency bundles for Schwab rebalance orchestration."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from quant_platform_kit.common.ports import ExecutionPort, MarketDataPort, NotificationPort, PortfolioPort


@dataclass(frozen=True)
class SchwabRebalanceConfig:
    translator: Callable[..., str]
    strategy_display_name: str
    limit_buy_premium: float
    sell_settle_delay_sec: float
    dry_run_only: bool = False
    post_sell_refresh_attempts: int = 1
    post_sell_refresh_interval_sec: float = 0.0
    sleeper: Callable[[float], None] | None = None
    extra_notification_lines: Sequence[str] = ()


@dataclass(frozen=True)
class SchwabRebalanceRuntime:
    fetch_reference_history: Callable[[], Any]
    portfolio_port: PortfolioPort
    market_data_port: MarketDataPort
    resolve_rebalance_plan: Callable[..., dict[str, Any]]
    notifications: NotificationPort
    execution_port_factory: Callable[[str], ExecutionPort] | None = None
    submit_equity_order: Callable[..., Any] | None = None
