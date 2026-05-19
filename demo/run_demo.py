"""
demo/run_demo.py - end-to-end demonstration of the vacation package assembly process.

Usage:
    python run_demo.py --gateway https://api-gateway-xxx.run.app
    python run_demo.py --gateway http://localhost:8080 # Run local
    
The script walks through the full scenario from the assignment plan:
    1. Submit vacation request
    2. Poll until a package is selected
    3. Print the result with explaination
"""

import argparse
import json
import time
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

def run_demo(gateway_url: str):
    gateway_url = gateway_url.rstrip("/")
    client = httpx.Client(timeout=30.0)
 
    headers = {"Authorization": "Bearer client-demo-user", "Content-Type": "application/json"}
 
    section("Step 1 — API Gateway health check")
    resp = client.get(f"{gateway_url}/health")
    if resp.status_code == 200:
        ok(f"Gateway is up: {resp.json()}")
    else:
        err(f"Gateway returned {resp.status_code}")
        return
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
 
    section("Step 3 — Polling for package assembly result")
    max_polls = 20
    poll_interval = 5  # seconds
 
    for i in range(max_polls):
        time.sleep(poll_interval)
        resp = client.get(f"{gateway_url}/requests/{request_id}", headers=headers)
        if resp.status_code != 200:
            warn(f"Poll {i+1}: unexpected status {resp.status_code}")
            continue
 
        data = resp.json()
        status = data.get("status", "unknown")
        info(f"Poll {i+1}/{max_polls} — status: {status}")
 
        if status == "completed":
            ok("Package assembly completed!")
            break
        elif status == "failed":
            err(f"Assembly failed: {data.get('error', 'unknown error')}")
            return
        elif status in ("submitted", "validating", "enriching", "composing", "scoring", "selecting"):
            info(f"  Still processing… ({status})")
    else:
        warn("Timed out waiting for result — check Firestore and Cloud Logging")
        return
 
    section("Step 4 — Selected package")
    pkg = data.get("selected_package", {})
    info(f"Enriched destination : {data.get('enriched_destination', 'N/A')}")
    info(f"Package ID           : {pkg.get('package_id', 'N/A')}")
    info(f"Total price          : €{pkg.get('total_price_eur', 'N/A')}")
    info(f"Score                : {pkg.get('score', 'N/A')}")
    info(f"Explanation          : {pkg.get('explanation', 'N/A')}")
 
    flight = pkg.get("flight_component", {})
    hotel  = pkg.get("hotel_component", {})
    activity = pkg.get("activity_component", {})
 
    info(f"\n  Flight  : {flight.get('provider', 'N/A')} — {flight.get('route', 'N/A')} — €{flight.get('price_eur', 'N/A')}")
    info(f"  Hotel   : {hotel.get('name', 'N/A')} — {hotel.get('nights', 'N/A')} nights — €{hotel.get('price_eur', 'N/A')}")
    info(f"  Activity: {activity.get('name', 'N/A')} — €{activity.get('price_eur', 'N/A')}")
 
    section("Step 5 — Business rules active during assembly")
    agency_headers = {"Authorization": "Bearer agency-demo-user"}
    resp = client.get(f"{gateway_url}/agency/rules", headers=agency_headers)
    if resp.status_code == 200:
        rules = resp.json().get("rules", [])
        for rule in rules:
            ok(f"Rule: {rule.get('description', rule)}")
    else:
        warn(f"Could not fetch rules: {resp.status_code}")
 
    section("Demo complete")
    ok("Full end-to-end scenario ran successfully")
    ok(f"Request ID for audit: {request_id}")
    info("Check Firestore 'coordination_event_log' collection to see all workflow events.")
 
 
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the vacation system end-to-end demo")
    parser.add_argument(
        "--gateway",
        default="http://localhost:8080",
        help="Base URL of the API Gateway (default: http://localhost:8080)",
    )
    args = parser.parse_args()
    run_demo(args.gateway)