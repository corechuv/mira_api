# db.py
import os
from dotenv import load_dotenv
from psycopg_pool import AsyncConnectionPool
from psycopg.rows import dict_row

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set.")

pool = AsyncConnectionPool(
    DATABASE_URL,
    min_size=1,
    max_size=10,
    open=False,
)

async def get_conn():
    async with pool.connection() as conn:
        # 👇 фикс: явно выставляем схему для каждой сессии
        await conn.execute("SET search_path TO mira, public")
        yield conn

def dict_cursor(conn):
    return conn.cursor(row_factory=dict_row)
