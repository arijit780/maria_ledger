-- Maria-Ledger: Schema with Hash-Chained Ledger (collation-fixed)
-- --------------------------------------------------------
-- This script is designed to be idempotent and safe for re-application.
-- It enforces a consistent utf8mb4_general_ci collation and keeps the
-- safe chain-append procedure and triggers.

-- Drop tables in reverse order of dependency to ensure a clean slate.
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS ledger_roots;
DROP TABLE IF EXISTS ledger;

-- ----------------------------------------------------------------------------
-- 0. Optional: ensure database default charset/collation (uncomment if desired)
-- ----------------------------------------------------------------------------
-- ALTER DATABASE `ledger_demo` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;

-- ----------------------------------------------------------------------------
-- 1. Universal Ledger Table (with chain)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ledger (
    tx_order BIGINT AUTO_INCREMENT PRIMARY KEY,
    tx_id VARCHAR(36) NOT NULL,
    table_name VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
    record_id VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
    op_type ENUM('INSERT','UPDATE','DELETE') NOT NULL,
    old_payload JSON,
    new_payload JSON,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),

    -- Chain protection columns
    prev_hash CHAR(64) NULL,
    chain_hash CHAR(64) NULL,

    UNIQUE KEY uq_tx_id (tx_id),
    INDEX idx_ledger_lookup (table_name, record_id, tx_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ----------------------------------------------------------------------------
-- 2. Merkle Root Checkpoints
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ledger_roots (
    id INT AUTO_INCREMENT PRIMARY KEY,
    table_name VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
    root_hash VARCHAR(64) NOT NULL,
    computed_at TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP(6),
    signer VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci,
    signature TEXT,
    pubkey_fingerprint VARCHAR(64),
    INDEX idx_roots_lookup (table_name, computed_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ----------------------------------------------------------------------------
-- 3. Live Data Table: customers (explicit collation on text columns)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS customers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
    email VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- ----------------------------------------------------------------------------
-- 4. Trigger Utility: Safe Chain Append
-- ----------------------------------------------------------------------------
DROP PROCEDURE IF EXISTS append_ledger_entry;
DELIMITER $$

CREATE PROCEDURE append_ledger_entry (
    IN p_table_name VARCHAR(255),
    IN p_record_id VARCHAR(255),
    IN p_op_type VARCHAR(10),
    IN p_old_payload JSON,
    IN p_new_payload JSON
)
BEGIN
    DECLARE v_prev_hash CHAR(64);
    DECLARE v_chain_hash CHAR(64);
    DECLARE v_tx_id VARCHAR(36);
    DECLARE v_created_at TIMESTAMP(6);

    -- Lock the last row for this table to prevent concurrent reads/writes.
    -- This serializes ledger inserts for a given table, ensuring chain integrity.
    SELECT chain_hash INTO v_prev_hash
    FROM ledger
    WHERE table_name = p_table_name
    ORDER BY tx_order DESC
    LIMIT 1
    FOR UPDATE;

    -- Use a conventional 'genesis' hash for the first entry.
    SET v_prev_hash = COALESCE(v_prev_hash, '0000000000000000000000000000000000000000000000000000000000000000');

    -- Generate UUID and timestamp ONCE and store in variables.
    SET v_tx_id = UUID();
    SET v_created_at = NOW(6);

    -- Compute the chain_hash for the new row. This must be perfectly reproducible.
    -- Use COALESCE with literal 'NULL' to distinguish from empty strings.
    SET v_chain_hash = SHA2(CONCAT_WS('|',
        v_prev_hash,
        v_tx_id,
        p_record_id,
        p_op_type,
        COALESCE(JSON_UNQUOTE(JSON_EXTRACT(p_old_payload, '$')), 'NULL'),
        COALESCE(JSON_UNQUOTE(JSON_EXTRACT(p_new_payload, '$')), 'NULL'),
        DATE_FORMAT(v_created_at, '%Y-%m-%d %H:%i:%s.%f')
    ), 256);

    -- Use the variables to ensure the inserted data matches what was hashed.
    INSERT INTO ledger (tx_id, table_name, record_id, op_type, old_payload, new_payload, created_at, prev_hash, chain_hash)
    VALUES (v_tx_id, p_table_name, p_record_id, p_op_type, p_old_payload, p_new_payload, v_created_at, v_prev_hash, v_chain_hash);
END$$

-- ----------------------------------------------------------------------------
-- 5. Triggers to Record Events (force-collation on string values)
-- ----------------------------------------------------------------------------

DROP TRIGGER IF EXISTS customers_after_insert$$
CREATE TRIGGER customers_after_insert
AFTER INSERT ON customers
FOR EACH ROW
BEGIN
    CALL append_ledger_entry(
        'customers',
        CAST(NEW.id AS CHAR),
        'INSERT',
        NULL,
        JSON_OBJECT(
            'name', CONVERT(NEW.name USING utf8mb4) COLLATE utf8mb4_general_ci,
            'email', CONVERT(NEW.email USING utf8mb4) COLLATE utf8mb4_general_ci
        )
    );
END$$

DROP TRIGGER IF EXISTS customers_after_update$$
CREATE TRIGGER customers_after_update
AFTER UPDATE ON customers
FOR EACH ROW
BEGIN
    CALL append_ledger_entry(
        'customers',
        CAST(NEW.id AS CHAR),
        'UPDATE',
        JSON_OBJECT(
            'name', CONVERT(OLD.name USING utf8mb4) COLLATE utf8mb4_general_ci,
            'email', CONVERT(OLD.email USING utf8mb4) COLLATE utf8mb4_general_ci
        ),
        JSON_OBJECT(
            'name', CONVERT(NEW.name USING utf8mb4) COLLATE utf8mb4_general_ci,
            'email', CONVERT(NEW.email USING utf8mb4) COLLATE utf8mb4_general_ci
        )
    );
END$$

DROP TRIGGER IF EXISTS customers_after_delete$$
CREATE TRIGGER customers_after_delete
AFTER DELETE ON customers
FOR EACH ROW
BEGIN
    CALL append_ledger_entry(
        'customers',
        CAST(OLD.id AS CHAR),
        'DELETE',
        JSON_OBJECT(
            'name', CONVERT(OLD.name USING utf8mb4) COLLATE utf8mb4_general_ci,
            'email', CONVERT(OLD.email USING utf8mb4) COLLATE utf8mb4_general_ci
        ),
        NULL
    );
END$$

DELIMITER ;
