import os
import sys

# Allow running from any directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from google.cloud import firestore
from mock_data import PROVIDERS

GOOGLE_CLOUD_PROJECT = "ada2026-assignment2"


def seed():
    db = firestore.Client(project=GOOGLE_CLOUD_PROJECT)
    collection = db.collection("provider_metadata")
    for p in PROVIDERS:
        # Deduplicate supported_destinations — keep only canonical city names for Firestore
        canonical = list({d for d in p["supported_destinations"] if len(d) > 3})
        doc_ref = collection.document(p["provider_id"])
        doc_ref.set({
            "provider_id": p["provider_id"],
            "name": p["name"],
            "provider_type": p["provider_type"],
            "supported_destinations": canonical,
            "reliability_score": p["reliability_score"],
            "margin_threshold": p["margin_threshold"],
            "api_status": "active",
        })
        print(f"Seeded: {p['provider_id']}")


if __name__ == "__main__":
    seed()
