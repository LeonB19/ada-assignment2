# ADA Assignment 2 — Multi-Agent Vacation Package System

## Services in this repo

| Folder | Owner | Type | Port (local) | What it does |
|---|---|---|---|---|
| `provider-mcp-server/` | Paritosh | FastMCP server | 8080 | Returns mock flight, hotel, activity offers |
| `destination-mcp-server/` | Paritosh | FastMCP server | 8081 | Resolves vague vacation prefs to a concrete city |
| `request-enrichment-agent/` | Paritosh | ADK LlmAgent + FastAPI | 8082 | Enriches vacation requests in Firestore |
| `price-normalization/` | Paritosh | FastAPI | 8083 | Validates and filters raw provider offers |
| `package-composer-agent/` | Paritosh | ADK LlmAgent + FastAPI | 8084 | Assembles 3 candidate packages (budget/balanced/premium) |
| `feasibility-check/` | Paritosh | FastAPI | 8085 | Checks budget and date alignment per package |
| `coordination-agent/` | Noud | ADK LlmAgent + FastAPI | 8086 | Orchestrates the full assembly pipeline |
| `vacation-requests-service/` | Noud | FastAPI | 8003 | Accepts vacation requests, writes to Firestore, fires Pub/Sub |
| `preference-validator/` | Noud | Cloud Function | — | Validates requests triggered by Pub/Sub |
| `api-gateway/` | Leon | FastAPI | — | Public entry point, JWT auth, rate limiting |
| `leon_infra/` | Leon | Terraform | — | GCP infrastructure (Cloud Run, Pub/Sub, Firestore) |

---

## Prerequisites

- Python 3.12
- A virtual environment with all dependencies installed (see below)
- Node.js (only needed if you want to use MCP Inspector to test the MCP servers visually)

### Set up the virtual environment (do this once)

```bash
cd ada-assignment2
python3.12 -m venv .venv
source .venv/bin/activate

pip install -r provider-mcp-server/requirements.txt
pip install -r destination-mcp-server/requirements.txt
pip install -r request-enrichment-agent/requirements.txt
pip install -r price-normalization/requirements.txt
pip install -r package-composer-agent/requirements.txt
pip install -r feasibility-check/requirements.txt
pip install -r coordination-agent/requirements.txt
```

### GCP setup (do this once)

```bash
gcloud auth application-default login
gcloud config set project ada2026-assignment2

# Create the Firestore database if it doesn't exist yet
gcloud firestore databases create --location=us-central1 --project=ada2026-assignment2
```

Billing must be enabled on the project for Vertex AI (used by all LLM agents):
`https://console.developers.google.com/billing/enable?project=ada2026-assignment2`

---

## Running the services locally

Always activate the venv first: `source .venv/bin/activate`

### 1. Provider MCP Server (port 8080)

```bash
cd provider-mcp-server
python server.py
# MCP endpoint: http://localhost:8080/mcp
```

### 2. Destination MCP Server (port 8081)

Open a second terminal:

```bash
cd destination-mcp-server
python server.py
# MCP endpoint: http://localhost:8081/mcp
```

### 3. Request Enrichment Agent

The enrichment agent needs the Destination MCP Server running first.

**Option A — Interactive CLI (for quick testing):**

```bash
cd request-enrichment-agent
DESTINATION_MCP_URL=http://localhost:8081/mcp adk run enrichment_agent
```

Then type a JSON payload:
```
{"destination": null, "vacation_type": "beach", "weather_preference": "warm"}
```

Expected output:
```json
{"enriched_destination": "Barcelona", "weather_preference": "warm", "enrichment_notes": "..."}
```

**Option B — REST API (for integration with other services):**

```bash
cd request-enrichment-agent
DESTINATION_MCP_URL=http://localhost:8081/mcp python app.py
# Runs on http://localhost:8082
```

Call it:
```bash
curl -X POST http://localhost:8082/enrich \
  -H "Content-Type: application/json" \
  -d '{"request_id": "<firestore-doc-id>"}'
```

Health check:
```bash
curl http://localhost:8082/healthz
```

---

## Running the full pipeline locally (Noud's services)

To run the end-to-end pipeline locally you need 8 terminals. Activate the venv first in each: `source .venv/bin/activate`

### Port map

| Terminal | Service | Command |
|---|---|---|
| 1 | Provider MCP | `cd provider-mcp-server && python server.py` |
| 2 | Destination MCP | `cd destination-mcp-server && python server.py` |
| 3 | Enrichment agent | `cd request-enrichment-agent && DESTINATION_MCP_URL=http://localhost:8081/mcp PORT=8082 python app.py` |
| 4 | Price normalization | `cd price-normalization && PORT=8083 python main.py` |
| 5 | Package composer | `cd package-composer-agent && PROVIDER_MCP_URL=http://localhost:8080/mcp PORT=8084 python app.py` |
| 6 | Feasibility check | `cd feasibility-check && PORT=8085 python main.py` |
| 7 | Coordination agent | see below |
| 8 | Vacation requests | `cd vacation-requests-service && uvicorn mail:app --host 0.0.0.0 --port 8003` |

### 7. Coordination Agent (port 8086)

Needs all other services running first.

```bash
cd coordination-agent
ENRICHMENT_URL=http://localhost:8082 \
NORMALIZATION_URL=http://localhost:8083 \
COMPOSER_URL=http://localhost:8084 \
FEASIBILITY_URL=http://localhost:8085 \
PROVIDER_MCP_URL=http://localhost:8080/mcp \
PORT=8086 \
python app.py
```

Health check:
```bash
curl http://localhost:8086/healthz
```

### End-to-end test

**Step 1 — Create a vacation request:**
```bash
curl -X POST http://localhost:8003/requests \
  -H "Content-Type: application/json" \
  -d '{
    "client_preferences": "warm beach holiday",
    "vacation_type": "beach",
    "travel_dates": "2026-07-10 to 2026-07-20",
    "budget": 2000,
    "weather_preference": "warm"
  }'
# Returns: {"status": "submitted", "request_id": "req_<id>"}
```

**Step 2 — Trigger the coordination agent** (replace `req_<id>` with the returned value):
```bash
curl -X POST http://localhost:8086/assemble \
  -H "Content-Type: application/json" \
  -d '{"request_id": "req_<id>"}'
```

The agent runs the full pipeline: Enrich → Fetch offers → Normalize → Compose → Feasibility → Score → Rules → Select.
Every step is logged to the `coordination_event_log` Firestore collection.
The final selected package is written back to the `vacation_requests` Firestore document.

### Environment variables for the Coordination Agent

| Variable | Default | Description |
|---|---|---|
| `ENRICHMENT_URL` | `http://localhost:8082` | Request Enrichment Agent |
| `NORMALIZATION_URL` | `http://localhost:8083` | Price Normalization Service |
| `COMPOSER_URL` | `http://localhost:8084` | Package Composer Agent |
| `FEASIBILITY_URL` | `http://localhost:8085` | Feasibility Check Service |
| `PROVIDER_MCP_URL` | `http://localhost:8080/mcp` | Provider MCP Server |
| `SCORING_URL` | _(empty)_ | Package Scoring Service (skipped if not set) |
| `BUSINESS_RULES_URL` | _(empty)_ | Business Rules Service (skipped if not set) |
| `PACKAGE_SELECTION_URL` | _(empty)_ | Package Selection Function (inline fallback if not set) |
| `PORT` | `8080` | HTTP port (set to 8086 locally to avoid conflict with Provider MCP) |

---

## Testing the MCP servers with MCP Inspector

MCP Inspector is a browser UI that lets you call MCP tools directly without writing any code. Useful for verifying the provider and destination servers work correctly.

```bash
npx @modelcontextprotocol/inspector
```

This opens a browser UI. In the UI:
- **Transport Type**: Streamable HTTP
- **URL**: `http://localhost:8080/mcp` (provider) or `http://localhost:8081/mcp` (destination)
- Click **Connect**, then go to the **Tools** tab to see and call the available tools.

---

## MCP Tools reference

### Provider MCP Server — `http://<host>/mcp`

| Tool | Parameters | Returns |
|---|---|---|
| `get_flight_offers` | `destination` (IATA or city), `start_date` (YYYY-MM-DD), `end_date` (YYYY-MM-DD), `travel_mode` (default: "flight") | List of flight `NormalizedOffer` dicts |
| `get_hotel_offers` | `destination` (city name), `start_date`, `end_date` | List of hotel `NormalizedOffer` dicts |
| `get_activity_offers` | `destination` (city name), `start_date`, `end_date` | List of activity `NormalizedOffer` dicts |

Example call (via MCP Inspector or from an ADK agent):
```json
{ "destination": "Barcelona", "start_date": "2026-07-10", "end_date": "2026-07-20" }
```

All offers follow the `NormalizedOffer` schema:
```json
{
  "offer_id": "flt_klm_BCN_2026-07-10",
  "provider_id": "klm",
  "offer_type": "flight",
  "price": 234.50,
  "currency": "EUR",
  "tax_included": true,
  "availability_window": { "start": "2026-07-10", "end": "2026-07-20" },
  "quote_expiry": "2026-07-11T10:00:00+00:00",
  "metadata": { "flight_number": "KL4821", "origin": "AMS", "destination": "BCN", ... }
}
```

Supported destinations: Barcelona, Rome, Athens, Innsbruck, Amsterdam (also accepts IATA codes: BCN, ROM, ATH, INN, AMS).

Providers included:

| Provider | Type | Reliability score |
|---|---|---|
| KLM | flight | 0.92 |
| Ryanair | flight | 0.65 (below 0.7 threshold — filtered by Business Rules) |
| Marriott | hotel | 0.88 |
| Booking Partner | hotel | 0.80 |
| GetYourGuide | activity | 0.85 |

---

### Destination MCP Server — `http://<host>/mcp`

| Tool | Parameters | Returns |
|---|---|---|
| `resolve_destination` | `vacation_type` (e.g. "beach", "ski", "city", "cultural", "hiking", "any"), `weather_preference` (e.g. "warm", "cold", "mild", "hot", "any") | `{ destination, rationale, source }` |

`source` is `"table"` if the combination was in the lookup table, `"llm"` if Gemini was called as fallback.

Example:
```json
Input:  { "vacation_type": "ski", "weather_preference": "cold" }
Output: { "destination": "Innsbruck", "rationale": "Austrian Alps, reliable winter snow", "source": "table" }
```

---

## Wiring these MCP servers into your ADK agent

If you are Noud or Manan and need to call the Provider MCP Server or Destination MCP Server from your ADK agent, here is the pattern (same as Lab 6):

```python
from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPServerParams
import os

# Point at the deployed Cloud Run URL in production, or localhost for local dev
provider_toolset = MCPToolset(
    connection_params=StreamableHTTPServerParams(
        url=os.environ.get("PROVIDER_MCP_URL", "http://localhost:8080/mcp")
    )
)

destination_toolset = MCPToolset(
    connection_params=StreamableHTTPServerParams(
        url=os.environ.get("DESTINATION_MCP_URL", "http://localhost:8081/mcp")
    )
)

my_agent = LlmAgent(
    name="my_agent",
    model="gemini-2.5-flash",
    instruction="Your instruction here...",
    tools=[provider_toolset],          # or destination_toolset, or both
)
```

The MCP tools are automatically discovered — the agent will see `get_flight_offers`, `get_hotel_offers`, `get_activity_offers` (from provider server) or `resolve_destination` (from destination server) as callable tools.

**Environment variables to set:**

| Variable | Local default | Production |
|---|---|---|
| `PROVIDER_MCP_URL` | `http://localhost:8080/mcp` | Cloud Run URL from Leon |
| `DESTINATION_MCP_URL` | `http://localhost:8081/mcp` | Cloud Run URL from Leon |
| `GOOGLE_API_KEY` | hardcoded in agent.py for now | Secret Manager (Leon configures) |
| `GOOGLE_CLOUD_PROJECT` | hardcoded as `ada2026-assignment2` | Set as Cloud Run env var |

---

## Calling the Enrichment Agent from your service

The enrichment agent exposes a single REST endpoint. Call it after a vacation request is submitted to Firestore:

```bash
POST http://<enrichment-agent-url>/enrich
Content-Type: application/json

{ "request_id": "<firestore-vacation-request-doc-id>" }
```

Response:
```json
{
  "request_id": "abc123",
  "enriched_destination": "Barcelona",
  "weather_preference": "warm",
  "enrichment_status": "enriched",
  "enrichment_notes": "Destination resolved via destination MCP server."
}
```

The agent also writes `enriched_destination`, `weather_preference`, `enrichment_status`, and `enrichment_timestamp` directly back to the `vacation_requests` Firestore document.

---

## Seeding Firestore provider metadata (run once)

Once you have GCP credentials set up (`gcloud auth application-default login`):

```bash
cd provider-mcp-server
python seed/seed_provider_metadata.py
```

This populates the `provider_metadata` Firestore collection with all 5 providers. Noud's Business Rules Service reads from this collection.

---

---

## Package Assembly Services

Three services that sit between the enrichment agent and the coordination agent.
Call order: **normalize → compose → check**

---

### Price Normalization (`price-normalization/`)

Validates raw offers from the Provider MCP Server — filters out malformed, zero-priced, or expired offers.

**Endpoint:** `POST /normalize`  
**Port (local):** 8083

**Input:**
```json
{
  "offers": [
    {
      "offer_id": "flt_klm_BCN_2026-07-10",
      "provider_id": "klm",
      "offer_type": "flight",
      "price": 234.50,
      "currency": "EUR",
      "tax_included": true,
      "availability_window": {"start": "2026-07-10", "end": "2026-07-20"},
      "quote_expiry": "2027-07-11T10:00:00+00:00",
      "metadata": {"flight_number": "KL4821"}
    }
  ]
}
```

**Output:**
```json
{
  "valid_offers": [...],
  "invalid_offers": [{"offer_id": "...", "errors": ["quote_expiry is in the past"]}],
  "total_received": 5,
  "total_valid": 4,
  "total_invalid": 1
}
```

Validation rules: offer shape must match `NormalizedOffer`, `price > 0`, `quote_expiry` not in the past.

**Run locally:**
```bash
cd price-normalization
pip install -r requirements.txt
python main.py
# http://localhost:8080
```

---

### Package Composer Agent (`package-composer-agent/`)

ADK agent that fetches live flight, hotel, and activity offers from the Provider MCP Server and assembles 3 candidate vacation packages (budget / balanced / premium).

Reads the vacation request from Firestore by `request_id`, runs the agent, and writes results to the `package_proposals` Firestore collection.

**Requires:** Provider MCP Server running.

**Endpoint:** `POST /compose`

**Input:**
```json
{"request_id": "req_abc12345"}
```

**Output:**
```json
{
  "request_id": "req_abc12345",
  "status": "proposed",
  "packages": [
    {
      "package_id": "pkg_001",
      "flight": {"..."},
      "hotel": {"..."},
      "activities": [{"..."}],
      "total_price": 1129.50,
      "rationale": "Budget-friendly option with essential activities."
    }
  ]
}
```

**Environment variables:**

| Variable | Local default | Production |
|---|---|---|
| `PROVIDER_MCP_URL` | `http://localhost:8080/mcp` | Cloud Run URL from Leon |
| `PORT` | `8080` | Set by Cloud Run |

**Run locally:**
```bash
cd package-composer-agent
pip install -r requirements.txt
PROVIDER_MCP_URL=http://localhost:8080/mcp python app.py
# http://localhost:8080
```

---

### Feasibility Check (`feasibility-check/`)

Runs three deterministic checks on candidate packages: budget, flight/hotel date alignment, and activity date range. No external dependencies.

**Endpoint:** `POST /check`

**Input:**
```json
{
  "packages": [
    {
      "package_id": "pkg_001",
      "flight": {
        "offer_id": "flt_klm_BCN_2026-07-10",
        "price": 234.50,
        "availability_window": {"start": "2026-07-10", "end": "2026-07-20"}
      },
      "hotel": {
        "offer_id": "htl_marriott_Barcelona_2026-07-10",
        "price": 850.00,
        "availability_window": {"start": "2026-07-10", "end": "2026-07-20"}
      },
      "activities": [
        {
          "offer_id": "act_getyourguide_Barcelona_2026-07-10_0",
          "price": 45.00,
          "availability_window": {"start": "2026-07-10", "end": "2026-07-20"}
        }
      ],
      "total_price": 1129.50
    }
  ],
  "budget": 2000.0,
  "travel_dates": {"start": "2026-07-10", "end": "2026-07-20"}
}
```

**Output:**
```json
{
  "results": [
    {"package_id": "pkg_001", "feasible": true, "reasons": []},
    {"package_id": "pkg_002", "feasible": false, "reasons": ["Total price €2150.00 exceeds budget €2000.00"]}
  ]
}
```

Checks per package:
1. `total_price <= budget`
2. Flight window overlaps hotel window
3. Each activity window falls within `travel_dates`

**Run locally:**
```bash
cd feasibility-check
pip install -r requirements.txt
python main.py
# http://localhost:8080
```

---

### For the Coordination Agent

Call these three services in this order for each vacation request:

| Step | Service | Endpoint | Input | Key output field |
|---|---|---|---|---|
| 1 | Price Normalization | `POST /normalize` | `{"offers": [...]}` | `valid_offers` |
| 2 | Package Composer | `POST /compose` | `{"request_id": "..."}` | `packages` |
| 3 | Feasibility Check | `POST /check` | `{"packages": [...], "budget": ..., "travel_dates": {...}}` | `results[].feasible` |

Pass `valid_offers` from Step 1 into the context for Step 2 (the composer agent fetches its own offers internally, but normalization should gate what's considered valid upstream). After Step 3, only packages where `feasible: true` should be presented to the client.

---

### Deployment (Package Assembly Services)

```bash
# Build and push
docker build -t us-central1-docker.pkg.dev/ada2026-assignment2/vacation-system/price-normalization:latest ./price-normalization
docker push us-central1-docker.pkg.dev/ada2026-assignment2/vacation-system/price-normalization:latest

docker build -t us-central1-docker.pkg.dev/ada2026-assignment2/vacation-system/package-composer-agent:latest ./package-composer-agent
docker push us-central1-docker.pkg.dev/ada2026-assignment2/vacation-system/package-composer-agent:latest

docker build -t us-central1-docker.pkg.dev/ada2026-assignment2/vacation-system/feasibility-check:latest ./feasibility-check
docker push us-central1-docker.pkg.dev/ada2026-assignment2/vacation-system/feasibility-check:latest

# Deploy
gcloud run deploy price-normalization \
  --image us-central1-docker.pkg.dev/ada2026-assignment2/vacation-system/price-normalization:latest \
  --region us-central1 --project ada2026-assignment2 \
  --service-account vacation-system-sa@ada2026-assignment2.iam.gserviceaccount.com \
  --allow-unauthenticated

gcloud run deploy package-composer-agent \
  --image us-central1-docker.pkg.dev/ada2026-assignment2/vacation-system/package-composer-agent:latest \
  --region us-central1 --project ada2026-assignment2 \
  --service-account vacation-system-sa@ada2026-assignment2.iam.gserviceaccount.com \
  --set-env-vars PROVIDER_MCP_URL=<provider-mcp-cloud-run-url> \
  --allow-unauthenticated

gcloud run deploy feasibility-check \
  --image us-central1-docker.pkg.dev/ada2026-assignment2/vacation-system/feasibility-check:latest \
  --region us-central1 --project ada2026-assignment2 \
  --service-account vacation-system-sa@ada2026-assignment2.iam.gserviceaccount.com \
  --allow-unauthenticated
```

---

## Deployment (Leon handles this)

Each service has a `Dockerfile`. Leon's Terraform in `leon_infra/` deploys them to Cloud Run. Once deployed, Leon will share the Cloud Run URLs — replace the localhost URLs above with those.

Docker image locations (Artifact Registry):
```
us-central1-docker.pkg.dev/ada2026-assignment2/vacation-system/provider-mcp-server:latest
us-central1-docker.pkg.dev/ada2026-assignment2/vacation-system/destination-mcp-server:latest
us-central1-docker.pkg.dev/ada2026-assignment2/vacation-system/request-enrichment-agent:latest
```
