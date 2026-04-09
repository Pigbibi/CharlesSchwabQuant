import json
import os
import subprocess
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
SCRIPT_PATH = ROOT / "scripts" / "print_strategy_profile_status.py"


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
    get_platform_profile_status_matrix,
    get_supported_profiles_for_platform,
)


class RuntimeConfigSupportTests(unittest.TestCase):
    def test_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = load_platform_runtime_settings()

        self.assertEqual(settings.strategy_profile, DEFAULT_STRATEGY_PROFILE)
        self.assertEqual(settings.strategy_display_name, "TQQQ Growth Income")
        self.assertEqual(settings.strategy_domain, US_EQUITY_DOMAIN)
        self.assertEqual(settings.notify_lang, DEFAULT_NOTIFY_LANG)
        self.assertFalse(settings.dry_run_only)
        self.assertIsNone(settings.feature_snapshot_path)
        self.assertIsNone(settings.feature_snapshot_manifest_path)
        self.assertIsNone(settings.strategy_config_path)
        self.assertIsNone(settings.strategy_config_source)

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
            frozenset(
                {
                    DEFAULT_STRATEGY_PROFILE,
                    "global_etf_rotation",
                    "russell_1000_multi_factor_defensive",
                    "soxl_soxx_trend_income",
                    "qqq_tech_enhancement",
                }
            ),
        )

    def test_platform_eligible_profiles_are_exposed_by_capability_matrix(self):
        self.assertEqual(
            get_eligible_profiles_for_platform(SCHWAB_PLATFORM),
            frozenset(
                {
                    DEFAULT_STRATEGY_PROFILE,
                    "global_etf_rotation",
                    "russell_1000_multi_factor_defensive",
                    "soxl_soxx_trend_income",
                    "qqq_tech_enhancement",
                }
            ),
        )

    def test_rejects_human_readable_alias(self):
        with patch.dict(os.environ, {"STRATEGY_PROFILE": "qqq_tqqq_growth_income"}, clear=True):
            with self.assertRaises(ValueError):
                load_platform_runtime_settings()

    def test_reads_schwab_dry_run_only_flag(self):
        with patch.dict(os.environ, {"SCHWAB_DRY_RUN_ONLY": "true"}, clear=True):
            settings = load_platform_runtime_settings()

        self.assertTrue(settings.dry_run_only)

    def test_platform_profile_matrix_marks_default(self):
        rows = get_platform_profile_matrix()
        by_profile = {row["canonical_profile"]: row for row in rows}
        self.assertEqual(by_profile[DEFAULT_STRATEGY_PROFILE]["display_name"], "TQQQ Growth Income")
        self.assertTrue(by_profile[DEFAULT_STRATEGY_PROFILE]["is_default"])
        self.assertIn("soxl_soxx_trend_income", by_profile)
        self.assertIn("global_etf_rotation", by_profile)
        self.assertIn("russell_1000_multi_factor_defensive", by_profile)
        self.assertIn("qqq_tech_enhancement", by_profile)

    def test_platform_profile_status_matrix_matches_current_schwab_rollout(self):
        rows = get_platform_profile_status_matrix()
        by_profile = {row["canonical_profile"]: row for row in rows}

        self.assertEqual(
            set(by_profile),
            {
                "tqqq_growth_income",
                "global_etf_rotation",
                "russell_1000_multi_factor_defensive",
                "soxl_soxx_trend_income",
                "qqq_tech_enhancement",
            },
        )
        self.assertEqual(
            by_profile["tqqq_growth_income"],
            {
                "canonical_profile": "tqqq_growth_income",
                "display_name": "TQQQ Growth Income",
                "domain": "us_equity",
                "eligible": True,
                "enabled": True,
                "is_default": True,
                "is_rollback": True,
                "platform": "schwab",
            },
        )
        self.assertEqual(
            by_profile["global_etf_rotation"]["display_name"],
            "Global ETF Rotation",
        )
        self.assertTrue(by_profile["global_etf_rotation"]["eligible"])
        self.assertTrue(by_profile["global_etf_rotation"]["enabled"])
        self.assertEqual(
            by_profile["russell_1000_multi_factor_defensive"]["display_name"],
            "Russell 1000 Multi-Factor",
        )
        self.assertTrue(by_profile["russell_1000_multi_factor_defensive"]["eligible"])
        self.assertTrue(by_profile["russell_1000_multi_factor_defensive"]["enabled"])
        self.assertEqual(
            by_profile["soxl_soxx_trend_income"]["display_name"],
            "SOXL/SOXX Semiconductor Trend Income",
        )
        self.assertTrue(by_profile["soxl_soxx_trend_income"]["eligible"])
        self.assertTrue(by_profile["soxl_soxx_trend_income"]["enabled"])
        self.assertEqual(
            by_profile["qqq_tech_enhancement"]["display_name"],
            "QQQ Tech Enhancement",
        )
        self.assertTrue(by_profile["qqq_tech_enhancement"]["eligible"])
        self.assertTrue(by_profile["qqq_tech_enhancement"]["enabled"])

    def test_print_strategy_profile_status_json_matches_registry(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--json"],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertEqual(json.loads(result.stdout), get_platform_profile_status_matrix())

    def test_print_strategy_profile_status_table_contains_expected_headers(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertIn("canonical_profile", result.stdout)
        self.assertIn("display_name", result.stdout)
        self.assertIn("tqqq_growth_income", result.stdout)
        self.assertIn("global_etf_rotation", result.stdout)
        self.assertIn("russell_1000_multi_factor_defensive", result.stdout)
        self.assertIn("TQQQ Growth Income", result.stdout)
        self.assertIn("Global ETF Rotation", result.stdout)
        self.assertIn("Russell 1000 Multi-Factor", result.stdout)
        self.assertIn("QQQ Tech Enhancement", result.stdout)

    def test_loads_feature_snapshot_env_for_tech_profile(self):
        with patch.dict(
            os.environ,
            {
                "STRATEGY_PROFILE": "qqq_tech_enhancement",
                "SCHWAB_FEATURE_SNAPSHOT_PATH": "gs://bucket/tech.csv",
                "SCHWAB_FEATURE_SNAPSHOT_MANIFEST_PATH": "gs://bucket/tech.csv.manifest.json",
                "SCHWAB_STRATEGY_CONFIG_PATH": "/workspace/configs/tech.json",
            },
            clear=True,
        ):
            settings = load_platform_runtime_settings()

        self.assertEqual(settings.strategy_profile, "qqq_tech_enhancement")
        self.assertEqual(settings.feature_snapshot_path, "gs://bucket/tech.csv")
        self.assertEqual(settings.feature_snapshot_manifest_path, "gs://bucket/tech.csv.manifest.json")
        self.assertEqual(settings.strategy_config_path, "/workspace/configs/tech.json")
        self.assertEqual(settings.strategy_config_source, "env")



if __name__ == "__main__":
    unittest.main()
