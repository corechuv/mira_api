# routers/products.py
from fastapi import APIRouter, Depends, Query
from psycopg import AsyncConnection
from db import get_conn, dict_cursor
from models import ProductsQuery, ProductsPage, ProductOut, PageOut

router = APIRouter(prefix="/products", tags=["products"])

SUPPORTED_LOCALES = {"ru", "en", "de", "uk"}  # добавили uk
ALIASES = {"ua": "uk"}  # принимаем ua как алиас

def normalize_locale(locale: str | None) -> str | None:
    if not locale:
        return None
    loc = locale.lower()
    if loc in ALIASES:
        loc = ALIASES[loc]
    return loc if loc in SUPPORTED_LOCALES else None


@router.get("", response_model=ProductsPage)
async def list_products(
    q: ProductsQuery = Depends(),
    locale: str | None = Query(None, description="ru|en|de|uk (ua → uk)"),
    conn: AsyncConnection = Depends(get_conn),
):
    loc = normalize_locale(locale)

    where: list[str] = []
    params: dict = {"limit": q.limit, "offset": q.offset}

    if q.search:
        params["q"] = f"%{q.search.lower()}%"
        # ищем по локализованным полям, если есть; иначе по базовым
        where.append(
            "(lower(coalesce(i_loc.title, p.title)) like %(q)s "
            " or lower(coalesce(i_loc.short, p.short)) like %(q)s "
            " or lower(coalesce(i_loc.description, p.description)) like %(q)s)"
        )

    if q.category:
        where.append("p.category = %(category)s")
        params["category"] = q.category
    if q.sub:
        where.append("p.sub = %(sub)s")
        params["sub"] = q.sub
    if q.leaf:
        where.append("p.leaf = %(leaf)s")
        params["leaf"] = q.leaf
    if q.price_min is not None:
        where.append("p.price >= %(pmin)s")
        params["pmin"] = q.price_min
    if q.price_max is not None:
        where.append("p.price <= %(pmax)s")
        params["pmax"] = q.price_max
    if q.rating_min is not None:
        where.append("p.rating >= %(rmin)s")
        params["rmin"] = q.rating_min

    order_by = {
        "popular": "p.rating desc nulls last, p.price asc",
        "price-asc": "p.price asc",
        "price-desc": "p.price desc",
    }[q.sort]

    where_sql = (" where " + " and ".join(where)) if where else ""
    join_loc = "LEFT JOIN product_i18n i_loc ON i_loc.product_id = p.id AND i_loc.locale = %(loc)s" if loc else ""
    if loc:
        params["loc"] = loc

    sql_count = f"select count(*) as c from products p {join_loc}{where_sql}"
    sql_items = f"""
      select
        p.id::text,
        coalesce(i_loc.slug, p.slug) as slug,
        coalesce(i_loc.title, p.title) as title,
        p.category, p.sub, p.leaf,
        p.price::float, p.rating::float,
        coalesce(i_loc.short, p.short) as short,
        coalesce(i_loc.description, p.description) as description,
        p.image_url as "imageUrl"
      from products p
      {join_loc}
      {where_sql}
      order by {order_by}
      limit %(limit)s offset %(offset)s
    """

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
async def get_product(
    slug: str,
    locale: str | None = Query(None, description="ru|en|de|uk (ua → uk); поиск по локализованному slug"),
    conn: AsyncConnection = Depends(get_conn),
):
    loc = normalize_locale(locale)

    async with dict_cursor(conn) as cur:
        if loc:
            # 1) пробуем найти по локализованному slug в product_i18n
            await cur.execute("""
              select
                p.id::text,
                coalesce(i_loc.slug, p.slug) as slug,
                coalesce(i_loc.title, p.title) as title,
                p.category, p.sub, p.leaf,
                p.price::float, p.rating::float,
                coalesce(i_loc.short, p.short) as short,
                coalesce(i_loc.description, p.description) as description,
                p.image_url as "imageUrl"
              from products p
              join product_i18n i_loc on i_loc.product_id = p.id and i_loc.locale = %(loc)s
              where i_loc.slug = %(slug)s
              limit 1
            """, {"slug": slug, "loc": loc})
            row = await cur.fetchone()
            if row:
                return ProductOut.model_validate(row)

        # 2) фолбэк — базовый slug из products
        await cur.execute("""
          select
            id::text, slug, title, category, sub, leaf, price::float, rating::float,
            short, description, image_url as "imageUrl"
          from products
          where slug = %(slug)s
          limit 1
        """, {"slug": slug})
        row = await cur.fetchone()
        return ProductOut.model_validate(row) if row else None
