import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
QPK_SRC = ROOT.parent / "QuantPlatformKit" / "src"
if str(QPK_SRC) not in sys.path:
    sys.path.insert(0, str(QPK_SRC))


from runtime_config_support import (  # noqa: E402
    DEFAULT_NOTIFY_LANG,
    DEFAULT_STRATEGY_PROFILE,
    load_platform_runtime_settings,
)
from strategy_registry import SCHWAB_PLATFORM, US_EQUITY_DOMAIN, get_supported_profiles_for_platform


class RuntimeConfigSupportTests(unittest.TestCase):
    def test_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = load_platform_runtime_settings()

        self.assertEqual(settings.strategy_profile, DEFAULT_STRATEGY_PROFILE)
        self.assertEqual(settings.strategy_domain, US_EQUITY_DOMAIN)
        self.assertEqual(settings.notify_lang, DEFAULT_NOTIFY_LANG)

    def test_uses_explicit_strategy_profile(self):
        with patch.dict(os.environ, {"STRATEGY_PROFILE": DEFAULT_STRATEGY_PROFILE}, clear=True):
            settings = load_platform_runtime_settings()

        self.assertEqual(settings.strategy_profile, DEFAULT_STRATEGY_PROFILE)

    def test_rejects_unknown_strategy_profile(self):
        with patch.dict(os.environ, {"STRATEGY_PROFILE": "balanced_income"}, clear=True):
            with self.assertRaisesRegex(ValueError, "Unsupported STRATEGY_PROFILE"):
                load_platform_runtime_settings()

    def test_platform_supported_profiles_are_filtered_by_registry(self):
        self.assertEqual(
            get_supported_profiles_for_platform(SCHWAB_PLATFORM),
            frozenset({DEFAULT_STRATEGY_PROFILE}),
        )


if __name__ == "__main__":
    unittest.main()
