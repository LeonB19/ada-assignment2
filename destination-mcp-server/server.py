import os

from mcp.server.fastmcp import FastMCP
from destination_data import DESTINATION_TABLE
from llm_fallback import resolve_via_llm

port = int(os.environ.get("PORT", 8081))
mcp = FastMCP("destination-mcp-server", host="0.0.0.0", port=port)


@mcp.tool()
def resolve_destination(vacation_type: str, weather_preference: str) -> dict:
    """Resolve a vague vacation request into a concrete destination city.

    Looks up known (vacation_type, weather_preference) combinations in an
    internal table. If no match is found, calls Gemini as a fallback.

    Args:
        vacation_type: e.g. "beach", "ski", "city", "cultural", "hiking", "any"
        weather_preference: e.g. "warm", "cold", "mild", "hot", "snowy", "any"

    Returns:
        Dict with keys:
            destination (str): concrete city name
            rationale (str): one-sentence explanation
            source (str): "table" if lookup matched, "llm" if Gemini was used
    """
    key = (vacation_type.lower().strip(), weather_preference.lower().strip())

    if key in DESTINATION_TABLE:
        result = DESTINATION_TABLE[key]
        return {**result, "source": "table"}

    # Fallback to LLM for combinations not in the table
    result = resolve_via_llm(vacation_type, weather_preference)
    return {**result, "source": "llm"}


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
