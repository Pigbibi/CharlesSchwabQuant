import unittest
import sys
import types
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


requests_stub = types.ModuleType("requests")
requests_stub.post = lambda *args, **kwargs: None

with patch.dict(sys.modules, {"requests": requests_stub}):
    from notifications.telegram import build_sender, build_signal_text, build_strategy_display_name, build_translator

from strategy_registry import SUPPORTED_STRATEGY_PROFILES


class FakeRequests:
    def __init__(self):
        self.calls = []

    def post(self, url, json, timeout):
        self.calls.append((url, json, timeout))
        return object()


class NotificationTests(unittest.TestCase):
    def test_build_translator_supports_chinese(self):
        translate = build_translator("zh")
        self.assertEqual(translate("equity"), "净值")
        self.assertEqual(translate("holdings_title"), "💼 持仓")
        self.assertEqual(translate("benchmark_title", symbol="QQQ"), "📈 QQQ 基准")
        self.assertEqual(translate("benchmark_exit", value="598.38"), "退出线: 598.38")
        self.assertEqual(translate("market_status_blend_gate_risk_on", asset="SOXX+SOXL"), "🚀 风险开启（SOXX+SOXL）")
        self.assertEqual(
            translate(
                "signal_blend_gate_risk_on",
                trend_symbol="SOXX",
                window=140,
                soxl_ratio="70.0%",
                soxx_ratio="20.0%",
            ),
            "SOXX 站上 140 日门槛线，持有 SOXL 70.0% + SOXX 20.0%",
        )
        self.assertEqual(
            translate(
                "small_account_warning_note",
                portfolio_equity="$0",
                min_recommended_equity="$1,000",
                reason=translate(
                    "small_account_warning_reason_integer_shares_min_position_value_may_prevent_backtest_replication"
                ),
            ),
            "小账户提示：净值 $0 低于建议 $1,000；整数股和最小仓位限制可能导致实盘无法完全复现回测",
        )

    def test_supported_strategy_profiles_have_translated_names(self):
        zh_name = build_strategy_display_name(build_translator("zh"))
        en_name = build_strategy_display_name(build_translator("en"))

        self.assertEqual(zh_name("global_etf_confidence_vol_gate"), "全球 ETF 置信波动门控")
        self.assertEqual(en_name("global_etf_confidence_vol_gate"), "Global ETF Confidence Vol Gate")
        for profile in SUPPORTED_STRATEGY_PROFILES:
            self.assertNotEqual(zh_name(profile), profile)
            self.assertNotEqual(en_name(profile), profile)

    def test_build_signal_text_formats_icon_and_label(self):
        signal_text = build_signal_text(build_translator("en"))
        self.assertEqual(signal_text("hold"), "💎 Trend Hold")

    def test_build_sender_posts_to_telegram(self):
        fake_requests = FakeRequests()
        sender = build_sender("token-1", "chat-1", requests_module=fake_requests)
        sender("hello")
        self.assertEqual(len(fake_requests.calls), 1)
        url, payload, timeout = fake_requests.calls[0]
        self.assertIn("token-1", url)
        self.assertEqual(payload["chat_id"], "chat-1")
        self.assertEqual(payload["text"], "hello")
        self.assertEqual(timeout, 15)


if __name__ == "__main__":
    unittest.main()
