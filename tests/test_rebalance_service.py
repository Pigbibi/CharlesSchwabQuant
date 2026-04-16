import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
QPK_SRC = ROOT.parent / "QuantPlatformKit" / "src"
if str(QPK_SRC) not in sys.path:
    sys.path.insert(0, str(QPK_SRC))

from application import rebalance_service
from application.rebalance_service import run_strategy_core
from notifications.telegram import build_translator


class RebalanceServiceTests(unittest.TestCase):
    def test_localize_notification_text_for_snapshot_guard_in_zh(self):
        localized = rebalance_service._localize_notification_text(
            "fail_closed | reason=feature_snapshot_path_missing",
            translator=build_translator("zh"),
        )
        assert localized == "关闭执行 | 原因=缺少特征快照路径"

    def test_localize_notification_text_for_qqq_tech_diagnostics_in_zh(self):
        localized = rebalance_service._localize_notification_text(
            (
                "regime=soft_defense breadth=41.2% benchmark_trend=down "
                "target_stock=60.0% realized_stock=60.0% selected=8 top=CIEN(0.92)"
            ),
            translator=build_translator("zh"),
        )

        assert localized == (
            "市场阶段=软防御 市场宽度=41.2% 基准趋势=向下 "
            "目标股票仓位=60.0% 实际股票仓位=60.0% 入选标的数=8 前排标的=CIEN(0.92)"
        )

    def test_translator_localizes_semiconductor_trend_status_for_zh(self):
        translate = build_translator("zh")
        self.assertEqual(translate("market_status_risk_on", asset="SOXL"), "🚀 风险开启（SOXL）")
        self.assertEqual(
            translate("signal_risk_on", window=150, ratio="40.2%"),
            "SOXL 站上 150 日均线，持有 SOXL，交易层风险仓位 40.2%",
        )

    def test_run_strategy_core_uses_managed_wrappers(self):
        sent_messages = []
        observed = {}
        snapshot = SimpleNamespace(
            positions=(
                SimpleNamespace(symbol="TQQQ", quantity=0, market_value=0.0),
                SimpleNamespace(symbol="BOXX", quantity=10, market_value=5000.0),
                SimpleNamespace(symbol="SPYI", quantity=0, market_value=0.0),
                SimpleNamespace(symbol="QQQI", quantity=0, market_value=0.0),
            ),
            total_equity=50000.0,
            buying_power=10000.0,
            metadata={"account_hash": "demo"},
        )
        quote_snapshots = {
            "TQQQ": SimpleNamespace(last_price=50.0, ask_price=50.1),
            "BOXX": SimpleNamespace(last_price=100.0, ask_price=100.0),
            "SPYI": SimpleNamespace(last_price=50.0, ask_price=50.0),
            "QQQI": SimpleNamespace(last_price=50.0, ask_price=50.0),
        }
        plan = {
            "strategy_profile": "tqqq_growth_income",
            "account_hash": "demo",
            "allocation": {
                "target_mode": "value",
                "strategy_symbols": ("TQQQ", "BOXX", "SPYI", "QQQI"),
                "risk_symbols": ("TQQQ",),
                "income_symbols": ("QQQI", "SPYI"),
                "safe_haven_symbols": ("BOXX",),
                "targets": {"TQQQ": 20000.0, "BOXX": 15000.0, "SPYI": 5000.0, "QQQI": 10000.0},
            },
            "portfolio": {
                "strategy_symbols": ("TQQQ", "BOXX", "SPYI", "QQQI"),
                "portfolio_rows": (("TQQQ", "BOXX"), ("QQQI", "SPYI")),
                "market_values": {"TQQQ": 0.0, "BOXX": 5000.0, "SPYI": 0.0, "QQQI": 0.0},
                "quantities": {"TQQQ": 0, "BOXX": 10, "SPYI": 0, "QQQI": 0},
                "total_equity": 50000.0,
                "liquid_cash": 10000.0,
                "cash_sweep_symbol": "BOXX",
            },
            "execution": {
                "trade_threshold_value": 500.0,
                "reserved_cash": 2500.0,
                "signal_display": "💎 Trend Hold",
                "dashboard_text": "dashboard",
                "separator": "━━━━━━━━━━━━━━━━━━",
                "benchmark_symbol": "QQQ",
                "benchmark_price": 400.0,
                "long_trend_value": 380.0,
                "exit_line": 360.0,
            },
        }
        translations = {
            "trade_header": "trade",
            "heartbeat_header": "heartbeat",
            "strategy_label": "strategy={name}",
            "signal_label": "signal",
            "equity": "equity",
            "buying_power": "buying_power",
            "market_sell_cmd": "sell",
            "limit_buy_cmd": "limit buy",
            "market_buy_cmd": "buy",
            "submitted": "submitted",
            "shares": "shares",
            "no_trades": "no trades",
            "market_sell": "market_sell",
            "limit_buy": "limit_buy",
            "market_buy": "market_buy",
            "failed": "failed",
            "buy_label": "buy",
            "exception": "exception",
        }

        run_strategy_core(
            object(),
            None,
            fetch_reference_history=lambda client: [{"close": 1.0, "high": 1.0, "low": 1.0}],
            fetch_managed_snapshot=lambda client: snapshot,
            fetch_managed_quotes=lambda client: quote_snapshots,
            resolve_rebalance_plan=lambda *, qqq_history, snapshot: (
                observed.setdefault("history_len", len(qqq_history)),
                observed.setdefault("snapshot_hash", snapshot.metadata["account_hash"]),
                plan,
            )[-1],
            submit_equity_order=lambda *_args, **_kwargs: SimpleNamespace(
                status="accepted",
                broker_order_id="order-1",
                raw_payload={},
            ),
            send_tg_message=sent_messages.append,
            translator=lambda key, **kwargs: translations.get(key, key).format(**kwargs) if kwargs else translations.get(key, key),
            strategy_display_name="TQQQ Growth Income",
            limit_buy_premium=1.005,
            sell_settle_delay_sec=0,
        )

        self.assertEqual(observed["history_len"], 1)
        self.assertEqual(observed["snapshot_hash"], "demo")
        self.assertTrue(sent_messages)
        self.assertIn("trade", sent_messages[0])
        self.assertIn("strategy=TQQQ Growth Income", sent_messages[0])

    def test_run_strategy_core_accepts_normalized_portfolio_and_execution_sections(self):
        sent_messages = []
        snapshot = SimpleNamespace(
            positions=(
                SimpleNamespace(symbol="TQQQ", quantity=0, market_value=0.0),
                SimpleNamespace(symbol="BOXX", quantity=10, market_value=5000.0),
            ),
            total_equity=50000.0,
            buying_power=10000.0,
            metadata={"account_hash": "demo"},
        )
        quote_snapshots = {
            "TQQQ": SimpleNamespace(last_price=50.0, ask_price=50.1),
            "BOXX": SimpleNamespace(last_price=100.0, ask_price=100.0),
        }
        plan = {
            "strategy_profile": "tqqq_growth_income",
            "account_hash": "demo",
            "allocation": {
                "target_mode": "value",
                "strategy_symbols": ("TQQQ", "BOXX"),
                "risk_symbols": ("TQQQ",),
                "income_symbols": (),
                "safe_haven_symbols": ("BOXX",),
                "targets": {"TQQQ": 20000.0, "BOXX": 15000.0},
            },
            "portfolio": {
                "strategy_symbols": ("TQQQ", "BOXX"),
                "portfolio_rows": (("TQQQ", "BOXX"),),
                "market_values": {"TQQQ": 0.0, "BOXX": 5000.0},
                "quantities": {"TQQQ": 0, "BOXX": 10},
                "total_equity": 50000.0,
                "liquid_cash": 10000.0,
                "cash_sweep_symbol": "BOXX",
            },
            "execution": {
                "trade_threshold_value": 500.0,
                "reserved_cash": 2500.0,
                "signal_display": "💎 Trend Hold",
                "dashboard_text": "dashboard",
                "separator": "━━━━━━━━━━━━━━━━━━",
                "benchmark_symbol": "QQQ",
                "benchmark_price": 400.0,
                "long_trend_value": 380.0,
                "exit_line": 360.0,
            },
        }
        translations = {
            "trade_header": "trade",
            "heartbeat_header": "heartbeat",
            "strategy_label": "strategy={name}",
            "signal_label": "signal",
            "equity": "equity",
            "buying_power": "buying_power",
            "market_sell_cmd": "sell",
            "limit_buy_cmd": "limit buy",
            "market_buy_cmd": "buy",
            "submitted": "submitted",
            "shares": "shares",
            "no_trades": "no trades",
            "market_sell": "market_sell",
            "limit_buy": "limit_buy",
            "market_buy": "market_buy",
            "failed": "failed",
            "buy_label": "buy",
            "exception": "exception",
        }

        run_strategy_core(
            object(),
            None,
            fetch_reference_history=lambda client: [{"close": 1.0, "high": 1.0, "low": 1.0}],
            fetch_managed_snapshot=lambda client: snapshot,
            fetch_managed_quotes=lambda client: quote_snapshots,
            resolve_rebalance_plan=lambda *, qqq_history, snapshot: plan,
            submit_equity_order=lambda *_args, **_kwargs: SimpleNamespace(
                status="accepted",
                broker_order_id="order-1",
                raw_payload={},
            ),
            send_tg_message=sent_messages.append,
            translator=lambda key, **kwargs: translations.get(key, key).format(**kwargs) if kwargs else translations.get(key, key),
            strategy_display_name="TQQQ Growth Income",
            limit_buy_premium=1.005,
            sell_settle_delay_sec=0,
        )

        self.assertTrue(sent_messages)
        self.assertIn("strategy=TQQQ Growth Income", sent_messages[0])

    def test_run_strategy_core_adds_plugin_context_to_heartbeat(self):
        sent_messages = []
        snapshot = SimpleNamespace(
            positions=(
                SimpleNamespace(symbol="TQQQ", quantity=100, market_value=10000.0),
                SimpleNamespace(symbol="BOXX", quantity=100, market_value=10000.0),
            ),
            total_equity=20000.0,
            buying_power=0.0,
            metadata={"account_hash": "demo"},
        )
        quote_snapshots = {
            "TQQQ": SimpleNamespace(last_price=100.0, ask_price=100.0),
            "BOXX": SimpleNamespace(last_price=100.0, ask_price=100.0),
        }
        plan = {
            "strategy_profile": "tqqq_growth_income",
            "account_hash": "demo",
            "allocation": {
                "target_mode": "value",
                "strategy_symbols": ("TQQQ", "BOXX"),
                "risk_symbols": ("TQQQ",),
                "income_symbols": (),
                "safe_haven_symbols": ("BOXX",),
                "targets": {"TQQQ": 10000.0, "BOXX": 10000.0},
            },
            "portfolio": {
                "strategy_symbols": ("TQQQ", "BOXX"),
                "portfolio_rows": (("TQQQ", "BOXX"),),
                "market_values": {"TQQQ": 10000.0, "BOXX": 10000.0},
                "quantities": {"TQQQ": 100, "BOXX": 100},
                "total_equity": 20000.0,
                "liquid_cash": 0.0,
                "cash_sweep_symbol": "BOXX",
            },
            "execution": {
                "trade_threshold_value": 500.0,
                "reserved_cash": 0.0,
                "signal_display": "Hold",
                "dashboard_text": "",
                "separator": "-----",
                "benchmark_symbol": "QQQ",
                "benchmark_price": 0.0,
                "long_trend_value": 0.0,
                "exit_line": 0.0,
            },
        }
        translations = {
            "heartbeat_header": "heartbeat",
            "strategy_label": "strategy={name}",
            "signal_label": "signal",
            "equity": "equity",
            "no_trades": "no trades",
        }

        def fail_submit(*_args, **_kwargs):
            raise AssertionError("no orders should be submitted for heartbeat")

        run_strategy_core(
            object(),
            None,
            fetch_reference_history=lambda client: [{"close": 1.0, "high": 1.0, "low": 1.0}],
            fetch_managed_snapshot=lambda client: snapshot,
            fetch_managed_quotes=lambda client: quote_snapshots,
            resolve_rebalance_plan=lambda *, qqq_history, snapshot: plan,
            submit_equity_order=fail_submit,
            send_tg_message=sent_messages.append,
            translator=lambda key, **kwargs: translations.get(key, key).format(**kwargs)
            if kwargs
            else translations.get(key, key),
            strategy_display_name="TQQQ Growth Income",
            limit_buy_premium=1.005,
            sell_settle_delay_sec=0,
            extra_notification_lines=(
                "Plugin crisis_response_shadow [shadow] no_action -> monitor",
            ),
        )

        self.assertEqual(len(sent_messages), 1)
        self.assertIn("heartbeat", sent_messages[0])
        self.assertIn(
            "Plugin crisis_response_shadow [shadow] no_action -> monitor",
            sent_messages[0],
        )
        self.assertIn("no trades", sent_messages[0])

    def test_run_strategy_core_refreshes_buying_power_after_sell_before_buying(self):
        sent_messages = []
        submitted_orders = []
        snapshots = [
            SimpleNamespace(
                positions=(
                    SimpleNamespace(symbol="TQQQ", quantity=0, market_value=0.0),
                    SimpleNamespace(symbol="BOXX", quantity=10, market_value=1000.0),
                ),
                total_equity=1200.0,
                buying_power=124.0,
                metadata={"account_hash": "demo", "phase": "before_sell"},
            ),
            SimpleNamespace(
                positions=(
                    SimpleNamespace(symbol="TQQQ", quantity=0, market_value=0.0),
                    SimpleNamespace(symbol="BOXX", quantity=1, market_value=100.0),
                ),
                total_equity=1200.0,
                buying_power=1024.0,
                metadata={"account_hash": "demo", "phase": "after_sell"},
            ),
        ]
        quote_snapshots = {
            "TQQQ": SimpleNamespace(last_price=50.0, ask_price=50.0),
            "BOXX": SimpleNamespace(last_price=100.0, ask_price=100.0),
        }
        base_execution = {
            "trade_threshold_value": 10.0,
            "reserved_cash": 0.0,
            "signal_display": "🚀 Entry",
            "dashboard_text": "dashboard",
            "separator": "━━━━━━━━━━━━━━━━━━",
            "benchmark_symbol": "QQQ",
            "benchmark_price": 400.0,
            "long_trend_value": 380.0,
            "exit_line": 380.0,
        }
        initial_plan = {
            "strategy_profile": "tqqq_growth_income",
            "account_hash": "demo",
            "allocation": {
                "target_mode": "value",
                "strategy_symbols": ("TQQQ", "BOXX"),
                "risk_symbols": ("TQQQ",),
                "income_symbols": (),
                "safe_haven_symbols": ("BOXX",),
                "targets": {"TQQQ": 900.0, "BOXX": 100.0},
            },
            "portfolio": {
                "strategy_symbols": ("TQQQ", "BOXX"),
                "portfolio_rows": (("TQQQ", "BOXX"),),
                "market_values": {"TQQQ": 0.0, "BOXX": 1000.0},
                "quantities": {"TQQQ": 0, "BOXX": 10},
                "total_equity": 1200.0,
                "liquid_cash": 124.0,
                "cash_sweep_symbol": "BOXX",
            },
            "execution": base_execution,
        }
        refreshed_plan = {
            **initial_plan,
            "portfolio": {
                "strategy_symbols": ("TQQQ", "BOXX"),
                "portfolio_rows": (("TQQQ", "BOXX"),),
                "market_values": {"TQQQ": 0.0, "BOXX": 100.0},
                "quantities": {"TQQQ": 0, "BOXX": 1},
                "total_equity": 1200.0,
                "liquid_cash": 1024.0,
                "cash_sweep_symbol": "BOXX",
            },
        }
        translations = {
            "trade_header": "trade",
            "heartbeat_header": "heartbeat",
            "strategy_label": "strategy={name}",
            "signal_label": "signal",
            "equity": "equity",
            "buying_power": "buying_power",
            "market_sell_cmd": "sell",
            "limit_buy_cmd": "limit buy",
            "market_buy_cmd": "buy",
            "submitted": "submitted",
            "shares": "shares",
            "no_trades": "no trades",
            "market_sell": "market_sell",
            "limit_buy": "limit_buy",
            "market_buy": "market_buy",
            "failed": "failed",
            "buy_label": "buy",
            "exception": "exception",
        }

        def fetch_snapshot(_client):
            return snapshots.pop(0)

        def resolve_plan(*, qqq_history, snapshot):
            self.assertEqual(len(qqq_history), 1)
            if snapshot.metadata["phase"] == "before_sell":
                return initial_plan
            return refreshed_plan

        def submit_order(_client, _account_hash, order_intent):
            submitted_orders.append(order_intent)
            return SimpleNamespace(
                status="accepted",
                broker_order_id=f"order-{len(submitted_orders)}",
                raw_payload={},
            )

        run_strategy_core(
            object(),
            None,
            fetch_reference_history=lambda client: [{"close": 1.0, "high": 1.0, "low": 1.0}],
            fetch_managed_snapshot=fetch_snapshot,
            fetch_managed_quotes=lambda client: quote_snapshots,
            resolve_rebalance_plan=resolve_plan,
            submit_equity_order=submit_order,
            send_tg_message=sent_messages.append,
            translator=lambda key, **kwargs: translations.get(key, key).format(**kwargs)
            if kwargs
            else translations.get(key, key),
            strategy_display_name="TQQQ Growth Income",
            limit_buy_premium=1.0,
            sell_settle_delay_sec=0,
        )

        self.assertEqual(len(submitted_orders), 2)
        self.assertEqual(submitted_orders[0].side, "sell")
        self.assertEqual(submitted_orders[0].symbol, "BOXX")
        self.assertEqual(submitted_orders[0].quantity, 9)
        self.assertEqual(submitted_orders[1].side, "buy")
        self.assertEqual(submitted_orders[1].symbol, "TQQQ")
        self.assertEqual(submitted_orders[1].quantity, 18)
        self.assertEqual(snapshots, [])
        self.assertTrue(sent_messages)

    def test_run_strategy_core_retries_refresh_until_sold_cash_is_available(self):
        sent_messages = []
        submitted_orders = []
        snapshots = [
            SimpleNamespace(
                positions=(
                    SimpleNamespace(symbol="TQQQ", quantity=0, market_value=0.0),
                    SimpleNamespace(symbol="BOXX", quantity=10, market_value=1000.0),
                ),
                total_equity=1200.0,
                buying_power=124.0,
                metadata={"account_hash": "demo", "phase": "before_sell"},
            ),
            SimpleNamespace(
                positions=(
                    SimpleNamespace(symbol="TQQQ", quantity=0, market_value=0.0),
                    SimpleNamespace(symbol="BOXX", quantity=1, market_value=100.0),
                ),
                total_equity=1200.0,
                buying_power=124.0,
                metadata={"account_hash": "demo", "phase": "stale_after_sell"},
            ),
            SimpleNamespace(
                positions=(
                    SimpleNamespace(symbol="TQQQ", quantity=0, market_value=0.0),
                    SimpleNamespace(symbol="BOXX", quantity=1, market_value=100.0),
                ),
                total_equity=1200.0,
                buying_power=1024.0,
                metadata={"account_hash": "demo", "phase": "settled_after_sell"},
            ),
        ]
        quote_snapshots = {
            "TQQQ": SimpleNamespace(last_price=50.0, ask_price=50.0),
            "BOXX": SimpleNamespace(last_price=100.0, ask_price=100.0),
        }
        base_execution = {
            "trade_threshold_value": 10.0,
            "reserved_cash": 0.0,
            "signal_display": "🚀 Entry",
            "dashboard_text": "dashboard",
            "separator": "━━━━━━━━━━━━━━━━━━",
            "benchmark_symbol": "QQQ",
            "benchmark_price": 400.0,
            "long_trend_value": 380.0,
            "exit_line": 380.0,
        }
        initial_plan = {
            "strategy_profile": "tqqq_growth_income",
            "account_hash": "demo",
            "allocation": {
                "target_mode": "value",
                "strategy_symbols": ("TQQQ", "BOXX"),
                "risk_symbols": ("TQQQ",),
                "income_symbols": (),
                "safe_haven_symbols": ("BOXX",),
                "targets": {"TQQQ": 900.0, "BOXX": 100.0},
            },
            "portfolio": {
                "strategy_symbols": ("TQQQ", "BOXX"),
                "portfolio_rows": (("TQQQ", "BOXX"),),
                "market_values": {"TQQQ": 0.0, "BOXX": 1000.0},
                "quantities": {"TQQQ": 0, "BOXX": 10},
                "total_equity": 1200.0,
                "liquid_cash": 124.0,
                "cash_sweep_symbol": "BOXX",
            },
            "execution": base_execution,
        }
        stale_plan = {
            **initial_plan,
            "portfolio": {
                "strategy_symbols": ("TQQQ", "BOXX"),
                "portfolio_rows": (("TQQQ", "BOXX"),),
                "market_values": {"TQQQ": 0.0, "BOXX": 100.0},
                "quantities": {"TQQQ": 0, "BOXX": 1},
                "total_equity": 1200.0,
                "liquid_cash": 124.0,
                "cash_sweep_symbol": "BOXX",
            },
        }
        settled_plan = {
            **initial_plan,
            "portfolio": {
                "strategy_symbols": ("TQQQ", "BOXX"),
                "portfolio_rows": (("TQQQ", "BOXX"),),
                "market_values": {"TQQQ": 0.0, "BOXX": 100.0},
                "quantities": {"TQQQ": 0, "BOXX": 1},
                "total_equity": 1200.0,
                "liquid_cash": 1024.0,
                "cash_sweep_symbol": "BOXX",
            },
        }
        translations = {
            "trade_header": "trade",
            "heartbeat_header": "heartbeat",
            "strategy_label": "strategy={name}",
            "signal_label": "signal",
            "equity": "equity",
            "buying_power": "buying_power",
            "market_sell_cmd": "sell",
            "limit_buy_cmd": "limit buy",
            "market_buy_cmd": "buy",
            "submitted": "submitted",
            "shares": "shares",
            "no_trades": "no trades",
            "market_sell": "market_sell",
            "limit_buy": "limit_buy",
            "market_buy": "market_buy",
            "failed": "failed",
            "buy_label": "buy",
            "exception": "exception",
        }

        def fetch_snapshot(_client):
            return snapshots.pop(0)

        def resolve_plan(*, qqq_history, snapshot):
            self.assertEqual(len(qqq_history), 1)
            phase = snapshot.metadata["phase"]
            if phase == "before_sell":
                return initial_plan
            if phase == "stale_after_sell":
                return stale_plan
            return settled_plan

        def submit_order(_client, _account_hash, order_intent):
            submitted_orders.append(order_intent)
            return SimpleNamespace(
                status="accepted",
                broker_order_id=f"order-{len(submitted_orders)}",
                raw_payload={},
            )

        run_strategy_core(
            object(),
            None,
            fetch_reference_history=lambda client: [{"close": 1.0, "high": 1.0, "low": 1.0}],
            fetch_managed_snapshot=fetch_snapshot,
            fetch_managed_quotes=lambda client: quote_snapshots,
            resolve_rebalance_plan=resolve_plan,
            submit_equity_order=submit_order,
            send_tg_message=sent_messages.append,
            translator=lambda key, **kwargs: translations.get(key, key).format(**kwargs)
            if kwargs
            else translations.get(key, key),
            strategy_display_name="TQQQ Growth Income",
            limit_buy_premium=1.0,
            sell_settle_delay_sec=0,
            post_sell_refresh_attempts=2,
            post_sell_refresh_interval_sec=0,
            sleeper=lambda _seconds: None,
        )

        self.assertEqual(len(submitted_orders), 2)
        self.assertEqual(submitted_orders[0].side, "sell")
        self.assertEqual(submitted_orders[0].symbol, "BOXX")
        self.assertEqual(submitted_orders[0].quantity, 9)
        self.assertEqual(submitted_orders[1].side, "buy")
        self.assertEqual(submitted_orders[1].symbol, "TQQQ")
        self.assertEqual(submitted_orders[1].quantity, 18)
        self.assertEqual(snapshots, [])
        self.assertTrue(sent_messages)

    def test_run_strategy_core_dry_run_skips_submit_and_marks_message(self):
        sent_messages = []
        snapshot = SimpleNamespace(
            positions=(
                SimpleNamespace(symbol="TQQQ", quantity=0, market_value=0.0),
                SimpleNamespace(symbol="BOXX", quantity=10, market_value=5000.0),
            ),
            total_equity=50000.0,
            buying_power=10000.0,
            metadata={"account_hash": "demo"},
        )
        quote_snapshots = {
            "TQQQ": SimpleNamespace(last_price=50.0, ask_price=50.1),
            "BOXX": SimpleNamespace(last_price=100.0, ask_price=100.0),
        }
        plan = {
            "strategy_profile": "tqqq_growth_income",
            "account_hash": "demo",
            "allocation": {
                "target_mode": "value",
                "strategy_symbols": ("TQQQ", "BOXX"),
                "risk_symbols": ("TQQQ",),
                "income_symbols": (),
                "safe_haven_symbols": ("BOXX",),
                "targets": {"TQQQ": 20000.0, "BOXX": 15000.0},
            },
            "portfolio": {
                "strategy_symbols": ("TQQQ", "BOXX"),
                "portfolio_rows": (("TQQQ", "BOXX"),),
                "market_values": {"TQQQ": 0.0, "BOXX": 5000.0},
                "quantities": {"TQQQ": 0, "BOXX": 10},
                "total_equity": 50000.0,
                "liquid_cash": 10000.0,
                "cash_sweep_symbol": "BOXX",
            },
            "execution": {
                "trade_threshold_value": 500.0,
                "reserved_cash": 2500.0,
                "signal_display": "💎 Trend Hold",
                "dashboard_text": "",
                "separator": "━━━━━━━━━━━━━━━━━━",
                "benchmark_symbol": "QQQ",
                "benchmark_price": 400.0,
                "long_trend_value": 380.0,
                "exit_line": 360.0,
            },
        }
        translations = {
            "trade_header": "trade",
            "heartbeat_header": "heartbeat",
            "strategy_label": "strategy={name}",
            "signal_label": "signal",
            "equity": "equity",
            "buying_power": "buying_power",
            "market_sell_cmd": "sell",
            "limit_buy_cmd": "limit buy",
            "market_buy_cmd": "buy",
            "submitted": "submitted",
            "shares": "shares",
            "no_trades": "no trades",
            "market_sell": "market_sell",
            "limit_buy": "limit_buy",
            "market_buy": "market_buy",
            "failed": "failed",
            "buy_label": "buy",
            "exception": "exception",
            "dry_run_banner": "模拟运行",
            "dry_run_trade_log": "模拟下单: {command} {symbol}: {quantity}{shares}",
            "dry_run_trade_log_with_price": "模拟下单: {command} {symbol} (${price}): {quantity}{shares}",
            "order_id_suffix": "订单号: {order_id}",
        }

        def fail_submit(*_args, **_kwargs):
            raise AssertionError("submit_equity_order should not be called in dry-run mode")

        run_strategy_core(
            object(),
            None,
            fetch_reference_history=lambda client: [{"close": 1.0, "high": 1.0, "low": 1.0}],
            fetch_managed_snapshot=lambda client: snapshot,
            fetch_managed_quotes=lambda client: quote_snapshots,
            resolve_rebalance_plan=lambda *, qqq_history, snapshot: plan,
            submit_equity_order=fail_submit,
            send_tg_message=sent_messages.append,
            translator=lambda key, **kwargs: translations.get(key, key).format(**kwargs) if kwargs else translations.get(key, key),
            strategy_display_name="TQQQ Growth Income",
            limit_buy_premium=1.005,
            sell_settle_delay_sec=0,
            dry_run_only=True,
        )

        self.assertTrue(sent_messages)
        self.assertIn("模拟运行", sent_messages[0])
        self.assertIn("模拟下单", sent_messages[0])


if __name__ == "__main__":
    unittest.main()
