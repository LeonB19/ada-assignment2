import os
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, ValidationError
import uvicorn

from models import NormalizedOffer

app = FastAPI(title="price-normalization")


class NormalizeRequest(BaseModel):
    offers: list[dict[str, Any]]


class InvalidOffer(BaseModel):
    offer_id: str
    errors: list[str]


class NormalizeResponse(BaseModel):
    valid_offers: list[dict[str, Any]]
    invalid_offers: list[InvalidOffer]
    total_received: int
    total_valid: int
    total_invalid: int


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.post("/normalize", response_model=NormalizeResponse)
def normalize(request: NormalizeRequest):
    valid_offers = []
    invalid_offers = []

    for raw in request.offers:
        offer_id = raw.get("offer_id", "<unknown>")
        errors = []

        # Validate shape against NormalizedOffer
        try:
            offer = NormalizedOffer.model_validate(raw)
        except ValidationError as e:
            for err in e.errors():
                field = ".".join(str(loc) for loc in err["loc"])
                errors.append(f"{field}: {err['msg']}")
            invalid_offers.append(InvalidOffer(offer_id=offer_id, errors=errors))
            continue

        # price must be positive
        if offer.price <= 0:
            errors.append("price must be positive")

        # quote_expiry must not be in the past
        expiry = offer.quote_expiry
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if expiry < datetime.now(timezone.utc):
            errors.append("quote_expiry is in the past")

        if errors:
            invalid_offers.append(InvalidOffer(offer_id=offer.offer_id, errors=errors))
        else:
            valid_offers.append(offer.model_dump(mode="json"))

    return NormalizeResponse(
        valid_offers=valid_offers,
        invalid_offers=invalid_offers,
        total_received=len(request.offers),
        total_valid=len(valid_offers),
        total_invalid=len(invalid_offers),
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
