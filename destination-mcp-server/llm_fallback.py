import json
import urllib.request
import urllib.error

GEMINI_API_KEY = "AIzaSyDoLIS6uLUshDTVPM-A_JTIYc7u_54gBhQ"
GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash:generateContent"
)


def resolve_via_llm(vacation_type: str, weather_preference: str) -> dict:
    """Call Gemini to resolve a destination when the lookup table has no match."""
    prompt = f"""You are a travel destination expert. Given the following preferences,
suggest ONE European city as a vacation destination.

vacation_type: {vacation_type}
weather_preference: {weather_preference}

Respond ONLY in valid JSON with this exact schema:
{{"destination": "<city name>", "rationale": "<one-sentence reason>"}}

Do not include markdown, code fences, or commentary."""

    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}]
    }).encode("utf-8")

    req = urllib.request.Request(
        GEMINI_API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-goog-api-key": GEMINI_API_KEY,
        },
        method="POST",
    )

    with urllib.request.urlopen(req) as resp:
        body = json.loads(resp.read().decode("utf-8"))

    text = body["candidates"][0]["content"]["parts"][0]["text"].strip()

    # Strip code fences if the model adds them
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    parsed = json.loads(text)
    return {
        "destination": parsed["destination"],
        "rationale": parsed["rationale"],
    }
