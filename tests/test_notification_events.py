import unittest

from notifications.events import (
    NotificationPublisher,
    RenderedNotification,
    publish_rendered_notification,
)


class NotificationEventsTests(unittest.TestCase):
    def test_publish_rendered_notification_splits_log_and_send_sinks(self):
        logged = []
        sent = []

        publish_rendered_notification(
            RenderedNotification(
                detailed_text="detailed copy",
                compact_text="compact copy",
            ),
            log_message=logged.append,
            send_message=sent.append,
        )

        self.assertEqual(logged, ["detailed copy"])
        self.assertEqual(sent, ["compact copy"])

    def test_publish_rendered_notification_skips_empty_sinks(self):
        logged = []
        sent = []

        publish_rendered_notification(
            RenderedNotification(detailed_text="  ", compact_text=""),
            log_message=logged.append,
            send_message=sent.append,
        )

        self.assertEqual(logged, [])
        self.assertEqual(sent, [])

    def test_notification_publisher_uses_configured_sinks(self):
        logged = []
        sent = []
        publisher = NotificationPublisher(
            log_message=logged.append,
            send_message=sent.append,
        )

        publisher.publish(
            RenderedNotification(
                detailed_text="detailed copy",
                compact_text="compact copy",
            )
        )

        self.assertEqual(logged, ["detailed copy"])
        self.assertEqual(sent, ["compact copy"])


if __name__ == "__main__":
    unittest.main()
