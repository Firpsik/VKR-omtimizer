CREATE SCHEMA IF NOT EXISTS mp;
SET search_path TO mp, public;

CREATE TABLE IF NOT EXISTS mp.marketplaces (
    marketplace_id SERIAL PRIMARY KEY,
    code VARCHAR(16) UNIQUE NOT NULL,
    name VARCHAR(64) NOT NULL
);

INSERT INTO mp.marketplaces (code, name) VALUES
    ('wb', 'Wildberries'),
    ('ozon', 'Ozon'),
    ('ym', 'Яндекс Маркет')
ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name;

CREATE TABLE IF NOT EXISTS mp.products (
    product_id SERIAL PRIMARY KEY,
    sku VARCHAR(64) UNIQUE NOT NULL,
    name VARCHAR(256) NOT NULL,
    category_id INT,
    canonical_category_id INT,
    weight_kg NUMERIC(10,3) NOT NULL,
    volume_l NUMERIC(10,3) NOT NULL,
    cost_rub NUMERIC(12,2) NOT NULL,
    promo_rub NUMERIC(12,2) NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS mp.sales_history (
    sale_id BIGSERIAL PRIMARY KEY,
    product_id INT NOT NULL REFERENCES mp.products(product_id) ON DELETE CASCADE,
    marketplace_id INT NOT NULL REFERENCES mp.marketplaces(marketplace_id),
    obs_date DATE NOT NULL,
    price_rub NUMERIC(12,2) NOT NULL,
    qty INT NOT NULL,
    is_promo BOOLEAN NOT NULL DEFAULT FALSE,
    stock_qty INT
);

CREATE INDEX IF NOT EXISTS idx_sales_history_pid_mid ON mp.sales_history (product_id, marketplace_id);
BEGIN;
SET search_path TO mp, public;

CREATE TABLE IF NOT EXISTS mp.canonical_groups (
    canonical_group_id  SERIAL  PRIMARY KEY,
    code                VARCHAR(32)  UNIQUE NOT NULL,
    name                VARCHAR(128) NOT NULL,
    sort_order          INT NOT NULL DEFAULT 0
);
COMMENT ON TABLE  mp.canonical_groups IS
    'Канонические товарные группы (верхний уровень) — справочник.';
COMMENT ON COLUMN mp.canonical_groups.code IS
    'Машинный идентификатор группы (используется в UI и в маппингах).';

CREATE TABLE IF NOT EXISTS mp.canonical_categories (
    canonical_category_id      SERIAL  PRIMARY KEY,
    canonical_group_id         INT  NOT NULL REFERENCES mp.canonical_groups,
    code                       VARCHAR(48)  UNIQUE NOT NULL,
    name                       VARCHAR(128) NOT NULL,
    requires_marking           BOOLEAN  NOT NULL DEFAULT FALSE,
    marking_cost_per_unit_rub  NUMERIC(8,2) NOT NULL DEFAULT 0,
    sort_order                 INT NOT NULL DEFAULT 0,
    is_custom                  BOOLEAN  NOT NULL DEFAULT FALSE,
    created_at                 TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE  mp.canonical_categories IS
    'Канонические товарные категории (листовой уровень). К этим строкам '
    'привязываются тарифы маркетплейсов через таблицы маппинга.';
COMMENT ON COLUMN mp.canonical_categories.requires_marking IS
    'Признак обязательной маркировки "Честный знак".';
COMMENT ON COLUMN mp.canonical_categories.marking_cost_per_unit_rub IS
    'Средняя стоимость маркировки на единицу (₽). Используется в '
    'юнит-экономике как фиксированный сбор.';
COMMENT ON COLUMN mp.canonical_categories.is_custom IS
    'TRUE для категорий, добавленных продавцом через UI (см. шаг 6).';

CREATE TABLE IF NOT EXISTS mp.wb_category_map (
    wb_category_id        SERIAL PRIMARY KEY,
    wb_category_code      VARCHAR(64) UNIQUE NOT NULL,
    wb_category_name      VARCHAR(256) NOT NULL,
    canonical_category_id INT  NOT NULL REFERENCES mp.canonical_categories
);
COMMENT ON TABLE mp.wb_category_map IS
    'Соответствие категорий Wildberries каноническим категориям АСМП-Маркет.';

CREATE TABLE IF NOT EXISTS mp.ozon_category_map (
    ozon_category_id      SERIAL PRIMARY KEY,
    ozon_category_code    VARCHAR(64) UNIQUE NOT NULL,
    ozon_category_name    VARCHAR(256) NOT NULL,
    canonical_category_id INT  NOT NULL REFERENCES mp.canonical_categories
);
COMMENT ON TABLE mp.ozon_category_map IS
    'Соответствие категорий Ozon каноническим категориям АСМП-Маркет.';

CREATE TABLE IF NOT EXISTS mp.ym_category_map (
    ym_category_id        SERIAL PRIMARY KEY,
    ym_category_code      VARCHAR(64) UNIQUE NOT NULL,
    ym_category_name      VARCHAR(256) NOT NULL,
    canonical_category_id INT  NOT NULL REFERENCES mp.canonical_categories
);
COMMENT ON TABLE mp.ym_category_map IS
    'Соответствие категорий Яндекс.Маркета каноническим категориям АСМП-Маркет.';

CREATE TABLE IF NOT EXISTS mp.tariff_rule (
    tariff_rule_id         BIGSERIAL PRIMARY KEY,
    marketplace_id         INT  NOT NULL REFERENCES mp.marketplaces,
    canonical_category_id  INT  NOT NULL REFERENCES mp.canonical_categories,
    scheme                 VARCHAR(16) NOT NULL,
    commission_pct         NUMERIC(6,4) NOT NULL,
    return_fee_rub         NUMERIC(8,2) NOT NULL DEFAULT 0,
    disposal_fee_rub       NUMERIC(8,2) NOT NULL DEFAULT 0,
    default_buyout_rate    NUMERIC(5,3) NOT NULL DEFAULT 0.920,
    default_return_rate    NUMERIC(5,3) NOT NULL DEFAULT 0.080,
    valid_from             DATE NOT NULL,
    valid_to               DATE,
    source_url             TEXT,
    comment                TEXT,
    UNIQUE (marketplace_id, canonical_category_id, scheme, valid_from),
    CHECK (scheme IN ('FBO','FBS','rFBS','FBY','FBY-Premium','Express','DBS')),
    CHECK (commission_pct >= 0 AND commission_pct <= 1),
    CHECK (default_buyout_rate >= 0 AND default_buyout_rate <= 1),
    CHECK (default_return_rate >= 0 AND default_return_rate <= 1)
);
COMMENT ON TABLE mp.tariff_rule IS
    'Супертип тарифных правил (CTI). Общие поля: комиссия, возврат, '
    'утилизация, ожидаемые доли выкупа/возврата. Подтипы — в таблицах '
    'tariff_rule_wb / tariff_rule_ozon / tariff_rule_ym.';

CREATE INDEX IF NOT EXISTS ix_tariff_rule_mp_cat
    ON mp.tariff_rule(marketplace_id, canonical_category_id);

CREATE TABLE IF NOT EXISTS mp.tariff_rule_wb (
    tariff_rule_id              BIGINT PRIMARY KEY
        REFERENCES mp.tariff_rule ON DELETE CASCADE,
    ktr                         NUMERIC(6,3) NOT NULL DEFAULT 1.0,
    warehouse_coef_default      NUMERIC(6,3) NOT NULL DEFAULT 1.0,
    logistics_base_rub          NUMERIC(8,2) NOT NULL,
    logistics_per_liter_rub     NUMERIC(8,2) NOT NULL,
    storage_per_liter_day_rub   NUMERIC(8,3) NOT NULL DEFAULT 0,
    default_promo_pct           NUMERIC(5,3) NOT NULL DEFAULT 0
);
COMMENT ON TABLE mp.tariff_rule_wb IS
    'Подтип WB: КТР, коэф. склада, формула логистики (база + ставка за '
    'каждый последующий литр), хранение, средняя реклама.';

CREATE TABLE IF NOT EXISTS mp.tariff_rule_ozon (
    tariff_rule_id              BIGINT PRIMARY KEY
        REFERENCES mp.tariff_rule ON DELETE CASCADE,
    last_mile_pct               NUMERIC(6,4) NOT NULL DEFAULT 0,
    last_mile_min_rub           NUMERIC(8,2) NOT NULL DEFAULT 0,
    last_mile_max_rub           NUMERIC(8,2) NOT NULL DEFAULT 0,
    acquiring_pct               NUMERIC(6,4) NOT NULL DEFAULT 0.0150,
    processing_fee_rub          NUMERIC(8,2) NOT NULL DEFAULT 0,
    storage_free_days           INT  NOT NULL DEFAULT 60,
    storage_per_liter_day_rub   NUMERIC(8,3) NOT NULL DEFAULT 0,
    locality_index_pct          NUMERIC(6,4) NOT NULL DEFAULT 0,
    default_promo_pct           NUMERIC(5,3) NOT NULL DEFAULT 0,
    default_seller_bonus_pct    NUMERIC(5,3) NOT NULL DEFAULT 0
);
COMMENT ON TABLE mp.tariff_rule_ozon IS
    'Подтип Ozon: last-mile (% с min/max), эквайринг, обработка отправлений, '
    'хранение (с бесплатным окном), индекс локализации, реклама, бонусы продавца.';

CREATE TABLE IF NOT EXISTS mp.tariff_rule_ym (
    tariff_rule_id              BIGINT PRIMARY KEY
        REFERENCES mp.tariff_rule ON DELETE CASCADE,
    last_mile_pct               NUMERIC(6,4) NOT NULL DEFAULT 0,
    last_mile_max_rub           NUMERIC(8,2) NOT NULL DEFAULT 0,
    acquiring_pct               NUMERIC(6,4) NOT NULL DEFAULT 0.0150,
    packaging_fee_rub           NUMERIC(8,2) NOT NULL DEFAULT 0,
    storage_free_days           INT  NOT NULL DEFAULT 60,
    storage_per_liter_day_rub   NUMERIC(8,3) NOT NULL DEFAULT 0,
    cofinance_pct               NUMERIC(6,4) NOT NULL DEFAULT 0,
    default_promo_pct           NUMERIC(5,3) NOT NULL DEFAULT 0
);
COMMENT ON TABLE mp.tariff_rule_ym IS
    'Подтип Яндекс.Маркета: last-mile с cap, эквайринг, упаковка FBY, '
    'хранение, со-финансирование Премиум, средняя реклама/бусты.';

CREATE TABLE IF NOT EXISTS mp.tariff_rule_ozon_logistics_tier (
    tariff_rule_id      BIGINT NOT NULL
        REFERENCES mp.tariff_rule_ozon ON DELETE CASCADE,
    volume_max_l        NUMERIC(8,3) NOT NULL,
    base_rub            NUMERIC(8,2) NOT NULL,
    per_liter_above_rub NUMERIC(8,2) NOT NULL DEFAULT 0,
    PRIMARY KEY (tariff_rule_id, volume_max_l)
);
COMMENT ON TABLE mp.tariff_rule_ozon_logistics_tier IS
    'Ступени логистики Ozon: до какого объёма (литров) действует базовая '
    'ставка, и сколько начисляется за каждый литр сверху.';

CREATE TABLE IF NOT EXISTS mp.tariff_rule_ym_logistics_tier (
    tariff_rule_id  BIGINT NOT NULL
        REFERENCES mp.tariff_rule_ym ON DELETE CASCADE,
    volume_max_l    NUMERIC(8,3) NOT NULL,
    base_rub        NUMERIC(8,2) NOT NULL,
    PRIMARY KEY (tariff_rule_id, volume_max_l)
);
COMMENT ON TABLE mp.tariff_rule_ym_logistics_tier IS
    'Ступени логистики Яндекс.Маркета.';

CREATE TABLE IF NOT EXISTS mp.wb_warehouse_daily (
    obs_date        DATE NOT NULL,
    warehouse_code  VARCHAR(64) NOT NULL,
    coef            NUMERIC(6,3) NOT NULL,
    PRIMARY KEY (obs_date, warehouse_code)
);
COMMENT ON TABLE mp.wb_warehouse_daily IS
    'Дневные значения коэффициента склада-источника WB. Заполняется '
    'опционально (через скрипт сбора с API WB). Пока пуста — используется '
    'warehouse_coef_default из tariff_rule_wb.';

CREATE TABLE IF NOT EXISTS mp.cost_events (
    event_id        BIGSERIAL PRIMARY KEY,
    marketplace_id  INT NOT NULL REFERENCES mp.marketplaces,
    product_id      INT REFERENCES mp.products,
    event_date      DATE NOT NULL,
    event_type      VARCHAR(32) NOT NULL,
    amount_rub      NUMERIC(12,2) NOT NULL,
    description     TEXT,
    source_csv      VARCHAR(64),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (event_type IN ('paid_supply','penalty','utilization','marking','other'))
);
COMMENT ON TABLE mp.cost_events IS
    'Событийные расходы: платная приёмка, штрафы, утилизация и т.п. '
    'Эти расходы НЕ являются тарифом, они происходят по факту — поэтому '
    'хранятся отдельно от tariff_rule. Источник — CSV-отчёты ЛК продавца.';

ALTER TABLE mp.products
    ADD COLUMN IF NOT EXISTS canonical_category_id INT
        REFERENCES mp.canonical_categories;

ALTER TABLE mp.products
    ADD COLUMN IF NOT EXISTS expected_promo_pct NUMERIC(5,3);
COMMENT ON COLUMN mp.products.expected_promo_pct IS
    'Переопределение default_promo_pct из тарифа: фактическая доля затрат '
    'на рекламу/продвижение для конкретного товара продавца.';

ALTER TABLE mp.products
    ADD COLUMN IF NOT EXISTS expected_buyout_rate NUMERIC(5,3);
COMMENT ON COLUMN mp.products.expected_buyout_rate IS
    'Переопределение default_buyout_rate (фактический процент выкупа).';

ALTER TABLE mp.products
    ADD COLUMN IF NOT EXISTS expected_return_rate NUMERIC(5,3);
COMMENT ON COLUMN mp.products.expected_return_rate IS
    'Переопределение default_return_rate (фактический процент возвратов).';

COMMIT;

SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'mp'
ORDER BY table_name;
BEGIN;
SET search_path TO mp, public;

DROP TABLE IF EXISTS mp.tariff_rule_ozon_logistics_tier;
DROP TABLE IF EXISTS mp.tariff_rule_ym_logistics_tier;

CREATE TABLE IF NOT EXISTS mp.wb_logistics (
    marketplace_id INT NOT NULL REFERENCES mp.marketplaces,
    scheme         VARCHAR(16) NOT NULL,
    base_rub       NUMERIC(8,2) NOT NULL,
    per_liter_rub  NUMERIC(8,2) NOT NULL,
    valid_from     DATE NOT NULL,
    valid_to       DATE,
    source_url     TEXT,
    PRIMARY KEY (marketplace_id, scheme, valid_from)
);
COMMENT ON TABLE mp.wb_logistics IS 'Базовый тариф WB: ставка за 1-й литр + за каждый дополнительный. Категория влияет через КТР в tariff_rule_wb.';

CREATE TABLE IF NOT EXISTS mp.ozon_logistics_tier (
    marketplace_id      INT NOT NULL REFERENCES mp.marketplaces,
    scheme              VARCHAR(16) NOT NULL,
    volume_max_l        NUMERIC(8,3) NOT NULL,
    base_rub            NUMERIC(8,2) NOT NULL,
    per_liter_above_rub NUMERIC(8,2) NOT NULL DEFAULT 0,
    valid_from          DATE NOT NULL,
    valid_to            DATE,
    source_url          TEXT,
    PRIMARY KEY (marketplace_id, scheme, volume_max_l, valid_from)
);
COMMENT ON TABLE mp.ozon_logistics_tier IS 'Ступенчатая логистика Ozon: на каждый объёмный диапазон своя ставка.';

CREATE TABLE IF NOT EXISTS mp.ym_logistics_tier (
    marketplace_id INT NOT NULL REFERENCES mp.marketplaces,
    scheme         VARCHAR(16) NOT NULL,
    volume_max_l   NUMERIC(8,3) NOT NULL,
    base_rub       NUMERIC(8,2) NOT NULL,
    valid_from     DATE NOT NULL,
    valid_to       DATE,
    source_url     TEXT,
    PRIMARY KEY (marketplace_id, scheme, volume_max_l, valid_from)
);
COMMENT ON TABLE mp.ym_logistics_tier IS 'Ступенчатая логистика Яндекс.Маркета.';

ALTER TABLE mp.tariff_rule_wb DROP COLUMN IF EXISTS logistics_base_rub;
ALTER TABLE mp.tariff_rule_wb DROP COLUMN IF EXISTS logistics_per_liter_rub;

COMMIT;
BEGIN;
SET search_path TO mp, public;

ALTER TABLE mp.products ALTER COLUMN category_id DROP NOT NULL;

COMMIT;
CREATE TABLE IF NOT EXISTS mp.users (
    user_id        SERIAL PRIMARY KEY,
    email          VARCHAR(128) UNIQUE NOT NULL,
    password_hash  VARCHAR(255) NOT NULL,
    display_name   VARCHAR(128),
    is_admin       BOOLEAN NOT NULL DEFAULT FALSE,
    is_demo        BOOLEAN NOT NULL DEFAULT FALSE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO mp.users (email, password_hash, display_name, is_demo)
VALUES (
    'demo@mail.ru',
    '$2b$12$placeholder_will_be_replaced_in_bootstrap',
    NULL,
    TRUE
) ON CONFLICT (email) DO NOTHING;

ALTER TABLE mp.products
    ADD COLUMN IF NOT EXISTS user_id INT
    REFERENCES mp.users(user_id) ON DELETE CASCADE;

UPDATE mp.products
   SET user_id = (SELECT user_id FROM mp.users WHERE is_demo = TRUE LIMIT 1)
 WHERE user_id IS NULL;

ALTER TABLE mp.products ALTER COLUMN user_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS idx_products_user ON mp.products(user_id);
BEGIN;
SET search_path TO mp, public;

ALTER TABLE mp.products DROP CONSTRAINT IF EXISTS products_sku_key;
ALTER TABLE mp.products DROP CONSTRAINT IF EXISTS products_sku_user_key;
ALTER TABLE mp.products
    ADD CONSTRAINT products_sku_user_key UNIQUE (sku, user_id);

COMMIT;
BEGIN;
SET search_path TO mp, public;

ALTER TABLE mp.product_overrides
    ADD COLUMN IF NOT EXISTS marketplace_id INT REFERENCES mp.marketplaces;

UPDATE mp.product_overrides po
   SET marketplace_id = m.marketplace_id
  FROM mp.marketplaces m
 WHERE po.marketplace_id IS NULL
   AND m.code = 'wb';

ALTER TABLE mp.product_overrides
    ALTER COLUMN marketplace_id SET NOT NULL;

ALTER TABLE mp.product_overrides
    DROP CONSTRAINT IF EXISTS product_overrides_pkey;

ALTER TABLE mp.product_overrides
    ADD CONSTRAINT product_overrides_pkey PRIMARY KEY (product_id, marketplace_id);

COMMIT;
BEGIN;
SET search_path TO mp, public;

ALTER TABLE mp.product_overrides
    ADD COLUMN IF NOT EXISTS packaging_fee_rub NUMERIC(8,2),
    ADD COLUMN IF NOT EXISTS cofinance_pct NUMERIC(6,4);

COMMIT;
