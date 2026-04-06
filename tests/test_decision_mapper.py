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
            strategy_profile="hybrid_growth_income",
        )

        self.assertEqual(plan["strategy_symbols"], ("TQQQ", "BOXX", "QQQI", "SPYI"))
        self.assertEqual(plan["sell_order_symbols"], ("TQQQ", "QQQI", "SPYI", "BOXX"))
        self.assertEqual(plan["buy_order_symbols"], ("QQQI", "SPYI", "TQQQ"))
        self.assertEqual(plan["cash_sweep_symbol"], "BOXX")
        self.assertEqual(plan["account_hash"], "demo")
        self.assertEqual(plan["target_values"]["BOXX"], 35000.0)


if __name__ == "__main__":
    unittest.main()
