"""
demo/run_demo.py - end-to-end demonstration of the vacation package assembly process.
"""

import argparse
import json
import os
import time
import threading
import httpx


GREEN   = "\033[92m"
YELLOW  = "\033[93m"
RED     = "\033[91m"
CYAN    = "\033[96m"
BOLD    = "\033[1m"
RESET   = "\033[0m"

def section(title: str):
    print(f"\n{BOLD}{CYAN}{'─'*60}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'─'*60}{RESET}")

def ok(msg: str):   print(f"  {GREEN}✓{RESET} {msg}")
def warn(msg: str): print(f"  {YELLOW}!{RESET} {msg}")
def err(msg: str):  print(f"  {RED}✗{RESET} {msg}")
def info(msg: str): print(f"    {msg}")

def _progress_label(data: dict) -> str:
    status = data.get("coordination_status") or data.get("status", "")
    if status == "completed" or data.get("selected_package"):
        return f"  ✅ Package selected!"
    if status in ("composing", "scoring", "selecting", "enriching"):
        return f"  ✈️  Fetching provider offers..."
    if data.get("enriched_destination"):
        return f"  🗺️  Destination resolved: {data['enriched_destination']}"
    return "  ⏳ Validating preferences..."


def _event_description(event_type: str, payload: dict) -> str:
    dest = payload.get("enriched_destination", "")
    descriptions = {
        "PIPELINE_STARTED":      "Pipeline initiated",
        "ENRICHMENT_COMPLETED":  f"Resolved destination to {dest}" if dest else "Destination enriched",
        "ENRICHMENT_FAILED":     f"Enrichment failed: {payload.get('error', '')}",
        "OFFERS_NORMALIZED":     f"{payload.get('total_valid', '?')} offers normalised",
        "NORMALIZATION_FAILED":  f"Normalisation failed: {payload.get('error', '')}",
        "PACKAGES_COMPOSED":     f"{payload.get('package_count', '?')} packages assembled",
        "COMPOSITION_FAILED":    f"Composition failed: {payload.get('error', '')}",
        "FEASIBILITY_CHECKED":   f"{payload.get('feasible_count', '?')} feasible packages",
        "FEASIBILITY_FAILED":    f"Feasibility check failed: {payload.get('error', '')}",
        "PACKAGES_SCORED":       f"{payload.get('package_count', '?')} packages scored, top score {payload.get('top_score', '?')}",
        "SCORING_FAILED":        f"Scoring failed: {payload.get('error', '')}",
        "SCORING_SKIPPED":       f"Scoring skipped: {payload.get('reason', '')}",
        "RULES_APPLIED":         f"{payload.get('rules_applied', [])} rules applied",
        "RULES_FAILED":          f"Rules failed: {payload.get('error', '')}",
        "RULES_SKIPPED":         f"Rules skipped: {payload.get('reason', '')}",
        "PACKAGE_SELECTED":      f"{payload.get('selected_package_id', '?')} selected (€{payload.get('total_price', 0):.2f})",
        "PIPELINE_COMPLETED":    "Pipeline completed",
        "PIPELINE_FAILED":       f"Pipeline failed: {payload.get('notes', '')}",
    }
    return descriptions.get(event_type, event_type.replace("_", " ").title())


def run_demo(gateway_url: str, coord_url: str):
    gateway_url = gateway_url.rstrip("/")
    client = httpx.Client(timeout=30.0)

    headers = {"Authorization": "Bearer client-demo-user", "Content-Type": "application/json"}

    # ── Step 1 ─────────────────────────────────────────────────────────────────
    section("Step 1 — API Gateway health check")
    resp = client.get(f"{gateway_url}/health")
    if resp.status_code == 200:
        ok(f"Gateway is up: {resp.json()}")
    else:
        err(f"Gateway returned {resp.status_code}")
        return

    # ── Step 2 ─────────────────────────────────────────────────────────────────
    section("Step 2 — Submit vacation request")
    request_body = {
        "client_preferences": "beach holiday, warm weather, relaxation, 2 adults, flying from Amsterdam",
        "destination": None,
        "vacation_type": "beach holiday",
        "travel_dates": "2025-07-10 to 2025-07-20",
        "travel_mode": "flight",
        "vacation_purpose": "relaxation",
        "weather_preference": "warm",
        "budget": 2000,
    }
    info(f"Request payload:\n{json.dumps(request_body, indent=4)}")

    resp = client.post(f"{gateway_url}/requests", json=request_body, headers=headers)
    if resp.status_code == 201:
        result = resp.json()
        request_id = result["request_id"]
        ok(f"Request submitted — ID: {request_id}")
    else:
        err(f"Submit failed: {resp.status_code} — {resp.text}")
        return

    # Directly trigger coordination agent in background
    if coord_url:
        info(f"Triggering coordination agent directly...")
        def trigger():
            try:
                r = httpx.post(
                    f"{coord_url.rstrip('/')}/assemble",
                    json={"request_id": request_id},
                    timeout=300,
                )
                info(f"Coordination agent finished: {r.status_code}")
            except Exception as e:
                warn(f"Coordination agent trigger error: {e}")
        threading.Thread(target=trigger, daemon=True).start()
        ok("Coordination agent triggered")
    else:
        warn("COORD_URL not set — relying on Pub/Sub trigger")

    # ── Step 3 ─────────────────────────────────────────────────────────────────
    section("Step 3 — Polling for package assembly result")
    max_polls = 40
    poll_interval = 10  # seconds
    seen_event_ids: set[str] = set()

    for i in range(max_polls):
        time.sleep(poll_interval)
        resp = client.get(f"{gateway_url}/requests/{request_id}", headers=headers)
        if resp.status_code != 200:
            warn(f"Poll {i+1}: unexpected status {resp.status_code}")
            continue

        data = resp.json()
        status = data.get("coordination_status") or data.get("status", "unknown")
        info(f"Poll {i+1}/{max_polls} — status: {status}")
        info(_progress_label(data))

        # Print new coordination events
        try:
            ev_resp = client.get(f"{gateway_url}/events/{request_id}", headers=headers)
            if ev_resp.status_code == 200:
                for event in ev_resp.json().get("events", []):
                    eid = event.get("event_id", "")
                    if eid in seen_event_ids:
                        continue
                    seen_event_ids.add(eid)
                    ts = event.get("timestamp") or ""
                    time_part = ts[11:19] if len(ts) >= 19 else "??:??:??"
                    desc = _event_description(event.get("event_type", ""), event.get("payload", {}))
                    info(f"  {CYAN}[{time_part}]{RESET} {event.get('event_type', '')} — {desc}")
        except Exception as e:
            warn(f"Could not fetch events: {e}")

        if status == "completed" or data.get("selected_package"):
            ok("Package assembly completed!")
            break
        elif status == "failed":
            err(f"Assembly failed: {data.get('error', 'unknown error')}")
            return
        elif status in ("submitted", "validating", "enriching", "composing", "scoring", "selecting", "pending"):
            info(f"  Still processing… ({status})")
    else:
        warn("Timed out waiting for result — check Firestore and Cloud Logging")
        return

    # ── Step 4 ─────────────────────────────────────────────────────────────────
    section("Step 4 — Selected package")
    pkg = data.get("selected_package", {})
    info(f"Enriched destination : {data.get('enriched_destination', 'N/A')}")
    info(f"Package ID           : {pkg.get('package_id', 'N/A')}")
    info(f"Total price          : €{pkg.get('total_price', pkg.get('total_price_eur', 'N/A'))}")
    info(f"Score                : {pkg.get('score', 'N/A')}")
    info(f"Explanation          : {data.get('explanation', pkg.get('rationale', 'N/A'))}")

    flight = pkg.get("flight") or pkg.get("flight_component", {})
    hotel = pkg.get("hotel") or pkg.get("hotel_component", {})
    activities = pkg.get("activities", [])
    activity = activities[0] if activities else pkg.get("activity_component", {})

    info(f"\n  Flight  : {flight.get('provider_id', 'N/A')} — "
         f"{flight.get('metadata', {}).get('origin', 'N/A')}→"
         f"{flight.get('metadata', {}).get('destination', 'N/A')} — "
         f"€{flight.get('price', 'N/A')}")
    info(f"  Hotel   : {hotel.get('metadata', {}).get('hotel_name', 'N/A')} — "
         f"{hotel.get('metadata', {}).get('nights', 'N/A')} nights — "
         f"€{hotel.get('price', 'N/A')}")
    info(f"  Activity: {activity.get('metadata', {}).get('activity_name', 'N/A')} — "
         f"€{activity.get('price', 'N/A')}")

    section("Demo complete")
    ok("Full end-to-end scenario ran successfully")
    ok(f"Request ID for audit: {request_id}")
    info("Check Firestore 'coordination_event_log' collection to see all workflow events.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the vacation system end-to-end demo")
    parser.add_argument("--gateway", default="http://localhost:8080")
    parser.add_argument("--coord", default=os.environ.get("COORD_URL", ""))
    args = parser.parse_args()
    run_demo(args.gateway, args.coord)
