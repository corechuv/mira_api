# routers/orders.py
import uuid, json
from fastapi import APIRouter, Depends, HTTPException
from psycopg import AsyncConnection
from db import get_conn, dict_cursor
from models import OrderCreateIn, OrderOut, CartItemIn, Totals, Customer, Shipping
from uuid import UUID
from security import get_optional_user, get_current_user
from models import UserPublic

router = APIRouter(prefix="/orders", tags=["orders"])

def _serialize_items(items: list[CartItemIn]) -> list[dict]:
    return [i.model_dump() for i in items]

@router.post("", response_model=OrderOut)
async def create_order(
    body: OrderCreateIn,
    current: UserPublic | None = Depends(get_optional_user),
    conn: AsyncConnection = Depends(get_conn)
):
    order_id = str(uuid.uuid4())
    payment = {
        "status": body.payment_status,
        "method": "card",
        "last4": body.last4 or "",
    }
    # если пользователь авторизован — проставим user_id/email в слоты "старой" схемы
    user_id = None
    async with dict_cursor(conn) as cur:
        if current:
            await cur.execute("select id::text from users where lower(email)=lower(%s)", (current.email,))
            urow = await cur.fetchone()
            user_id = urow["id"] if urow else None

    async with conn.transaction():
        async with dict_cursor(conn) as cur:
            await cur.execute(
                """
                insert into orders
                (id, created_at, currency, vat_rate, totals, customer, shipping, payment, status, user_id, email)
                values (%s, now(), %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, 'processing', %s::uuid, %s)
                """,
                (
                    order_id,
                    body.currency,
                    body.vatRate,
                    json.dumps(body.totals.model_dump()),
                    json.dumps(body.customer.model_dump()),
                    json.dumps(body.shipping.model_dump()),
                    json.dumps(payment),
                    user_id,
                    body.customer.email,
                ),
            )

            for it in body.items:
                await cur.execute(
                    """
                    insert into order_items (id, order_id, product_id, title, slug, price, qty, image_url)
                    values (%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (str(uuid.uuid4()), order_id, it.id, it.title, it.slug, it.price, it.qty, it.imageUrl),
                )

            await cur.execute(
                """
                select id::text, created_at::timestamptz::text,
                       totals, customer, shipping, payment, status, refund
                from orders where id=%s::uuid
                """,
                (order_id,),
            )
            row = await cur.fetchone()

            await cur.execute(
                """
                select product_id::text as id, title, slug, price::float, qty, image_url as "imageUrl"
                from order_items where order_id=%s::uuid
                """,
                (order_id,),
            )
            items = await cur.fetchall()

    return OrderOut(
        id=row["id"],
        created_at=row["created_at"],
        items=[CartItemIn.model_validate(i) for i in items],
        totals=Totals.model_validate(row["totals"]),
        customer=Customer.model_validate(row["customer"]),
        shipping=Shipping.model_validate(row["shipping"]),
        payment=row["payment"],
        status=row["status"],
        refund=row.get("refund"),
    )

@router.get("", response_model=list[OrderOut])
async def list_orders(
    email: str | None = None,
    current: UserPublic | None = Depends(get_optional_user),
    conn: AsyncConnection = Depends(get_conn),
):
    effective_email = (current.email if current else None) or email
    if not effective_email:
        raise HTTPException(401, "Email is required (or send Authorization bearer token)")

    async with dict_cursor(conn) as cur:
        await cur.execute(
            """
            select id::text, created_at::timestamptz::text,
                   totals, customer, shipping, payment, status, refund
            from orders
            where lower((customer->>'email')) = lower(%s)
               or lower(email) = lower(%s)
            order by created_at desc
            """,
            (effective_email, effective_email),
        )
        orders = await cur.fetchall()

        res: list[OrderOut] = []
        for o in orders:
            await cur.execute(
                """
                select product_id::text as id, title, slug, price::float, qty, image_url as "imageUrl"
                from order_items where order_id=%s::uuid
                """,
                (o["id"],),
            )
            items = await cur.fetchall()
            res.append(
                OrderOut(
                    id=o["id"],
                    created_at=o["created_at"],
                    items=[CartItemIn.model_validate(i) for i in items],
                    totals=Totals.model_validate(o["totals"]),
                    customer=Customer.model_validate(o["customer"]),
                    shipping=Shipping.model_validate(o["shipping"]),
                    payment=o["payment"],
                    status=o["status"],
                    refund=o.get("refund"),
                )
            )
    return res

@router.post("/{order_id}/cancel")
async def cancel_order(order_id: str, conn: AsyncConnection = Depends(get_conn)):
    async with dict_cursor(conn) as cur:
        await cur.execute(
            "select status, (payment->>'status') as pay from orders where id=%s::uuid",
            (order_id,),
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(404, "Order not found")
        if row["status"] in ("shipped","delivered","refund_requested","refunded","cancelled"):
            raise HTTPException(400, "Order cannot be cancelled")  # или "Order is final"
        if row["pay"] == "paid":
            raise HTTPException(400, "Cannot cancel a paid order")
        await cur.execute("update orders set status='cancelled' where id=%s::uuid", (order_id,))
    return {"ok": True}

@router.post("/{order_id}/request-return")
async def request_return(
    order_id: str,
    reason: str,
    comment: str | None = None,
    conn: AsyncConnection = Depends(get_conn),
):
    async with dict_cursor(conn) as cur:
        await cur.execute(
            "select status, created_at, (payment->>'status') as pay from orders where id=%s::uuid",
            (order_id,),
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(404, "Order not found")
        if row["pay"] != "paid":
            raise HTTPException(400, "Only paid orders can be returned")
        if row["status"] in ("cancelled", "refund_requested", "refunded"):
            raise HTTPException(400, "Order not eligible")

        await cur.execute(
            "select (now() - created_at) <= interval '30 days' as ok from orders where id=%s::uuid",
            (order_id,),
        )
        ok = (await cur.fetchone())["ok"]
        if not ok:
            raise HTTPException(400, "Return window closed")

        await cur.execute(
            """
            update orders
            set status='refund_requested',
                refund = jsonb_build_object(
                  'requestedAt', now()::text,
                  'reason', %s::text,
                  'comment', coalesce(%s::text, ''),
                  'approved', false
                )
            where id=%s::uuid
            """,
            (reason, comment, order_id),
        )
    return {"ok": True}

@router.post("/{order_id}/refund/approve")
async def approve_refund(
    order_id: str,
    amount: float | None = None,
    conn: AsyncConnection = Depends(get_conn),
):
    async with dict_cursor(conn) as cur:
        await cur.execute(
            "select status, (payment->>'status') as pay, (totals->>'grand')::numeric as grand "
            "from orders where id=%s::uuid",
            (order_id,),
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(404, "Order not found")
        if row["pay"] != "paid":
            raise HTTPException(400, "Only paid orders can be refunded")
        if row["status"] != "refund_requested":
            raise HTTPException(400, "Refund not requested")

        amt = amount if amount is not None else float(row["grand"])
        await cur.execute(
            """
            update orders
            set status='refunded',
                refund = coalesce(refund,'{}'::jsonb)
                    || jsonb_build_object(
                         'approved', true,
                         'amount', to_jsonb(%s::numeric),
                         'processedAt', now()::text
                       )
            where id=%s::uuid
            """,
            (amt, order_id),
        )
    return {"ok": True}

@router.post("/{order_id}/refund/cancel")
async def cancel_refund_request(order_id: str, conn: AsyncConnection = Depends(get_conn)):
    async with dict_cursor(conn) as cur:
        await cur.execute(
            "select status, (payment->>'status') as pay from orders where id=%s::uuid",
            (order_id,),
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(404, "Order not found")
        if row["status"] != "refund_requested":
            raise HTTPException(400, "No refund request to cancel")
        await cur.execute(
            "update orders set status='processing', refund = refund - 'approved' where id=%s::uuid",
            (order_id,),
        )
    return {"ok": True}

@router.get("/{order_id}", response_model=OrderOut)
async def get_order(order_id: UUID, conn: AsyncConnection = Depends(get_conn)):
    order_id = str(order_id)
    async with dict_cursor(conn) as cur:
        await cur.execute(
            """
            select id::text, created_at::timestamptz::text,
                   totals, customer, shipping, payment, status, refund
            from orders where id=%s::uuid
            """,
            (order_id,),
        )
        o = await cur.fetchone()
        if not o:
            raise HTTPException(404, "Order not found")

        await cur.execute(
            """
            select product_id::text as id, title, slug, price::float, qty, image_url as "imageUrl"
            from order_items
            where order_id=%s::uuid
            """,
            (order_id,),
        )
        items = await cur.fetchall()

    return OrderOut(
        id=o["id"],
        created_at=o["created_at"],
        items=[CartItemIn.model_validate(i) for i in items],
        totals=Totals.model_validate(o["totals"]),
        customer=Customer.model_validate(o["customer"]),
        shipping=Shipping.model_validate(o["shipping"]),
        payment=o["payment"],
        status=o["status"],
        refund=o.get("refund"),
    )

# --- helper: смена статуса с проверками ---
async def _set_status(conn: AsyncConnection, order_id: str, new_status: str):
    async with dict_cursor(conn) as cur:
        await cur.execute(
            "select status, (payment->>'status') as pay from orders where id=%s::uuid",
            (order_id,),
        )
        row = await cur.fetchone()
        if not row:
            raise HTTPException(404, "Order not found")
        if row["status"] in ("cancelled", "refunded"):
            raise HTTPException(400, "Order is final")
        if new_status in ("shipped", "delivered") and row["pay"] != "paid":
            raise HTTPException(400, "Order must be paid")

        allowed = {
            "processing": {"packed"},
            "packed": {"shipped"},
            "shipped": {"delivered"},
            "delivered": set(),
            "refund_requested": set(),
            "cancelled": set(),
            "refunded": set(),
        }
        cur_state = row["status"]
        if new_status not in allowed.get(cur_state, set()):
            raise HTTPException(400, f"Cannot transition {cur_state} → {new_status}")

        await cur.execute(
            "update orders set status=%s where id=%s::uuid",
            (new_status, order_id),
        )
    return {"ok": True}

@router.post("/{order_id}/packed")
async def mark_packed(order_id: str, conn: AsyncConnection = Depends(get_conn)):
    return await _set_status(conn, order_id, "packed")

@router.post("/{order_id}/shipped")
async def mark_shipped(order_id: str, conn: AsyncConnection = Depends(get_conn)):
    return await _set_status(conn, order_id, "shipped")

@router.post("/{order_id}/delivered")
async def mark_delivered(order_id: str, conn: AsyncConnection = Depends(get_conn)):
    return await _set_status(conn, order_id, "delivered")

@router.post("/{order_id}/pay")
async def mark_paid(
    order_id: str,
    last4: str = "4242",
    conn: AsyncConnection = Depends(get_conn),
):
    async with dict_cursor(conn) as cur:
        await cur.execute("select 1 from orders where id=%s::uuid", (order_id,))
        if not await cur.fetchone():
            from fastapi import HTTPException
            raise HTTPException(404, "Order not found")

        await cur.execute("""
          update orders
             set payment = jsonb_build_object('status','paid','method','card','last4', %s::text),
                 status = case when status='processing' then 'packed' else status end
           where id=%s::uuid
        """, (last4, order_id))
    return {"ok": True}
