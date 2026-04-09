import unittest
from types import SimpleNamespace

from quant_platform_kit.strategy_contracts import PositionTarget, StrategyDecision

from decision_mapper import map_strategy_decision_to_plan


class DecisionMapperTests(unittest.TestCase):
    def test_maps_hybrid_growth_decision_to_execution_plan(self):
        snapshot = SimpleNamespace(
            total_equity=120000.0,
            buying_power=20000.0,
            positions=(
                SimpleNamespace(symbol="TQQQ", quantity=10, market_value=8000.0),
                SimpleNamespace(symbol="BOXX", quantity=20, market_value=4000.0),
                SimpleNamespace(symbol="SPYI", quantity=30, market_value=1500.0),
                SimpleNamespace(symbol="QQQI", quantity=30, market_value=1700.0),
            ),
            metadata={"account_hash": "demo"},
        )
        decision = StrategyDecision(
            positions=(
                PositionTarget(symbol="TQQQ", target_value=30000.0),
                PositionTarget(symbol="BOXX", target_value=35000.0, role="safe_haven"),
                PositionTarget(symbol="SPYI", target_value=12000.0, role="income"),
                PositionTarget(symbol="QQQI", target_value=18000.0, role="income"),
            ),
            diagnostics={
                "signal_display": "💎 Trend Hold",
                "dashboard": "dashboard",
                "threshold": 1200.0,
                "reserved": 2500.0,
                "qqq_price": 400.0,
                "ma200": 380.0,
                "exit_line": 360.0,
                "real_buying_power": 20000.0,
                "total_equity": 120000.0,
            },
        )

        plan = map_strategy_decision_to_plan(
            decision,
            snapshot=snapshot,
            strategy_profile="tqqq_growth_income",
        )

        self.assertEqual(plan["account_hash"], "demo")
        self.assertEqual(plan["allocation"]["target_mode"], "value")
        self.assertEqual(plan["allocation"]["strategy_symbols"], ("TQQQ", "BOXX", "QQQI", "SPYI"))
        self.assertEqual(plan["allocation"]["targets"]["BOXX"], 35000.0)
        self.assertEqual(plan["portfolio"]["cash_sweep_symbol"], "BOXX")
        self.assertEqual(plan["portfolio"]["portfolio_rows"], (("TQQQ", "BOXX"), ("QQQI", "SPYI")))
        self.assertEqual(plan["execution"]["trade_threshold_value"], 1200.0)
        self.assertNotIn("strategy_symbols", plan)
        self.assertNotIn("sell_order_symbols", plan)
        self.assertNotIn("buy_order_symbols", plan)
        self.assertNotIn("target_values", plan)

    def test_prefers_normalized_execution_annotations_when_present(self):
        snapshot = SimpleNamespace(
            total_equity=120000.0,
            buying_power=20000.0,
            positions=(SimpleNamespace(symbol="TQQQ", quantity=10, market_value=8000.0),),
            metadata={"account_hash": "demo"},
        )
        decision = StrategyDecision(
            positions=(PositionTarget(symbol="TQQQ", target_value=30000.0),),
            diagnostics={
                "execution_annotations": {
                    "trade_threshold_value": 500.0,
                    "reserved_cash": 1200.0,
                    "signal_display": "hold",
                    "dashboard_text": "dashboard",
                    "benchmark_symbol": "QQQ",
                    "benchmark_price": 400.0,
                    "long_trend_value": 380.0,
                    "exit_line": 360.0,
                }
            },
        )

        plan = map_strategy_decision_to_plan(
            decision,
            snapshot=snapshot,
            strategy_profile="tqqq_growth_income",
        )

        self.assertEqual(plan["execution"]["trade_threshold_value"], 500.0)
        self.assertEqual(plan["execution"]["reserved_cash"], 1200.0)
        self.assertEqual(plan["execution"]["signal_display"], "hold")
        self.assertEqual(plan["execution"]["dashboard_text"], "dashboard")


if __name__ == "__main__":
    unittest.main()
