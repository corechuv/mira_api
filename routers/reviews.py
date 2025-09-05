# routers/reviews.py
import uuid, datetime as dt
from fastapi import APIRouter, Depends, HTTPException
from psycopg import AsyncConnection
from db import get_conn, dict_cursor
from models import ReviewOut, ReviewCreate

router = APIRouter(prefix="/reviews", tags=["reviews"])

@router.get("", response_model=list[ReviewOut])
async def list_reviews(product_id: str, conn: AsyncConnection = Depends(get_conn)):
    async with dict_cursor(conn) as cur:
        await cur.execute("""
          select id::text, product_id::text, author, rating, text, created_at::timestamptz::text, helpful
          from reviews
          where product_id = %s
          order by created_at desc
          limit 200
        """, (product_id,))
        rows = await cur.fetchall()
    return [ReviewOut.model_validate(r) for r in rows]

@router.post("", response_model=ReviewOut)
async def add_review(body: ReviewCreate, conn: AsyncConnection = Depends(get_conn)):
    rid = str(uuid.uuid4())
    now = dt.datetime.utcnow().isoformat()
    async with dict_cursor(conn) as cur:
        await cur.execute("""
          insert into reviews (id, product_id, author, rating, text, created_at, helpful)
          values (%s,%s,%s,%s,%s, now(), 0)
          returning id::text, product_id::text, author, rating, text, created_at::timestamptz::text, helpful
        """, (rid, body.product_id, body.author, body.rating, body.text))
        row = await cur.fetchone()
    return ReviewOut.model_validate(row)

@router.post("/{review_id}/vote")
async def vote_helpful(review_id: str, conn: AsyncConnection = Depends(get_conn)):
    async with dict_cursor(conn) as cur:
        await cur.execute("update reviews set helpful = helpful + 1 where id = %s", (review_id,))
        if cur.rowcount == 0:
            raise HTTPException(404, "Review not found")
    return {"ok": True}
