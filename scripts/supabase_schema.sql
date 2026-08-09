-- =============================================================================
-- JRF Motorcycle Shop System - PostgreSQL (Supabase) Schema
-- -----------------------------------------------------------------------------
-- Paste this entire file into the Supabase SQL Editor and click RUN.
--
-- This mirrors the SQLAlchemy models in app.py and creates:
--   1. All application tables (staff, parts, suppliers, sales, settings, etc.)
--   2. Helper scalar functions used by /api/low-stock-parts, /api/calculate-discount
--   3. Row Level Security (RLS) DISABLED on every table so your LOCAL Flask app
--      (which connects with the strong `postgres` role) can read/write freely.
--
-- NOTE: Because you connect with the `postgres` role via the direct connection
-- string, RLS is bypassed anyway. DISABLING RLS below is done defensively so the
-- tables are also writable if you ever point the Supabase JS client / anon role at them.
-- =============================================================================

-- Drop existing tables first (clean slate - drops data too). Remove this block
-- if you are running on an existing schema you want to keep.
DROP TABLE IF EXISTS maintenance_logs, expenses, purchase_order_items, purchase_orders,
    customers, system_logs, audit_logs, backup_logs, supplier_part, sale_details,
    sales, stock_entries, suppliers, parts, notifications, settings, staff CASCADE;

-- =============================================================================
-- STAFF (users) table -- the staff table is referenced by many tables so create first
-- =============================================================================
CREATE TABLE IF NOT EXISTS staff (
    id            SERIAL PRIMARY KEY,
    name          VARCHAR(100) NOT NULL,
    role          VARCHAR(50)  NOT NULL,
    contact_no    VARCHAR(20),
    email         VARCHAR(100) UNIQUE NOT NULL,
    username      VARCHAR(80)  UNIQUE NOT NULL,
    password_hash VARCHAR(128)
);

-- =============================================================================
-- SETTINGS
-- =============================================================================
CREATE TABLE IF NOT EXISTS settings (
    id            SERIAL PRIMARY KEY,
    category      VARCHAR(50)  NOT NULL,
    setting_key   VARCHAR(100) NOT NULL,
    setting_value TEXT,
    setting_type  VARCHAR(20)  DEFAULT 'string',
    description   TEXT,
    updated_at    TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_by    INTEGER      REFERENCES staff(id),
    CONSTRAINT uq_settings_category_key UNIQUE (category, setting_key)
);

-- =============================================================================
-- NOTIFICATIONS
-- =============================================================================
CREATE TABLE IF NOT EXISTS notifications (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER      NOT NULL REFERENCES staff(id) ON DELETE CASCADE,
    title       VARCHAR(200) NOT NULL,
    message     TEXT         NOT NULL,
    type        VARCHAR(50)  DEFAULT 'info',
    category    VARCHAR(50)  DEFAULT 'system',
    is_read     BOOLEAN      DEFAULT FALSE,
    created_at  TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    read_at     TIMESTAMP,
    action_url  VARCHAR(500),
    action_text VARCHAR(100)
);

-- =============================================================================
-- PARTS
-- =============================================================================
CREATE TABLE IF NOT EXISTS parts (
    id             SERIAL PRIMARY KEY,
    name           VARCHAR(100) NOT NULL,
    description    TEXT,
    part_type      VARCHAR(50),
    brand          VARCHAR(50),
    price          DOUBLE PRECISION NOT NULL,
    stock_quantity INTEGER      DEFAULT 0,
    updated_at     TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- SUPPLIERS
-- =============================================================================
CREATE TABLE IF NOT EXISTS suppliers (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    contact_no  VARCHAR(20),
    address     TEXT
);

-- =============================================================================
-- SUPPLIERS-PARTS (many-to-many association table)
-- =============================================================================
CREATE TABLE IF NOT EXISTS supplier_part (
    supplier_id INTEGER NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
    part_id     INTEGER NOT NULL REFERENCES parts(id) ON DELETE CASCADE,
    PRIMARY KEY (supplier_id, part_id)
);

-- =============================================================================
-- STOCK ENTRIES
-- =============================================================================
CREATE TABLE IF NOT EXISTS stock_entries (
    id          SERIAL PRIMARY KEY,
    entry_date  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    quantity    INTEGER   NOT NULL,
    part_id     INTEGER   NOT NULL REFERENCES parts(id) ON DELETE CASCADE
);

-- =============================================================================
-- CUSTOMERS
-- =============================================================================
CREATE TABLE IF NOT EXISTS customers (
    id            SERIAL PRIMARY KEY,
    name          VARCHAR(100) NOT NULL,
    email         VARCHAR(100) UNIQUE,
    phone         VARCHAR(20),
    address       TEXT,
    created_date  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active     BOOLEAN   DEFAULT TRUE
);

-- =============================================================================
-- SALES
-- =============================================================================
CREATE TABLE IF NOT EXISTS sales (
    id              SERIAL PRIMARY KEY,
    sale_date       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    total_amount    DOUBLE PRECISION NOT NULL,
    payment_method  VARCHAR(50)  NOT NULL,
    staff_id        INTEGER      NOT NULL REFERENCES staff(id),
    customer_id     INTEGER      REFERENCES customers(id),
    receipt_number  VARCHAR(50)  UNIQUE,
    notes           TEXT
);

-- =============================================================================
-- SALE DETAILS
-- =============================================================================
CREATE TABLE IF NOT EXISTS sale_details (
    sale_id       INTEGER NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
    part_id       INTEGER NOT NULL REFERENCES parts(id) ON DELETE CASCADE,
    quantity      INTEGER NOT NULL,
    price_at_sale DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (sale_id, part_id)
);

-- NOTE: The schema uses a composite PK (sale_id, part_id) to match the SQLAlchemy
-- model. If the SQLAlchemy model sales detail id expectations differ, adjust here.

-- =============================================================================
-- BACKUP LOGS
-- =============================================================================
CREATE TABLE IF NOT EXISTS backup_logs (
    id              SERIAL PRIMARY KEY,
    backup_date     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    backup_type     VARCHAR(50)  DEFAULT 'manual',
    backup_location VARCHAR(500),
    file_size       BIGINT,
    status          VARCHAR(20)  DEFAULT 'success',
    created_by      INTEGER REFERENCES staff(id)
);

-- =============================================================================
-- AUDIT LOGS
-- =============================================================================
CREATE TABLE IF NOT EXISTS audit_logs (
    id           SERIAL PRIMARY KEY,
    action_date  TIMESTAMP  DEFAULT CURRENT_TIMESTAMP,
    user_id      INTEGER    REFERENCES staff(id),
    action_type  VARCHAR(50)  NOT NULL,
    table_name   VARCHAR(50)  NOT NULL,
    record_id    INTEGER,
    old_values   TEXT,
    new_values   TEXT,
    ip_address   VARCHAR(45),
    user_agent   VARCHAR(500)
);

-- =============================================================================
-- SYSTEM LOGS
-- =============================================================================
CREATE TABLE IF NOT EXISTS system_logs (
    id         SERIAL PRIMARY KEY,
    log_date   TIMESTAMP  DEFAULT CURRENT_TIMESTAMP,
    log_level  VARCHAR(20) DEFAULT 'info',
    category   VARCHAR(50),
    message    TEXT NOT NULL,
    details    TEXT,
    source     VARCHAR(100)
);

-- =============================================================================
-- PURCHASE ORDERS
-- =============================================================================
CREATE TABLE IF NOT EXISTS purchase_orders (
    id            SERIAL PRIMARY KEY,
    order_number  VARCHAR(50) UNIQUE NOT NULL,
    supplier_id   INTEGER   NOT NULL REFERENCES suppliers(id),
    order_date    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expected_date TIMESTAMP,
    status        VARCHAR(50) DEFAULT 'pending',
    total_amount  DOUBLE PRECISION DEFAULT 0.0,
    created_by    INTEGER REFERENCES staff(id)
);

-- =============================================================================
-- PURCHASE ORDER ITEMS
-- =============================================================================
CREATE TABLE IF NOT EXISTS purchase_order_items (
    id                SERIAL PRIMARY KEY,
    purchase_order_id INTEGER NOT NULL REFERENCES purchase_orders(id) ON DELETE CASCADE,
    part_id           INTEGER NOT NULL REFERENCES parts(id),
    quantity          INTEGER   NOT NULL,
    unit_price        DOUBLE PRECISION NOT NULL,
    total_price       DOUBLE PRECISION NOT NULL
);

-- =============================================================================
-- EXPENSES
-- =============================================================================
CREATE TABLE IF NOT EXISTS expenses (
    id             SERIAL PRIMARY KEY,
    expense_date   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    category       VARCHAR(50)  NOT NULL,
    description    TEXT         NOT NULL,
    amount         DOUBLE PRECISION NOT NULL,
    payment_method VARCHAR(50)  NOT NULL,
    receipt_number VARCHAR(100),
    created_by     INTEGER REFERENCES staff(id)
);

-- =============================================================================
-- MAINTENANCE LOGS
-- =============================================================================
CREATE TABLE IF NOT EXISTS maintenance_logs (
    id                SERIAL PRIMARY KEY,
    part_id           INTEGER REFERENCES parts(id),
    maintenance_date  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    maintenance_type  VARCHAR(50)  NOT NULL,
    equipment_name    VARCHAR(100) NOT NULL,
    description       TEXT         NOT NULL,
    cost              DOUBLE PRECISION DEFAULT 0.0,
    performed_by      VARCHAR(100),
    notes             TEXT,
    next_maintenance  TIMESTAMP,
    created_by        INTEGER REFERENCES staff(id)
);

-- =============================================================================
-- HELPER FUNCTIONS (mirror the MySQL functions used by report endpoints)
-- The Flask endpoints call these via SELECT; if they don't exist the endpoints
-- gracefully fall back to plain ORM queries, so they are optional but useful.
-- =============================================================================
CREATE OR REPLACE FUNCTION get_stock_status(p_qty INTEGER)
RETURNS VARCHAR(20)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_qty IS NULL OR p_qty <= 0 THEN
        RETURN 'out_of_stock';
    ELSIF p_qty < 5 THEN
        RETURN 'low_stock';
    ELSIF p_qty <= 10 THEN
        RETURN 'moderate';
    ELSE
        RETURN 'in_stock';
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION format_currency(p_amount DOUBLE PRECISION)
RETURNS VARCHAR(30)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN CONCAT('PHP ', TO_CHAR(COALESCE(p_amount, 0), 'FM999,999,999.00'));
END;
$$;

CREATE OR REPLACE FUNCTION calculate_discount(p_price DOUBLE PRECISION, p_discount_percent DOUBLE PRECISION)
RETURNS DOUBLE PRECISION
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN ROUND((p_price * p_discount_percent / 100.0)::numeric, 2)::double precision;
END;
$$;

-- =============================================================================
-- DISABLE ROW LEVEL SECURITY on all tables (LOCAL DEV ONLY)
-- Keeps the local Flask app (postgres role) and even an anon client unblocked.
-- =============================================================================
ALTER TABLE staff            DISABLE ROW LEVEL SECURITY;
ALTER TABLE settings         DISABLE ROW LEVEL SECURITY;
ALTER TABLE notifications    DISABLE ROW LEVEL SECURITY;
ALTER TABLE parts            DISABLE ROW LEVEL SECURITY;
ALTER TABLE suppliers        DISABLE ROW LEVEL SECURITY;
ALTER TABLE supplier_part   DISABLE ROW LEVEL SECURITY;
ALTER TABLE stock_entries    DISABLE ROW LEVEL SECURITY;
ALTER TABLE customers        DISABLE ROW LEVEL SECURITY;
ALTER TABLE sales            DISABLE ROW LEVEL SECURITY;
ALTER TABLE sale_details     DISABLE ROW LEVEL SECURITY;
ALTER TABLE backup_logs      DISABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs       DISABLE ROW LEVEL SECURITY;
ALTER TABLE system_logs      DISABLE ROW LEVEL SECURITY;
ALTER TABLE purchase_orders      DISABLE ROW LEVEL SECURITY;
ALTER TABLE purchase_order_items DISABLE ROW LEVEL SECURITY;
ALTER TABLE expenses         DISABLE ROW LEVEL SECURITY;
ALTER TABLE maintenance_logs DISABLE ROW LEVEL SECURITY;
