# app.py
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from db import pool
from routers import products, reviews, addresses, orders, auth, categories
from routers import payments
from routers import locations
from routers import geo

ALLOWED_ORIGINS = [
    "http://localhost:5173",
    os.getenv("FRONTEND_ORIGIN","").strip() or "https://mira-client.netlify.app/"
]

async def lifespan(app: FastAPI):
    await pool.open()
    yield
    await pool.close()

app = FastAPI(title="Mira API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "https://mira-client.netlify.app/", "https://shop.center-mira.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"api":"ok","db":True}

# роутеры
app.include_router(products)
app.include_router(reviews)
app.include_router(addresses)
app.include_router(orders)
app.include_router(auth)
app.include_router(categories)

app.include_router(payments.router)
app.include_router(locations.router)
app.include_router(geo.router)

# добавить Bearer-схему в OpenAPI (для удобства тестирования)
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
    )
    openapi_schema.setdefault("components", {}).setdefault("securitySchemes", {})["HTTPBearer"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
    }
    # по умолчанию не требуем авторизацию на всех роутах
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi
