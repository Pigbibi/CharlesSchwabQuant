"""Builder helpers for Schwab broker-side runtime adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

from quant_platform_kit.common.models import PricePoint, PriceSeries, QuoteSnapshot
from quant_platform_kit.common.port_adapters import (
    CallableExecutionPort,
    CallableMarketDataPort,
    CallablePortfolioPort,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class SchwabRuntimeBrokerAdapters:
    managed_symbols: tuple[str, ...]
    fetch_account_snapshot_fn: Any
    fetch_quotes_fn: Any
    fetch_daily_price_history_fn: Any
    submit_equity_order_fn: Any
    clock: Any = _utcnow

    def fetch_managed_snapshot(self, client):
        return self.fetch_account_snapshot_fn(client, strategy_symbols=list(self.managed_symbols))

    def build_market_data_port(self, client):
        quote_cache: dict[str, QuoteSnapshot] = {}
        price_series_cache: dict[str, PriceSeries] = {}

        def load_quote(symbol: str) -> QuoteSnapshot:
            normalized_symbol = str(symbol).strip().upper()
            cached = quote_cache.get(normalized_symbol)
            if cached is not None:
                return cached
            raw_quotes = self.fetch_quotes_fn(client, [normalized_symbol])
            raw_snapshot = raw_quotes[normalized_symbol]
            snapshot = QuoteSnapshot(
                symbol=normalized_symbol,
                as_of=self.clock(),
                last_price=float(raw_snapshot.last_price),
                ask_price=(
                    float(raw_snapshot.ask_price)
                    if getattr(raw_snapshot, "ask_price", None) is not None
                    else None
                ),
                bid_price=(
                    float(raw_snapshot.bid_price)
                    if getattr(raw_snapshot, "bid_price", None) is not None
                    else None
                ),
            )
            quote_cache[normalized_symbol] = snapshot
            return snapshot

        def load_price_series(symbol: str) -> PriceSeries:
            normalized_symbol = str(symbol).strip().upper()
            cached = price_series_cache.get(normalized_symbol)
            if cached is not None:
                return cached
            candles = self.fetch_daily_price_history_fn(client, normalized_symbol)
            if not candles:
                raise ValueError(f"Price history unavailable for {normalized_symbol}")
            fallback_start = self.clock() - timedelta(days=max(0, len(candles) - 1))
            points = []
            for index, candle in enumerate(candles):
                if candle.get("datetime") is None:
                    as_of = fallback_start + timedelta(days=index)
                else:
                    raw_datetime = int(candle["datetime"])
                    if abs(raw_datetime) > 10_000_000_000:
                        raw_datetime /= 1000
                    as_of = datetime.fromtimestamp(raw_datetime, tz=timezone.utc)
                points.append(
                    PricePoint(
                        as_of=as_of,
                        close=float(candle["close"]),
                    )
                )
            series = PriceSeries(
                symbol=normalized_symbol,
                currency="USD",
                points=tuple(points),
            )
            price_series_cache[normalized_symbol] = series
            return series

        return CallableMarketDataPort(
            quote_loader=load_quote,
            price_series_loader=load_price_series,
        )

    def build_price_history(self, market_data_port, symbol: str):
        series = market_data_port.get_price_series(symbol)
        return [
            {
                "datetime": int(point.as_of.timestamp() * 1000),
                "close": float(point.close),
                "high": float(point.close),
                "low": float(point.close),
            }
            for point in series.points
        ]

    def build_market_history_loader(self, market_data_port):
        def load_market_history(_broker_client, symbol, *_args, **_kwargs):
            series = market_data_port.get_price_series(str(symbol).strip().upper())
            if not series.points:
                return pd.Series(dtype=float)
            closes = [float(point.close) for point in series.points]
            index = [pd.Timestamp(point.as_of) for point in series.points]
            return pd.Series(closes, index=pd.DatetimeIndex(index), dtype=float)

        return load_market_history

    def build_portfolio_port(self, client):
        return CallablePortfolioPort(lambda: self.fetch_managed_snapshot(client))

    def build_execution_port(self, client, account_hash: str):
        return CallableExecutionPort(
            lambda order_intent: self.submit_equity_order_fn(client, account_hash, order_intent)
        )


def build_runtime_broker_adapters(
    *,
    managed_symbols: tuple[str, ...],
    fetch_account_snapshot_fn,
    fetch_quotes_fn,
    fetch_daily_price_history_fn,
    submit_equity_order_fn,
    clock=_utcnow,
) -> SchwabRuntimeBrokerAdapters:
    return SchwabRuntimeBrokerAdapters(
        managed_symbols=tuple(managed_symbols),
        fetch_account_snapshot_fn=fetch_account_snapshot_fn,
        fetch_quotes_fn=fetch_quotes_fn,
        fetch_daily_price_history_fn=fetch_daily_price_history_fn,
        submit_equity_order_fn=submit_equity_order_fn,
        clock=clock,
    )
