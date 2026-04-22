"""Notification rendering helpers for CharlesSchwabPlatform."""

from __future__ import annotations

import re

from notifications.events import RenderedNotification
from quant_platform_kit.common.notification_localization import (
    localize_notification_text as _base_localize_notification_text,
    translator_uses_zh as _base_translator_uses_zh,
)

_DETAIL_FIELD_SPLIT_RE = re.compile(r"\s+(?=[^\s=:：]+[=:：])")


def _has_benchmark_context(execution):
    return any(
        float(execution.get(key) or 0.0) > 0.0
        for key in ("benchmark_price", "long_trend_value", "exit_line")
    )


def _translator_uses_zh(translator) -> bool:
    return _base_translator_uses_zh(translator)


def _localize_notification_text(text, *, translator):
    return _base_localize_notification_text(text, translator=translator)


def _split_detail_segment(text: str) -> list[str]:
    value = str(text or "").strip()
    if not value:
        return []
    if "=" not in value and ":" not in value and "：" not in value:
        return [value]
    return [part.strip() for part in _DETAIL_FIELD_SPLIT_RE.split(value) if part.strip()]


def _split_labeled_text(text: str) -> list[str]:
    segments = [segment.strip() for segment in str(text or "").split(" | ") if segment.strip()]
    if not segments:
        return []
    lines = [segments[0]]
    for segment in segments[1:]:
        lines.extend(_split_detail_segment(segment))
    return lines


def _format_label_value_lines(label: str, value: str) -> list[str]:
    parts = _split_labeled_text(value)
    if not parts:
        return []
    lines = [f"{label}: {parts[0]}"]
    lines.extend(f"  - {part}" for part in parts[1:])
    return lines


def _format_benchmark_lines(execution, *, translator) -> list[str]:
    if not _has_benchmark_context(execution):
        return []
    benchmark_symbol = str(execution["benchmark_symbol"])
    benchmark_price = float(execution["benchmark_price"])
    long_trend_value = float(execution["long_trend_value"])
    exit_line = float(execution["exit_line"])
    return [
        translator("benchmark_title", symbol=benchmark_symbol),
        f"  - {translator('benchmark_price', symbol=benchmark_symbol, value=f'{benchmark_price:.2f}')}",
        f"  - {translator('benchmark_ma200', value=f'{long_trend_value:.2f}')}",
        f"  - {translator('benchmark_exit', value=f'{exit_line:.2f}')}",
    ]


def _is_holding_segment(segment: str) -> bool:
    label, sep, value = str(segment or "").partition(":")
    symbol = label.strip().replace(".", "").replace("-", "")
    return bool(sep and symbol.isalnum() and "$" in value)


def _format_inline_segments(line: str, *, translator, holdings_title_emitted: bool) -> tuple[list[str], bool]:
    parts = [part.strip() for part in str(line or "").split(" | ") if part.strip()]
    if len(parts) <= 1:
        return [str(line or "").strip()], holdings_title_emitted

    if all(_is_holding_segment(part) for part in parts):
        lines = []
        if not holdings_title_emitted:
            lines.append(translator("holdings_title"))
            holdings_title_emitted = True
        lines.extend(f"  - {part}" for part in parts)
        return lines, holdings_title_emitted

    first, rest = parts[0], parts[1:]
    if first.startswith(("📊", "💰", "💵")):
        lines = [first]
        lines.extend(f"  - {part}" for part in rest)
        return lines, holdings_title_emitted
    return [f"  - {part}" for part in parts], holdings_title_emitted


def _format_dashboard_text(text: str, *, translator) -> str:
    raw_lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    formatted_lines: list[str] = []
    holdings_title_emitted = False
    for line in raw_lines:
        expanded, holdings_title_emitted = _format_inline_segments(
            line,
            translator=translator,
            holdings_title_emitted=holdings_title_emitted,
        )
        formatted_lines.extend(expanded)
    return "\n".join(formatted_lines)


def _build_timing_audit_lines(execution, *, translator) -> list[str]:
    signal_date = str(execution.get("signal_date") or "").strip()
    effective_date = str(execution.get("effective_date") or "").strip()
    contract = str(execution.get("execution_timing_contract") or "").strip()
    if not signal_date and not effective_date and not contract:
        return []
    label = "⏱ 执行时点" if _translator_uses_zh(translator) else "⏱ Timing"
    if signal_date and effective_date:
        value = f"{signal_date} -> {effective_date}"
    else:
        value = signal_date or effective_date or contract
    if contract and contract not in value:
        value = f"{value} ({contract})" if value else contract
    return [f"{label}: {value}"]


def _format_holdings_lines(portfolio_rows, market_values, *, translator) -> list[str]:
    lines = [translator("holdings_title")]
    for row in portfolio_rows:
        for symbol in row:
            lines.append(f"  - {symbol}: ${market_values[symbol]:,.2f}")
    return lines


def _first_detail_line(text: str) -> str:
    parts = _split_labeled_text(text)
    return parts[0] if parts else ""


def _render_extra_notification_block(extra_notification_lines) -> str:
    block = "\n".join(
        str(line).strip() for line in extra_notification_lines if str(line).strip()
    )
    if not block:
        return ""
    return f"{block}\n"


def _build_compact_trade_message(
    *,
    translator,
    strategy_display_name,
    dry_run_only,
    extra_notification_block,
    dashboard_text,
    separator,
    status_display,
    signal_display,
    timing_lines,
    trade_logs,
) -> str:
    lines = [
        translator("trade_header"),
        translator("strategy_label", name=strategy_display_name),
    ]
    if dry_run_only:
        lines.append(translator("dry_run_banner"))
    if extra_notification_block:
        lines.extend(line for line in extra_notification_block.splitlines() if line.strip())
    dashboard = str(dashboard_text or "").strip()
    if dashboard:
        lines.append(separator)
        lines.extend(line for line in dashboard.splitlines() if line.strip())
    lines.extend(timing_lines)
    status_summary = _first_detail_line(status_display)
    if status_summary:
        lines.append(f"📊 {status_summary}")
    signal_summary = _first_detail_line(signal_display)
    if signal_summary:
        lines.append(f"📊 {translator('signal_label')}: {signal_summary}")
    lines.extend(str(log).strip() for log in trade_logs if str(log).strip())
    return "\n".join(lines)


def _build_compact_heartbeat_message(
    *,
    translator,
    strategy_display_name,
    dry_run_only,
    extra_notification_block,
    total_equity,
    dashboard_text,
    separator,
    status_display,
    signal_display,
    timing_lines,
) -> str:
    lines = [
        translator("heartbeat_header"),
        translator("strategy_label", name=strategy_display_name),
        f"💰 {translator('equity')}: ${total_equity:,.2f}",
    ]
    if dry_run_only:
        lines.append(translator("dry_run_banner"))
    if extra_notification_block:
        lines.extend(line for line in extra_notification_block.splitlines() if line.strip())
    dashboard = str(dashboard_text or "").strip()
    if dashboard:
        lines.append(separator)
        lines.extend(line for line in dashboard.splitlines() if line.strip())
    lines.extend(timing_lines)
    status_summary = _first_detail_line(status_display)
    if status_summary:
        lines.append(f"📊 {status_summary}")
    signal_summary = _first_detail_line(signal_display)
    if signal_summary:
        lines.append(f"🎯 {translator('signal_label')}: {signal_summary}")
    lines.append(translator("no_trades"))
    return "\n".join(lines)


def render_trade_notification(
    *,
    translator,
    strategy_display_name,
    dry_run_only,
    extra_notification_lines,
    execution,
    trade_logs,
) -> RenderedNotification:
    signal_display = _localize_notification_text(execution["signal_display"], translator=translator)
    status_display = _localize_notification_text(execution.get("status_display"), translator=translator)
    extra_notification_block = _render_extra_notification_block(extra_notification_lines)
    dashboard_text = _format_dashboard_text(str(execution["dashboard_text"]), translator=translator)
    timing_lines = _build_timing_audit_lines(execution, translator=translator)
    separator = str(execution["separator"])
    status_line = "\n".join(_split_labeled_text(f"📊 {status_display}")) + "\n" if status_display else ""
    dashboard_block = f"{dashboard_text}\n{separator}\n" if dashboard_text else ""
    trade_signal_lines = _format_label_value_lines(f"📊 {translator('signal_label')}", signal_display)
    trade_signal_block = "\n".join(trade_signal_lines)
    dry_run_line = f"{translator('dry_run_banner')}\n" if dry_run_only else ""
    detailed_text = (
        f"{translator('trade_header')}\n"
        f"{translator('strategy_label', name=strategy_display_name)}\n"
        f"{dry_run_line}"
        f"{extra_notification_block}"
        f"{chr(10).join(timing_lines) + chr(10) if timing_lines else ''}"
        f"{status_line}"
        f"{trade_signal_block}\n\n"
        f"{dashboard_block}"
        + "\n".join(trade_logs)
    )
    compact_text = _build_compact_trade_message(
        translator=translator,
        strategy_display_name=strategy_display_name,
        dry_run_only=dry_run_only,
        extra_notification_block=extra_notification_block,
        dashboard_text=dashboard_text,
        separator=separator,
        status_display=status_display,
        signal_display=signal_display,
        timing_lines=timing_lines,
        trade_logs=trade_logs,
    )
    return RenderedNotification(detailed_text=detailed_text, compact_text=compact_text)


def render_heartbeat_notification(
    *,
    translator,
    strategy_display_name,
    dry_run_only,
    extra_notification_lines,
    execution,
    portfolio,
) -> RenderedNotification:
    signal_display = _localize_notification_text(execution["signal_display"], translator=translator)
    status_display = _localize_notification_text(execution.get("status_display"), translator=translator)
    extra_notification_block = _render_extra_notification_block(extra_notification_lines)
    dashboard_text = _format_dashboard_text(str(execution["dashboard_text"]), translator=translator)
    timing_lines = _build_timing_audit_lines(execution, translator=translator)
    separator = str(execution["separator"])
    total_equity = float(portfolio["total_equity"])
    portfolio_rows = tuple(portfolio["portfolio_rows"])
    market_values = dict(portfolio["market_values"])
    status_line = "\n".join(_split_labeled_text(f"📊 {status_display}")) + "\n" if status_display else ""
    dashboard_block = f"{dashboard_text}\n{separator}\n" if dashboard_text else ""
    benchmark_lines = _format_benchmark_lines(execution, translator=translator)
    benchmark_block = "\n".join(benchmark_lines) + "\n" if benchmark_lines else ""
    heartbeat_signal_lines = _format_label_value_lines(f"🎯 {translator('signal_label')}", signal_display)
    heartbeat_signal_block = "\n".join(heartbeat_signal_lines)
    if dashboard_block:
        portfolio_block = dashboard_block
    else:
        holdings_lines = _format_holdings_lines(portfolio_rows, market_values, translator=translator)
        portfolio_block = (
            f"💰 {translator('equity')}: ${total_equity:,.2f}\n"
            f"{separator}\n"
            + "\n".join(holdings_lines) + "\n"
            f"{separator}\n"
        )
    detailed_text = (
        f"{translator('heartbeat_header')}\n"
        f"{translator('strategy_label', name=strategy_display_name)}\n"
        f"{extra_notification_block}"
        f"{portfolio_block}"
        f"{chr(10).join(timing_lines) + chr(10) if timing_lines else ''}"
        f"{status_line}"
        f"{heartbeat_signal_block}\n"
        f"{benchmark_block}"
        f"{separator}\n"
        f"{translator('no_trades')}"
    )
    compact_text = _build_compact_heartbeat_message(
        translator=translator,
        strategy_display_name=strategy_display_name,
        dry_run_only=dry_run_only,
        extra_notification_block=extra_notification_block,
        total_equity=total_equity,
        dashboard_text=dashboard_text,
        separator=separator,
        status_display=status_display,
        signal_display=signal_display,
        timing_lines=timing_lines,
    )
    return RenderedNotification(detailed_text=detailed_text, compact_text=compact_text)
