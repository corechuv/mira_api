# routers/locations.py
import os
from fastapi import APIRouter, HTTPException, Query
import httpx

router = APIRouter(prefix="/locations", tags=["locations"])

# PROD ключ из DHL Developer Portal (App -> Show key)
DHL_KEY = os.getenv("DHL_API_KEY", "").strip()

# Всегда прод-хост (без песочницы)
DHL_BASE_URL = os.getenv("DHL_BASE_URL", "https://api.dhl.com/location-finder/v1/locations").strip()

# Фронт шлёт: packstation | postfiliale | parcelshop
# DHL в проде принимает: packstation | postoffice | parcelshop
TYPE_MAP = {
    "packstation": "packstation",
    "postfiliale": "postoffice",
    "parcelshop": "parcelshop",
}

@router.get("")
async def list_locations(
    zip: str = Query(..., alias="zip"),
    city: str = Query("", description="Опционально, можно пусто"),
    type: str = Query("packstation", description="packstation | postfiliale | parcelshop"),
    radius: int = Query(5, ge=1, le=50),
    results: int = Query(10, ge=1, le=50),
):
    if not DHL_KEY:
        # 424, чтобы лог говорил прямо о конфиге
        raise HTTPException(424, detail="DHL lookup failed: DHL_API_KEY is not configured")

    dhl_type = TYPE_MAP.get(type.lower().strip(), type.lower().strip())

    # Собираем query; пустые значения не отправляем
    params = {
        "countryCode": "DE",
        "postalCode": zip,
        "types": dhl_type,
        "radius": radius,
        "limit": results,
    }
    if city and city.strip():
        params["city"] = city.strip()

    headers = {
        "Accept": "application/json",
        "DHL-API-Key": DHL_KEY,  # точное имя заголовка
        # (не обязательно, но можно) "Accept-Language": "de-DE",
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(DHL_BASE_URL, params=params, headers=headers)
    except httpx.RequestError as e:
        raise HTTPException(502, detail=f"DHL network error: {e!s}")

    # Подсветим типовую проблему — не тот ключ/не та подписка
    if resp.status_code == 401:
        raise HTTPException(
            424,
            detail=f"DHL unauthorized (401). "
                   f"Check that your APP has Unified Location Finder in PRODUCTION "
                   f"and you are using the PROD API key. Raw: {resp.text}",
        )

    if resp.status_code >= 400:
        raise HTTPException(502, detail=f"DHL lookup failed ({resp.status_code}): {resp.text}")

    data = resp.json()

    # Ответ у DHL: locations[], но на всякий случай поддержим items[]
    items_raw = data.get("locations") or data.get("items") or []

    items = []
    for loc in items_raw:
        # адрес
        addr = (loc.get("address") or {})
        # координаты встречаются как location.geo или coordinates
        geo = ((loc.get("location") or {}).get("geo")) or (loc.get("coordinates") or {})
        lat = geo.get("latitude")
        lng = geo.get("longitude")

        # тип: либо массив types[], либо поле type
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
            "lat": lat,
            "lng": lng,
        })

    return {"items": items}
