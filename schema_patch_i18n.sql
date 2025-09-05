-- schema_patch_i18n.sql
SET search_path TO mira, public;

-- Таблица переводов (если ещё не создана) — сразу с uk
CREATE TABLE IF NOT EXISTS product_i18n (
  product_id uuid NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  locale text NOT NULL,
  title text NOT NULL,
  short text,
  description text,
  slug text NOT NULL,
  PRIMARY KEY (product_id, locale),
  UNIQUE (locale, slug)
);

-- Обновляем/создаём CHECK так, чтобы допустить 'uk'
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.table_constraints
    WHERE table_schema = 'mira' AND table_name = 'product_i18n'
      AND constraint_type = 'CHECK'
      AND constraint_name = 'product_i18n_locale_check'
  ) THEN
    EXECUTE 'ALTER TABLE product_i18n DROP CONSTRAINT product_i18n_locale_check';
  END IF;
  EXECUTE $chk$
    ALTER TABLE product_i18n
    ADD CONSTRAINT product_i18n_locale_check
    CHECK (locale IN ('ru','en','de','uk'))
  $chk$;
END$$;

-- Индексы
CREATE INDEX IF NOT EXISTS idx_product_i18n_loc ON product_i18n(locale);
CREATE INDEX IF NOT EXISTS idx_product_i18n_slug_loc ON product_i18n(locale, slug);
