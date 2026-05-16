import os
import json

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from google.cloud import firestore

from enrichment_agent.agent import root_agent
from firestore_client import get_vacation_request, update_vacation_request

app = FastAPI(title="Request Enrichment Agent", version="1.0.0")

session_service = InMemorySessionService()
runner = Runner(
    agent=root_agent,
    app_name="enrichment-agent",
    session_service=session_service,
)


class EnrichRequestInput(BaseModel):
    request_id: str


class EnrichRequestOutput(BaseModel):
    request_id: str
    enriched_destination: str
    weather_preference: str
    enrichment_status: str
    enrichment_notes: str


@app.post("/enrich", response_model=EnrichRequestOutput)
async def enrich(payload: EnrichRequestInput):
    # 1. Read vacation request from Firestore
    request = get_vacation_request(payload.request_id)
    if not request:
        raise HTTPException(status_code=404, detail="Request not found")

    # 2. Build the prompt from the request fields
    input_data = {
        "destination": request.get("destination"),
        "vacation_type": request.get("vacation_type"),
        "weather_preference": request.get("weather_preference"),
    }
    user_message = types.Content(
        role="user",
        parts=[types.Part(text=json.dumps(input_data))],
    )

    # 3. Create a fresh session and run the agent
    session = await session_service.create_session(
        app_name="enrichment-agent",
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

    # 4. Parse the agent's JSON output
    text = final_response.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    enriched = json.loads(text)

    # 5. Write enriched fields back to Firestore
    update_vacation_request(payload.request_id, {
        "enriched_destination": enriched["enriched_destination"],
        "weather_preference": enriched["weather_preference"],
        "enrichment_status": "enriched",
        "enrichment_timestamp": firestore.SERVER_TIMESTAMP,
    })

    # 6. Return the enriched response to the caller
    return EnrichRequestOutput(
        request_id=payload.request_id,
        enriched_destination=enriched["enriched_destination"],
        weather_preference=enriched["weather_preference"],
        enrichment_status="enriched",
        enrichment_notes=enriched.get("enrichment_notes", ""),
    )


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
