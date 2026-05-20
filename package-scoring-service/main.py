import os
import logging
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Package Scoring Service", version="1.0.0")

# Scoring weights
W_PRICE       = 0.30
W_WEATHER     = 0.25
W_ACTIVITY    = 0.25
W_CONVENIENCE = 0.20


class ScoreRequest(BaseModel):
    request_id: str
    packages: list[dict[str, Any]]
    preferences: dict[str, Any]


class ScoreResponse(BaseModel):
    scored_packages: list[dict[str, Any]]


def _score_price_fit(total_price: float, budget: float) -> float:
    """Higher score the further below budget the package is."""
    if not budget or budget <= 0:
        return 0.5
    if total_price >= budget:
        return 0.0
    return min(1.0, (budget - total_price) / budget)


def _score_weather(package: dict, weather_preference: str) -> float:
    """1.0 if destination weather matches preference, 0.5 otherwise."""
    if not weather_preference:
        return 0.5
    pref = weather_preference.lower()
    # Check hotel metadata, then activity metadata for a weather hint
    hotel = package.get("hotel") or {}
    hotel_meta = hotel.get("metadata") or {}
    package_weather = (
        hotel_meta.get("weather")
        or hotel_meta.get("climate")
        or hotel_meta.get("weather_type")
        or ""
    ).lower()
    if not package_weather:
        return 0.5
    return 1.0 if pref in package_weather or package_weather in pref else 0.5


def _score_activity_relevance(package: dict, vacation_type: str) -> float:
    """Score based on how well activity categories match the vacation type."""
    if not vacation_type:
        return 0.5
    vtype = vacation_type.lower()
    activities = package.get("activities") or []
    if not activities:
        return 0.5

    matches = 0
    for act in activities:
        meta = (act.get("metadata") or {})
        category = (
            meta.get("category") or meta.get("type") or meta.get("activity_type") or ""
        ).lower()
        tags = [t.lower() for t in meta.get("tags", [])]
        if vtype in category or any(vtype in t or t in vtype for t in tags):
            matches += 1
        # Also match common synonyms
        elif _vacation_type_matches(vtype, category, tags):
            matches += 1

    return min(1.0, matches / len(activities)) if activities else 0.5


_VACATION_SYNONYMS: dict[str, list[str]] = {
    "beach":    ["beach", "sea", "coastal", "swimming", "sun", "sand", "water"],
    "ski":      ["ski", "snow", "winter", "mountain", "alpine"],
    "city":     ["city", "urban", "sightseeing", "museum", "culture", "tour"],
    "cultural": ["cultural", "museum", "history", "heritage", "art", "tour"],
    "relaxation": ["spa", "wellness", "relax", "yoga", "retreat"],
    "adventure": ["adventure", "hiking", "climbing", "outdoor", "sport"],
}


def _vacation_type_matches(vtype: str, category: str, tags: list[str]) -> bool:
    synonyms = _VACATION_SYNONYMS.get(vtype, [vtype])
    combined = category + " " + " ".join(tags)
    return any(s in combined for s in synonyms)


def _score_travel_convenience(package: dict, travel_mode: str) -> float:
    """1.0 if travel mode matches flight metadata, 0.5 otherwise."""
    if not travel_mode:
        return 0.5
    mode = travel_mode.lower()
    flight = package.get("flight") or {}
    flight_meta = flight.get("metadata") or {}
    package_mode = (
        flight_meta.get("mode")
        or flight_meta.get("travel_mode")
        or flight_meta.get("transport_type")
        or flight.get("offer_type")
        or flight.get("type")
        or ""
    ).lower()
    if not package_mode:
        # If no mode metadata, treat a package that has a flight component as matching "flight"
        if mode == "flight" and flight:
            return 1.0
        return 0.5
    return 1.0 if mode in package_mode or package_mode in mode else 0.0


def _score_package(package: dict, preferences: dict) -> float:
    budget   = float(preferences.get("budget") or 0)
    w_pref   = str(preferences.get("weather_preference") or "")
    vtype    = str(preferences.get("vacation_type") or "")
    t_mode   = str(preferences.get("travel_mode") or "")
    price    = float(package.get("total_price") or 0)

    s_price  = _score_price_fit(price, budget)
    s_weather = _score_weather(package, w_pref)
    s_activity = _score_activity_relevance(package, vtype)
    s_conv   = _score_travel_convenience(package, t_mode)

    score = (
        W_PRICE       * s_price
        + W_WEATHER   * s_weather
        + W_ACTIVITY  * s_activity
        + W_CONVENIENCE * s_conv
    )
    logger.debug(
        f"pkg={package.get('package_id')} price={s_price:.2f} weather={s_weather:.2f} "
        f"activity={s_activity:.2f} convenience={s_conv:.2f} total={score:.4f}"
    )
    return round(score, 4)


@app.post("/score", response_model=ScoreResponse)
def score(payload: ScoreRequest):
    logger.info(f"Scoring {len(payload.packages)} packages for request_id={payload.request_id}")
    scored = []
    for pkg in payload.packages:
        pkg_copy = dict(pkg)
        pkg_copy["score"] = _score_package(pkg, payload.preferences)
        scored.append(pkg_copy)
    scored.sort(key=lambda p: p["score"], reverse=True)
    logger.info(
        f"Scoring complete for {payload.request_id}: "
        f"top score={scored[0]['score'] if scored else 'N/A'}"
    )
    return ScoreResponse(scored_packages=scored)


@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": "package-scoring-service"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
