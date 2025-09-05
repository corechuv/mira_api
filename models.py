# models.py
from typing import Optional, List, Literal
from pydantic import BaseModel, Field, EmailStr, conint, confloat

# ===== PRODUCTS =====
class ProductOut(BaseModel):
    id: str
    slug: str
    title: str
    category: str
    sub: Optional[str] = None
    leaf: Optional[str] = None
    price: confloat(ge=0)  # float нормально для ответа
    rating: confloat(ge=0, le=5) | None = None
    short: Optional[str] = None
    description: Optional[str] = None
    # в БД/SQL колонка алиасится как "imageUrl", а наружу поле отдаём как image_url
    image_url: Optional[str] = Field(None, alias="imageUrl")

class ProductsQuery(BaseModel):
    search: Optional[str] = None
    category: Optional[str] = None
    sub: Optional[str] = None
    leaf: Optional[str] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    rating_min: Optional[float] = None
    sort: Literal["popular","price-asc","price-desc"] = "popular"
    limit: conint(ge=1, le=100) = 24
    offset: conint(ge=0) = 0

class PageOut(BaseModel):
    total: int
    limit: int
    offset: int

class ProductsPage(BaseModel):
    items: List[ProductOut]
    page: PageOut

# ===== REVIEWS =====
class ReviewOut(BaseModel):
    id: str
    product_id: str
    author: str
    rating: conint(ge=1, le=5)
    text: str
    created_at: str
    helpful: int

class ReviewCreate(BaseModel):
    product_id: str
    author: str
    rating: conint(ge=1, le=5)
    text: str

# ===== ADDRESSES =====
class Address(BaseModel):
    id: str
    user_email: EmailStr
    first_name: str
    last_name: str
    street: str | None = None
    house: str | None = None
    zip: str
    city: str
    phone: str | None = None
    note: str | None = None
    pack_type: Literal["packstation","postfiliale"] | None = None
    post_nummer: str | None = None
    station_nr: str | None = None
    is_default: bool = False

class AddressCreate(BaseModel):
    # будет игнорироваться на бэке и заменяться email текущего пользователя
    user_email: EmailStr | None = None
    first_name: str
    last_name: str
    street: str | None = None
    house: str | None = None
    zip: str
    city: str
    phone: str | None = None
    note: str | None = None
    pack_type: Literal["packstation","postfiliale"] | None = None
    post_nummer: str | None = None
    station_nr: str | None = None
    is_default: bool = False

class AddressUpdate(AddressCreate):
    pass

# ===== ORDERS =====
class CartItemIn(BaseModel):
    id: str               # product_id
    qty: conint(ge=1)
    title: str
    price: float
    slug: str
    imageUrl: str | None = None

class Totals(BaseModel):
    subtotal: float
    shipping: float
    grand: float
    vatIncluded: float

class Customer(BaseModel):
    firstName: str
    lastName: str
    email: EmailStr
    phone: str | None = None

class Shipping(BaseModel):
    method: Literal["dhl","express","packstation","pickup"]
    packType: Literal["packstation","postfiliale"] | None = None
    address: dict

class OrderCreateIn(BaseModel):
    id: Optional[str] = None
    createdAt: Optional[str] = None
    items: List[CartItemIn]
    totals: Totals
    customer: Customer
    shipping: Shipping
    vatRate: float = 0.19
    currency: Literal["EUR"] = "EUR"
    payment_status: Literal["paid","pending"] = "pending"
    last4: str | None = None

class OrderOut(BaseModel):
    id: str
    created_at: str
    items: List[CartItemIn]
    totals: Totals
    customer: Customer
    shipping: Shipping
    payment: dict | None = None
    status: Literal["processing","packed","shipped","delivered","cancelled","refund_requested","refunded"]
    refund: dict | None = None

# ===== AUTH =====
class UserUpsertIn(BaseModel):
    email: EmailStr
    name: str

class UserPublic(BaseModel):
    id: str
    email: EmailStr
    name: str

class UserUpdateIn(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    current_password: str | None = None   # для смены пароля
    new_password: str | None = None

class RegisterIn(BaseModel):
    email: EmailStr
    name: str
    password: str

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"

class MeOut(BaseModel):
    user: UserPublic
