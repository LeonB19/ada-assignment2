import os
import json
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from composer_agent.agent import root_agent
from firestore_client import get_vacation_request, save_package_proposal

app = FastAPI(title="Package Composer Agent", version="1.0.0")

session_service = InMemorySessionService()
runner = Runner(
    agent=root_agent,
    app_name="composer-agent",
    session_service=session_service,
)


class ComposeRequestInput(BaseModel):
    request_id: str


def _parse_travel_dates(travel_dates) -> tuple[str, str]:
    """Parse travel_dates into (start_date, end_date).

    Handles two formats:
      - string: "2026-07-10 to 2026-07-20"
      - dict:   {"departure": "2026-07-10", "return": "2026-07-20"}
    """
    if isinstance(travel_dates, dict):
        return travel_dates["departure"], travel_dates["return"]
    # string format: "YYYY-MM-DD to YYYY-MM-DD"
    parts = str(travel_dates).split(" to ")
    return parts[0].strip(), parts[1].strip()


@app.post("/compose")
async def compose(payload: ComposeRequestInput):
    # 1. Read vacation request from Firestore
    request = get_vacation_request(payload.request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")

    # 2. Parse travel dates
    travel_dates = request.get("travel_dates")
    if not travel_dates:
        raise HTTPException(status_code=422, detail="travel_dates missing from request")
    start_date, end_date = _parse_travel_dates(travel_dates)

    # 3. Build input for the agent — use enriched_destination if available
    input_data = {
        "destination": request.get("enriched_destination") or request.get("destination"),
        "start_date": start_date,
        "end_date": end_date,
        "budget": request.get("budget"),
        "vacation_type": request.get("vacation_type"),
        "weather_preference": request.get("weather_preference"),
        "travel_mode": request.get("travel_mode", "flight"),
        "client_preferences": request.get("client_preferences"),
    }

    user_message = types.Content(
        role="user",
        parts=[types.Part(text=json.dumps(input_data))],
    )

    # 4. Create a fresh session and run the agent
    session = await session_service.create_session(
        app_name="composer-agent",
        user_id="system",
    )

    final_response = None
    async for event in runner.run_async(
        user_id="system",
        session_id=session.id,
        new_message=user_message,
    ):
        if event.is_final_response():
            final_response = event.content.parts[0].text

    if not final_response:
        raise HTTPException(status_code=500, detail="Agent returned no response")

    # 5. Strip markdown fences defensively and parse JSON
    text = final_response.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    packages = json.loads(text)

    # 6. Save to Firestore package_proposals collection
    save_package_proposal(payload.request_id, {
        "request_id": payload.request_id,
        "packages": packages,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "proposed",
    })

    # 7. Return to caller
    return {
        "request_id": payload.request_id,
        "packages": packages,
        "status": "proposed",
    }


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
