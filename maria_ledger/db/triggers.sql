-- Maria-Ledger Universal Ledger Setup
--
-- This script sets up the database schema for the event-sourcing architecture.
-- It creates a universal `ledger` table to immutably store all changes,
-- a `ledger_roots` table for Merkle checkpoints, and an example `customers`
-- table with triggers that automatically populate the ledger.

-- Drop old tables if they exist to prevent conflicts with the new design.
DROP TABLE IF EXISTS ledger_customers;
DROP TABLE IF EXISTS ledger_roots;
DROP TABLE IF EXISTS ledger;
DROP TABLE IF EXISTS customers;


-- ----------------------------------------------------------------------------
-- 1. The Universal Ledger Table
-- This table is the single source of truth for all changes in the system.
-- It is used by `reconstruct.py` and `verify_state.py`.
-- ----------------------------------------------------------------------------
CREATE TABLE ledger (
    tx_order BIGINT AUTO_INCREMENT PRIMARY KEY,
    tx_id VARCHAR(36) NOT NULL,
    table_name VARCHAR(255) NOT NULL,
    record_id VARCHAR(255) NOT NULL,
    op_type ENUM('INSERT', 'UPDATE', 'DELETE') NOT NULL,
    old_payload JSON,
    new_payload JSON,
    created_at TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP(6),
    INDEX (table_name, record_id, tx_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ----------------------------------------------------------------------------
-- 2. The Merkle Roots Checkpoint Table
-- This table stores the cryptographic checkpoints of your data tables.
-- It is used by `merkle_service.py`.
-- ----------------------------------------------------------------------------
CREATE TABLE ledger_roots (
    id INT AUTO_INCREMENT PRIMARY KEY,
    table_name VARCHAR(255) NOT NULL,
    root_hash VARCHAR(64) NOT NULL,
    computed_at TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP(6),
    reference_root VARCHAR(64),
    reference_table VARCHAR(255),
    signer VARCHAR(255),
    signature TEXT,
    pubkey_fingerprint VARCHAR(64),
    INDEX (table_name, computed_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ----------------------------------------------------------------------------
-- 3. An Example "Live" Table (`customers`)
-- This is a standard table for your application's data.
-- Triggers on this table will automatically write audit events to the `ledger`.
-- ----------------------------------------------------------------------------
CREATE TABLE customers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ----------------------------------------------------------------------------
-- 4. Triggers to Populate the Universal Ledger
-- ----------------------------------------------------------------------------

DELIMITER $$
CREATE TRIGGER customers_after_insert AFTER INSERT ON customers FOR EACH ROW
BEGIN
    -- The payload should contain only the data, not the primary key itself.
    -- The `NEW` object contains the final state of the row after the INSERT.
    INSERT INTO ledger (tx_id, table_name, record_id, op_type, new_payload)
    VALUES (UUID(), 'customers', NEW.id, 'INSERT', JSON_OBJECT('name', NEW.name, 'email', NEW.email, 'created_at', NEW.created_at, 'updated_at', NEW.updated_at));
END$$

CREATE TRIGGER customers_after_update AFTER UPDATE ON customers FOR EACH ROW
BEGIN
    -- The `OLD` object has the state before the update, `NEW` has the state after. This is correct.
    INSERT INTO ledger (tx_id, table_name, record_id, op_type, old_payload, new_payload)
    VALUES (UUID(), 'customers', NEW.id, 'UPDATE', JSON_OBJECT('name', OLD.name, 'email', OLD.email, 'created_at', OLD.created_at, 'updated_at', OLD.updated_at), JSON_OBJECT('name', NEW.name, 'email', NEW.email, 'created_at', NEW.created_at, 'updated_at', NEW.updated_at));
END$$

CREATE TRIGGER customers_after_delete AFTER DELETE ON customers FOR EACH ROW
BEGIN
    INSERT INTO ledger (tx_id, table_name, record_id, op_type, old_payload)
    -- The `OLD` object correctly represents the state of the row just before it was deleted.
    VALUES (UUID(), 'customers', OLD.id, 'DELETE', JSON_OBJECT('name', OLD.name, 'email', OLD.email, 'created_at', OLD.created_at, 'updated_at', OLD.updated_at));
END$$
DELIMITER ;