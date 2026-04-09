import unittest
from unittest.mock import patch

import strategy_runtime as strategy_runtime_module
from quant_platform_kit.strategy_contracts import (
    StrategyDecision,
    StrategyManifest,
    StrategyRuntimeAdapter,
)


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


class StrategyRuntimeTests(unittest.TestCase):
    def test_runtime_exposes_managed_symbols_and_benchmark(self):
        entrypoint = _FakeEntrypoint()
        runtime = strategy_runtime_module.LoadedStrategyRuntime(
            entrypoint=entrypoint,
            runtime_adapter=StrategyRuntimeAdapter(portfolio_input_name="portfolio_snapshot"),
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
                    runtime_overrides={"benchmark_symbol": "VGT"},
                )

        mock_loader.assert_called_once_with("tqqq_growth_income")
        self.assertIs(runtime.entrypoint, entrypoint)
        self.assertEqual(runtime.benchmark_symbol, "VGT")
        self.assertEqual(runtime.managed_symbols, ("TQQQ", "BOXX", "SPYI", "QQQI"))


if __name__ == "__main__":
    unittest.main()
