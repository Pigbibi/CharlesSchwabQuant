import importlib
import os
import sys
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


def install_stub_modules():
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

    rebalance_service_module = types.ModuleType("application.rebalance_service")
    rebalance_service_module.run_strategy_core = lambda *args, **kwargs: None

    cloud_run_module = types.ModuleType("entrypoints.cloud_run")
    cloud_run_module.is_market_open_today = lambda: True

    strategy_runtime_module = types.ModuleType("strategy_runtime")
    strategy_runtime_module.load_strategy_runtime = lambda *_args, **_kwargs: types.SimpleNamespace(
        merged_runtime_config={
            "benchmark_symbol": "QQQ",
            "managed_symbols": ("TQQQ", "BOXX", "SPYI", "QQQI"),
        },
        managed_symbols=("TQQQ", "BOXX", "SPYI", "QQQI"),
        benchmark_symbol="QQQ",
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
        "application.rebalance_service": rebalance_service_module,
        "entrypoints.cloud_run": cloud_run_module,
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


def load_module():
    with install_stub_modules():
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

        def fake_run_strategy_core(client, now_ny):
            observed["called"] = True
            self.assertIsNotNone(client)
            self.assertIsNone(now_ny)

        module.run_strategy_core = fake_run_strategy_core

        with module.app.test_request_context("/", method="POST"):
            body, status = module.handle_schwab()

        self.assertEqual(status, 200)
        self.assertEqual(body, "OK")
        self.assertTrue(observed["called"])


if __name__ == "__main__":
    unittest.main()
