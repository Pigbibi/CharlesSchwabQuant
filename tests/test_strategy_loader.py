import unittest


class StrategyLoaderTests(unittest.TestCase):
    def test_load_strategy_entrypoint_resolves_hybrid_growth_income(self):
        try:
            from strategy_loader import load_strategy_entrypoint_for_profile

            entrypoint = load_strategy_entrypoint_for_profile("hybrid_growth_income")
        except ModuleNotFoundError as exc:
            if exc.name in {"numpy", "pandas"}:
                self.skipTest(f"{exc.name} is not installed")
            raise

        self.assertEqual(entrypoint.manifest.profile, "hybrid_growth_income")
        self.assertEqual(
            entrypoint.manifest.default_config["managed_symbols"],
            ("TQQQ", "BOXX", "SPYI", "QQQI"),
        )

    def test_load_strategy_entrypoint_resolves_hybrid_growth_income_alias(self):
        try:
            from strategy_loader import load_strategy_entrypoint_for_profile

            entrypoint = load_strategy_entrypoint_for_profile("qqq_tqqq_growth_income")
        except ModuleNotFoundError as exc:
            if exc.name in {"numpy", "pandas"}:
                self.skipTest(f"{exc.name} is not installed")
            raise

        self.assertEqual(
            entrypoint.manifest.profile,
            "hybrid_growth_income",
        )


if __name__ == "__main__":
    unittest.main()
