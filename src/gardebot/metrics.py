"""Metrics collection for Gardebot using Prometheus."""

from prometheus_client import Counter, Histogram

webhook_events_total = Counter("gardebot_webhook_events_total", "Webhook events processed", ["event", "handled"])
webhook_errors_total = Counter("gardebot_webhook_errors_total", "Webhook errors", ["event", "code"])
webhook_latency = Histogram("gardebot_webhook_latency_seconds", "Webhook handling latency", ["event"])
participant_sync_total = Counter("gardebot_participant_sync_total", "Participant sync executions")

initialize_total = Counter("gardebot_initialize_total", "Initialization executions")
poll_publish_total = Counter("gardebot_poll_publish_total", "Poll publication outcomes", ["status"])
vote_processed_total = Counter("gardebot_vote_processed_total", "Vote processing outcomes", ["result"])


def record_event(event: str, handled: bool, duration: float) -> None:
    """Record a webhook event processing."""
    webhook_events_total.labels(event=event, handled=str(handled)).inc()
    webhook_latency.labels(event=event).observe(duration)


def record_error(event: str, code: str) -> None:
    """Record a webhook error."""
    webhook_errors_total.labels(event=event, code=code).inc()


def record_participant_sync() -> None:
    """Record a participant synchronization execution."""
    participant_sync_total.inc()


def record_initialize() -> None:
    """Record a Gardebot initialization execution."""
    initialize_total.inc()


def record_poll_publish(status: str) -> None:
    """Record a poll publication outcome."""
    poll_publish_total.labels(status=status).inc()


def record_vote_processed(result: str) -> None:
    """Record a vote processing outcome."""
    vote_processed_total.labels(result=result).inc()
