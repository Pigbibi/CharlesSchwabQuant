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
        runtime_adapter=types.SimpleNamespace(
            available_inputs=frozenset({"benchmark_history", "portfolio_snapshot"})
        ),
        evaluate=lambda **_kwargs: None,
    )

    runtime_config_support_module = types.ModuleType("runtime_config_support")
    runtime_config_support_module.load_platform_runtime_settings = lambda: types.SimpleNamespace(
        strategy_profile="tqqq_growth_income",
        strategy_display_name="TQQQ Growth Income",
        strategy_domain="us_equity",
        notify_lang="en",
        dry_run_only=False,
        reserved_cash_floor_usd=150.0,
        reserved_cash_ratio=0.03,
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


class SharedChatIdTests(unittest.TestCase):
    def test_global_telegram_chat_id_is_used(self):
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
                module = importlib.reload(module)

        self.assertEqual(module.TG_CHAT_ID, "shared-chat-id")
        self.assertEqual(module.SECRET_ID, "schwab_token")


if __name__ == "__main__":
    unittest.main()
