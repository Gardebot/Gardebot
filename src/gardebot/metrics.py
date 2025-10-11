"""Metrics collection for Gardebot using Prometheus."""

from prometheus_client import Counter, Histogram

webhook_events_total = Counter("gardebot_webhook_events_total", "Webhook events processed", ["event", "handled"])
webhook_errors_total = Counter("gardebot_webhook_errors_total", "Webhook errors", ["event", "code"])
webhook_latency = Histogram("gardebot_webhook_latency_seconds", "Webhook handling latency", ["event"])
participant_sync_total = Counter("gardebot_participant_sync_total", "Participant sync executions")


def record_event(event: str, handled: bool, duration: float) -> None:
    """Record a webhook event processing."""
    webhook_events_total.labels(event=event, handled=str(handled)).inc()
    webhook_latency.labels(event=event).observe(duration)


def record_error(event: str, code: str) -> None:
    """Record an error that occurred during webhook processing."""
    webhook_errors_total.labels(event=event, code=code).inc()


def record_participant_sync() -> None:
    """Record a participant sync execution."""
    participant_sync_total.inc()
