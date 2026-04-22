import importlib
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
PLATFORM_KIT_SRC = ROOT.parent / "QuantPlatformKit" / "src"
if str(PLATFORM_KIT_SRC) not in sys.path:
    sys.path.insert(0, str(PLATFORM_KIT_SRC))


def install_stub_modules(strategy_plugin_mounts_json=None, notify_lang="en"):
    flask_module = types.ModuleType("flask")

    class Flask:
        def __init__(self, _name):
            self._routes = {}

        def route(self, path, methods=None):
            def decorator(func):
                self._routes[(path, tuple(methods or []))] = func
                return func

            return decorator

        def test_request_context(self, *_args, **_kwargs):
            class _Context:
                def __enter__(self_inner):
                    return self_inner

                def __exit__(self_inner, exc_type, exc, tb):
                    return False

            return _Context()

        def run(self, *args, **kwargs):
            return None

    flask_module.Flask = Flask

    requests_module = types.ModuleType("requests")
    requests_module.post = lambda *args, **kwargs: None
    pandas_module = types.ModuleType("pandas")

    rebalance_service_module = types.ModuleType("application.rebalance_service")
    rebalance_service_module.run_strategy_core = lambda *args, **kwargs: None

    cloud_run_module = types.ModuleType("entrypoints.cloud_run")
    cloud_run_module.is_market_open_today = lambda: True

    runtime_config_support_module = types.ModuleType("runtime_config_support")
    runtime_config_support_module.load_platform_runtime_settings = lambda: types.SimpleNamespace(
        strategy_profile="tqqq_growth_income",
        strategy_display_name="TQQQ Growth Income",
        strategy_domain="us_equity",
        notify_lang=notify_lang,
        dry_run_only=False,
        reserved_cash_floor_usd=150.0,
        reserved_cash_ratio=0.03,
        strategy_plugin_mounts_json=strategy_plugin_mounts_json,
    )

    strategy_runtime_module = types.ModuleType("strategy_runtime")
    strategy_runtime_module.load_strategy_runtime = lambda *_args, **_kwargs: types.SimpleNamespace(
        merged_runtime_config={
            "benchmark_symbol": "QQQ",
            "managed_symbols": ("TQQQ", "BOXX", "SPYI", "QQQI"),
        },
        managed_symbols=("TQQQ", "BOXX", "SPYI", "QQQI"),
        benchmark_symbol="QQQ",
        runtime_adapter=types.SimpleNamespace(
            available_inputs=frozenset({"benchmark_history", "portfolio_snapshot"}),
            runtime_policy=types.SimpleNamespace(signal_effective_after_trading_days=1),
        ),
        evaluate=lambda **_kwargs: None,
    )

    google_module = types.ModuleType("google")
    google_module.__path__ = []

    google_auth_module = types.ModuleType("google.auth")
    google_auth_module.default = lambda *args, **kwargs: (None, None)

    google_cloud_module = types.ModuleType("google.cloud")
    google_cloud_module.__path__ = []
    google_secretmanager_module = types.ModuleType("google.cloud.secretmanager_v1")

    schwab_module = types.ModuleType("schwab")
    auth_module = types.ModuleType("schwab.auth")
    client_module = types.ModuleType("schwab.client")
    equities_module = types.ModuleType("schwab.orders.equities")
    equities_module.equity_buy_market = lambda *args, **kwargs: None
    equities_module.equity_sell_market = lambda *args, **kwargs: None
    equities_module.equity_buy_limit = lambda *args, **kwargs: None

    pandas_market_calendars = types.ModuleType("pandas_market_calendars")

    modules = {
        "flask": flask_module,
        "requests": requests_module,
        "pandas": pandas_module,
        "application.rebalance_service": rebalance_service_module,
        "entrypoints.cloud_run": cloud_run_module,
        "runtime_config_support": runtime_config_support_module,
        "strategy_runtime": strategy_runtime_module,
        "google": google_module,
        "google.auth": google_auth_module,
        "google.cloud": google_cloud_module,
        "google.cloud.secretmanager_v1": google_secretmanager_module,
        "schwab": schwab_module,
        "schwab.auth": auth_module,
        "schwab.client": client_module,
        "schwab.orders.equities": equities_module,
        "pandas_market_calendars": pandas_market_calendars,
    }
    return patch.dict(sys.modules, modules)


def load_module(*, strategy_plugin_mounts_json=None, notify_lang="en"):
    with install_stub_modules(
        strategy_plugin_mounts_json=strategy_plugin_mounts_json,
        notify_lang=notify_lang,
    ):
        with patch.dict(
            os.environ,
            {
                "SCHWAB_API_KEY": "app-key",
                "SCHWAB_APP_SECRET": "app-secret",
                "GLOBAL_TELEGRAM_CHAT_ID": "shared-chat-id",
            },
            clear=False,
        ):
            sys.modules.pop("main", None)
            module = importlib.import_module("main")
            return importlib.reload(module)


class RequestHandlingTests(unittest.TestCase):
    def test_handle_schwab_returns_market_closed(self):
        module = load_module()
        module.get_client_from_secret = lambda *args, **kwargs: object()
        module.is_market_open_today = lambda: False
        module.run_strategy_core = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not run"))

        with module.app.test_request_context("/", method="POST"):
            body, status = module.handle_schwab()

        self.assertEqual(status, 200)
        self.assertEqual(body, "Market Closed")

    def test_handle_schwab_runs_strategy_when_market_open(self):
        module = load_module()
        observed = {"called": False}

        module.get_client_from_secret = lambda *args, **kwargs: object()
        module.is_market_open_today = lambda: True

        def fake_run_strategy_core(client, now_ny, **_kwargs):
            observed["called"] = True
            self.assertIsNotNone(client)
            self.assertIsNone(now_ny)

        module.run_strategy_core = fake_run_strategy_core

        with module.app.test_request_context("/", method="POST"):
            body, status = module.handle_schwab()

        self.assertEqual(status, 200)
        self.assertEqual(body, "OK")
        self.assertTrue(observed["called"])

    def test_handle_schwab_emits_structured_runtime_events(self):
        module = load_module()
        observed = []

        module.build_run_id = lambda: "run-001"
        module.emit_runtime_log = lambda context, event, **fields: observed.append((context.run_id, event, fields))
        module.get_client_from_secret = lambda *args, **kwargs: object()
        module.is_market_open_today = lambda: True
        module.run_strategy_core = lambda *_args, **_kwargs: None

        with module.app.test_request_context("/", method="POST"):
            body, status = module.handle_schwab()

        self.assertEqual(status, 200)
        self.assertEqual(body, "OK")
        self.assertEqual(
            [event for _run_id, event, _fields in observed],
            ["strategy_cycle_received", "strategy_cycle_started", "strategy_cycle_completed"],
        )
        self.assertTrue(all(run_id == "run-001" for run_id, _event, _fields in observed))

    def test_handle_schwab_persists_machine_readable_report(self):
        module = load_module()
        observed = {}

        module.build_run_id = lambda: "run-001"
        module.get_client_from_secret = lambda *args, **kwargs: object()
        module.is_market_open_today = lambda: True
        module.run_strategy_core = lambda *_args, **_kwargs: None
        module.persist_execution_report = lambda report: observed.setdefault("report", report) or "/tmp/report.json"

        with module.app.test_request_context("/", method="POST"):
            body, status = module.handle_schwab()

        self.assertEqual(status, 200)
        self.assertEqual(body, "OK")
        self.assertEqual(observed["report"]["status"], "ok")
        self.assertEqual(observed["report"]["strategy_profile"], "tqqq_growth_income")
        self.assertEqual(
            observed["report"]["summary"]["strategy_display_name"],
            "TQQQ Growth Income",
        )
        self.assertEqual(observed["report"]["run_source"], "cloud_run")
        self.assertFalse(observed["report"]["dry_run"])
        self.assertEqual(
            observed["report"]["summary"]["managed_symbols"],
            ["TQQQ", "BOXX", "SPYI", "QQQI"],
        )
        self.assertEqual(observed["report"]["summary"]["execution_timing_contract"], "next_trading_day")
        self.assertTrue(observed["report"]["summary"]["signal_date"])
        self.assertTrue(observed["report"]["summary"]["effective_date"])

    def test_handle_schwab_attaches_strategy_plugin_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            signal_path = Path(temp_dir) / "latest_signal.json"
            signal_path.write_text(
                json.dumps(
                    {
                        "strategy": "tqqq_growth_income",
                        "plugin": "crisis_response_shadow",
                        "mode": "shadow",
                        "configured_mode": "shadow",
                        "effective_mode": "shadow",
                        "schema_version": "crisis_response_shadow.v1",
                        "as_of": "2026-04-17",
                        "canonical_route": "no_action",
                        "suggested_action": "monitor",
                        "would_trade_if_enabled": False,
                        "execution_controls": {
                            "broker_order_allowed": False,
                            "live_allocation_mutation_allowed": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            mount_config = json.dumps(
                {
                    "strategy_plugins": [
                        {
                            "strategy": "tqqq_growth_income",
                            "plugin": "crisis_response_shadow",
                            "signal_path": str(signal_path),
                            "enabled": True,
                        }
                    ]
                }
            )
            module = load_module(strategy_plugin_mounts_json=mount_config)
            observed = {}

            module.get_client_from_secret = lambda *args, **kwargs: object()
            module.is_market_open_today = lambda: True
            module.persist_execution_report = (
                lambda report: observed.setdefault("report", report) or "/tmp/report.json"
            )

            def fake_run_strategy_core(client, now_ny, *, strategy_plugin_signals=()):
                observed["signals"] = strategy_plugin_signals
                self.assertIsNotNone(client)
                self.assertIsNone(now_ny)

            module.run_strategy_core = fake_run_strategy_core

            with module.app.test_request_context("/", method="POST"):
                body, status = module.handle_schwab()

        self.assertEqual(status, 200)
        self.assertEqual(body, "OK")
        self.assertEqual(len(observed["signals"]), 1)
        plugin_summary = observed["report"]["summary"]["strategy_plugins"][0]
        self.assertEqual(plugin_summary["strategy"], "tqqq_growth_income")
        self.assertEqual(plugin_summary["plugin"], "crisis_response_shadow")
        self.assertEqual(plugin_summary["effective_mode"], "shadow")
        self.assertEqual(plugin_summary["canonical_route"], "no_action")
        self.assertEqual(plugin_summary["suggested_action"], "monitor")

    def test_strategy_plugin_notification_line_uses_i18n(self):
        module = load_module(notify_lang="zh")
        signal = types.SimpleNamespace(
            plugin="crisis_response_shadow",
            effective_mode="shadow",
            canonical_route="no_action",
            suggested_action="watch_only",
        )

        lines = module.build_strategy_plugin_notification_lines((signal,))

        self.assertEqual(len(lines), 1)
        self.assertIn("插件：危机响应观察", lines[0])
        self.assertIn("模式：影子观察", lines[0])
        self.assertIn("路由：不操作", lines[0])
        self.assertIn("建议：仅观察", lines[0])

    def test_handle_schwab_reports_plugin_config_error_without_blocking_strategy(self):
        mount_config = json.dumps(
            {
                "strategy_plugins": [
                    {
                        "strategy": "tqqq_growth_income",
                        "plugin": "crisis_response_shadow",
                        "mode": "shadow",
                        "signal_path": "/tmp/missing_signal.json",
                    }
                ]
            }
        )
        module = load_module(strategy_plugin_mounts_json=mount_config)
        observed = {"called": False}

        module.get_client_from_secret = lambda *args, **kwargs: object()
        module.is_market_open_today = lambda: True
        module.persist_execution_report = lambda report: observed.setdefault("report", report) or "/tmp/report.json"

        def fake_run_strategy_core(client, now_ny, *, strategy_plugin_signals=()):
            observed["called"] = True
            self.assertEqual(strategy_plugin_signals, ())

        module.run_strategy_core = fake_run_strategy_core

        with module.app.test_request_context("/", method="POST"):
            body, status = module.handle_schwab()

        self.assertEqual(status, 200)
        self.assertEqual(body, "OK")
        self.assertTrue(observed["called"])
        self.assertIn(
            "platform plugin mount config must not set mode",
            observed["report"]["diagnostics"]["strategy_plugin_error"],
        )

    def test_build_account_state_from_snapshot_uses_strategy_symbols(self):
        module = load_module()
        snapshot = types.SimpleNamespace(
            total_equity=50000.0,
            buying_power=12000.0,
            positions=(
                types.SimpleNamespace(symbol="TQQQ", quantity=5, market_value=1000.0),
                types.SimpleNamespace(symbol="BOXX", quantity=10, market_value=5000.0),
                types.SimpleNamespace(symbol="QQQ", quantity=99, market_value=9999.0),
            ),
            metadata={"cash_available_for_trading": 8000.0},
        )

        account_state = module.build_account_state_from_snapshot(snapshot)

        self.assertEqual(account_state["available_cash"], 8000.0)
        self.assertEqual(account_state["market_values"]["TQQQ"], 1000.0)
        self.assertEqual(account_state["market_values"]["BOXX"], 5000.0)
        self.assertNotIn("QQQ", account_state["market_values"])
        self.assertEqual(account_state["total_strategy_equity"], 50000.0)

    def test_build_semiconductor_indicators_uses_soxl_and_soxx_histories(self):
        module = load_module()

        def fake_history(_client, symbol):
            if symbol == "SOXL":
                return [{"close": 100.0 + idx} for idx in range(160)]
            if symbol == "SOXX":
                return [{"close": 210.0 + idx} for idx in range(160)]
            raise AssertionError(f"unexpected symbol {symbol}")

        module.fetch_default_daily_price_history_candles = fake_history

        indicators = module.build_semiconductor_indicators(object(), trend_window=150)

        self.assertEqual(indicators["soxl"]["price"], 259.0)
        self.assertAlmostEqual(indicators["soxl"]["ma_trend"], sum(100.0 + idx for idx in range(10, 160)) / 150)
        self.assertEqual(indicators["soxx"]["price"], 369.0)
        self.assertAlmostEqual(indicators["soxx"]["ma_trend"], sum(210.0 + idx for idx in range(10, 160)) / 150)
        self.assertAlmostEqual(indicators["soxx"]["ma20"], sum(210.0 + idx for idx in range(140, 160)) / 20)
        self.assertGreater(indicators["soxx"]["ma20_slope"], 0.0)


if __name__ == "__main__":
    unittest.main()
