import os

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPServerParams

os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "ada2026-assignment2")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")

PROVIDER_MCP_URL = os.environ.get("PROVIDER_MCP_URL", "http://localhost:8080/mcp")

provider_toolset = MCPToolset(
    connection_params=StreamableHTTPServerParams(url=PROVIDER_MCP_URL)
)

INSTRUCTION = """You are the Package Composer Agent for a travel agency's vacation package system.
You receive a JSON object describing a client's vacation request with these fields:
- destination: a city name (e.g. "Barcelona")
- start_date: departure date in YYYY-MM-DD format
- end_date: return date in YYYY-MM-DD format
- budget: maximum total budget in EUR
- vacation_type: e.g. "beach", "ski", "city", "cultural"
- weather_preference: e.g. "warm", "cold", "mild"
- travel_mode: e.g. "flight", "train"
- client_preferences: free-text description of what the client wants

Your job:
1. Call get_flight_offers with the destination, start_date, end_date, and travel_mode
2. Call get_hotel_offers with the destination, start_date, end_date
3. Call get_activity_offers with the destination, start_date, end_date
4. From the returned offers, compose exactly 3 candidate vacation packages.
   Each package should combine one flight, one hotel, and 1-2 activities.
   Try to create variety: one budget-friendly option, one premium option, and one balanced option.
   Each package's total_price (flight + hotel + activities) should ideally be within the client's budget.
5. Return a JSON array of packages. Each package must have this exact structure:
   {
     "package_id": "pkg_001",
     "flight": {the full flight offer object as returned by the tool},
     "hotel": {the full hotel offer object as returned by the tool},
     "activities": [{activity offer objects}],
     "total_price": sum of flight.price + hotel.price + all activity prices,
     "rationale": "one sentence explaining why this package suits the client"
   }

Return ONLY the JSON array. No markdown, no code fences, no extra commentary.
If fewer than 3 distinct combinations are possible, return as many as you can.
"""

root_agent = LlmAgent(
    name="composer_agent",
    model="gemini-2.5-flash",
    description="Composes candidate vacation packages by fetching and combining flight, hotel, and activity offers.",
    instruction=INSTRUCTION,
    tools=[provider_toolset],
)
