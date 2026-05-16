import os

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPServerParams

GEMINI_API_KEY = "AIzaSyDoLIS6uLUshDTVPM-A_JTIYc7u_54gBhQ"
os.environ.setdefault("GOOGLE_API_KEY", GEMINI_API_KEY)

DESTINATION_MCP_URL = os.environ.get("DESTINATION_MCP_URL", "http://localhost:8081/mcp")

destination_toolset = MCPToolset(
    connection_params=StreamableHTTPServerParams(url=DESTINATION_MCP_URL)
)

INSTRUCTION = """You are the Request Enrichment Agent for a travel agency's
vacation package system. You receive a vacation request that may have vague,
incomplete, or missing fields. Your job is to enrich it into a concrete request
that downstream agents can act on.

You receive a JSON object with these fields:
- destination: may be a city, a vacation type ("beach holiday"), or null
- vacation_type: e.g. "beach", "ski", "city", "cultural", or null
- weather_preference: e.g. "warm", "cold", "mild", or null

Your responsibilities:
1. If `destination` is null or vague (not a recognised European city name), call the
   `resolve_destination` tool with the available vacation_type and
   weather_preference to get a concrete city.
2. If `weather_preference` is null:
   - Infer from vacation_type: beach -> "warm", ski -> "cold",
     hiking -> "mild", city/cultural -> "mild".
   - If vacation_type is also null, default to "any".
3. Return a JSON object in this exact shape:
   {
     "enriched_destination": "<concrete city name>",
     "weather_preference": "<warm|cold|mild|hot|any>",
     "enrichment_notes": "<one-sentence explanation of what you changed>"
   }

Do not include markdown, code fences, or commentary. Only the JSON object.
"""

root_agent = LlmAgent(
    name="enrichment_agent",
    model="gemini-2.5-flash",
    description="Enriches vague vacation requests into concrete bookable ones.",
    instruction=INSTRUCTION,
    tools=[destination_toolset],
)
