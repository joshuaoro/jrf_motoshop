-- =============================================================================
-- JRF Motorcycle Shop System - PostgreSQL helper functions + RLS off (idempotent)
-- -----------------------------------------------------------------------------
-- Safe to run repeatedly on an existing Supabase schema. It does NOT drop any
-- tables. Creates/replaces the scalar functions used by the report endpoints and
-- re-ensures Row Level Security is disabled on all app tables.
-- Use the Supabase SQL Editor, or run:  python setup_database_objects.py
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

ALTER TABLE staff            DISABLE ROW LEVEL SECURITY;
ALTER TABLE settings         DISABLE ROW LEVEL SECURITY;
ALTER TABLE notifications    DISABLE ROW LEVEL SECURITY;
ALTER TABLE parts            DISABLE ROW LEVEL SECURITY;
ALTER TABLE suppliers        DISABLE ROW LEVEL SECURITY;
ALTER TABLE supplier_part    DISABLE ROW LEVEL SECURITY;
ALTER TABLE stock_entries    DISABLE ROW LEVEL SECURITY;
ALTER TABLE customers        DISABLE ROW LEVEL SECURITY;
ALTER TABLE sales            DISABLE ROW LEVEL SECURITY;
ALTER TABLE sale_details     DISABLE ROW LEVEL SECURITY;
ALTER TABLE backup_logs      DISABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs       DISABLE ROW LEVEL SECURITY;
ALTER TABLE system_logs      DISABLE ROW LEVEL SECURITY;
ALTER TABLE purchase_orders       DISABLE ROW LEVEL SECURITY;
ALTER TABLE purchase_order_items  DISABLE ROW LEVEL SECURITY;
ALTER TABLE expenses         DISABLE ROW LEVEL SECURITY;
ALTER TABLE maintenance_logs DISABLE ROW LEVEL SECURITY;