# routers/locations.py
import os
from fastapi import APIRouter, HTTPException, Query
import httpx

router = APIRouter(prefix="/locations", tags=["locations"])

DHL_KEY = os.getenv("DHL_API_KEY", "")
DHL_ENV = (os.getenv("DHL_API_ENV") or "prod").lower().strip()  # "prod" | "sandbox"

BASE_URL = (
    "https://api.dhl.com/location-finder/v1/locations"
    if DHL_ENV == "prod"
    else "https://api-sandbox.dhl.com/location-finder/v1/locations"
)

@router.get("")
async def list_locations(
    zip: str = Query(..., alias="zip"),
    city: str = Query(...),
    type: str = Query("packstation"),  # UI шлёт "type"
    radius: int = Query(5, ge=1, le=50),
    results: int = Query(10, ge=1, le=50),
):
    if not DHL_KEY:
        raise HTTPException(424, detail="DHL lookup failed: DHL_API_KEY is not configured")

    # DHL ожидает параметр types, добавим countryCode=DE и limit
    params = {
        "countryCode": "DE",
        "postalCode": zip,
        "city": city,
        "types": type,   # packstation | postfiliale | parcelshop
        "radius": radius,
        "limit": results,
    }
    headers = {
        "Accept": "application/json",
        "DHL-API-Key": DHL_KEY,   # ВАЖНО: именно так называется
    }

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(BASE_URL, params=params, headers=headers)

    # Нормализуем ошибки, чтобы в логах было понятно
    if resp.status_code == 401:
        raise HTTPException(424, detail=f"DHL unauthorized: {resp.text}")
    if resp.status_code >= 400:
        raise HTTPException(502, detail=f"DHL lookup failed: {resp.text}")

    data = resp.json()

    # Нормализуем ответ под фронт (items со сведениями)
    items_raw = data.get("locations") or data.get("items") or []
    items = []
    for loc in items_raw:
        addr = loc.get("address", {})
        coords = (loc.get("location", {}) or {}).get("geo", {})
        items.append({
            "id": loc.get("locationId") or loc.get("id"),
            "name": loc.get("name") or loc.get("type"),
            "type": (loc.get("types") or [loc.get("type")])[0] if loc.get("types") or loc.get("type") else None,
            "street": addr.get("streetAddress") or addr.get("street") or "",
            "house": addr.get("streetNumber") or "",
            "zip": addr.get("postalCode") or "",
            "city": addr.get("city") or "",
            "openingHours": loc.get("openingHours") or loc.get("openingTimes") or [],
            "lat": coords.get("latitude"),
            "lng": coords.get("longitude"),
        })

    return {"items": items}
