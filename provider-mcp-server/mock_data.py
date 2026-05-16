import hashlib
from datetime import datetime, timedelta, timezone

PROVIDERS = [
    {
        "provider_id": "klm",
        "name": "KLM Royal Dutch Airlines",
        "provider_type": "flight",
        "supported_destinations": ["BCN", "ROM", "ATH", "INN", "Barcelona", "Rome", "Athens", "Innsbruck"],
        "reliability_score": 0.92,
        "margin_threshold": 0.15,
    },
    {
        "provider_id": "ryanair",
        "name": "Ryanair",
        "provider_type": "flight",
        "supported_destinations": ["BCN", "ROM", "ATH", "Barcelona", "Rome", "Athens"],
        "reliability_score": 0.65,
        "margin_threshold": 0.10,
    },
    {
        "provider_id": "marriott",
        "name": "Marriott",
        "provider_type": "hotel",
        "supported_destinations": ["Barcelona", "Rome", "Athens", "Innsbruck", "BCN", "ROM", "ATH", "INN"],
        "reliability_score": 0.88,
        "margin_threshold": 0.20,
    },
    {
        "provider_id": "booking_partner",
        "name": "Booking Partner",
        "provider_type": "hotel",
        "supported_destinations": ["Barcelona", "Rome", "Amsterdam", "BCN", "ROM", "AMS"],
        "reliability_score": 0.80,
        "margin_threshold": 0.18,
    },
    {
        "provider_id": "getyourguide",
        "name": "GetYourGuide",
        "provider_type": "activity",
        "supported_destinations": ["Barcelona", "Rome", "Athens", "Amsterdam", "Innsbruck",
                                   "BCN", "ROM", "ATH", "AMS", "INN"],
        "reliability_score": 0.85,
        "margin_threshold": 0.25,
    },
]

# IATA-to-city and city-to-IATA mappings for normalising destination inputs
IATA_TO_CITY = {
    "BCN": "Barcelona",
    "ROM": "Rome",
    "ATH": "Athens",
    "INN": "Innsbruck",
    "AMS": "Amsterdam",
}

CITY_TO_IATA = {v: k for k, v in IATA_TO_CITY.items()}


def matches_destination(provider: dict, destination: str) -> bool:
    """Return True if the provider supports the given destination (IATA or city name)."""
    dest_upper = destination.upper()
    dest_title = destination.title()
    supported = provider["supported_destinations"]
    return dest_upper in supported or dest_title in supported or destination in supported


def deterministic_price(provider_id: str, destination: str, start_date: str,
                         min_price: float, max_price: float) -> float:
    """
    Hash (provider_id, destination, start_date) to a float in [min_price, max_price].
    Same inputs always return the same price.
    """
    seed = f"{provider_id}|{destination}|{start_date}"
    digest = int(hashlib.md5(seed.encode()).hexdigest(), 16)
    ratio = (digest % 10000) / 10000.0
    return round(min_price + ratio * (max_price - min_price), 2)


def quote_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=24)
