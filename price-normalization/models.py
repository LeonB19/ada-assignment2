from pydantic import BaseModel
from typing import Literal, Optional
from datetime import date, datetime


class AvailabilityWindow(BaseModel):
    start: date
    end: date


class NormalizedOffer(BaseModel):
    offer_id: str
    provider_id: str
    offer_type: Literal["flight", "hotel", "activity"]
    price: float
    currency: str = "EUR"
    tax_included: bool = True
    availability_window: AvailabilityWindow
    quote_expiry: datetime
    metadata: dict
