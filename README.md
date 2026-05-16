# ADA Assignment 2 — Multi-Agent Vacation Package System

## Services in this repo (Paritosh)

| Folder | Type | Port (local) | What it does |
|---|---|---|---|
| `provider-mcp-server/` | FastMCP server | 8080 | Returns mock flight, hotel, activity offers |
| `destination-mcp-server/` | FastMCP server | 8081 | Resolves vague vacation prefs to a concrete city |
| `request-enrichment-agent/` | ADK LlmAgent + FastAPI | 8082 | Enriches vacation requests in Firestore |

Other folders: `api-gateway/` (Leon), `leon_infra/` (Leon's Terraform).

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

# Install deps for all three services
pip install -r provider-mcp-server/requirements.txt
pip install -r destination-mcp-server/requirements.txt
pip install -r request-enrichment-agent/requirements.txt
```

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

## Deployment (Leon handles this)

Each service has a `Dockerfile`. Leon's Terraform in `leon_infra/` deploys them to Cloud Run. Once deployed, Leon will share the Cloud Run URLs — replace the localhost URLs above with those.

Docker image locations (Artifact Registry):
```
us-central1-docker.pkg.dev/ada2026-assignment2/vacation-system/provider-mcp-server:latest
us-central1-docker.pkg.dev/ada2026-assignment2/vacation-system/destination-mcp-server:latest
us-central1-docker.pkg.dev/ada2026-assignment2/vacation-system/request-enrichment-agent:latest
```
