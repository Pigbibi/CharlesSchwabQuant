import unittest
from types import SimpleNamespace
from unittest.mock import patch

import strategy_runtime as strategy_runtime_module
from quant_platform_kit.strategy_contracts import (
    StrategyDecision,
    StrategyManifest,
    StrategyRuntimeAdapter,
)
from runtime_config_support import PlatformRuntimeSettings


class _FakeEntrypoint:
    def __init__(self):
        self.manifest = StrategyManifest(
            profile="tqqq_growth_income",
            domain="us_equity",
            display_name="Hybrid Growth Income",
            description="test entrypoint",
            required_inputs=frozenset({"benchmark_history", "portfolio_snapshot"}),
            default_config={
                "benchmark_symbol": "QQQ",
                "managed_symbols": ("TQQQ", "BOXX", "SPYI", "QQQI"),
            },
        )

    def evaluate(self, ctx):
        self.ctx = ctx
        return StrategyDecision(diagnostics={"signal_display": "hold"})


class _TechEntrypoint:
    manifest = StrategyManifest(
        profile="qqq_tech_enhancement",
        domain="us_equity",
        display_name="QQQ Tech Enhancement",
        description="test entrypoint",
        required_inputs=frozenset({"feature_snapshot"}),
        default_config={"safe_haven": "BOXX", "benchmark_symbol": "QQQ"},
    )

    def evaluate(self, ctx):
        self.ctx = ctx
        return StrategyDecision(diagnostics={"signal_description": "risk on"})


class _RussellEntrypoint:
    manifest = StrategyManifest(
        profile="russell_1000_multi_factor_defensive",
        domain="us_equity",
        display_name="Russell 1000 Multi-Factor",
        description="test entrypoint",
        required_inputs=frozenset({"feature_snapshot"}),
        default_config={"safe_haven": "BOXX", "benchmark_symbol": "SPY"},
    )

    def evaluate(self, ctx):
        self.ctx = ctx
        return StrategyDecision(diagnostics={"signal_description": "broad risk on"})


def _build_runtime_settings(profile: str, *, feature_snapshot_path: str | None = None) -> PlatformRuntimeSettings:
    return PlatformRuntimeSettings(
        strategy_profile=profile,
        strategy_display_name=(
            "QQQ Tech Enhancement" if profile == "qqq_tech_enhancement" else "TQQQ Growth Income"
        ),
        strategy_domain="us_equity",
        notify_lang="en",
        dry_run_only=False,
        feature_snapshot_path=feature_snapshot_path,
        feature_snapshot_manifest_path=None,
        strategy_config_path=None,
        strategy_config_source=None,
    )


class StrategyRuntimeTests(unittest.TestCase):
    def test_runtime_exposes_managed_symbols_and_benchmark(self):
        entrypoint = _FakeEntrypoint()
        runtime = strategy_runtime_module.LoadedStrategyRuntime(
            entrypoint=entrypoint,
            runtime_adapter=StrategyRuntimeAdapter(portfolio_input_name="portfolio_snapshot"),
            runtime_settings=_build_runtime_settings("tqqq_growth_income"),
            merged_runtime_config={
                "benchmark_symbol": "QQQ",
                "managed_symbols": ("TQQQ", "BOXX", "SPYI", "QQQI"),
            },
        )

        result = runtime.evaluate(
            benchmark_history=[{"close": 1.0, "high": 1.0, "low": 1.0}],
            portfolio_snapshot=object(),
            signal_text_fn=str,
            translator=lambda key, **_kwargs: key,
        )

        self.assertEqual(runtime.managed_symbols, ("TQQQ", "BOXX", "SPYI", "QQQI"))
        self.assertEqual(runtime.benchmark_symbol, "QQQ")
        self.assertIn("signal_text_fn", entrypoint.ctx.runtime_config)
        self.assertEqual(result.metadata["strategy_profile"], "tqqq_growth_income")

    def test_market_history_runtime_loads_loader_into_context(self):
        class _GlobalEntrypoint:
            manifest = StrategyManifest(
                profile="global_etf_rotation",
                domain="us_equity",
                display_name="Global ETF Rotation",
                description="test entrypoint",
                required_inputs=frozenset({"market_history"}),
                default_config={"safe_haven": "BIL", "ranking_pool": ("VOO", "VGK")},
            )

            def evaluate(self, ctx):
                self.ctx = ctx
                return StrategyDecision(diagnostics={"signal_description": "quarterly"})

        entrypoint = _GlobalEntrypoint()
        runtime = strategy_runtime_module.LoadedStrategyRuntime(
            entrypoint=entrypoint,
            runtime_adapter=StrategyRuntimeAdapter(portfolio_input_name="portfolio_snapshot"),
            runtime_settings=_build_runtime_settings("global_etf_rotation"),
            merged_runtime_config={"safe_haven": "BIL", "ranking_pool": ("VOO", "VGK")},
        )

        def market_history_loader(*_args, **_kwargs):
            return [1.0, 2.0, 3.0]

        snapshot = object()
        result = runtime.evaluate(
            market_history=market_history_loader,
            portfolio_snapshot=snapshot,
            signal_text_fn=str,
            translator=lambda key, **_kwargs: key,
        )

        self.assertIs(entrypoint.ctx.market_data["market_history"], market_history_loader)
        self.assertIs(entrypoint.ctx.portfolio, snapshot)
        self.assertEqual(result.metadata["strategy_profile"], "global_etf_rotation")

    def test_load_strategy_runtime_merges_overrides_on_top_of_entrypoint_defaults(self):
        entrypoint = _FakeEntrypoint()

        with patch.object(strategy_runtime_module, "load_strategy_entrypoint_for_profile", return_value=entrypoint) as mock_loader:
            with patch.object(
                strategy_runtime_module,
                "load_strategy_runtime_adapter_for_profile",
                return_value=StrategyRuntimeAdapter(portfolio_input_name="portfolio_snapshot"),
            ):
                runtime = strategy_runtime_module.load_strategy_runtime(
                    "tqqq_growth_income",
                    runtime_settings=_build_runtime_settings("tqqq_growth_income"),
                    runtime_overrides={"benchmark_symbol": "VGT"},
                )

        mock_loader.assert_called_once_with("tqqq_growth_income")
        self.assertIs(runtime.entrypoint, entrypoint)
        self.assertEqual(runtime.benchmark_symbol, "VGT")
        self.assertEqual(runtime.managed_symbols, ("TQQQ", "BOXX", "SPYI", "QQQI"))

    def test_feature_snapshot_runtime_loads_snapshot_into_context(self):
        entrypoint = _TechEntrypoint()
        runtime = strategy_runtime_module.LoadedStrategyRuntime(
            entrypoint=entrypoint,
            runtime_adapter=StrategyRuntimeAdapter(
                status_icon="🧲",
                required_feature_columns=frozenset({"symbol", "close", "as_of"}),
                snapshot_date_columns=("as_of",),
                require_snapshot_manifest=False,
                managed_symbols_extractor=lambda *_args, **_kwargs: ("AAPL", "MSFT", "BOXX"),
                portfolio_input_name="portfolio_snapshot",
            ),
            runtime_settings=_build_runtime_settings(
                "qqq_tech_enhancement",
                feature_snapshot_path="gs://bucket/tech.csv",
            ),
            merged_runtime_config={"safe_haven": "BOXX", "benchmark_symbol": "QQQ"},
            logger=lambda _message: None,
        )

        with patch.object(
            strategy_runtime_module,
            "load_feature_snapshot_guarded",
            return_value=SimpleNamespace(
                frame=[
                    {"as_of": "2026-04-08", "symbol": "AAPL", "close": 100.0},
                    {"as_of": "2026-04-08", "symbol": "MSFT", "close": 200.0},
                ],
                metadata={"snapshot_guard_decision": "proceed", "snapshot_as_of": "2026-04-08"},
            ),
        ):
            result = runtime.evaluate(
                portfolio_snapshot=object(),
                translator=lambda key, **_kwargs: key,
                signal_text_fn=str,
            )

        self.assertEqual(entrypoint.ctx.market_data["feature_snapshot"][0]["symbol"], "AAPL")
        self.assertEqual(result.metadata["managed_symbols"], ("AAPL", "MSFT", "BOXX"))
        self.assertEqual(result.metadata["status_icon"], "🧲")

    def test_feature_snapshot_runtime_loads_russell_snapshot_into_context(self):
        entrypoint = _RussellEntrypoint()
        runtime = strategy_runtime_module.LoadedStrategyRuntime(
            entrypoint=entrypoint,
            runtime_adapter=StrategyRuntimeAdapter(
                status_icon="📏",
                required_feature_columns=frozenset({"symbol", "sector", "mom_6_1", "mom_12_1", "sma200_gap", "vol_63", "maxdd_126"}),
                managed_symbols_extractor=lambda *_args, **_kwargs: ("AAPL", "MSFT", "BOXX"),
                portfolio_input_name="portfolio_snapshot",
            ),
            runtime_settings=_build_runtime_settings(
                "russell_1000_multi_factor_defensive",
                feature_snapshot_path="gs://bucket/russell.csv",
            ),
            merged_runtime_config={"safe_haven": "BOXX", "benchmark_symbol": "SPY"},
            logger=lambda _message: None,
        )

        with patch.object(
            strategy_runtime_module,
            "load_feature_snapshot_guarded",
            return_value=SimpleNamespace(
                frame=[
                    {"symbol": "SPY", "sector": "Benchmark", "mom_6_1": 0.1, "mom_12_1": 0.2, "sma200_gap": 0.03, "vol_63": 0.15, "maxdd_126": -0.12},
                    {"symbol": "AAPL", "sector": "Technology", "mom_6_1": 0.3, "mom_12_1": 0.4, "sma200_gap": 0.08, "vol_63": 0.20, "maxdd_126": -0.10},
                ],
                metadata={"snapshot_guard_decision": "proceed", "snapshot_as_of": "2026-04-08"},
            ),
        ):
            result = runtime.evaluate(
                portfolio_snapshot=object(),
                translator=lambda key, **_kwargs: key,
                signal_text_fn=str,
            )

        self.assertEqual(entrypoint.ctx.market_data["feature_snapshot"][1]["symbol"], "AAPL")
        self.assertEqual(result.metadata["managed_symbols"], ("AAPL", "MSFT", "BOXX"))
        self.assertEqual(result.metadata["status_icon"], "📏")


if __name__ == "__main__":
    unittest.main()
