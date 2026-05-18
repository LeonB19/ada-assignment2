import json
import os
from google.cloud import pubsub_v1

GOOGLE_CLOUD_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "ada2026-assignment2")

_publisher = None


def get_publisher() -> pubsub_v1.PublisherClient:
    global _publisher
    if _publisher is None:
        _publisher = pubsub_v1.PublisherClient()
    return _publisher


def publish_event(topic_id: str, data: dict) -> str:
    """Publish a JSON message to a Pub/Sub topic. Returns the message ID."""
    publisher = get_publisher()
    topic_path = publisher.topic_path(GOOGLE_CLOUD_PROJECT, topic_id)
    future = publisher.publish(topic_path, json.dumps(data).encode("utf-8"))
    return future.result()
