"""Builder helpers for Schwab runtime notification adapters."""

from __future__ import annotations

from dataclasses import dataclass

from notifications.events import NotificationPublisher, RenderedNotification
from quant_platform_kit.common.port_adapters import CallableNotificationPort
from quant_platform_kit.common.ports import NotificationPort


@dataclass(frozen=True)
class SchwabNotificationAdapters:
    notification_port: NotificationPort
    cycle_publisher: NotificationPublisher

    def publish_cycle_notification(self, *, detailed_text: str, compact_text: str) -> None:
        self.cycle_publisher.publish(
            RenderedNotification(
                detailed_text=detailed_text,
                compact_text=compact_text,
            )
        )


def build_runtime_notification_adapters(
    *,
    send_message,
    log_message=None,
) -> SchwabNotificationAdapters:
    return SchwabNotificationAdapters(
        notification_port=CallableNotificationPort(send_message),
        cycle_publisher=NotificationPublisher(
            log_message=log_message or (lambda message: print(message, flush=True)),
            send_message=send_message,
        ),
    )
