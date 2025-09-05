# routers/auth.py
import uuid
from fastapi import APIRouter, Depends, HTTPException
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from db import get_conn
from models import (
    UserUpsertIn, UserPublic, RegisterIn, LoginIn, TokenOut, MeOut, UserUpdateIn
)
from security import hash_password, verify_password, create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register", response_model=TokenOut, status_code=201)
async def register(body: RegisterIn, conn: AsyncConnection = Depends(get_conn)):
    async with conn.cursor(row_factory=dict_row) as cur:
        # уже есть такой email?
        await cur.execute("select 1 from users where lower(email)=lower(%s)", (body.email,))
        if await cur.fetchone():
            raise HTTPException(409, "Email already registered")

        uid = str(uuid.uuid4())
        pwd_hash = hash_password(body.password)
        await cur.execute(
            "insert into users(id,email,name,password_hash,created_at) values(%s,%s,%s,%s,now())",
            (uid, body.email, body.name.strip(), pwd_hash),
        )
    token = create_access_token(sub=body.email)
    return TokenOut(access_token=token, token_type="bearer")


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, conn: AsyncConnection = Depends(get_conn)):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "select id::text, email, name, password_hash from users where lower(email)=lower(%s)",
            (body.email,),
        )
        row = await cur.fetchone()
        if not row or not verify_password(body.password, row.get("password_hash")):
            raise HTTPException(401, "Invalid email or password")
    token = create_access_token(sub=row["email"])
    return TokenOut(access_token=token, token_type="bearer")


@router.get("/me", response_model=MeOut)
async def me(user: UserPublic = Depends(get_current_user)):
    return MeOut(user=user)


# совместимость с твоим апдейтом имени/автосозданием (OAuth/Social)
@router.post("/upsert", response_model=UserPublic)
async def upsert_user(body: UserUpsertIn, conn: AsyncConnection = Depends(get_conn)):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("select id::text, email, name from users where lower(email)=lower(%s)", (body.email,))
        row = await cur.fetchone()
        if row:
            if (row["name"] or "").strip() != body.name.strip():
                await cur.execute("update users set name=%s where id=%s", (body.name.strip(), row["id"]))
                row["name"] = body.name.strip()
            return UserPublic.model_validate(row)
        uid = str(uuid.uuid4())
        await cur.execute(
            "insert into users(id,email,name,created_at) values(%s,%s,%s,now()) returning id::text, email, name",
            (uid, body.email, body.name.strip()),
        )
        row = await cur.fetchone()
    return UserPublic.model_validate(row)

@router.api_route("/me", methods=["PATCH", "PUT"], response_model=UserPublic)
async def update_me(
    body: UserUpdateIn,
    current: UserPublic = Depends(get_current_user),
    conn: AsyncConnection = Depends(get_conn),
):
    # актуальные значения пользователя
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("select id::text, email, name, password_hash from users where id=%s::uuid", (current.id,))
        row = await cur.fetchone()
        if not row:
            raise HTTPException(401, "User not found")

    old_email = row["email"]
    changed = False

    # 1) смена имени
    if body.name is not None and body.name.strip() != row["name"]:
        async with conn.cursor() as cur:
            await cur.execute("update users set name=%s where id=%s::uuid", (body.name.strip(), current.id))
        current.name = body.name.strip()
        changed = True

    # 2) смена пароля (если передан new_password — требуем current_password и проверяем)
    if body.new_password:
        if not body.current_password:
            raise HTTPException(400, "current_password is required to change password")
        if not verify_password(body.current_password, row.get("password_hash")):
            raise HTTPException(400, "Current password is incorrect")
        pwd_hash = hash_password(body.new_password)
        async with conn.cursor() as cur:
            await cur.execute("update users set password_hash=%s where id=%s::uuid", (pwd_hash, current.id))
        changed = True

    # 3) смена email (с каскадными апдейтами там, где у тебя поиск по email)
    if body.email and body.email.lower() != old_email.lower():
        # проверка уникальности
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("select 1 from users where lower(email)=lower(%s)", (body.email,))
            if await cur.fetchone():
                raise HTTPException(409, "Email already registered")

        async with conn.transaction():
            async with conn.cursor() as cur:
                # users
                await cur.execute("update users set email=%s where id=%s::uuid", (body.email, current.id))
                # addresses.user_email
                await cur.execute(
                    "update addresses set user_email=%s where lower(user_email)=lower(%s)",
                    (body.email, old_email),
                )
                # orders.email
                await cur.execute(
                    "update orders set email=%s where lower(email)=lower(%s)",
                    (body.email, old_email),
                )
                # orders.customer->>'email'
                await cur.execute(
                    "update orders set customer = jsonb_set(coalesce(customer,'{}'::jsonb), '{email}', to_jsonb(%s::text), true)"
                    " where lower(customer->>'email') = lower(%s)",
                    (body.email, old_email),
                )
        current.email = body.email
        changed = True

    if not changed:
        # ничего не поменяли — вернём текущее
        return current

    return current