-- ============================================
-- Reset environment
-- ============================================
SET FOREIGN_KEY_CHECKS=0;

-- Initialize hash chain session variables
SET @last_customer_hash = NULL;
SET @last_order_hash = NULL;

-- First drop triggers if they exist
DROP TRIGGER IF EXISTS trg_orders_hash_update;
DROP TRIGGER IF EXISTS trg_orders_hash_insert;
DROP TRIGGER IF EXISTS trg_customers_hash_update;
DROP TRIGGER IF EXISTS trg_customers_hash_insert;

-- Then drop tables
DROP TABLE IF EXISTS ledger_orders;
DROP TABLE IF EXISTS ledger_customers;
DROP TABLE IF EXISTS ledger_roots;

SET FOREIGN_KEY_CHECKS=1;

-- ============================================
-- Tamper-evident ledger_customers table
-- ============================================
CREATE TABLE ledger_customers (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    name            VARCHAR(255),
    email           VARCHAR(255),
    valid_from      TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP(6),
    valid_to        TIMESTAMP(6) NULL,
    row_hash        CHAR(64),
    prev_hash       CHAR(64)
) WITH SYSTEM VERSIONING;

-- ============================================
-- Trigger: hash chaining on INSERT
-- ============================================
DELIMITER //

-- Initialize session variable if not exists
SET @last_customer_hash = NULL;

CREATE TRIGGER trg_customers_hash_insert
BEFORE INSERT ON ledger_customers
FOR EACH ROW
BEGIN
    DECLARE last_hash CHAR(64);
    DECLARE last_id BIGINT;
    
    -- -- Start a read-only transaction for consistency
    -- START TRANSACTION READ ONLY;
    
    -- Get the last ID with a lock
    SELECT MAX(id) INTO last_id 
    FROM ledger_customers 
    FOR UPDATE;
    
    IF last_id IS NULL THEN
        -- First row
        SET NEW.prev_hash = REPEAT('0', 64);
    ELSE
        -- Get the hash of the last row with a lock
        SELECT row_hash INTO last_hash
        FROM ledger_customers 
        WHERE id = last_id
        FOR UPDATE;
        
        SET NEW.prev_hash = IFNULL(last_hash, REPEAT('0',64));
    END IF;
    
    -- COMMIT;
    
    -- Calculate new row hash
    SET NEW.row_hash = LOWER(SHA2(CONCAT(
        NEW.name, NEW.email, NEW.valid_from, NEW.prev_hash
    ), 256));
END;
//

-- ============================================
-- Trigger: hash chaining on UPDATE
-- ============================================
CREATE TRIGGER trg_customers_hash_update
BEFORE UPDATE ON ledger_customers
FOR EACH ROW
BEGIN
    SET NEW.prev_hash = OLD.row_hash;
    SET NEW.row_hash = LOWER(SHA2(CONCAT(
        NEW.name, NEW.email, NEW.valid_from, NEW.prev_hash
    ), 256));
END;
//
DELIMITER ;

-- ============================================
-- Tamper-evident ledger_orders table
-- ============================================
CREATE TABLE ledger_orders (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    customer_id     BIGINT,
    amount          DECIMAL(10,2),
    status          VARCHAR(50),
    valid_from      TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP(6),
    valid_to        TIMESTAMP(6) NULL,
    row_hash        CHAR(64),
    prev_hash       CHAR(64),
    FOREIGN KEY (customer_id) REFERENCES ledger_customers(id)
) WITH SYSTEM VERSIONING;

-- ============================================
-- Trigger: hash chaining on INSERT for orders
-- ============================================
DELIMITER //

-- Initialize session variable if not exists
SET @last_order_hash = NULL;

CREATE TRIGGER trg_orders_hash_insert
BEFORE INSERT ON ledger_orders
FOR EACH ROW
BEGIN
    DECLARE last_hash CHAR(64);
    DECLARE last_id BIGINT;
    
    -- Get the last ID with a lock
    SELECT IFNULL(MAX(id), 0) INTO last_id 
    FROM ledger_orders LOCK IN SHARE MODE;
    
    IF last_id = 0 THEN
        -- First row
        SET NEW.prev_hash = REPEAT('0', 64);
    ELSE
        -- Get the hash of the last row with a lock
        SELECT row_hash INTO last_hash
        FROM ledger_orders 
        WHERE id = last_id
        LOCK IN SHARE MODE;
        
        SET NEW.prev_hash = IFNULL(last_hash, REPEAT('0',64));
    END IF;
    
    -- Calculate new row hash
    SET NEW.row_hash = LOWER(SHA2(CONCAT(
        NEW.customer_id, NEW.amount, NEW.status, NEW.valid_from, NEW.prev_hash
    ), 256));
END;
//

-- ============================================
-- Trigger: hash chaining on UPDATE for orders
-- ============================================
CREATE TRIGGER trg_orders_hash_update
BEFORE UPDATE ON ledger_orders
FOR EACH ROW
BEGIN
    SET NEW.prev_hash = OLD.row_hash;
    SET NEW.row_hash = LOWER(SHA2(CONCAT(
        NEW.customer_id, NEW.amount, NEW.status, NEW.valid_from, NEW.prev_hash
    ), 256));
END;
//

DELIMITER ;

-- ============================================
-- Ledger roots table (Merkle root storage)
-- ============================================
CREATE TABLE ledger_roots (
    table_name VARCHAR(255),
    root_hash CHAR(64),
    reference_root CHAR(64) NULL,
    reference_table VARCHAR(255) NULL,
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(6),
    signature TEXT,
    signer VARCHAR(255),
    pubkey_fingerprint CHAR(64),
    PRIMARY KEY(table_name, computed_at),
    CONSTRAINT chk_reference_integrity CHECK (
        (reference_root IS NULL AND reference_table IS NULL) OR 
        (reference_root IS NOT NULL AND reference_table IS NOT NULL)
    )
);
