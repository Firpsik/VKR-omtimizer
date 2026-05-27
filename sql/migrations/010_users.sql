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
    'demo@asop.local',
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
