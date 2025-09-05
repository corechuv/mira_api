-- compat.sql
SET search_path TO mira, public;

-- products: добавить плоские рубрики, как ждёт код/сид
ALTER TABLE products
  ADD COLUMN IF NOT EXISTS category text,
  ADD COLUMN IF NOT EXISTS sub      text,
  ADD COLUMN IF NOT EXISTS leaf     text;

-- reviews: добавить счётчик helpful, как ждёт код/сид
ALTER TABLE reviews
  ADD COLUMN IF NOT EXISTS helpful integer NOT NULL DEFAULT 0;

-- addresses: код работает по user_email, a не по user_id
ALTER TABLE addresses
  ADD COLUMN IF NOT EXISTS user_email citext;
-- чтобы вставки без user_id не падали:
ALTER TABLE addresses
  ALTER COLUMN user_id DROP NOT NULL;

-- orders: код использует JSONB-снапшоты
ALTER TABLE orders
  ADD COLUMN IF NOT EXISTS totals   jsonb,
  ADD COLUMN IF NOT EXISTS customer jsonb,
  ADD COLUMN IF NOT EXISTS shipping jsonb,
  ADD COLUMN IF NOT EXISTS payment  jsonb,
  ADD COLUMN IF NOT EXISTS refund   jsonb;

-- в текущей схеме email NOT NULL — код его не заполняет (берёт из customer->>'email')
ALTER TABLE orders
  ALTER COLUMN email DROP NOT NULL;

