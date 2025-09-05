# routers/payments.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import os, stripe

router = APIRouter(prefix="/payments", tags=["payments"])

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")

class IntentIn(BaseModel):
    amount: int
    currency: str = "EUR"

@router.post("/intent")
def create_intent(data: IntentIn):
    if not stripe.api_key:
        raise HTTPException(500, "STRIPE_SECRET_KEY is not set")
    if data.amount < 50:
        raise HTTPException(400, "Minimum amount is 50 cents")
    pi = stripe.PaymentIntent.create(
        amount=data.amount,
        currency=data.currency.lower(),
        automatic_payment_methods={"enabled": True},
    )
    return {"client_secret": pi.client_secret}
