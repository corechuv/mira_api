# routers/products.py
from fastapi import APIRouter, Depends
from psycopg import AsyncConnection
from db import get_conn, dict_cursor
from models import ProductsQuery, ProductsPage, ProductOut, PageOut

router = APIRouter(prefix="/products", tags=["products"])

@router.get("", response_model=ProductsPage)
async def list_products(
    q: ProductsQuery = Depends(),
    conn: AsyncConnection = Depends(get_conn),
):
    where = []
    params = {}

    if q.search:
        where.append("(lower(title) like %(q)s or lower(short) like %(q)s or lower(description) like %(q)s)")
        params["q"] = f"%{q.search.lower()}%"
    if q.category:
        where.append("category = %(category)s")
        params["category"] = q.category
    if q.sub:
        where.append("sub = %(sub)s")
        params["sub"] = q.sub
    if q.leaf:
        where.append("leaf = %(leaf)s")
        params["leaf"] = q.leaf
    if q.price_min is not None:
        where.append("price >= %(pmin)s")
        params["pmin"] = q.price_min
    if q.price_max is not None:
        where.append("price <= %(pmax)s")
        params["pmax"] = q.price_max
    if q.rating_min is not None:
        where.append("rating >= %(rmin)s")
        params["rmin"] = q.rating_min

    order_by = {
        "popular": "rating desc nulls last, price asc",
        "price-asc": "price asc",
        "price-desc": "price desc",
    }[q.sort]

    where_sql = (" where " + " and ".join(where)) if where else ""
    sql_count = f"select count(*) as c from products{where_sql}"
    sql_items = f"""
      select id::text, slug, title, category, sub, leaf, price::float, rating::float,
             short, description, image_url as "imageUrl"
      from products
      {where_sql}
      order by {order_by}
      limit %(limit)s offset %(offset)s
    """
    params["limit"] = q.limit
    params["offset"] = q.offset

    async with dict_cursor(conn) as cur:
        await cur.execute(sql_count, params)
        total = (await cur.fetchone())["c"]
        await cur.execute(sql_items, params)
        rows = await cur.fetchall()

    return ProductsPage(
        items=[ProductOut.model_validate(r) for r in rows],
        page=PageOut(total=total, limit=q.limit, offset=q.offset),
    )

@router.get("/{slug}", response_model=ProductOut | None)
async def get_product(slug: str, conn: AsyncConnection = Depends(get_conn)):
    async with dict_cursor(conn) as cur:
        await cur.execute("""
          select id::text, slug, title, category, sub, leaf, price::float, rating::float,
                 short, description, image_url as "imageUrl"
          from products where slug = %s
        """, (slug,))
        row = await cur.fetchone()
    return ProductOut.model_validate(row) if row else None
