import os
import hashlib
from datetime import date, datetime, timedelta, timezone

from mcp.server.fastmcp import FastMCP
from models import AvailabilityWindow, NormalizedOffer
from mock_data import (
    PROVIDERS, IATA_TO_CITY, matches_destination,
    deterministic_price, quote_expiry,
)

port = int(os.environ.get("PORT", 8080))
mcp = FastMCP("provider-mcp-server", host="0.0.0.0", port=port)


def _seeded_int(provider_id: str, destination: str, start_date: str, salt: str = "") -> int:
    """Deterministic integer from inputs — used for flight numbers etc."""
    seed = f"{provider_id}|{destination}|{start_date}|{salt}"
    return int(hashlib.md5(seed.encode()).hexdigest(), 16) % 9000 + 1000


@mcp.tool()
def get_flight_offers(
    destination: str,
    start_date: str,
    end_date: str,
    travel_mode: str = "flight",
) -> list[dict]:
    """Return mock flight offers for a destination and date range.

    Args:
        destination: IATA code or city name (e.g. "BCN", "Barcelona")
        start_date: Departure date in YYYY-MM-DD
        end_date: Return date in YYYY-MM-DD
        travel_mode: One of "flight", "train" (default: "flight")

    Returns:
        List of NormalizedOffer dicts for available flights.
    """
    flight_providers = [
        p for p in PROVIDERS
        if p["provider_type"] == "flight" and matches_destination(p, destination)
    ]

    # Normalise destination to IATA for offer_id
    dest_upper = destination.upper()
    iata = dest_upper if len(dest_upper) == 3 else next(
        (k for k, v in IATA_TO_CITY.items() if v.lower() == destination.lower()), dest_upper[:3]
    )

    prefix_map = {"klm": "KL", "ryanair": "FR"}

    offers = []
    for p in flight_providers:
        price = deterministic_price(p["provider_id"], destination, start_date, 120.0, 450.0)
        flight_num = f"{prefix_map.get(p['provider_id'], p['provider_id'][:2].upper())}{_seeded_int(p['provider_id'], destination, start_date)}"
        offer = NormalizedOffer(
            offer_id=f"flt_{p['provider_id']}_{iata}_{start_date}",
            provider_id=p["provider_id"],
            offer_type="flight",
            price=price,
            currency="EUR",
            tax_included=True,
            availability_window=AvailabilityWindow(
                start=date.fromisoformat(start_date),
                end=date.fromisoformat(end_date),
            ),
            quote_expiry=quote_expiry(),
            metadata={
                "flight_number": flight_num,
                "origin": "AMS",
                "destination": iata,
                "departure_time": f"{start_date}T09:00:00",
                "arrival_time": f"{start_date}T12:30:00",
                "travel_class": "economy",
            },
        )
        offers.append(offer.model_dump(mode="json"))

    return offers


@mcp.tool()
def get_hotel_offers(
    destination: str,
    start_date: str,
    end_date: str,
) -> list[dict]:
    """Return mock hotel offers for a destination and date range.

    Args:
        destination: City name (e.g. "Barcelona", "Rome")
        start_date: Check-in date in YYYY-MM-DD
        end_date: Check-out date in YYYY-MM-DD

    Returns:
        List of NormalizedOffer dicts for available hotels.
    """
    hotel_providers = [
        p for p in PROVIDERS
        if p["provider_type"] == "hotel" and matches_destination(p, destination)
    ]

    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    nights = max((end - start).days, 1)

    hotel_names = {
        "marriott": {
            "Barcelona": "Marriott Barcelona",
            "Rome": "Marriott Rome",
            "Athens": "Marriott Athens",
            "Innsbruck": "Marriott Innsbruck",
        },
        "booking_partner": {
            "Barcelona": "Hotel Arts Barcelona",
            "Rome": "Hotel de Russie Rome",
            "Amsterdam": "Hotel V Amsterdam",
        },
    }

    dest_title = destination.title()
    room_types = ["double", "twin", "suite"]

    offers = []
    for p in hotel_providers:
        price_per_night = deterministic_price(p["provider_id"], destination, start_date, 80.0, 350.0)
        total_price = round(price_per_night * nights, 2)
        room_seed = _seeded_int(p["provider_id"], destination, start_date) % 3
        name = hotel_names.get(p["provider_id"], {}).get(dest_title, f"{p['name']} {dest_title}")
        rating = round(3.5 + (_seeded_int(p["provider_id"], destination, start_date, "rating") % 15) / 10, 1)

        offer = NormalizedOffer(
            offer_id=f"htl_{p['provider_id']}_{dest_title.replace(' ', '')}_{start_date}",
            provider_id=p["provider_id"],
            offer_type="hotel",
            price=total_price,
            currency="EUR",
            tax_included=True,
            availability_window=AvailabilityWindow(
                start=start,
                end=end,
            ),
            quote_expiry=quote_expiry(),
            metadata={
                "hotel_name": name,
                "room_type": room_types[room_seed],
                "nights": nights,
                "rating": rating,
            },
        )
        offers.append(offer.model_dump(mode="json"))

    return offers


@mcp.tool()
def get_activity_offers(
    destination: str,
    start_date: str,
    end_date: str,
) -> list[dict]:
    """Return mock activity offers for a destination and date range.

    Args:
        destination: City name (e.g. "Barcelona", "Rome")
        start_date: Start date in YYYY-MM-DD
        end_date: End date in YYYY-MM-DD

    Returns:
        List of NormalizedOffer dicts for available activities.
    """
    activity_providers = [
        p for p in PROVIDERS
        if p["provider_type"] == "activity" and matches_destination(p, destination)
    ]

    activities_by_city = {
        "Barcelona": [
            {"name": "Sagrada Familia Tour", "duration_hours": 2, "category": "cultural"},
            {"name": "Barceloneta Beach Day", "duration_hours": 6, "category": "leisure"},
            {"name": "Park Guell Guided Tour", "duration_hours": 3, "category": "cultural"},
            {"name": "Flamenco Show Evening", "duration_hours": 2, "category": "entertainment"},
        ],
        "Rome": [
            {"name": "Colosseum Skip-the-Line Tour", "duration_hours": 3, "category": "cultural"},
            {"name": "Vatican Museums Tour", "duration_hours": 4, "category": "cultural"},
            {"name": "Roman Food Walking Tour", "duration_hours": 3, "category": "food"},
        ],
        "Athens": [
            {"name": "Acropolis Guided Tour", "duration_hours": 3, "category": "cultural"},
            {"name": "Athens Food & Wine Tour", "duration_hours": 3, "category": "food"},
            {"name": "Cape Sounion Day Trip", "duration_hours": 8, "category": "excursion"},
        ],
        "Amsterdam": [
            {"name": "Canal Boat Tour", "duration_hours": 2, "category": "leisure"},
            {"name": "Rijksmuseum Visit", "duration_hours": 3, "category": "cultural"},
            {"name": "Keukenhof Gardens Day Trip", "duration_hours": 6, "category": "leisure"},
        ],
        "Innsbruck": [
            {"name": "Alpine Hiking Day Tour", "duration_hours": 8, "category": "outdoor"},
            {"name": "Nordkette Cable Car Experience", "duration_hours": 4, "category": "outdoor"},
            {"name": "Ski Day Pass — Stubaier Gletscher", "duration_hours": 8, "category": "ski"},
        ],
    }

    dest_title = destination.title()
    city_activities = activities_by_city.get(
        dest_title,
        [{"name": f"{dest_title} City Tour", "duration_hours": 3, "category": "cultural"}]
    )

    # Pick 2-4 activities deterministically
    seed_idx = _seeded_int("getyourguide", destination, start_date) % len(city_activities)
    count = 2 + (seed_idx % min(3, len(city_activities)))
    selected = city_activities[:count]

    offers = []
    for i, activity in enumerate(selected):
        price = deterministic_price("getyourguide", destination, f"{start_date}_{i}", 25.0, 120.0)
        offer = NormalizedOffer(
            offer_id=f"act_getyourguide_{dest_title.replace(' ', '')}_{start_date}_{i}",
            provider_id="getyourguide",
            offer_type="activity",
            price=price,
            currency="EUR",
            tax_included=True,
            availability_window=AvailabilityWindow(
                start=date.fromisoformat(start_date),
                end=date.fromisoformat(end_date),
            ),
            quote_expiry=quote_expiry(),
            metadata={
                "activity_name": activity["name"],
                "duration_hours": activity["duration_hours"],
                "category": activity["category"],
            },
        )
        offers.append(offer.model_dump(mode="json"))

    return offers


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
