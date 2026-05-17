import os
from google.cloud import firestore

GOOGLE_CLOUD_PROJECT = "ada2026-assignment2"

_db = None


def get_db():
    global _db
    if _db is None:
        _db = firestore.Client(project=GOOGLE_CLOUD_PROJECT)
    return _db


def get_vacation_request(request_id: str) -> dict | None:
    doc = get_db().collection("vacation_requests").document(request_id).get()
    return doc.to_dict() if doc.exists else None


def save_package_proposal(request_id: str, data: dict):
    get_db().collection("package_proposals").document(request_id).set(data)
