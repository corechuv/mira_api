# routers/locations.py
import os
from fastapi import APIRouter, HTTPException, Query
import httpx

router = APIRouter(prefix="/locations", tags=["locations"])

DHL_KEY = (os.getenv("DHL_API_KEY") or "").strip()
DHL_BASE_URL = (os.getenv("DHL_BASE_URL") or "https://api.dhl.com/location-finder/v1/locations").strip()

# фронт шлёт "postfiliale", у DHL это "postoffice"
TYPE_MAP = {
    "packstation": "packstation",
    "postfiliale": "postoffice",
    "parcelshop": "parcelshop",
}

@router.get("")
async def list_locations(
    zip: str = Query(..., alias="zip"),
    city: str = Query("", description="можно пусто"),
    type: str = Query("packstation"),
    radius: int = Query(5, ge=1, le=50),
    results: int = Query(10, ge=1, le=50),
):
    if not DHL_KEY:
        raise HTTPException(424, detail="DHL lookup failed: DHL_API_KEY is not configured")

    params = {
        "countryCode": "DE",
        "postalCode": zip,
        "types": TYPE_MAP.get(type.lower().strip(), type.lower().strip()),
        "radius": radius,
        "limit": results,
    }
    if city.strip():
        params["city"] = city.strip()

    headers = {
        "Accept": "application/json",
        "DHL-API-Key": DHL_KEY,  # именно это имя
        # "Accept-Language": "de-DE",  # не обязательно
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(DHL_BASE_URL, params=params, headers=headers)
    except httpx.RequestError as e:
        raise HTTPException(502, detail=f"DHL network error: {e!s}")

    corr_id = resp.headers.get("Correlation-Id") or resp.headers.get("CorrelationId") or ""

    if resp.status_code == 401:
        # даём максимально полезную подсказку и correlation id
        raise HTTPException(
            424,
            detail=(
                "DHL unauthorized (401). Verify your app is SUBSCRIBED to "
                "Unified Location Finder **PRODUCTION**, and that you're using the **PROD API Key**. "
                f"Correlation-Id: {corr_id or 'n/a'}. Raw: {resp.text}"
            ),
        )

    if resp.status_code >= 400:
        raise HTTPException(502, detail=f"DHL lookup failed ({resp.status_code}) [CorrId: {corr_id or 'n/a'}]: {resp.text}")

    data = resp.json()
    items_raw = data.get("locations") or data.get("items") or []

    items = []
    for loc in items_raw:
        addr = (loc.get("address") or {})
        geo = ((loc.get("location") or {}).get("geo")) or (loc.get("coordinates") or {})
        types_list = loc.get("types") or []
        loc_type = (types_list[0] if types_list else loc.get("type"))

        items.append({
            "id": loc.get("locationId") or loc.get("id"),
            "name": loc.get("name") or loc_type,
            "type": loc_type,
            "street": addr.get("streetAddress") or addr.get("street") or "",
            "house": addr.get("streetNumber") or "",
            "zip": addr.get("postalCode") or "",
            "city": addr.get("city") or "",
            "openingHours": loc.get("openingHours") or loc.get("openingTimes") or [],
            "lat": geo.get("latitude"),
            "lng": geo.get("longitude"),
        })

    return {"items": items}
