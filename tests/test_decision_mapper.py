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

    def test_applies_platform_reserved_cash_floor_for_weight_targets(self):
        snapshot = SimpleNamespace(
            total_equity=1000.0,
            buying_power=400.0,
            positions=(SimpleNamespace(symbol="AAPL", quantity=1, market_value=400.0),),
            metadata={"account_hash": "demo"},
        )
        decision = StrategyDecision(
            positions=(PositionTarget(symbol="AAPL", target_weight=0.40),),
            diagnostics={"signal_display": "hold"},
        )

        plan = map_strategy_decision_to_plan(
            decision,
            snapshot=snapshot,
            strategy_profile="tech_communication_pullback_enhancement",
            runtime_metadata={
                "schwab_execution_policy": {
                    "reserved_cash_floor_usd": 150.0,
                    "reserved_cash_ratio": 0.03,
                }
            },
        )

        self.assertEqual(plan["execution"]["reserved_cash"], 150.0)

    def test_platform_reserved_cash_floor_can_raise_strategy_reserve(self):
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
                }
            },
        )

        plan = map_strategy_decision_to_plan(
            decision,
            snapshot=snapshot,
            strategy_profile="tqqq_growth_income",
            runtime_metadata={
                "schwab_execution_policy": {
                    "reserved_cash_floor_usd": 150.0,
                    "reserved_cash_ratio": 0.03,
                }
            },
        )

        self.assertEqual(plan["execution"]["reserved_cash"], 3600.0)

    def test_soxl_profile_keeps_strategy_reserve_without_platform_floor(self):
        snapshot = SimpleNamespace(
            total_equity=1175.76,
            buying_power=201.75,
            positions=(SimpleNamespace(symbol="SOXL", quantity=0, market_value=0.0),),
            metadata={"account_hash": "demo"},
        )
        decision = StrategyDecision(
            positions=(PositionTarget(symbol="SOXL", target_value=1000.0),),
            diagnostics={
                "execution_annotations": {
                    "reserved_cash": 35.27,
                }
            },
        )

        plan = map_strategy_decision_to_plan(
            decision,
            snapshot=snapshot,
            strategy_profile="soxl_soxx_trend_income",
            runtime_metadata={
                "schwab_execution_policy": {
                    "reserved_cash_floor_usd": 150.0,
                    "reserved_cash_ratio": 0.03,
                }
            },
        )

        self.assertEqual(plan["execution"]["reserved_cash"], 35.27)

    def test_translates_weight_targets_for_tech_communication_pullback_enhancement(self):
        snapshot = SimpleNamespace(
            total_equity=100000.0,
            buying_power=20000.0,
            positions=(
                SimpleNamespace(symbol="AAPL", quantity=10, market_value=10000.0),
                SimpleNamespace(symbol="BOXX", quantity=20, market_value=4000.0),
            ),
            metadata={"account_hash": "demo"},
        )
        decision = StrategyDecision(
            positions=(
                PositionTarget(symbol="AAPL", target_weight=0.35),
                PositionTarget(symbol="MSFT", target_weight=0.25),
                PositionTarget(symbol="BOXX", target_weight=0.40, role="safe_haven"),
            ),
            diagnostics={
                "signal_display": "🧲 Risk On",
                "dashboard": "dashboard",
            },
        )

        plan = map_strategy_decision_to_plan(
            decision,
            snapshot=snapshot,
            strategy_profile="tech_communication_pullback_enhancement",
        )

        self.assertEqual(plan["allocation"]["target_mode"], "value")
        self.assertEqual(plan["allocation"]["targets"]["AAPL"], 35000.0)
        self.assertEqual(plan["allocation"]["targets"]["MSFT"], 25000.0)
        self.assertEqual(plan["allocation"]["targets"]["BOXX"], 40000.0)

    def test_translates_weight_targets_for_global_etf_rotation(self):
        snapshot = SimpleNamespace(
            total_equity=100000.0,
            buying_power=15000.0,
            positions=(
                SimpleNamespace(symbol="VOO", quantity=10, market_value=10000.0),
                SimpleNamespace(symbol="BIL", quantity=20, market_value=2000.0),
            ),
            metadata={"account_hash": "demo"},
        )
        decision = StrategyDecision(
            positions=(
                PositionTarget(symbol="VGK", target_weight=0.5),
                PositionTarget(symbol="EWJ", target_weight=0.3),
                PositionTarget(symbol="BIL", target_weight=0.2, role="safe_haven"),
            ),
            diagnostics={
                "signal_description": "quarterly",
                "canary_status": "SPY:✅, EFA:✅",
            },
        )

        plan = map_strategy_decision_to_plan(
            decision,
            snapshot=snapshot,
            strategy_profile="global_etf_rotation",
        )

        self.assertEqual(plan["allocation"]["target_mode"], "value")
        self.assertEqual(plan["allocation"]["targets"]["VGK"], 50000.0)
        self.assertEqual(plan["allocation"]["targets"]["EWJ"], 30000.0)
        self.assertEqual(plan["allocation"]["targets"]["BIL"], 20000.0)
        self.assertEqual(plan["execution"]["signal_display"], "quarterly")
        self.assertEqual(plan["execution"]["status_display"], "SPY:✅, EFA:✅")

    def test_translates_weight_targets_for_russell_strategy(self):
        snapshot = SimpleNamespace(
            total_equity=100000.0,
            buying_power=15000.0,
            positions=(
                SimpleNamespace(symbol="AAPL", quantity=10, market_value=10000.0),
                SimpleNamespace(symbol="BOXX", quantity=20, market_value=3000.0),
            ),
            metadata={"account_hash": "demo"},
        )
        decision = StrategyDecision(
            positions=(
                PositionTarget(symbol="AAPL", target_weight=0.30),
                PositionTarget(symbol="MSFT", target_weight=0.30),
                PositionTarget(symbol="NVDA", target_weight=0.20),
                PositionTarget(symbol="BOXX", target_weight=0.20, role="safe_haven"),
            ),
            diagnostics={
                "signal_description": "risk on",
                "status_description": "breadth=62.0% | regime=risk_on | benchmark=up",
                "benchmark_symbol": "SPY",
            },
        )

        plan = map_strategy_decision_to_plan(
            decision,
            snapshot=snapshot,
            strategy_profile="russell_1000_multi_factor_defensive",
        )

        self.assertEqual(plan["allocation"]["target_mode"], "value")
        self.assertEqual(plan["allocation"]["targets"]["AAPL"], 30000.0)
        self.assertEqual(plan["allocation"]["targets"]["BOXX"], 20000.0)
        self.assertEqual(plan["execution"]["signal_display"], "risk on")
        self.assertEqual(
            plan["execution"]["status_display"],
            "breadth=62.0% | regime=risk_on | benchmark=up",
        )


if __name__ == "__main__":
    unittest.main()
