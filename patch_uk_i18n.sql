-- patch_uk_i18n.sql
-- Добавляет/обновляет таблицу переводов, включает 'uk',
-- делает бэкфилл под все товары и задаёт понятные uk-тексты
-- для демо-SKU (и локализованный slug для multivitamins).

BEGIN;
SET search_path TO mira, public;

-- 1) Таблица переводов (если нет)
CREATE TABLE IF NOT EXISTS product_i18n (
  product_id uuid NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  locale     text NOT NULL,
  title      text NOT NULL,
  short      text,
  description text,
  slug       text NOT NULL,
  PRIMARY KEY (product_id, locale),
  UNIQUE (locale, slug)
);

-- 2) CHECK на локали с 'uk'
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.table_constraints
    WHERE table_schema='mira'
      AND table_name='product_i18n'
      AND constraint_type='CHECK'
      AND constraint_name='product_i18n_locale_check'
  ) THEN
    EXECUTE 'ALTER TABLE product_i18n DROP CONSTRAINT product_i18n_locale_check';
  END IF;

  EXECUTE $chk$
    ALTER TABLE product_i18n
    ADD CONSTRAINT product_i18n_locale_check
    CHECK (locale IN ('ru','en','de','uk'))
  $chk$;
END$$;

-- 3) Индексы (если нет)
CREATE INDEX IF NOT EXISTS idx_product_i18n_loc      ON product_i18n(locale);
CREATE INDEX IF NOT EXISTS idx_product_i18n_slug_loc ON product_i18n(locale, slug);

-- 4) Бэкфилл: создать заглушки для 'uk' там, где их нет
INSERT INTO product_i18n (product_id, locale, title, short, description, slug)
SELECT p.id, 'uk', p.title, p.short, p.description, p.slug
FROM products p
LEFT JOIN product_i18n i
  ON i.product_id = p.id AND i.locale = 'uk'
WHERE i.product_id IS NULL;

-- 5) Осмысленные uk-тексты для демо-товаров

-- 5.1 multivitamins — показываем локализованный slug
UPDATE product_i18n i
SET title       = 'Мультивітаміни',
    short       = 'Щоденний вітамінний комплекс',
    description = 'Демонстраційний товар для smoke-тестів API',
    slug        = 'multivitaminy'
FROM products p
WHERE i.product_id = p.id
  AND i.locale = 'uk'
  AND p.slug = 'multivitamins';

-- 5.2 серия multivitamins-sport-* — uk-тексты (slug оставляем тем же)
UPDATE product_i18n i
SET title       = 'Sports Research, Фітоцераміди Mini-Gels, 350 мг, 30 м’яких капсул',
    short       = 'Комплекс для підтримки здоров’я.',
    description = '350 мг на порцію. Сприяє зволоженню шкіри …'
FROM products p
WHERE i.product_id = p.id
  AND i.locale = 'uk'
  AND p.slug IN ('multivitamins-sport-1','multivitamins-sport-2','multivitamins-3','multivitamins-4','multivitamins-5');

COMMIT;

-- 6) Контрольные выборки (не обязательны)
-- SELECT locale, count(*) FROM product_i18n GROUP BY locale ORDER BY locale;
-- SELECT * FROM product_i18n WHERE locale='uk' AND slug IN ('multivitaminy','multivitamins');
