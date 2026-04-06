import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
QPK_SRC = ROOT.parent / "QuantPlatformKit" / "src"
if str(QPK_SRC) not in sys.path:
    sys.path.insert(0, str(QPK_SRC))

from application.rebalance_service import run_strategy_core


class RebalanceServiceTests(unittest.TestCase):
    def test_run_strategy_core_uses_managed_wrappers(self):
        sent_messages = []
        observed = {}
        snapshot = SimpleNamespace(
            positions=(
                SimpleNamespace(symbol="TQQQ", quantity=0, market_value=0.0),
                SimpleNamespace(symbol="BOXX", quantity=10, market_value=5000.0),
                SimpleNamespace(symbol="SPYI", quantity=0, market_value=0.0),
                SimpleNamespace(symbol="QQQI", quantity=0, market_value=0.0),
            ),
            total_equity=50000.0,
            buying_power=10000.0,
            metadata={"account_hash": "demo"},
        )
        quote_snapshots = {
            "TQQQ": SimpleNamespace(last_price=50.0, ask_price=50.1),
            "BOXX": SimpleNamespace(last_price=100.0, ask_price=100.0),
            "SPYI": SimpleNamespace(last_price=50.0, ask_price=50.0),
            "QQQI": SimpleNamespace(last_price=50.0, ask_price=50.0),
        }
        plan = {
            "strategy_symbols": ("TQQQ", "BOXX", "SPYI", "QQQI"),
            "sell_order_symbols": ("TQQQ", "QQQI", "SPYI", "BOXX"),
            "buy_order_symbols": ("QQQI", "SPYI", "TQQQ"),
            "cash_sweep_symbol": "BOXX",
            "portfolio_rows": (("TQQQ", "BOXX"), ("QQQI", "SPYI")),
            "account_hash": "demo",
            "market_values": {"TQQQ": 0.0, "BOXX": 5000.0, "SPYI": 0.0, "QQQI": 0.0},
            "quantities": {"TQQQ": 0, "BOXX": 10, "SPYI": 0, "QQQI": 0},
            "total_equity": 50000.0,
            "real_buying_power": 10000.0,
            "reserved": 2500.0,
            "threshold": 500.0,
            "target_values": {"TQQQ": 20000.0, "BOXX": 15000.0, "SPYI": 5000.0, "QQQI": 10000.0},
            "sig_display": "💎 Trend Hold",
            "dashboard": "dashboard",
            "qqq_p": 400.0,
            "ma200": 380.0,
            "exit_line": 360.0,
            "separator": "━━━━━━━━━━━━━━━━━━",
        }

        run_strategy_core(
            object(),
            None,
            fetch_reference_history=lambda client: [{"close": 1.0, "high": 1.0, "low": 1.0}],
            fetch_managed_snapshot=lambda client: snapshot,
            fetch_managed_quotes=lambda client: quote_snapshots,
            resolve_rebalance_plan=lambda *, qqq_history, snapshot: (
                observed.setdefault("history_len", len(qqq_history)),
                observed.setdefault("snapshot_hash", snapshot.metadata["account_hash"]),
                plan,
            )[-1],
            submit_equity_order=lambda *_args, **_kwargs: SimpleNamespace(
                status="accepted",
                broker_order_id="order-1",
                raw_payload={},
            ),
            send_tg_message=sent_messages.append,
            translator=lambda key, **_kwargs: {
                "trade_header": "trade",
                "heartbeat_header": "heartbeat",
                "signal_label": "signal",
                "equity": "equity",
                "buying_power": "buying_power",
                "market_sell_cmd": "sell",
                "limit_buy_cmd": "limit buy",
                "market_buy_cmd": "buy",
                "submitted": "submitted",
                "shares": "shares",
                "no_trades": "no trades",
                "market_sell": "market_sell",
                "limit_buy": "limit_buy",
                "market_buy": "market_buy",
                "failed": "failed",
                "buy_label": "buy",
                "exception": "exception",
            }.get(key, key),
            limit_buy_premium=1.005,
            sell_settle_delay_sec=0,
        )

        self.assertEqual(observed["history_len"], 1)
        self.assertEqual(observed["snapshot_hash"], "demo")
        self.assertTrue(sent_messages)
        self.assertIn("trade", sent_messages[0])


if __name__ == "__main__":
    unittest.main()
