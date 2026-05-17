import os
from datetime import date

from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="feasibility-check")


class DateWindow(BaseModel):
    start: date
    end: date


class OfferSummary(BaseModel):
    offer_id: str
    price: float
    availability_window: DateWindow


class Package(BaseModel):
    package_id: str
    flight: OfferSummary
    hotel: OfferSummary
    activities: list[OfferSummary]
    total_price: float


class CheckRequest(BaseModel):
    packages: list[Package]
    budget: float
    travel_dates: DateWindow


class PackageResult(BaseModel):
    package_id: str
    feasible: bool
    reasons: list[str]


class CheckResponse(BaseModel):
    results: list[PackageResult]


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.post("/check", response_model=CheckResponse)
def check(request: CheckRequest):
    results = []

    for pkg in request.packages:
        reasons = []

        # 1. Budget check
        if pkg.total_price > request.budget:
            reasons.append(
                f"Total price €{pkg.total_price:.2f} exceeds budget €{request.budget:.2f}"
            )

        # 2. Date alignment: flight window must overlap with hotel window
        flight_w = pkg.flight.availability_window
        hotel_w = pkg.hotel.availability_window
        if flight_w.start > hotel_w.end or hotel_w.start > flight_w.end:
            reasons.append("Flight dates do not align with hotel dates")

        # 3. Each activity must fall within travel_dates
        travel = request.travel_dates
        for activity in pkg.activities:
            aw = activity.availability_window
            if aw.start < travel.start or aw.end > travel.end:
                reasons.append(
                    f"Activity {activity.offer_id} dates are outside the travel date range"
                )

        results.append(PackageResult(
            package_id=pkg.package_id,
            feasible=len(reasons) == 0,
            reasons=reasons,
        ))

    return CheckResponse(results=results)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
