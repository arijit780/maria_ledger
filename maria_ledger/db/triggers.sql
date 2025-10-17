-- ============================================
-- Reset environment
-- ============================================
DROP TABLE IF EXISTS ledger_roots;
DROP TABLE IF EXISTS ledger_customers;

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

CREATE TRIGGER trg_customers_hash_insert
BEFORE INSERT ON ledger_customers
FOR EACH ROW
BEGIN
    DECLARE last_hash CHAR(64);
    SELECT row_hash INTO last_hash
    FROM ledger_customers
    ORDER BY valid_from DESC
    LIMIT 1;

    SET NEW.prev_hash = IFNULL(last_hash, REPEAT('0',64));
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
-- Ledger roots table (Merkle root storage)
-- ============================================
CREATE TABLE ledger_roots (
    table_name VARCHAR(255),
    root_hash CHAR(64),
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(6),
    signature TEXT,
    signer VARCHAR(255),
    pubkey_fingerprint CHAR(64),
    PRIMARY KEY(table_name, computed_at)
);
