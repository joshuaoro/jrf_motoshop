-- =====================================================
-- Database Objects for JRF Motorcycle Shop System
-- =====================================================
-- This file contains:
-- 1. Stored Procedures
-- 2. Functions
-- 3. Triggers
-- =====================================================

-- =====================================================
-- 1. STORED PROCEDURES
-- =====================================================

-- Stored Procedure: Get Low Stock Parts
-- Returns all parts with stock quantity below a specified threshold
DELIMITER //
DROP PROCEDURE IF EXISTS GetLowStockParts //
CREATE PROCEDURE GetLowStockParts(IN threshold INT)
BEGIN
    SELECT 
        id,
        name,
        part_type,
        brand,
        price,
        stock_quantity,
        description
    FROM parts
    WHERE stock_quantity < threshold
    ORDER BY stock_quantity ASC, name ASC;
END //
DELIMITER ;

-- Stored Procedure: Calculate Monthly Sales
-- Calculates total sales for a specific month and year
DELIMITER //
DROP PROCEDURE IF EXISTS CalculateMonthlySales //
CREATE PROCEDURE CalculateMonthlySales(
    IN p_year INT,
    IN p_month INT,
    OUT total_sales DECIMAL(10, 2),
    OUT total_count INT
)
BEGIN
    SELECT 
        COALESCE(SUM(total_amount), 0),
        COUNT(*)
    INTO total_sales, total_count
    FROM sales
    WHERE YEAR(sale_date) = p_year
    AND MONTH(sale_date) = p_month;
END //
DELIMITER ;

-- Stored Procedure: Get Sales Report by Staff
-- Returns sales statistics grouped by staff member for a date range
DELIMITER //
DROP PROCEDURE IF EXISTS GetSalesReportByStaff //
CREATE PROCEDURE GetSalesReportByStaff(
    IN start_date DATE,
    IN end_date DATE
)
BEGIN
    SELECT 
        s.id AS staff_id,
        s.name AS staff_name,
        s.role,
        COUNT(sa.id) AS total_sales_count,
        COALESCE(SUM(sa.total_amount), 0) AS total_sales_amount,
        COALESCE(AVG(sa.total_amount), 0) AS average_sale_amount
    FROM staff s
    LEFT JOIN sales sa ON s.id = sa.staff_id
        AND DATE(sa.sale_date) BETWEEN start_date AND end_date
    GROUP BY s.id, s.name, s.role
    ORDER BY total_sales_amount DESC;
END //
DELIMITER ;

-- =====================================================
-- 2. FUNCTIONS
-- =====================================================

-- Function: Calculate Discount
-- Calculates discount amount based on price and discount percentage
DELIMITER //
DROP FUNCTION IF EXISTS CalculateDiscount //
CREATE FUNCTION CalculateDiscount(
    price DECIMAL(10, 2),
    discount_percent DECIMAL(5, 2)
) RETURNS DECIMAL(10, 2)
DETERMINISTIC
READS SQL DATA
BEGIN
    DECLARE discount_amount DECIMAL(10, 2);
    
    IF discount_percent < 0 THEN
        SET discount_percent = 0;
    ELSEIF discount_percent > 100 THEN
        SET discount_percent = 100;
    END IF;
    
    SET discount_amount = price * (discount_percent / 100);
    RETURN discount_amount;
END //
DELIMITER ;

-- Function: Get Stock Status
-- Returns stock status based on quantity (Low, Medium, High)
DELIMITER //
DROP FUNCTION IF EXISTS GetStockStatus //
CREATE FUNCTION GetStockStatus(
    stock_quantity INT
) RETURNS VARCHAR(10)
DETERMINISTIC
READS SQL DATA
BEGIN
    DECLARE status VARCHAR(10);
    
    IF stock_quantity = 0 THEN
        SET status = 'Out';
    ELSEIF stock_quantity < 5 THEN
        SET status = 'Low';
    ELSEIF stock_quantity < 20 THEN
        SET status = 'Medium';
    ELSE
        SET status = 'High';
    END IF;
    
    RETURN status;
END //
DELIMITER ;

-- Function: Format Currency
-- Formats a number as currency with PHP symbol
DELIMITER //
DROP FUNCTION IF EXISTS FormatCurrency //
CREATE FUNCTION FormatCurrency(
    amount DECIMAL(10, 2)
) RETURNS VARCHAR(20)
DETERMINISTIC
READS SQL DATA
BEGIN
    RETURN CONCAT('₱', FORMAT(amount, 2));
END //
DELIMITER ;

-- =====================================================
-- 3. TRIGGERS
-- =====================================================

-- Trigger: Update Stock After Sale Detail Insert
-- Automatically updates part stock when a sale detail is inserted
DELIMITER //
DROP TRIGGER IF EXISTS trg_update_stock_after_sale //
CREATE TRIGGER trg_update_stock_after_sale
AFTER INSERT ON sale_details
FOR EACH ROW
BEGIN
    UPDATE parts
    SET stock_quantity = stock_quantity - NEW.quantity
    WHERE id = NEW.part_id;
    
    -- Prevent negative stock
    UPDATE parts
    SET stock_quantity = 0
    WHERE id = NEW.part_id AND stock_quantity < 0;
END //
DELIMITER ;

-- Trigger: Log Stock Entry
-- Automatically creates a stock entry record when stock is updated
DELIMITER //
DROP TRIGGER IF EXISTS trg_log_stock_entry //
CREATE TRIGGER trg_log_stock_entry
AFTER UPDATE ON parts
FOR EACH ROW
BEGIN
    -- Only log if stock quantity changed
    IF OLD.stock_quantity != NEW.stock_quantity THEN
        INSERT INTO stock_entries (part_id, quantity, entry_date)
        VALUES (
            NEW.id,
            NEW.stock_quantity - OLD.stock_quantity,
            NOW()
        );
    END IF;
END //
DELIMITER ;

-- Trigger: Prevent Negative Stock on Update
-- Ensures stock quantity never goes below zero
DELIMITER //
DROP TRIGGER IF EXISTS trg_prevent_negative_stock //
CREATE TRIGGER trg_prevent_negative_stock
BEFORE UPDATE ON parts
FOR EACH ROW
BEGIN
    IF NEW.stock_quantity < 0 THEN
        SET NEW.stock_quantity = 0;
    END IF;
END //
DELIMITER ;

-- =====================================================
-- Verification Queries (Optional - for testing)
-- =====================================================

-- Test stored procedure
-- CALL GetLowStockParts(5);

-- Test function
-- SELECT CalculateDiscount(1000.00, 10.00) AS discount_amount;
-- SELECT GetStockStatus(3) AS stock_status;
-- SELECT FormatCurrency(1234.56) AS formatted_price;

-- Test trigger (will fire automatically on INSERT/UPDATE)
-- INSERT INTO sale_details (sale_id, part_id, quantity, price_at_sale) VALUES (1, 1, 2, 100.00);

