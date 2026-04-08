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
from strategy_registry import (
    SCHWAB_PLATFORM,
    US_EQUITY_DOMAIN,
    get_eligible_profiles_for_platform,
    get_platform_profile_matrix,
    get_supported_profiles_for_platform,
)


class RuntimeConfigSupportTests(unittest.TestCase):
    def test_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = load_platform_runtime_settings()

        self.assertEqual(settings.strategy_profile, DEFAULT_STRATEGY_PROFILE)
        self.assertEqual(settings.strategy_display_name, "QQQ/TQQQ Growth Income")
        self.assertEqual(settings.strategy_domain, US_EQUITY_DOMAIN)
        self.assertEqual(settings.notify_lang, DEFAULT_NOTIFY_LANG)
        self.assertFalse(settings.dry_run_only)

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
            frozenset({DEFAULT_STRATEGY_PROFILE, "semiconductor_rotation_income"}),
        )

    def test_platform_eligible_profiles_are_exposed_by_capability_matrix(self):
        self.assertEqual(
            get_eligible_profiles_for_platform(SCHWAB_PLATFORM),
            frozenset({DEFAULT_STRATEGY_PROFILE, "semiconductor_rotation_income"}),
        )

    def test_accepts_human_readable_alias(self):
        with patch.dict(os.environ, {"STRATEGY_PROFILE": "qqq_tqqq_growth_income"}, clear=True):
            settings = load_platform_runtime_settings()

        self.assertEqual(settings.strategy_profile, DEFAULT_STRATEGY_PROFILE)

    def test_reads_schwab_dry_run_only_flag(self):
        with patch.dict(os.environ, {"SCHWAB_DRY_RUN_ONLY": "true"}, clear=True):
            settings = load_platform_runtime_settings()

        self.assertTrue(settings.dry_run_only)

    def test_platform_profile_matrix_marks_default(self):
        rows = get_platform_profile_matrix()
        by_profile = {row["canonical_profile"]: row for row in rows}
        self.assertEqual(by_profile[DEFAULT_STRATEGY_PROFILE]["display_name"], "QQQ/TQQQ Growth Income")
        self.assertTrue(by_profile[DEFAULT_STRATEGY_PROFILE]["is_default"])
        self.assertIn("semiconductor_rotation_income", by_profile)



if __name__ == "__main__":
    unittest.main()
