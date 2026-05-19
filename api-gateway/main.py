import os
import time
import httpx
import logging
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

COORDINATION_AGENT_URL =        os.getenv("COORDINATION_AGENT_URL", "http://localhost:8001")
BUSINESS_RULES_URL =            os.getenv("BUSINESS_RULES_URL", "http://localhost:8002")
VACATION_REQUEST_URL =         os.getenv("VACATION_REQUESTS_URL", "http://localhost:8003")
JWT_SECRET =                    os.getenv("JWT_SECRET", "dev-secret")
PROJECT_ID =                    os.getenv("PROJECT_ID", "ada2026-assignment2")

RATE_LIMIT_REQUESTS = 30
RATE_LIMIT_WINDOW   = 60

request_counts: dict[str, list[float]] = defaultdict(list)

def rate_limit_check(request: Request):
    ip = request.client.host
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW
    
    request_counts[ip] = [t for t in request_counts[ip] if t > window_start]
    
    if len(request_counts[ip]) >= RATE_LIMIT_REQUESTS:
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Try again later."
            )
        request_counts[ip].append(now)
        
def verify_jwt(request: Request):
    auth_header = request.headers.get("Authorization", "")
    if request.url.path in ("/health", "/"):
        return {"sub": "anonymous"}
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = auth_header.split(" ", 1)[1]
    
    return {"sub": token}

http_client: httpx.AsyncClient | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    http_client = httpx.AsyncClient(timeout=300.0)
    logger.info("API Gateway started")
    yield
    await http_client.aclose()
    logger.info("API Gateway shut down")
    
app = FastAPI(
    title="Vacation Package System - API Gateway",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"status": "ok", "service": "API Gateway"}

@app.get("/")
async def root():
    return {
        "service": "Vacation Package System API Gateway",
        "routes": {
            "POST /requests":               "Submit a vacation request (client)",
            "GET  /requests/{id}":          "Get a vacation request (client)",
            "GET  /requests":               "List vacation requests (client)",
            "POST /agency/rules":           "Add a business rule (agency)",
            "GET  /agency/rules":           "List business rules (agency)",
            "POST /agency/rules/{id}/delete": "Delete a business rule (agency)",
        }
    }
    
@app.post("/requests", status_code=201)
async def submit_request(
    body: dict,
    request: Request,
    user: dict = Depends(verify_jwt),
    _rl: None = Depends(rate_limit_check),
):
    """
    Route: Client submits a vacation request.
    Forwards to Vacation Request Service, which stores it in Firestore
    and publishes VacationRequestSubmitted to Pub/Sub.
    The Coordination Agent picks that event up and starts assembly.
    """
    logger.info(f"Routing POST /requests from user={user['sub']}")
 
    try:
        resp = await http_client.post(
            f"{VACATION_REQUEST_URL}/requests",
            json={**body, "client_id": user["sub"]},
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"Vacation Request Service unavailable: {e}")
 
    return resp.json()

@app.get("/requests/{request_id}")
async def get_request(
    request_id: str,
    request: Request,
    user: dict = Depends(verify_jwt),
    _rl: None = Depends(rate_limit_check),
):
    """Route: Get a specific vacation request by ID."""
    logger.info(f"Routing GET /requests/{request_id}")
    try:
        resp = await http_client.get(f"{VACATION_REQUEST_URL}/requests/{request_id}")
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"Vacation Request Service unavailable: {e}")
    return resp.json()

@app.get("/requests")
async def list_requests(
    request: Request,
    user: dict = Depends(verify_jwt),
    _rl: None = Depends(rate_limit_check),
):
    """Route: List all vacation requests."""
    logger.info("Routing GET /requests")
    try:
        resp = await http_client.get(f"{VACATION_REQUEST_URL}/requests")
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"Vacation Request Service unavailable: {e}")
    return resp.json()

@app.post("/agency/rules", status_code=201)
async def add_rule(
    body: dict,
    request: Request,
    user: dict = Depends(verify_jwt),
    _rl: None = Depends(rate_limit_check),
):
    """
    Route: Travel agency adds a business rule.
    Forwards to Business Rules Service.
    """
    logger.info(f"Routing POST /agency/rules from user={user['sub']}")
    try:
        resp = await http_client.post(f"{BUSINESS_RULES_URL}/rules", json=body)
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"Business Rules Service unavailable: {e}")
    return resp.json()

@app.get("/agency/rules")
async def list_rules(
    request: Request,
    user: dict = Depends(verify_jwt),
    _rl: None = Depends(rate_limit_check),
):
    """Route: Travel agency lists all business rules."""
    logger.info("Routing GET /agency/rules")
    try:
        resp = await http_client.get(f"{BUSINESS_RULES_URL}/rules")
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"Business Rules Service unavailable: {e}")
    return resp.json()

@app.post("/agency/rules/{rule_id}/delete")
async def delete_rule(
    rule_id: str,
    request: Request,
    user: dict = Depends(verify_jwt),
    _rl: None = Depends(rate_limit_check),
):
    """Route: Travel agency deletes a business rule."""
    logger.info(f"Routing DELETE /agency/rules/{rule_id}")
    try:
        resp = await http_client.delete(f"{BUSINESS_RULES_URL}/rules/{rule_id}")
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text)
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"Business Rules Service unavailable: {e}")
    return resp.json()

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error on {request.method} {request.url}: {exc}")
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})