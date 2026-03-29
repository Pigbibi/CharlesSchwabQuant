import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from notifications.telegram import build_sender, build_signal_text, build_translator


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
