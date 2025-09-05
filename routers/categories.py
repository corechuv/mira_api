# routers/categories.py
from fastapi import APIRouter, Depends
from psycopg import AsyncConnection
from db import get_conn, dict_cursor

router = APIRouter(prefix="/categories", tags=["categories"])

@router.get("", response_model=list[dict])
async def list_categories(conn: AsyncConnection = Depends(get_conn)):
    async with dict_cursor(conn) as cur:
        await cur.execute("""
            select id::text, title, slug, parent_id::text
            from categories
            order by title
        """)
        rows = await cur.fetchall()

    # Собираем дерево: id -> node
    nodes: dict[str, dict] = {
        r["id"]: {"title": r["title"], "slug": r["slug"], "children": []}
        for r in rows
    }
    roots: list[dict] = []
    for r in rows:
        pid = r["parent_id"]
        node = nodes[r["id"]]
        if pid and pid in nodes:
            nodes[pid]["children"].append(node)
        else:
            roots.append(node)

    # Пустые children не мешают; фронту подходит форма из src/data/categories.ts
    return roots
