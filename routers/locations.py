# routers/locations.py
import os
from fastapi import APIRouter, HTTPException, Query
import httpx

router = APIRouter(prefix="/locations", tags=["locations"])

DHL_KEY = os.getenv("DHL_API_KEY")
TIMEOUT = 12.0

def _hdrs():
    if not DHL_KEY:
        raise HTTPException(500, "DHL_API_KEY is not configured")
    return {"DHL-API-Key": DHL_KEY}

# Нормализация под единый фронтовый формат
def _normalize(payload: dict):
    data = payload.get("locations") or payload.get("data") or payload.get("items") or payload
    if not isinstance(data, list):
        data = data.get("results") or []
    out = []
    for loc in data:
        addr = loc.get("address") or {}
        coords = loc.get("location") or loc.get("coordinates") or {}
        out.append({
            "id": str(loc.get("id") or loc.get("locationId") or loc.get("number") or ""),
            "name": loc.get("name") or loc.get("title") or (f"Packstation {loc.get('number')}" if loc.get("number") else "Location"),
            "type": (loc.get("type") or loc.get("locationType") or "").lower(),
            "street": addr.get("streetAddress") or addr.get("street") or "",
            "houseNo": addr.get("houseNumber") or addr.get("houseNo") or "",
            "zip": addr.get("postalCode") or addr.get("zip") or "",
            "city": addr.get("addressLocality") or addr.get("city") or "",
            "lat": coords.get("latitude") or coords.get("lat"),
            "lng": coords.get("longitude") or coords.get("lng"),
            "distance": loc.get("distance"),
            "packstationNumber": loc.get("number") or loc.get("packstationNumber"),
            "openingHours": loc.get("openingHours") or loc.get("openingHoursText") or [],
        })
    return {"items": out}

@router.get("")
async def search_locations(
    zip: str = Query(..., min_length=3),
    city: str | None = None,
    radius: int = 5,
    type: str = "packstation",   # packstation | postfiliale | parcelshop
    results: int = 10,
):
    # Попробуем два распространённых варианта ендпоинтов DHL.
    urls = [
        "https://api.dhl.com/location-finder/v1/locations",
        "https://api.dhl.com/locations/v1/find-by-address",
    ]
    params = {
        "countryCode": "DE",
        "postalCode": zip,
        "addressLocality": city,
        "radius": radius,
        "results": results,
        "locationType": type,
        "type": type,  # на всякий случай для второго варианта
    }
    last = None
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for url in urls:
            try:
                r = await client.get(url, params=params, headers=_hdrs())
                if r.status_code >= 400:
                    last = r.text
                    continue
                return _normalize(r.json())
            except Exception as e:
                last = str(e)
    raise HTTPException(502, f"DHL lookup failed: {last or 'unknown error'}")
