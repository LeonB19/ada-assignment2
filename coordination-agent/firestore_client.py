import os
from google.cloud import firestore

GOOGLE_CLOUD_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "ada2026-assignment2")

_db = None


def get_db() -> firestore.Client:
    global _db
    if _db is None:
        _db = firestore.Client(project=GOOGLE_CLOUD_PROJECT)
    return _db


def get_vacation_request(request_id: str) -> dict | None:
    doc = get_db().collection("vacation_requests").document(request_id).get()
    return doc.to_dict() if doc.exists else None


def update_vacation_request(request_id: str, fields: dict):
    get_db().collection("vacation_requests").document(request_id).update(fields)


def log_coordination_event(
    event_type: str,
    request_id: str,
    payload: dict,
    source: str = "coordination_agent",
) -> str:
    """Append an event to the coordination_event_log collection. Returns the new doc ID."""
    _, ref = get_db().collection("coordination_event_log").add({
        "event_type": event_type,
        "request_id": request_id,
        "timestamp": firestore.SERVER_TIMESTAMP,
        "source": source,
        "payload": payload,
    })
    return ref.id
