# Maria Ledger

**Cryptographic tamper-evident database system built on MariaDB**

Maria Ledger adds cryptographic guarantees to any MariaDB table, enabling provable data integrity for financial compliance, healthcare audits, and any scenario requiring cryptographic proof of data integrity.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Installation & Setup](#installation--setup)
- [Quick Start](#quick-start)
- [CLI Commands Reference](#cli-commands-reference)
- [Advanced Usage](#advanced-usage)
- [Integration with MariaDB Features](#integration-with-mariadb-features)

---

## Overview

Maria Ledger transforms any MariaDB table into a **cryptographically secure audit trail**. Every change is automatically tracked via database triggers, cryptographically linked in an immutable ledger, and verifiable through Merkle tree proofs.

### Key Features

- **Zero Code Changes**: One command enables ledger control on any existing table
- **Cryptographic Integrity**: SHA-256 hash chains + Merkle tree verification
- **Automatic Tracking**: Database triggers capture all INSERT/UPDATE/DELETE operations
- **External Verification**: Auditors can verify without database access
- **MariaDB Integration**: Works with ColumnStore, Vector Search, and Temporal Tables
- **Universal Ledger Pattern**: Single ledger table for all business tables

### Use Cases

- Financial transaction compliance
- Healthcare audit trails
- Regulatory reporting
- Supply chain tracking
- Legal document versioning
- Any scenario requiring cryptographic proof of data integrity

---

## Theory & Design Principles

### Why Cryptographic Integrity?

Traditional databases provide **trust-based integrity**: auditors must trust that:
- Database administrators haven't modified data
- System logs haven't been altered
- Access controls are properly enforced

**Maria Ledger provides cryptographic integrity**:
- **Tamper-Evident**: Any modification breaks the cryptographic chain
- **Verifiable**: External auditors can verify without trusting the database
- **Immutable History**: Past states cannot be changed without detection
- **Mathematical Proof**: Integrity is proven cryptographically, not by policy

### Threat Model

Maria Ledger protects against:

1. **Data Tampering**: Unauthorized modification of table data
- **Protection**: Hash chain detects any change
- **Detection**: Merkle root mismatch reveals tampering

2. **History Alteration**: Changing or deleting historical records
- **Protection**: Immutable append-only ledger
- **Detection**: Hash chain breaks if history is modified

3. **Retroactive Changes**: Backdating or modifying past transactions
- **Protection**: Cryptographic timestamps + hash chain
- **Detection**: Non-monotonic timestamps + chain breaks

4. **Cover-Up Attempts**: Tampering with audit logs to hide changes
- **Protection**: Ledger entries are cryptographically linked
- **Detection**: Chain hash mismatch reveals tampering

**Maria Ledger does NOT protect against:**
- Database-level attacks (full database deletion)
- Physical access to server (hardware attacks)
- Compromised cryptographic keys (private key theft)

### Mathematical Foundations

#### Hash Functions (SHA-256)

**Properties:**
- **Deterministic**: Same input always produces same output
- **One-Way**: Cannot reverse hash to get original data
- **Avalanche Effect**: Small input change → completely different hash
- **Collision Resistant**: Practically impossible to find two inputs with same hash

**Usage in Maria Ledger:**
```
chain_hash = SHA256(prev_hash || tx_id || record_id || op_type || payload || timestamp)
```

**Security Guarantee**: If any component changes, `chain_hash` changes completely. This makes tampering detectable.

#### Hash Chains

**Concept**: Each entry cryptographically links to the previous entry.

```
Entry 1: chain_hash₁ = H(genesis || data₁)
Entry 2: chain_hash₂ = H(chain_hash₁ || data₂)
Entry 3: chain_hash₃ = H(chain_hash₂ || data₃)
```

**Properties:**
- **Transitive Integrity**: If Entry 3 is valid → Entry 2 is valid → Entry 1 is valid
- **Tamper Detection**: Changing Entry 2 breaks Entry 3's chain_hash
- **Historical Proof**: Proves the entire sequence hasn't changed

**Logical Proof:**
```
Given: chain_hash₃ = H(chain_hash₂ || data₃)
If: chain_hash₂ changes → chain_hash₃ ≠ H(new_chain_hash₂ || data₃)
Therefore: Tampering is detectable
```

#### Merkle Trees

**Concept**: Efficient way to prove integrity of large datasets with a single hash.

**Construction:**
1. Compute hash of each ledger entry: `H₁, H₂, H₃, ..., Hₙ`
2. Build binary tree by hashing pairs: `H(H₁ || H₂)`, `H(H₃ || H₄)`, ...
3. Continue until single root hash remains: `MerkleRoot`

**Properties:**
- **Efficiency**: O(log n) proof size for n entries
- **Incremental**: Can update root when new entries added
- **Verifiable**: One hash proves integrity of millions of entries

**Merkle Proof Example:**
```
To prove Entry 5 is part of the ledger:
1. Compute hash of Entry 5: H₅
2. Provide sibling hashes: H₄, H(H₆||H₇), H(H₁||H₂||H₃||H₄)
3. Recomputed root matches stored MerkleRoot → Entry 5 is authentic
```

**Why Merkle Trees Matter:**
- **Scalability**: Verify millions of entries with one hash
- **External Auditing**: Auditor doesn't need full database access
- **Checkpointing**: Prove state at any point in time

### Design Rationale

#### Why Universal Ledger Pattern?

**Alternative 1: Per-Table Audit Logs**
```
customers_audit_log
orders_audit_log
payments_audit_log
```

**Problems:**
- ❌ Schema complexity (many tables)
- ❌ Cross-table queries difficult
- ❌ No unified integrity verification
- ❌ Harder to maintain consistency

**Universal Ledger Solution:**
```
single ledger table
├── table_name: 'customers'
├── table_name: 'orders'
└── table_name: 'payments'
```

**Benefits:**
- ✅ Simple schema (one table)
- ✅ Easy cross-table queries
- ✅ Unified Merkle root for all tables
- ✅ Single source of truth

**Logical Justification**: All changes to any table are conceptually the same: a modification to the database state. A universal ledger treats them uniformly while maintaining table context through the `table_name` column.

#### Why Database Triggers?

**Alternative 1: Application-Level Logging**
```python
def update_customer(customer_id, data):
db.update(customer_id, data)
ledger.append("UPDATE", customer_id, data) # Manual logging
```

**Problems:**
- ❌ Easy to forget logging
- ❌ Not atomic (can fail separately)
- ❌ Application code must change
- ❌ Bypassable (direct SQL access)

**Trigger Solution:**
```sql
CREATE TRIGGER customers_after_update
AFTER UPDATE ON customers
FOR EACH ROW
BEGIN
CALL append_ledger_entry(...); -- Automatic
END;
```

**Benefits:**
- ✅ Impossible to bypass
- ✅ Atomic with data change
- ✅ Zero application code changes
- ✅ Enforced at database level

**Logical Justification**: Integrity must be enforced at the lowest level (database) where data actually changes. Triggers guarantee that **every** change is logged, regardless of how it happens (application, SQL, bulk import).

#### Why Stored Procedure with Locking?

**The Problem**: Concurrent writes can break the hash chain.

**Scenario:**
```
Thread 1: Reads last chain_hash = H₀
Thread 2: Reads last chain_hash = H₀
Thread 1: Computes H₁ = H(H₀ || data₁), inserts
Thread 2: Computes H₂ = H(H₀ || data₂), inserts
Result: Both entries claim H₀ as prev_hash → chain broken!
```

**Solution**: `FOR UPDATE` lock in stored procedure.

```sql
SELECT chain_hash INTO prev_hash
FROM ledger
WHERE table_name = p_table_name
ORDER BY tx_order DESC
LIMIT 1
FOR UPDATE; -- Lock this row
```

**How it works:**
1. Lock last entry for the table
2. Read `prev_hash` (guaranteed consistent)
3. Compute new `chain_hash`
4. Insert new entry
5. Release lock

**Result**: Only one thread can insert at a time per table → chain always valid.

**Logical Justification**: Hash chains require strict ordering. Database-level locking ensures serializability of ledger writes, maintaining cryptographic integrity.

#### Why Merkle Root Checkpoints?

**The Problem**: Verifying every entry in a large ledger is expensive.

**Scenario**:
- 1 million ledger entries
- Verifying all would take minutes
- External auditor needs quick verification

**Solution**: Periodic Merkle root checkpoints.

```
Every N entries or every hour:
1. Compute Merkle root of all entries
2. Sign root with private key
3. Store in ledger_roots table
```

**Verification Process:**
1. Get latest Merkle root from `ledger_roots`
2. Recompute Merkle root from all `ledger` entries
3. Compare: stored == computed?
4. Verify signature with public key

**Time Complexity:**
- Without checkpoints: O(n) to verify n entries
- With checkpoints: O(1) to verify latest checkpoint

**Logical Justification**: Merkle roots provide a constant-time integrity proof. Even with millions of entries, verification is fast and scalable.

### Security Guarantees

**Formal Properties:**

1. **Tamper Detection**
```
If data is modified → hash chain breaks → detection guaranteed
```

2. **Historical Integrity**
```
If past entry is changed → all future chain_hashes change → detection guaranteed
```

3. **Immutability**
```
Ledger entries cannot be deleted without breaking chain → history preserved
```

4. **Verifiability**
```
External auditor with public key can verify without database access
```

5. **Non-Repudiation**
```
Digital signature proves who created checkpoint → cannot deny
```

**Limitations:**

1. **First Entry Problem**: Genesis hash is predictable (mitigated by signing Merkle roots)
2. **Replay Attacks**: Old valid transactions could be replayed (mitigated by tx_id uniqueness)
3. **Key Compromise**: If private key stolen, attacker can create valid signatures (mitigated by key rotation)

---

## Architecture

### Core Concepts

#### 1. **Universal Ledger Pattern**

Instead of creating separate audit tables for each business table, Maria Ledger uses **one universal `ledger` table** that tracks changes across all tables:

```
ledger table structure:
├── tx_order (auto-increment transaction sequence)
├── tx_id (unique transaction identifier - UUID)
├── table_name (which business table changed)
├── record_id (which record changed)
├── op_type (INSERT, UPDATE, or DELETE)
├── old_payload (JSON snapshot of old data)
├── new_payload (JSON snapshot of new data)
├── created_at (timestamp)
├── prev_hash (previous entry's chain_hash)
└── chain_hash (SHA-256 hash linking entries)
```

**Benefits:**
- Simpler schema (one table vs. many)
- Cross-table audit queries
- Efficient Merkle tree construction
- Centralized integrity verification

#### 2. **Hash Chains**

Each ledger entry is cryptographically linked to the previous entry:

```
Entry 1: chain_hash = SHA256(genesis_hash || tx_id || record_id || op_type || payload || timestamp)
Entry 2: chain_hash = SHA256(Entry1.chain_hash || tx_id || record_id || op_type || payload || timestamp)
Entry 3: chain_hash = SHA256(Entry2.chain_hash || tx_id || record_id || op_type || payload || timestamp)
```

**Properties:**
- **Tamper-evident**: Any change breaks the chain
- **Immutable**: Previous entries cannot be modified without detection
- **Verifiable**: External auditors can recompute and verify

#### 3. **Merkle Trees**

Periodic checkpoints store Merkle roots of all ledger entries:

```
Merkle Tree Construction:
1. Compute hash of each ledger entry (chain_hash)
2. Build binary tree by hashing pairs: H(left || right)
3. Root hash = single hash representing entire ledger state
4. Sign root hash with private key for external verification
```

**Benefits:**
- **Efficient Verification**: One hash proves integrity of millions of entries
- **Point-in-Time Proofs**: Can prove state at any checkpoint
- **External Auditing**: Merkle root + signature = verifiable proof

#### 4. **Database Triggers**

Automatic capture of all changes via MariaDB triggers:

```sql
-- Example trigger for INSERT
CREATE TRIGGER table_name_after_insert
AFTER INSERT ON table_name
FOR EACH ROW
BEGIN
CALL append_ledger_entry(
'table_name',
CAST(NEW.id AS CHAR),
'INSERT',
NULL,
JSON_OBJECT(...)
);
END;
```

**Properties:**
- **Automatic**: No application code changes required
- **Atomic**: Trigger execution is part of the same transaction
- **Consistent**: Hash chain computed in stored procedure with locking

#### 5. **Stored Procedure: `append_ledger_entry`**

Central procedure that ensures hash chain integrity:

```sql
CREATE PROCEDURE append_ledger_entry(
p_table_name, p_record_id, p_op_type, p_old_payload, p_new_payload
)
BEGIN
-- 1. Lock last entry for this table (prevents concurrent writes)
SELECT chain_hash INTO prev_hash FROM ledger
WHERE table_name = p_table_name
ORDER BY tx_order DESC LIMIT 1 FOR UPDATE;
-- 2. Compute chain_hash: SHA256(prev_hash || tx_id || ...)
SET chain_hash = SHA256(CONCAT(prev_hash, tx_id, record_id, ...));
-- 3. Insert new ledger entry
INSERT INTO ledger (..., prev_hash, chain_hash) VALUES (...);
END;
```

**Why this works:**
- `FOR UPDATE` lock ensures only one concurrent insertion per table
- Genesis hash provides starting point for chain
- Deterministic hash computation ensures reproducibility

### Data Flow

```
Application INSERT/UPDATE/DELETE
↓
Database Trigger (automatic)
↓
append_ledger_entry() stored procedure
↓
Compute prev_hash (lock last entry)
↓
Compute chain_hash (SHA-256)
↓
Insert into ledger table
↓
Transaction commits (or rolls back)
```

### Verification Flow

```
External Auditor wants to verify:
↓
1. Get latest Merkle root + signature from ledger_roots
↓
2. Recompute Merkle root from all ledger entries
↓
3. Compare: stored root == computed root?
↓
4. Verify signature with public key
↓
Result: Cryptographic proof of integrity (or detection of tampering)
```

---

## Installation & Setup

### Prerequisites

- **Python 3.9+**
- **MariaDB 10.5+** (or MySQL 8.0+)
- **OpenSSL** (for key generation)

### Step 1: Install Maria Ledger

```bash
# Clone repository
git clone <repository-url>
cd maria_ledger

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate # On Windows: .venv\Scripts\activate

# Install package
pip install -e .
```

### Step 2: Database Setup

Create the ledger infrastructure in your MariaDB database:

```bash
mysql -u YOUR_USER -p YOUR_DATABASE < maria_ledger/db/triggers.sql
```

This creates:
- `ledger` table (universal ledger)
- `ledger_roots` table (Merkle root checkpoints)
- `append_ledger_entry` stored procedure

### Step 3: Generate Cryptographic Keys

```bash
# Create keys directory
mkdir -p keys

# Generate private key
openssl genrsa -out keys/private_key.pem 4096

# Generate public key
openssl rsa -in keys/private_key.pem -pubout -out keys/public_key.pem
```

### Step 4: Configure `config.yaml`

Create `config.yaml` in the project root:

```yaml
db:
host: localhost
port: 3306
user: your_user
password: 'your_password'
name: your_database

crypto:
private_key_path: keys/private_key.pem
public_key_path: keys/public_key.pem
signer_id: "maria-ledger"
```

### Step 5: Verify Installation

```bash
# Check CLI is available
maria-ledger --help

# Run audit to verify database connection
maria-ledger audit
```

---

## Quick Start

This guide walks you through setting up Maria Ledger with sample tables.

### Step 1: Setup Database Infrastructure

First, create the ledger infrastructure (ledger table, ledger_roots table, and stored procedures):

```bash
sudo mysql
mysql -u YOUR_USER -p YOUR_DATABASE < maria_ledger/db/triggers.sql
```

This creates:
- `ledger` table (universal ledger)
- `ledger_roots` table (Merkle root checkpoints)
- `append_ledger_entry` stored procedure
- Example `customers` table (optional, you can use your own)

### Step 2: Populate Customers Table

Populate the `customers` table with sample data:

```bash
#manually insert
"
INSERT INTO customers (name, email) VALUES ('Alice', 'alice@example.com');
INSERT INTO customers (name, email) VALUES ('Bob', 'bob@example.com');
INSERT INTO customers (name, email) VALUES ('Charlie', 'charlie@example.com');
INSERT INTO customers (name, email) VALUES ('Diana', 'diana@example.com');
INSERT INTO customers (name, email) VALUES ('Eve', 'eve@example.com');
INSERT INTO customers (name, email) VALUES ('Frank', 'frank@example.com');
INSERT INTO customers (name, email) VALUES ('Grace', 'grace@example.com');
INSERT INTO customers (name, email) VALUES ('Heidi', 'heidi@example.com');
INSERT INTO customers (name, email) VALUES ('Ivan', 'ivan@example.com');
INSERT INTO customers (name, email) VALUES ('Judy', 'judy@example.com');
INSERT INTO customers (name, email) VALUES ('Kevin', 'kevin@example.com');
INSERT INTO customers (name, email) VALUES ('Linda', 'linda@example.com');
INSERT INTO customers (name, email) VALUES ('Mallory', 'mallory@example.com');
INSERT INTO customers (name, email) VALUES ('Nancy', 'nancy@example.com');
INSERT INTO customers (name, email) VALUES ('Oscar', 'oscar@example.com');
"
```

### Step 3: Create and Populate Products Table

Create the `products` table and populate it with sample data:

```bash
#manually create and populate
"
CREATE TABLE IF NOT EXISTS products (
id INT AUTO_INCREMENT PRIMARY KEY,
name VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
price DECIMAL(10, 2) NOT NULL,
category VARCHAR(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci,
description TEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci,
stock INT DEFAULT 0,
created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

INSERT INTO products (name, price, category, description, stock) VALUES
('Laptop Pro', 1299.99, 'Electronics', 'High-performance laptop with 16GB RAM', 25),
('Wireless Mouse', 29.99, 'Accessories', 'Ergonomic wireless mouse', 150),
('Mechanical Keyboard', 89.99, 'Accessories', 'RGB mechanical keyboard with blue switches', 75),
('USB-C Cable', 19.99, 'Accessories', '6ft USB-C charging cable', 200),
('Monitor 27\"', 299.99, 'Electronics', '4K 27-inch monitor', 40),
('Webcam HD', 79.99, 'Accessories', '1080p HD webcam for video calls', 60),
('Laptop Stand', 49.99, 'Accessories', 'Aluminum laptop stand for ergonomics', 90),
('HDD 1TB', 59.99, 'Storage', 'External 1TB hard drive', 120),
('SSD 500GB', 89.99, 'Storage', 'NVMe SSD 500GB', 80),
('USB Hub', 24.99, 'Accessories', '7-port USB 3.0 hub', 100);
"
```

### Step 4: Bootstrap Tables

Bring both tables under ledger control:

```bash
#We dont need to bootstrap the customers table in the triggers.sql we already have done that

python maria_ledger/scripts/gen_keys.py
#Wrote private_key.pem and public_key.pem to keys/

# Bootstrap products table
maria-ledger bootstrap products

# Or with specific fields for hash computation
maria-ledger bootstrap products --fields-to-hash "name,price,category"
```

**What happens during bootstrap:**
1. ✅ Snapshot existing data into ledger
2. ✅ Create triggers for INSERT/UPDATE/DELETE
3. ✅ Create initial Merkle root checkpoint

### Step 5: Make Changes

Make some changes to test the ledger like:

```sql
-- Insert new product
INSERT INTO products (name, price, category) VALUES ('Monitor', 199.99, 'Electronics');

-- Update existing product
UPDATE products SET price = 949.99 WHERE id = 1;

-- Delete product
DELETE FROM products WHERE id = 2;

-- Insert new customer
INSERT INTO customers (name, email) VALUES ('Paul', 'paul@example.com');

-- Update customer
UPDATE customers SET email = 'newemail@example.com' WHERE id = 1;
```

All changes are automatically tracked in the ledger!

### Step 6: Verify Integrity(there are more ....refer the manual for more info)

Verify the integrity of your ledger:

```bash
# Verify customers table
maria-ledger verify customers
maria-ledger verify customers --live
maria-ledger verify-chain customers

# Verify products table
maria-ledger verify products
maria-ledger verify products --live
maria-ledger verify products --comprehensive
```

### Step 7: Explore Timeline and History

View the audit history:

```bash
# View timeline for a specific product
maria-ledger timeline products --id 1

# View table-wide timeline
maria-ledger timeline products

# View time range
maria-ledger timeline products --from-tx 5 --to-tx 15

# Reconstruct current state
maria-ledger reconstruct products
```

---

## CLI Commands Reference

### Core Commands

#### `bootstrap`

Brings an existing table under ledger control.

**Usage:**
```bash
maria-ledger bootstrap TABLE_NAME [--fields-to-hash "field1,field2"]
```

**Options:**
- `--fields-to-hash`: Comma-separated list of fields for hash computation during verification. If not specified, all tracked fields are used.

**What it does:**
- Snapshots existing data into ledger
- Creates triggers for INSERT/UPDATE/DELETE
- Creates initial Merkle root checkpoint

**Example:**
```bash
# Track all fields, hash all fields
maria-ledger bootstrap products

# Track all fields, but hash only specific ones
maria-ledger bootstrap products --fields-to-hash "name,price,category"
```

---

#### `verify`

Unified verification command with multiple modes.

**Usage:**
```bash
maria-ledger verify TABLE_NAME [OPTIONS]
```

**Options:**
- `--force`: Force re-computation and storage of a new Merkle root
- `--live`: Verify live table state against reconstructed state from ledger
- `--comprehensive`: Perform both stored root verification and live state verification
- `--filter key:value`: Filter rows for verification (can be used multiple times)
- `--export PATH`: Export proof to JSON file (requires exactly one matching row)

**Verification Modes:**

1. **Default (Stored Root Verification):**
```bash
maria-ledger verify products
```
- Compares stored Merkle root with freshly computed root
- Detects tampering in ledger entries

2. **Live State Verification:**
```bash
maria-ledger verify products --live
```
- Reconstructs table state from ledger
- Compares with current live table state
- Detects discrepancies between ledger and table

3. **Comprehensive Verification:**
```bash
maria-ledger verify products --comprehensive
```
- Performs both stored root and live state verification
- Most thorough integrity check

4. **Row-Level Verification:**
```bash
# Verify all matching rows
maria-ledger verify products --filter "category:Electronics"
# Export proof for single row
maria-ledger verify products --filter "id:1" --export proof.json
```

---

#### `verify-chain`

Verifies the cryptographic hash chain integrity.

**Usage:**
```bash
maria-ledger verify-chain TABLE_NAME
```

**What it does:**
- Validates hash chain continuity
- Ensures each `prev_hash` matches previous entry's `chain_hash`
- Detects any breaks in the cryptographic chain

**Example:**
```bash
maria-ledger verify-chain products
```

**Output:**
- ✅ Success: All chain hashes are valid
- ❌ Failure: Chain break detected (tampering)

---


---

### Data Inspection Commands

#### `timeline`

Shows chronological audit history for records.

**Usage:**
```bash
maria-ledger timeline TABLE_NAME [OPTIONS]
```

**Options:**
- `--id RECORD_ID`: Show timeline for specific record
- `--from-tx TX_ORDER`: Starting transaction order (inclusive)
- `--to-tx TX_ORDER`: Ending transaction order (inclusive)
- `--verify-chain`: Validate hash chain continuity during replay
- `--json`: Output as JSON array

**Modes:**

1. **Single Record Timeline:**
```bash
maria-ledger timeline products --id 3
```
Shows all changes (INSERT/UPDATE/DELETE) for record ID 3

2. **Table-Wide Timeline:**
```bash
maria-ledger timeline products
```
Shows all transactions across all records in chronological order

3. **Time Range Filter:**
```bash
maria-ledger timeline products --from-tx 10 --to-tx 25
```
Shows transactions between tx_order 10 and 25

4. **Diff Mode:**
```bash
maria-ledger timeline products --from-tx 10 --to-tx 25
```
Compares state at tx_order 10 vs tx_order 25 (shows what changed)

**Example Output:**
```
tx_order | op_type | record_id | timestamp | changes
---------|---------|-----------|---------------------|------------------
1 | INSERT | 1 | 2025-01-01 10:00:00 | name: Laptop, price: 999.99
2 | UPDATE | 1 | 2025-01-01 11:00:00 | price: 999.99 → 949.99
3 | DELETE | 2 | 2025-01-01 12:00:00 | (deleted)
```

---

#### `reconstruct`

Reconstructs table's state from the ledger.

**Usage:**
```bash
maria-ledger reconstruct TABLE_NAME [OPTIONS]
```

**Options:**
- `--out-csv PATH`: Write reconstructed state as CSV file
- `--filter key:value`: Filter by column value (can be used multiple times)

**What it does:**
- Reads all ledger entries for the table
- Applies operations in order (INSERT → UPDATE → DELETE)
- Reconstructs final state
- Computes Merkle root of reconstructed state

**Example:**
```bash
# Reconstruct current state
maria-ledger reconstruct products

# Reconstruct and save to CSV
maria-ledger reconstruct products --out-csv products_state.csv

# Reconstruct with filters
maria-ledger reconstruct products --filter "category:Electronics"
```

---

### Forensic & Analysis Commands

#### `forensic`

Performs deep forensic analysis on the ledger's transaction chain.

**Usage:**
```bash
maria-ledger forensic TABLE_NAME [OPTIONS]
```

**Options:**
- `--out PATH`, `-o`: Write report to file
- `--json`: Output results in JSON format
- `--detail LEVEL`, `-d`: Level of detail (1-3, default: 1)

**What it does:**
- Analyzes ledger entries for anomalies and tampering patterns
- Detects:
- Hash chain breaks
- Timestamp inconsistencies
- Duplicate transaction IDs
- Gaps in transaction sequence
- Non-monotonic timestamps
- Generates risk score (0-100)

**Example:**
```bash
maria-ledger forensic products --detail 3 --out report.json
```

---

#### `snapshot`

Creates a signed, immutable snapshot of table's state.

**Usage:**
```bash
maria-ledger snapshot TABLE_NAME --out PATH [OPTIONS]
```

**Options:**
- `--out PATH`: Path to write snapshot JSON file (required)
- `--store-root`: Also insert the root into the ledger_roots table

**What it does:**
- Reconstructs table state from ledger
- Computes Merkle root
- Signs root hash with private key
- Exports as JSON manifest:
```json
{
"table_name": "products",
"merkle_root": "abc123...",
"signature": "...",
"computed_at": "2025-01-01T10:00:00Z",
"tx_order": 150,
"state": {...}
}
```

**Example:**
```bash
maria-ledger snapshot products --out snapshot.json --store-root
```

---

## Advanced Usage

### Fields to Hash Configuration

When bootstrapping, you can specify which fields to use for hash computation:

```bash
# Track all fields, but verify against critical ones only
maria-ledger bootstrap customers --fields-to-hash "name,email,status"
```

**Why use this:**
- **Full Audit Trail**: All fields are tracked in ledger
- **Focused Verification**: Verification only checks critical fields
- **Ignore Metadata**: Timestamps, soft-delete flags don't affect verification hash

**Example Use Case:**
```sql
CREATE TABLE transactions (
id INT PRIMARY KEY,
amount DECIMAL(10,2),
from_account VARCHAR(255),
to_account VARCHAR(255),
status VARCHAR(50),
created_at TIMESTAMP,
updated_at TIMESTAMP
);
```

```bash
# Bootstrap: track all, verify against critical fields
maria-ledger bootstrap transactions --fields-to-hash "amount,from_account,to_account"

# Now verification focuses on financial data, ignores timestamps
maria-ledger verify transactions
```

---

### Cross-Table Verification

Maria Ledger's universal ledger pattern enables cross-table verification:

```bash
# Verify multiple tables
maria-ledger verify customers
maria-ledger verify orders
maria-ledger verify payments

# Or audit all at once
maria-ledger audit
```

---

### Point-in-Time Reconstruction

Reconstruct table state at any transaction point:

```bash
# Reconstruct current state
maria-ledger reconstruct products

# Reconstruct at specific transaction (if supported)
# Timeline shows transaction history
maria-ledger timeline products --from-tx 10 --to-tx 25
```
---

## Architecture Diagram Prompt

For generating architecture diagrams, use this prompt:

```
Design a technical architecture diagram for Maria Ledger showing:

1. Application Layer: Python CLI and Library API
2. Database Layer:
- Universal ledger table (hash-chained entries)
- ledger_roots table (Merkle checkpoints)
- Business tables (products, customers, etc.)
- Database triggers (automatic capture)
- append_ledger_entry stored procedure
3. Cryptographic Layer:
- SHA-256 hash chains (prev_hash → chain_hash)
- Merkle tree construction (periodic checkpoints)
- Digital signatures (RSA signing of Merkle roots)
4. Verification Layer:
- External auditor verification (public key + Merkle root)
- Hash chain continuity checks
- Live state reconstruction
5. MariaDB Features Integration:
- ColumnStore (historical analytics)
- Vector Search (semantic anomaly detection)
- Temporal Tables (versioning)

Include this quote: "Maria Ledger adds cryptographic guarantees to ANY MariaDB feature. We've integrated ColumnStore for efficient historical snapshot analysis and Vector search for semantic anomaly detection. It's cryptographic integrity meets MariaDB's analytics and AI capabilities."

Show data flow: Application → Trigger → Stored Procedure → Ledger → Merkle Root → External Verification
```

---

## Contributing

Contributions welcome! Please read the contributing guidelines before submitting PRs.

## License

[Your License Here]

## Support

For issues and questions:
- GitHub Issues: [Repository URL]
- Documentation: [Docs URL]

---

**Built with ❤️ for the MariaDB Hackathon**