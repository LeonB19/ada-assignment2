import asyncio
import base64
import json
import logging
import os

from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from coordination_agent.agent import root_agent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Coordination Agent", version="1.0.0")

session_service = InMemorySessionService()
runner = Runner(
    agent=root_agent,
    app_name="coordination-agent",
    session_service=session_service,
)


async def _run_pipeline(request_id: str) -> dict:
    """Run the coordination agent for a single request_id and return the parsed result."""
    user_message = types.Content(
        role="user",
        parts=[types.Part(text=json.dumps({"request_id": request_id}))],
    )

    _RETRYABLE = ("503", "UNAVAILABLE", "ResourceExhausted")
    max_retries = 5
    final_response = None

    for attempt in range(max_retries + 1):
        try:
            session = await session_service.create_session(
                app_name="coordination-agent",
                user_id="system",
            )
            final_response = None
            async for event in runner.run_async(
                user_id="system",
                session_id=session.id,
                new_message=user_message,
            ):
                logger.info(f"Event: is_final={event.is_final_response()}, has_content={event.content is not None}")
                if event.is_final_response():
                    logger.info(f"Final event content: {event.content}")
                    if event.content and event.content.parts:
                        for part in event.content.parts:
                            logger.info(f"Part: text={part.text[:100] if part.text else None}")
                            if part.text:
                                final_response = part.text
                                break
            break  # success
        except Exception as e:
            if attempt < max_retries and any(k in str(e) for k in _RETRYABLE):
                wait = (attempt + 1) * 10
                logger.warning(
                    f"Gemini transient error (attempt {attempt + 1}/{max_retries}), "
                    f"retrying in {wait}s: {e}"
                )
                await asyncio.sleep(wait)
            else:
                raise

    if not final_response:
        return {"status": "error", "request_id": request_id, "reason": "Agent returned no response"}

    text = final_response.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.error(f"Agent returned non-JSON for {request_id}: {text[:200]}")
        return {"status": "error", "request_id": request_id, "reason": "Agent returned malformed JSON"}


async def _run_pipeline_background(request_id: str) -> None:
    """Fire-and-forget wrapper used by the Pub/Sub push endpoint."""
    try:
        result = await _run_pipeline(request_id)
        logger.info(f"Pipeline completed for {request_id}: status={result.get('status')}")
    except Exception as e:
        logger.error(f"Background pipeline failed for {request_id}: {e}")


# ── Models ────────────────────────────────────────────────────────────────────

class AssembleRequest(BaseModel):
    request_id: str


class PubSubMessage(BaseModel):
    data: str
    messageId: str = ""
    publishTime: str = ""


class PubSubPushRequest(BaseModel):
    message: PubSubMessage
    subscription: str = ""


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.post("/assemble")
async def assemble(payload: AssembleRequest):
    """
    Called by the Google Workflow. Runs the full pipeline synchronously
    and returns the selected package.
    """
    logger.info(f"Assemble requested for request_id={payload.request_id}")
    try:
        return await _run_pipeline(payload.request_id)
    except Exception as e:
        logger.error(f"Pipeline error for {payload.request_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/start", status_code=200)
async def start_from_pubsub(payload: PubSubPushRequest, background_tasks: BackgroundTasks):
    """
    Pub/Sub push endpoint. Decodes the message, extracts request_id, and kicks
    off the pipeline as a background task so we can ack immediately (within the
    300 s ack deadline defined in Terraform).
    """
    try:
        decoded = base64.b64decode(payload.message.data).decode("utf-8")
        data = json.loads(decoded)
        request_id = data.get("request_id")
    except Exception as e:
        logger.error(f"Failed to decode Pub/Sub message: {e}")
        return {"status": "ack", "reason": "malformed message"}

    if not request_id:
        logger.error("No request_id in Pub/Sub message payload")
        return {"status": "ack", "reason": "missing request_id"}

    logger.info(f"Pub/Sub trigger received for request_id={request_id}")
    background_tasks.add_task(_run_pipeline_background, request_id)
    return {"status": "accepted", "request_id": request_id}


@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": "coordination-agent"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
