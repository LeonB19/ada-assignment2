import os
import logging
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any
from google.cloud import firestore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GOOGLE_CLOUD_PROJECT = os.environ.get("PROJECT_ID", "ada2026-assignment2")
MIN_RELIABILITY_SCORE = 0.7
MIN_MARGIN_FACTOR     = 1.15   # 15% agency margin
DEFAULT_COST_FLOOR    = 800.0

app = FastAPI(title="Business Rules Service", version="1.0.0")

_db = None


def get_db() -> firestore.Client:
    global _db
    if _db is None:
        _db = firestore.Client(project=GOOGLE_CLOUD_PROJECT)
    return _db


def _get_provider_metadata(provider_id: str) -> dict:
    """Fetch provider metadata from Firestore, returning {} on miss."""
    if not provider_id:
        return {}
    try:
        doc = get_db().collection("provider_metadata").document(provider_id).get()
        return doc.to_dict() if doc.exists else {}
    except Exception as e:
        logger.warning(f"Could not fetch provider_metadata for {provider_id}: {e}")
        return {}


def _get_budget(request_id: str) -> float | None:
    """Read client budget from vacation_requests Firestore collection."""
    try:
        doc = get_db().collection("vacation_requests").document(request_id).get()
        if doc.exists:
            return float(doc.to_dict().get("budget") or 0) or None
    except Exception as e:
        logger.warning(f"Could not read budget for {request_id}: {e}")
    return None


def _provider_ids(package: dict) -> list[str]:
    """Collect all provider IDs referenced in a package."""
    ids = []
    for component_key in ("flight", "hotel"):
        comp = package.get(component_key) or {}
        pid = comp.get("provider_id") or comp.get("provider")
        if pid:
            ids.append(str(pid))
    for act in (package.get("activities") or []):
        pid = act.get("provider_id") or act.get("provider")
        if pid:
            ids.append(str(pid))
    return ids


class RulesRequest(BaseModel):
    request_id: str
    packages: list[dict[str, Any]]


class RulesResponse(BaseModel):
    filtered_packages: list[dict[str, Any]]
    rules_applied: list[str]


@app.post("/rules/apply", response_model=RulesResponse)
def apply_rules(payload: RulesRequest):
    logger.info(
        f"Applying business rules to {len(payload.packages)} packages "
        f"for request_id={payload.request_id}"
    )

    packages = list(payload.packages)
    rules_applied: list[str] = []

    # ── Rule 1: Provider reliability ─────────────────────────────────────────
    reliable: list[dict] = []
    for pkg in packages:
        provider_ids = _provider_ids(pkg)
        passes = True
        for pid in provider_ids:
            meta = _get_provider_metadata(pid)
            reliability = meta.get("reliability_score")
            if reliability is not None and float(reliability) < MIN_RELIABILITY_SCORE:
                logger.info(
                    f"Excluding {pkg.get('package_id')} — provider {pid} "
                    f"reliability={reliability} < {MIN_RELIABILITY_SCORE}"
                )
                passes = False
                break
        if passes:
            reliable.append(pkg)

    rules_applied.append("reliability_filter")
    logger.info(f"After reliability filter: {len(reliable)}/{len(packages)} packages remain")
    packages = reliable

    # ── Rule 2: Agency margin enforcement ────────────────────────────────────
    margin_ok: list[dict] = []
    for pkg in packages:
        total_price = float(pkg.get("total_price") or 0)
        # Try to get cost_floor from the first provider's metadata; fall back to default
        cost_floor = DEFAULT_COST_FLOOR
        for pid in _provider_ids(pkg):
            meta = _get_provider_metadata(pid)
            if "cost_floor" in meta:
                cost_floor = float(meta["cost_floor"])
                break
        min_price = cost_floor * MIN_MARGIN_FACTOR
        if total_price >= min_price:
            margin_ok.append(pkg)
        else:
            logger.info(
                f"Excluding {pkg.get('package_id')} — total_price={total_price:.2f} "
                f"< cost_floor*1.15={min_price:.2f}"
            )

    rules_applied.append("margin_enforcement")
    logger.info(f"After margin filter: {len(margin_ok)}/{len(packages)} packages remain")
    packages = margin_ok

    # ── Rule 3: Client budget cap ─────────────────────────────────────────────
    budget = _get_budget(payload.request_id)
    within_budget: list[dict] = []
    if budget and budget > 0:
        for pkg in packages:
            total_price = float(pkg.get("total_price") or 0)
            if total_price <= budget:
                within_budget.append(pkg)
            else:
                logger.info(
                    f"Excluding {pkg.get('package_id')} — "
                    f"total_price={total_price:.2f} > budget={budget:.2f}"
                )
        packages = within_budget
    else:
        logger.info("Budget not available — skipping budget cap rule")

    rules_applied.append("budget_filter")
    logger.info(
        f"Rules complete for {payload.request_id}: "
        f"{len(packages)} packages pass all rules"
    )

    return RulesResponse(filtered_packages=packages, rules_applied=rules_applied)


@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": "business-rules-service"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
