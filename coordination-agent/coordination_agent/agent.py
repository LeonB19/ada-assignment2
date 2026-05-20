import os
import httpx

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPServerParams

GEMINI_API_KEY = "AIzaSyBUDhiTTzgDoX4WSx2ZmBWyBkCcu1o-SD0"
os.environ.setdefault("GOOGLE_API_KEY", GEMINI_API_KEY)
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "ada2026-assignment2")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")

PROVIDER_MCP_URL   = os.environ.get("PROVIDER_MCP_URL",   "http://localhost:8080/mcp")
ENRICHMENT_URL     = os.environ.get("ENRICHMENT_URL",     "http://localhost:8082")
NORMALIZATION_URL  = os.environ.get("NORMALIZATION_URL",  "http://localhost:8083")
COMPOSER_URL       = os.environ.get("COMPOSER_URL",       "http://localhost:8084")
FEASIBILITY_URL    = os.environ.get("FEASIBILITY_URL",    "http://localhost:8085")
SCORING_URL        = os.environ.get("SCORING_URL",        "")
BUSINESS_RULES_URL = os.environ.get("BUSINESS_RULES_URL", "")
SELECTION_URL      = os.environ.get("PACKAGE_SELECTION_URL", "")



def _log(event_type: str, request_id: str, payload: dict) -> None:
    from firestore_client import log_coordination_event
    log_coordination_event(event_type, request_id, payload)


def _parse_travel_dates(travel_dates) -> tuple[str, str]:
    if isinstance(travel_dates, dict):
        return travel_dates.get("departure") or travel_dates.get("start"), \
               travel_dates.get("return")    or travel_dates.get("end")
    parts = str(travel_dates).split(" to ")
    return parts[0].strip(), parts[1].strip()

def get_vacation_request_details(request_id: str) -> dict:
    """Read the full vacation request from Firestore.

    Call this at the start of the pipeline to retrieve destination,
    travel_dates, budget, vacation_type, weather_preference, and travel_mode.
    Parse start_date and end_date from travel_dates (split on " to ").

    Args:
        request_id: The Firestore document ID (e.g. "req_abc12345").

    Returns:
        All fields of the vacation request, or {"error": "..."} if not found.
    """
    from firestore_client import get_vacation_request
    req = get_vacation_request(request_id)
    if not req:
        return {"error": f"Vacation request {request_id} not found in Firestore"}
    return req

def enrich_vacation_request(request_id: str) -> dict:
    """Resolve a vague destination to a concrete European city.

    Calls the Request Enrichment Agent (POST /enrich). Must be called before
    fetching provider offers — the enriched_destination is the canonical city name.

    Args:
        request_id: The vacation request document ID.

    Returns:
        {"status": "success", "enriched_destination": "...", "weather_preference": "..."}
        or {"status": "error", "error": "..."}.
    """
    try:
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(f"{ENRICHMENT_URL}/enrich", json={"request_id": request_id})
            resp.raise_for_status()
            result = resp.json()
        _log("ENRICHMENT_COMPLETED", request_id, {
            "enriched_destination": result.get("enriched_destination"),
            "weather_preference": result.get("weather_preference"),
        })
        return {"status": "success", **result}
    except Exception as e:
        _log("ENRICHMENT_FAILED", request_id, {"error": str(e)})
        return {"status": "error", "error": str(e)}

def normalize_offers(request_id: str, offers: list[dict]) -> dict:
    """Validate raw offers fetched from the Provider MCP server.

    Filters out malformed offers, zero-priced offers, and expired quote windows.
    Call this after combining get_flight_offers + get_hotel_offers + get_activity_offers.

    Args:
        request_id: Used only for logging.
        offers: Combined list of raw offer dicts from the provider MCP tools.

    Returns:
        {"status": "success", "valid_offers": [...], "total_valid": N, "total_invalid": M}
        or {"status": "error", "error": "..."}.
    """
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(f"{NORMALIZATION_URL}/normalize", json={"offers": offers})
            resp.raise_for_status()
            result = resp.json()
        _log("OFFERS_NORMALIZED", request_id, {
            "total_received": result.get("total_received"),
            "total_valid":    result.get("total_valid"),
            "total_invalid":  result.get("total_invalid"),
        })
        return {"status": "success", **result}
    except Exception as e:
        _log("NORMALIZATION_FAILED", request_id, {"error": str(e)})
        return {"status": "error", "error": str(e)}

def compose_vacation_packages(request_id: str) -> dict:
    """Assemble 3 candidate vacation packages (budget / balanced / premium).

    Calls the Package Composer Agent (POST /compose), which fetches its own offers
    from the Provider MCP server and combines flight + hotel + activities.
    Results are also persisted to the package_proposals Firestore collection.

    Args:
        request_id: The vacation request document ID.

    Returns:
        {"status": "success", "packages": [...], "package_count": N}
        or {"status": "error", "error": "..."}.
    """
    try:
        with httpx.Client(timeout=300.0) as client:
            resp = client.post(f"{COMPOSER_URL}/compose", json={"request_id": request_id})
            resp.raise_for_status()
            result = resp.json()
        packages = result.get("packages", [])
        _log("PACKAGES_COMPOSED", request_id, {
            "package_count": len(packages),
            "package_ids": [p.get("package_id") for p in packages],
        })
        return {"status": "success", "packages": packages, "package_count": len(packages)}
    except Exception as e:
        _log("COMPOSITION_FAILED", request_id, {"error": str(e)})
        return {"status": "error", "error": str(e)}

def check_package_feasibility(request_id: str, packages: list[dict]) -> dict:
    """Check budget and date alignment for each candidate package.

    Reads budget and travel_dates from the Firestore vacation request, then calls
    the Feasibility Check service (POST /check). Returns only the packages that
    passed — you do not need to filter the results yourself.

    Args:
        request_id: Used to load budget + travel_dates from Firestore.
        packages: Package dicts from compose_vacation_packages.

    Returns:
        {"status": "success", "feasible_packages": [...], "feasible_count": N, "infeasible_count": M}
        or {"status": "error", "error": "..."}.
    """
    from firestore_client import get_vacation_request
    req = get_vacation_request(request_id)
    if not req:
        return {"status": "error", "error": "Vacation request not found"}

    budget = req.get("budget", 999_999)
    try:
        start_date, end_date = _parse_travel_dates(req.get("travel_dates", ""))
        travel_dates = {"start": start_date, "end": end_date}
    except Exception as e:
        return {"status": "error", "error": f"Cannot parse travel_dates: {e}"}

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(f"{FEASIBILITY_URL}/check", json={
                "packages":     packages,
                "budget":       budget,
                "travel_dates": travel_dates,
            })
            resp.raise_for_status()
            result = resp.json()

        feasible_ids = {
            r["package_id"] for r in result.get("results", []) if r.get("feasible")
        }
        feasible = [p for p in packages if p.get("package_id") in feasible_ids]

        _log("FEASIBILITY_CHECKED", request_id, {
            "total_checked":    len(packages),
            "feasible_count":   len(feasible),
            "infeasible_count": len(packages) - len(feasible),
        })
        return {
            "status":             "success",
            "feasible_packages":  feasible,
            "feasible_count":     len(feasible),
            "infeasible_count":   len(packages) - len(feasible),
        }
    except Exception as e:
        _log("FEASIBILITY_FAILED", request_id, {"error": str(e)})
        return {"status": "error", "error": str(e)}

def score_vacation_packages(request_id: str, packages: list[dict]) -> dict:
    """Rank packages by price fit (30%), weather match (25%), activity relevance (25%), convenience (20%).

    Calls the Package Scoring Service (POST /score). Non-critical: if the service
    is unavailable, returns the packages unchanged with score=0 and the pipeline
    continues. You must still call apply_business_rules after this step.

    Args:
        request_id: Used to fetch preferences and for logging.
        packages: Feasible packages from check_package_feasibility.

    Returns:
        {"status": "success"|"unavailable", "scored_packages": [...]}
    """
    from firestore_client import get_vacation_request
    if not SCORING_URL:
        _log("SCORING_SKIPPED", request_id, {"reason": "SCORING_URL not configured"})
        return {"status": "unavailable", "scored_packages": packages}

    req = get_vacation_request(request_id) or {}
    preferences = {
        "vacation_type":      req.get("vacation_type"),
        "weather_preference": req.get("weather_preference"),
        "budget":             req.get("budget"),
        "travel_mode":        req.get("travel_mode"),
        "client_preferences": req.get("client_preferences"),
    }

    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(f"{SCORING_URL}/score", json={
                "request_id":  request_id,
                "packages":    packages,
                "preferences": preferences,
            })
            resp.raise_for_status()
            result = resp.json()
        scored = result.get("scored_packages", packages)
        _log("PACKAGES_SCORED", request_id, {
            "package_count": len(scored),
            "top_score":     scored[0].get("score") if scored else None,
        })
        return {"status": "success", "scored_packages": scored}
    except Exception as e:
        _log("SCORING_FAILED", request_id, {"error": str(e)})
        return {"status": "unavailable", "scored_packages": packages}

def apply_business_rules(request_id: str, packages: list[dict]) -> dict:
    """Filter packages by business rules: provider reliability, agency margin, budget.

    Calls the Business Rules Service (POST /rules/apply). Rules applied:
      1. Exclude providers with reliability_score < 0.7 (e.g. Ryanair at 0.65)
      2. Enforce minimum 15% agency margin
      3. Filter packages exceeding client budget
    Non-critical: if the service is unavailable, returns packages unchanged.

    Args:
        request_id: For logging.
        packages: Scored packages from score_vacation_packages.

    Returns:
        {"status": "success"|"unavailable", "filtered_packages": [...]}
    """
    if not BUSINESS_RULES_URL:
        _log("RULES_SKIPPED", request_id, {"reason": "BUSINESS_RULES_URL not configured"})
        return {"status": "unavailable", "filtered_packages": packages}

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(f"{BUSINESS_RULES_URL}/rules/apply", json={
                "request_id": request_id,
                "packages":   packages,
            })
            resp.raise_for_status()
            result = resp.json()
        filtered = result.get("filtered_packages", packages)
        _log("RULES_APPLIED", request_id, {
            "input_count":  len(packages),
            "output_count": len(filtered),
            "rules_applied": result.get("rules_applied", []),
        })
        return {"status": "success", "filtered_packages": filtered}
    except Exception as e:
        _log("RULES_FAILED", request_id, {"error": str(e)})
        return {"status": "unavailable", "filtered_packages": packages}

def select_best_package(request_id: str, packages: list[dict]) -> dict:
    """Pick the top-ranked package that passed all rules and persist the selection.

    Calls the Package Selection Cloud Function (PACKAGE_SELECTION_URL/select) if
    configured. Otherwise selects inline: highest score wins, ties broken by lowest price.
    Writes the selection back to the vacation_requests Firestore document.

    Args:
        request_id: The vacation request ID.
        packages: Final scored + rule-filtered packages.

    Returns:
        {"status": "success", "selected_package": {...}, "explanation": "..."}
        or {"status": "error", "error": "No packages available"}.
    """
    from firestore_client import update_vacation_request
    if not packages:
        return {"status": "error", "error": "No packages available for selection"}

    selected = None
    if SELECTION_URL:
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(f"{SELECTION_URL}/select", json={
                    "request_id": request_id,
                    "packages":   packages,
                })
                resp.raise_for_status()
                selected = resp.json().get("selected_package")
        except Exception:
            pass  # Fall through to inline selection

    if selected is None:
        selected = max(
            packages,
            key=lambda p: (p.get("score", 0), -p.get("total_price", 999_999)),
        )

    explanation = (
        f"Selected package {selected.get('package_id')} "
        f"(€{selected.get('total_price', 'N/A')}, score={selected.get('score', 'N/A')}). "
        f"{selected.get('rationale', '')}"
    )

    update_vacation_request(request_id, {
        "selected_package_id": selected.get("package_id"),
        "selected_package":    selected,
        "coordination_status": "completed",
    })
    _log("PACKAGE_SELECTED", request_id, {
        "selected_package_id": selected.get("package_id"),
        "total_price":         selected.get("total_price"),
        "score":               selected.get("score"),
    })
    return {"status": "success", "selected_package": selected, "explanation": explanation}

def log_pipeline_event(event_type: str, request_id: str, notes: str) -> dict:
    """Write a pipeline-level milestone to the coordination_event_log in Firestore.

    Use for: PIPELINE_STARTED, PIPELINE_FAILED, PIPELINE_COMPLETED, and any
    custom checkpoints. Service-level events are logged automatically inside
    the other tools — this tool is only for pipeline-level milestones.

    Args:
        event_type: SCREAMING_SNAKE_CASE label (e.g. "PIPELINE_STARTED").
        request_id: The vacation request ID.
        notes: One sentence describing what happened.

    Returns:
        {"status": "logged", "event_type": "...", "event_id": "..."}
    """
    from firestore_client import log_coordination_event
    event_id = log_coordination_event(event_type, request_id, {"notes": notes})
    return {"status": "logged", "event_type": event_type, "event_id": event_id}

def publish_pubsub_event(topic_id: str, request_id: str, notes: str) -> dict:
    """Publish an event to a Pub/Sub topic.

    Call at exactly two points in the pipeline:
      1. After compose_vacation_packages succeeds → topic_id="package-proposal-generated"
      2. After select_best_package succeeds       → topic_id="package-selected"

    Args:
        topic_id: Pub/Sub topic name ("package-proposal-generated" or "package-selected").
        request_id: The vacation request ID.
        notes: Short human-readable description of the event.

    Returns:
        {"status": "published", "message_id": "..."} or {"status": "error", "error": "..."}.
    """
    from pubsub_client import publish_event
    try:
        message_id = publish_event(topic_id, {"request_id": request_id, "notes": notes})
        return {"status": "published", "message_id": message_id, "topic": topic_id}
    except Exception as e:
        return {"status": "error", "error": str(e)}

provider_toolset = MCPToolset(
    connection_params=StreamableHTTPServerParams(url=PROVIDER_MCP_URL)
)

INSTRUCTION = """You are the Coordination Agent for a vacation package system.
You orchestrate the complete assembly pipeline from a raw vacation request to a
selected package. You receive: {"request_id": "<id>"}

Execute the following steps IN ORDER. Do not skip any step.

━━ STEP 1 — START ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Call: log_pipeline_event(event_type="PIPELINE_STARTED", request_id=<id>, notes="Pipeline initiated")

━━ STEP 2 — LOAD REQUEST ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Call: get_vacation_request_details(request_id=<id>)
Remember: destination, vacation_type, weather_preference, travel_dates, budget, travel_mode.
Parse start_date and end_date from travel_dates by splitting on " to ".

━━ STEP 3 — ENRICH ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Call: enrich_vacation_request(request_id=<id>)
If status="error":
  Call log_pipeline_event(event_type="PIPELINE_FAILED", ...) then return:
  {"status": "error", "request_id": <id>, "reason": <error>}
Remember: enriched_destination from the result.

━━ STEP 4 — FETCH PROVIDER OFFERS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Using enriched_destination and start_date / end_date from the request:
Call: get_flight_offers(destination=<enriched_destination>, start_date=<start>, end_date=<end>, travel_mode=<mode or "flight">)
Call: get_hotel_offers(destination=<enriched_destination>, start_date=<start>, end_date=<end>)
Call: get_activity_offers(destination=<enriched_destination>, start_date=<start>, end_date=<end>)
Combine all three returned lists into one flat list.

━━ STEP 5 — NORMALIZE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Call: normalize_offers(request_id=<id>, offers=<combined list from Step 4>)
Continue even if some offers are invalid — the valid_offers count is informational.

━━ STEP 6 — COMPOSE PACKAGES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Call: compose_vacation_packages(request_id=<id>)
If status="error":
  Call log_pipeline_event(event_type="PIPELINE_FAILED", ...) then return error JSON.
Call: publish_pubsub_event(topic_id="package-proposal-generated", request_id=<id>, notes="3 packages composed")
Remember: packages list from the result.

━━ STEP 7 — FEASIBILITY CHECK ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Call: check_package_feasibility(request_id=<id>, packages=<packages from Step 6>)
If feasible_count=0:
  Call log_pipeline_event(event_type="PIPELINE_FAILED", notes="No feasible packages within budget and dates")
  Return: {"status": "error", "request_id": <id>, "reason": "No packages are feasible within budget and travel dates"}
Remember: feasible_packages from the result.

━━ STEP 8 — SCORE PACKAGES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Call: score_vacation_packages(request_id=<id>, packages=<feasible_packages from Step 7>)
Use scored_packages from the result regardless of status (service may be unavailable).

━━ STEP 9 — APPLY BUSINESS RULES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Call: apply_business_rules(request_id=<id>, packages=<scored_packages from Step 8>)
Use filtered_packages from the result regardless of status.
If filtered_packages is empty, use scored_packages instead (do not fail the pipeline).

━━ STEP 10 — SELECT BEST PACKAGE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Call: select_best_package(request_id=<id>, packages=<filtered_packages from Step 9>)
If status="error": call log_pipeline_event(event_type="PIPELINE_FAILED", ...) and return error.
Call: publish_pubsub_event(topic_id="package-selected", request_id=<id>, notes="Best package selected")

━━ STEP 11 — FINISH ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Call: log_pipeline_event(event_type="PIPELINE_COMPLETED", request_id=<id>, notes="Assembly complete")

Return ONLY this JSON (no markdown, no code fences, no extra text):
{"status": "success", "request_id": "<id>", "selected_package": <package object from Step 10>, "explanation": "<explanation from Step 10>"}
"""

root_agent = LlmAgent(
    name="coordination_agent",
    model="gemini-1.5-flash",
    description="Orchestrates the full vacation package assembly pipeline.",
    instruction=INSTRUCTION,
    tools=[
        get_vacation_request_details,
        enrich_vacation_request,
        normalize_offers,
        compose_vacation_packages,
        check_package_feasibility,
        score_vacation_packages,
        apply_business_rules,
        select_best_package,
        log_pipeline_event,
        publish_pubsub_event,
        provider_toolset,
    ],
)
