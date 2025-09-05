# routers/geo.py
import os
from typing import Optional
from fastapi import APIRouter, Request, HTTPException
import httpx

router = APIRouter(prefix="/geo", tags=["geo"])

# Можно выбрать провайдер через переменные окружения:
# GEO_PROVIDER = ipwhois | ipinfo  (default: ipwhois)
# IPINFO_TOKEN = <token>            (если выбран ipinfo)
GEO_PROVIDER = (os.getenv("GEO_PROVIDER") or "ipwhois").strip().lower()
IPINFO_TOKEN = (os.getenv("IPINFO_TOKEN") or "").strip()

_HEADER_COUNTRY_KEYS = [
    "cf-ipcountry",                 # Cloudflare
    "cloudfront-viewer-country",    # AWS CloudFront
    "fly-client-country",           # Fly.io
    "x-appengine-country",          # Google App Engine
    "x-geo-country",                # generic
    "x-country-code",               # generic
]

def _pick_header_country(req: Request) -> Optional[str]:
    for k in _HEADER_COUNTRY_KEYS:
        v = req.headers.get(k)
        if v and len(v.strip()) == 2:
            return v.strip().upper()
    return None

def _client_ip(req: Request) -> Optional[str]:
    # X-Forwarded-For: client, proxy1, proxy2
    xff = req.headers.get("x-forwarded-for")
    if xff:
        ip = xff.split(",")[0].strip()
        if ip:
            return ip
    xri = req.headers.get("x-real-ip")
    if xri:
        return xri.strip()
    return (req.client.host if req.client else None)

async def _lookup_country_by_ip(ip: str) -> Optional[str]:
    try:
        timeout = httpx.Timeout(5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            if GEO_PROVIDER == "ipinfo":
                if not IPINFO_TOKEN:
                    return None
                r = await client.get(f"https://ipinfo.io/{ip}", params={"token": IPINFO_TOKEN})
                if r.status_code != 200:
                    return None
                cc = (r.json() or {}).get("country")
                return (cc or "").strip().upper() or None
            # default: ipwho.is
            r = await client.get(f"https://ipwho.is/{ip}", params={"fields": "success,country_code"})
            if r.status_code != 200:
                return None
            data = r.json() or {}
            if data.get("success") is False:
                return None
            cc = data.get("country_code")
            return (cc or "").strip().upper() or None
    except Exception:
        return None

@router.get("/country")
async def country(request: Request):
    """
    Вернёт ISO-код страны клиента (например, {'country':'UA'}).
    Логика:
      1) Пытаемся взять из заголовков CDN/прокси.
      2) Иначе — берём IP клиента и спрашиваем внешний сервис.
    """
    # 1) заголовки CDN
    cc = _pick_header_country(request)
    if cc:
        return {"country": cc, "source": "header"}

    # 2) внешний сервис по IP
    ip = _client_ip(request)
    if not ip:
        # не удалось определить
        return {"country": None, "source": "unknown"}

    cc = await _lookup_country_by_ip(ip)
    if cc:
        return {"country": cc, "source": "service", "ip": ip}

    # совсем не удалось
    return {"country": None, "source": "unknown", "ip": ip}
