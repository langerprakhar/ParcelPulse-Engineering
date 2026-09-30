"""The Redis message the API publishes must match what parcelpulse-worker consumes."""

import os
import uuid
from collections.abc import Iterator

import pytest
import redis
from dramatiq.brokers.redis import RedisBroker

from parcelpulse_api.queue import DramatiqNotificationPublisher

DEFAULT_TEST_REDIS_URL = "redis://localhost:56379/15"


@pytest.fixture
def redis_url() -> Iterator[str]:
    url = os.environ.get("TEST_REDIS_URL", DEFAULT_TEST_REDIS_URL)
    client = redis.Redis.from_url(url, socket_connect_timeout=2)
    try:
        client.flushdb()
    except redis.exceptions.ConnectionError as exc:
        pytest.fail(
            "This test needs Redis. Start one with "
            "'docker compose -f docker-compose.dev.yml up -d --wait' or set TEST_REDIS_URL. "
            f"Connection error: {exc}",
            pytrace=False,
        )
    yield url
    client.flushdb()
    client.close()


def test_published_message_follows_the_worker_contract(redis_url: str) -> None:
    publisher = DramatiqNotificationPublisher(
        redis_url=redis_url, queue_name="notifications", actor_name="deliver_notification"
    )
    notification_id = uuid.uuid4()

    publisher.publish(notification_id, correlation_id="corr-42")

    # Read it back the way a Dramatiq worker would.
    worker_side = RedisBroker(url=redis_url, middleware=[])
    consumer = worker_side.consume("notifications", prefetch=1, timeout=1000)
    message = next(consumer)
    assert message is not None
    assert message.queue_name == "notifications"
    assert message.actor_name == "deliver_notification"
    assert message.args == (str(notification_id),)
    assert message.kwargs == {"correlation_id": "corr-42"}
    consumer.ack(message)
    consumer.close()
    publisher.close()


def test_ping_succeeds_against_a_live_broker(redis_url: str) -> None:
    publisher = DramatiqNotificationPublisher(
        redis_url=redis_url, queue_name="notifications", actor_name="deliver_notification"
    )
    publisher.ping()
    publisher.close()


def test_publish_raises_when_the_broker_is_unreachable() -> None:
    publisher = DramatiqNotificationPublisher(
        redis_url="redis://localhost:1/0",
        queue_name="notifications",
        actor_name="deliver_notification",
    )
    # Refused or timed out, depending on the platform; both are RedisError.
    with pytest.raises(redis.exceptions.RedisError):
        publisher.publish(uuid.uuid4())
    with pytest.raises(redis.exceptions.RedisError):
        publisher.ping()
