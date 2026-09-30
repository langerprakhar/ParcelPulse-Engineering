"""Operational metrics, exposed in Prometheus text format at GET /metrics.

Each application instance owns its registry, so tests (and multiple apps in
one process) never share or double-register collectors.
"""

from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest

CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


class Metrics:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()

        self.http_requests = Counter(
            "parcelpulse_http_requests_total",
            "HTTP requests handled, by route template and response status.",
            ["method", "route", "status"],
            registry=self.registry,
        )
        self.http_request_duration = Histogram(
            "parcelpulse_http_request_duration_seconds",
            "HTTP request duration in seconds, by route template.",
            ["method", "route"],
            registry=self.registry,
        )
        self.webhook_deliveries = Counter(
            "parcelpulse_webhook_deliveries_total",
            "Authenticated carrier webhook deliveries, by processing result.",
            ["result"],
            registry=self.registry,
        )
        self.webhook_rejections = Counter(
            "parcelpulse_webhook_rejections_total",
            "Carrier webhook deliveries rejected before processing, by reason.",
            ["reason"],
            registry=self.registry,
        )
        self.out_of_order_events = Counter(
            "parcelpulse_tracking_events_out_of_order_total",
            "Tracking events that arrived after an event with a later carrier timestamp.",
            registry=self.registry,
        )
        self.notifications_planned = Counter(
            "parcelpulse_notifications_planned_total",
            "Notifications written to the outbox.",
            registry=self.registry,
        )
        self.notification_publish_failures = Counter(
            "parcelpulse_notification_publish_failures_total",
            "Notifications that could not be published to the broker after commit.",
            registry=self.registry,
        )

    def render(self) -> bytes:
        return generate_latest(self.registry)
