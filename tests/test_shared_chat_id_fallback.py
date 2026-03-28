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


def install_stub_modules():
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


class SharedChatIdFallbackTests(unittest.TestCase):
    def test_global_telegram_chat_id_is_used_when_service_chat_id_missing(self):
        with install_stub_modules():
            with patch.dict(
                os.environ,
                {
                    "SCHWAB_API_KEY": "app-key",
                    "SCHWAB_APP_SECRET": "app-secret",
                    "TELEGRAM_CHAT_ID": "",
                    "GLOBAL_TELEGRAM_CHAT_ID": "shared-chat-id",
                },
                clear=False,
            ):
                sys.modules.pop("main", None)
                module = importlib.import_module("main")
                module = importlib.reload(module)

        self.assertEqual(module.TG_CHAT_ID, "shared-chat-id")


if __name__ == "__main__":
    unittest.main()
