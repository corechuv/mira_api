# routers/addresses.py
import uuid
from fastapi import APIRouter, Depends, HTTPException
from psycopg import AsyncConnection
from db import get_conn, dict_cursor
from models import Address, AddressCreate, AddressUpdate, UserPublic
from security import get_optional_user, get_current_user

router = APIRouter(prefix="/addresses", tags=["addresses"])

@router.get("", response_model=list[Address])
async def list_addresses(
    email: str | None = None,
    current: UserPublic | None = Depends(get_optional_user),
    conn: AsyncConnection = Depends(get_conn),
):
    # если есть авторизация — игнорируем query email и берём свой
    effective_email = (current.email if current else None) or email
    if not effective_email:
        raise HTTPException(401, "Email is required (or send Authorization bearer token)")
    async with dict_cursor(conn) as cur:
        await cur.execute("""
          select id::text, user_email, first_name, last_name, street, house, zip, city, phone, note,
                 pack_type, post_nummer, station_nr, is_default
          from addresses
          where lower(user_email) = lower(%s)
          order by is_default desc, created_at desc
        """, (effective_email,))
        rows = await cur.fetchall()
    return [Address.model_validate(r) for r in rows]


@router.post("", response_model=Address)
async def create_address(
    body: AddressCreate,
    current: UserPublic = Depends(get_current_user),
    conn: AsyncConnection = Depends(get_conn),
):
    # насильно привязываем адрес к текущему пользователю
    aid = str(uuid.uuid4())
    user_email = current.email
    async with dict_cursor(conn) as cur:
        if body.is_default:
            await cur.execute("update addresses set is_default=false where lower(user_email) = lower(%s)", (user_email,))
        await cur.execute("""
          insert into addresses
          (id, user_email, first_name, last_name, street, house, zip, city, phone, note,
           pack_type, post_nummer, station_nr, is_default, created_at)
          values
          (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
          returning id::text, user_email, first_name, last_name, street, house, zip, city, phone, note,
                    pack_type, post_nummer, station_nr, is_default
        """, (aid, user_email, body.first_name, body.last_name, body.street, body.house,
              body.zip, body.city, body.phone, body.note, body.pack_type, body.post_nummer,
              body.station_nr, body.is_default))
        row = await cur.fetchone()
    return Address.model_validate(row)


@router.put("/{addr_id}", response_model=Address)
async def update_address(
    addr_id: str,
    body: AddressUpdate,
    current: UserPublic = Depends(get_current_user),
    conn: AsyncConnection = Depends(get_conn),
):
    user_email = current.email
    async with dict_cursor(conn) as cur:
        # проверим, что адрес принадлежит пользователю
        await cur.execute("select 1 from addresses where id=%s and lower(user_email)=lower(%s)", (addr_id, user_email))
        if not await cur.fetchone():
            raise HTTPException(404, "Address not found")

        if body.is_default:
            await cur.execute("update addresses set is_default=false where lower(user_email) = lower(%s)", (user_email,))
        await cur.execute("""
          update addresses set
            first_name=%s, last_name=%s, street=%s, house=%s, zip=%s, city=%s,
            phone=%s, note=%s, pack_type=%s, post_nummer=%s, station_nr=%s, is_default=%s
          where id=%s and lower(user_email)=lower(%s)
          returning id::text, user_email, first_name, last_name, street, house, zip, city, phone, note,
                    pack_type, post_nummer, station_nr, is_default
        """, (body.first_name, body.last_name, body.street, body.house,
              body.zip, body.city, body.phone, body.note, body.pack_type, body.post_nummer,
              body.station_nr, body.is_default, addr_id, user_email))
        row = await cur.fetchone()
        if not row:
            raise HTTPException(404, "Address not found")
    return Address.model_validate(row)


@router.delete("/{addr_id}")
async def delete_address(
    addr_id: str,
    current: UserPublic = Depends(get_current_user),
    conn: AsyncConnection = Depends(get_conn),
):
    async with dict_cursor(conn) as cur:
        await cur.execute("delete from addresses where id=%s and lower(user_email)=lower(%s)", (addr_id, current.email))
        if cur.rowcount == 0:
            raise HTTPException(404, "Address not found")
    return {"ok": True}


@router.post("/{addr_id}/default")
async def make_default(
    addr_id: str,
    current: UserPublic = Depends(get_current_user),
    conn: AsyncConnection = Depends(get_conn),
):
    async with dict_cursor(conn) as cur:
        await cur.execute("update addresses set is_default=false where lower(user_email)=lower(%s)", (current.email,))
        await cur.execute(
            "update addresses set is_default=true where id=%s and lower(user_email)=lower(%s)",
            (addr_id, current.email),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "Address not found")
    return {"ok": True}
