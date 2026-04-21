"""Notification rendering helpers for CharlesSchwabPlatform."""

from __future__ import annotations

import re

from notifications.events import RenderedNotification


_ZH_REASON_REPLACEMENTS = (
    ("feature snapshot guard blocked execution", "特征快照校验阻止执行"),
    ("feature snapshot required", "需要特征快照"),
    ("feature snapshot compute failed", "特征快照计算失败"),
    ("feature_snapshot_download_failed", "特征快照下载失败"),
    ("feature_snapshot_compute_failed", "特征快照计算失败"),
    ("feature_snapshot_path_missing", "缺少特征快照路径"),
    ("feature_snapshot_missing", "特征快照不存在"),
    ("feature_snapshot_stale", "特征快照过旧"),
    ("feature_snapshot_manifest_missing", "缺少快照清单"),
    ("feature_snapshot_profile_mismatch", "快照策略名不匹配"),
    ("feature_snapshot_config_name_mismatch", "快照配置名不匹配"),
    ("feature_snapshot_config_path_mismatch", "快照配置路径不匹配"),
    ("feature_snapshot_contract_version_mismatch", "快照契约版本不匹配"),
    ("soxl_soxx_trend_income", "SOXL/SOXX 半导体趋势收益"),
    ("tqqq_growth_income", "TQQQ 增长收益"),
    ("global_etf_rotation", "全球 ETF 轮动"),
    ("russell_1000_multi_factor_defensive", "罗素1000多因子"),
    ("tech_communication_pullback_enhancement", "科技通信回调增强"),
    ("qqq_tech_enhancement", "科技通信回调增强"),
    ("mega_cap_leader_rotation_aggressive", "Mega Cap 激进龙头轮动"),
    ("mega_cap_leader_rotation_dynamic_top20", "Mega Cap 动态 Top20 龙头轮动"),
    ("mega_cap_leader_rotation_top50_balanced", "Mega Cap Top50 平衡龙头轮动"),
    ("dynamic_mega_leveraged_pullback", "Mega Cap 2x 回调策略"),
    ("outside_monthly_execution_window", "当前不在月度执行窗口"),
    ("no_execution_window_after_snapshot", "快照后没有可用执行窗口"),
    ("no-op", "不执行"),
    ("monthly snapshot cadence", "月度快照节奏"),
    ("waiting inside execution window", "等待进入执行窗口"),
    ("small_account_warning=true", "小账户提示=是"),
    ("portfolio_equity=", "净值="),
    ("min_recommended_equity=", "建议最低净值="),
    (
        "integer_shares_min_position_value_may_prevent_backtest_replication",
        "整数股和最小仓位限制可能导致实盘无法完全复现回测",
    ),
    (
        "integer-share minimum position sizing may prevent backtest replication",
        "整数股和最小仓位限制可能导致实盘无法完全复现回测",
    ),
    ("small account warning: portfolio equity", "小账户提示：净值"),
    ("small account warning", "小账户提示"),
    ("is below the recommended", "低于建议"),
    ("is below recommended", "低于建议"),
    ("snapshot_as_of=", "快照日期="),
    ("snapshot=", "快照日期="),
    ("allowed=", "允许日期="),
    ("<unknown>", "未知"),
    ("<none>", "无"),
    ("RISK-ON", "风险开启"),
    ("DE-LEVER", "降杠杆"),
    ("regime=hard_defense", "市场阶段=强防御"),
    ("regime=soft_defense", "市场阶段=软防御"),
    ("regime=risk_on", "市场阶段=进攻"),
    ("benchmark_trend=down", "基准趋势=向下"),
    ("benchmark_trend=up", "基准趋势=向上"),
    ("benchmark=down", "基准趋势=向下"),
    ("benchmark=up", "基准趋势=向上"),
    ("breadth=", "市场宽度="),
    ("target_stock=", "目标股票仓位="),
    ("realized_stock=", "实际股票仓位="),
    ("stock_exposure=", "股票目标仓位="),
    ("safe_haven=", "避险仓位="),
    ("selected=", "入选标的数="),
    ("top=", "前排标的="),
    ("no_selection", "无入选标的"),
    ("outside_execution_window", "当前不在执行窗口"),
    ("insufficient_buying_power", "购买力不足"),
    ("missing_price", "缺少报价"),
    ("no_equity", "无净值"),
    ("fail_closed", "关闭执行"),
    ("reason=", "原因="),
)
_DETAIL_FIELD_SPLIT_RE = re.compile(r"\s+(?=[^\s=:：]+[=:：])")


def _has_benchmark_context(execution):
    return any(
        float(execution.get(key) or 0.0) > 0.0
        for key in ("benchmark_price", "long_trend_value", "exit_line")
    )


def _translator_uses_zh(translator) -> bool:
    sample = str(translator("no_trades"))
    return any("\u4e00" <= ch <= "\u9fff" for ch in sample)


def _localize_notification_text(text, *, translator):
    value = str(text or "").strip()
    if not value or not _translator_uses_zh(translator):
        return value
    localized = value
    for source, target in _ZH_REASON_REPLACEMENTS:
        localized = localized.replace(source, target)
    return localized


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
