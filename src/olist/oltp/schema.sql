-- ==============================================
-- 1. DROP — safe re-runs: children first (FK order)
-- ==============================================

DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS order_payments;
DROP TABLE IF EXISTS reviews;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS sellers;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS geolocation;
DROP TABLE IF EXISTS product_category_name_translation;


-- ==============================================
-- 2. CREATE — parents first (FK order)
-- ==============================================

CREATE TABLE customers (
    customer_id TEXT PRIMARY KEY,
    customer_unique_id TEXT NOT NULL,
    customer_zip_code_prefix INTEGER NOT NULL,
    customer_city TEXT NOT NULL,
    customer_state CHAR(2) NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE sellers (
    seller_id TEXT PRIMARY KEY,
    seller_zip_code_prefix INTEGER NOT NULL,
    seller_city TEXT NOT NULL,
    seller_state CHAR(2) NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE products (
    product_id TEXT PRIMARY KEY, 
    product_category_name TEXT, 
    product_name_lenght INTEGER, 
    product_description_lenght INTEGER, 
    product_photos_qty INTEGER, 
    product_weight_g INTEGER, 
    product_length_cm INTEGER, 
    product_height_cm INTEGER, 
    product_width_cm INTEGER, 
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE geolocation (
    geolocation_id BIGSERIAL PRIMARY KEY, 
    geolocation_zip_code_prefix INTEGER NOT NULL, 
    geolocation_lat DOUBLE PRECISION NOT NULL, 
    geolocation_lng DOUBLE PRECISION NOT NULL, 
    geolocation_city TEXT NOT NULL, 
    geolocation_state CHAR(2) NOT NULL, 
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE product_category_name_translation (
    product_category_name TEXT PRIMARY KEY, 
    product_category_name_english TEXT NOT NULL, 
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE orders (
    order_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    order_status VARCHAR(20) NOT NULL,
    order_purchase_timestamp TIMESTAMP NOT NULL,
    order_approved_at TIMESTAMP,
    order_delivered_carrier_date TIMESTAMP,
    order_delivered_customer_date TIMESTAMP,
    order_estimated_delivery_date TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE order_items (
    order_id TEXT REFERENCES orders(order_id),
    order_item_id INTEGER,
    product_id TEXT REFERENCES products(product_id),
    seller_id TEXT REFERENCES sellers(seller_id),
    shipping_limit_date TIMESTAMP NOT NULL,
    price NUMERIC(10,2) NOT NULL,
    freight_value NUMERIC(10,2) NOT NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (order_id, order_item_id)
);

CREATE TABLE order_payments (
    order_id TEXT REFERENCES orders(order_id), 
    payment_sequential INTEGER, 
    payment_type VARCHAR(20) NOT NULL, 
    payment_installments INTEGER NOT NULL, 
    payment_value NUMERIC(10,2) NOT NULL, 
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(), 
    PRIMARY KEY (order_id, payment_sequential)
);

CREATE TABLE reviews (
    review_id TEXT,
    order_id TEXT REFERENCES orders(order_id), 
    review_score SMALLINT CHECK (review_score BETWEEN 1 AND 5), 
    review_comment_title TEXT, 
    review_comment_message TEXT, 
    review_creation_date TIMESTAMP, 
    review_answer_timestamp TIMESTAMP, 
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (review_id, order_id)
);


-- ==============================================
-- 3. TRIGGER FUNCTION — stamps updated_at on every UPDATE
-- ==============================================

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ==============================================
-- 4. TRIGGERS — one per table, wires function to each UPDATE
-- ==============================================

CREATE TRIGGER customers_set_updated_at
BEFORE UPDATE ON customers
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER sellers_set_updated_at
BEFORE UPDATE ON sellers
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER products_set_updated_at
BEFORE UPDATE ON products
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER geolocation_set_updated_at
BEFORE UPDATE ON geolocation
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER product_category_name_translation_set_updated_at
BEFORE UPDATE ON product_category_name_translation
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER orders_set_updated_at
BEFORE UPDATE ON orders
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER order_items_set_updated_at
BEFORE UPDATE ON order_items
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER order_payments_set_updated_at
BEFORE UPDATE ON order_payments
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER reviews_set_updated_at
BEFORE UPDATE ON reviews
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

