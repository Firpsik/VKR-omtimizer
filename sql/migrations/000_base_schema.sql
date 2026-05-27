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
