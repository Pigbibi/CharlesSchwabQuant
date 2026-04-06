import unittest
from unittest.mock import patch

import strategy_runtime as strategy_runtime_module
from quant_platform_kit.strategy_contracts import StrategyDecision


class _FakeEntrypoint:
    def __init__(self):
        self.manifest = type(
            "Manifest",
            (),
            {
                "profile": "hybrid_growth_income",
                "default_config": {
                    "benchmark_symbol": "QQQ",
                    "managed_symbols": ("TQQQ", "BOXX", "SPYI", "QQQI"),
                },
            },
        )()

    def evaluate(self, ctx):
        self.ctx = ctx
        return StrategyDecision(diagnostics={"signal_display": "hold"})


class StrategyRuntimeTests(unittest.TestCase):
    def test_runtime_exposes_managed_symbols_and_benchmark(self):
        entrypoint = _FakeEntrypoint()
        runtime = strategy_runtime_module.LoadedStrategyRuntime(
            entrypoint=entrypoint,
            merged_runtime_config={
                "benchmark_symbol": "QQQ",
                "managed_symbols": ("TQQQ", "BOXX", "SPYI", "QQQI"),
            },
        )

        result = runtime.evaluate(
            qqq_history=[{"close": 1.0, "high": 1.0, "low": 1.0}],
            snapshot=object(),
            signal_text_fn=str,
            translator=lambda key, **_kwargs: key,
        )

        self.assertEqual(runtime.managed_symbols, ("TQQQ", "BOXX", "SPYI", "QQQI"))
        self.assertEqual(runtime.benchmark_symbol, "QQQ")
        self.assertIn("signal_text_fn", entrypoint.ctx.runtime_config)
        self.assertEqual(result.metadata["strategy_profile"], "hybrid_growth_income")

    def test_load_strategy_runtime_merges_overrides_on_top_of_entrypoint_defaults(self):
        entrypoint = _FakeEntrypoint()

        with patch.object(strategy_runtime_module, "load_strategy_entrypoint_for_profile", return_value=entrypoint) as mock_loader:
            runtime = strategy_runtime_module.load_strategy_runtime(
                "hybrid_growth_income",
                runtime_overrides={"benchmark_symbol": "VGT"},
            )

        mock_loader.assert_called_once_with("hybrid_growth_income")
        self.assertIs(runtime.entrypoint, entrypoint)
        self.assertEqual(runtime.benchmark_symbol, "VGT")
        self.assertEqual(runtime.managed_symbols, ("TQQQ", "BOXX", "SPYI", "QQQI"))


if __name__ == "__main__":
    unittest.main()
