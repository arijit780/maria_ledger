# Maria Ledger - CLI Command Reference

This document provides a detailed explanation of every command available through the `maria-ledger` command-line interface (CLI).

---

## Core Commands

These commands form the primary workflow for managing and verifying ledger-enabled tables.

### `bootstrap`

**Purpose**: Brings an existing database table under the control of Maria Ledger.

This is the first command you run on a table. It sets up the entire auditing infrastructure for that table, creating a baseline for all future integrity checks.

**Usage:**
```bash
maria-ledger bootstrap TABLE_NAME [OPTIONS]
```

**Arguments & Options:**
- `TABLE_NAME` (Required): The name of the database table you want to start tracking.
- `--fields-to-hash "field1,field2"` (Optional): A comma-separated string of column names. When verifying integrity, the system will generate hashes based *only* on these fields, even though all fields are still recorded in the ledger. This is useful for ignoring metadata fields like `updated_at` that change frequently but don't affect the record's core integrity.

**What It Does:**
1.  **Snapshots Data**: It takes a snapshot of every existing row in the specified table and records it in the universal `ledger` table as an initial state.
2.  **Creates Triggers**: It dynamically generates and installs `AFTER INSERT`, `AFTER UPDATE`, and `AFTER DELETE` triggers on the table. These triggers automatically capture all subsequent changes.
3.  **Creates First Checkpoint**: It computes the first Merkle root from the initial snapshot and stores it in the `ledger_roots` table. This signed root acts as the first "anchor of trust."

**Example:**
```bash
# Bring the 'products' table under ledger control
maria-ledger bootstrap products

# Bring 'transactions' under control, but only use amount and account fields for verification
maria-ledger bootstrap transactions --fields-to-hash "amount,from_account,to_account"
```

---

### `verify`

**Purpose**: A powerful, multi-mode command to verify the cryptographic integrity of a table.

This is the most important command for auditing. It checks if the data's history has been tampered with and if the live data matches its audited history.

**Usage:**
```bash
maria-ledger verify TABLE_NAME [OPTIONS]
```

**Verification Modes & Options:**

- **Default Mode (Stored Root Verification)**
  - **Command**: `maria-ledger verify TABLE_NAME`
  - **Action**: Reconstructs the table's state from the `ledger` history, computes a new Merkle root, and compares it against the latest trusted root stored in the `ledger_roots` table.
  - **Detects**: Tampering within the `ledger` table itself (e.g., a modified or deleted history entry).

- **Live State Verification**
  - **Command**: `maria-ledger verify TABLE_NAME --live`
  - **Action**: Reconstructs the state from the `ledger` and compares it, row by row, against the data in the *live* database table.
  - **Detects**: Discrepancies where the live table has been altered outside the ledger's view (e.g., by disabling triggers and making a change).

- **Comprehensive Verification**
  - **Command**: `maria-ledger verify TABLE_NAME --comprehensive`
  - **Action**: Performs both the **Stored Root Verification** and the **Live State Verification** in one go. This is the most thorough check.

- **Force Checkpoint**
  - **Command**: `maria-ledger verify TABLE_NAME --force`
  - **Action**: If verification fails due to legitimate changes, this option computes a new Merkle root from the current ledger state and saves it as the new trusted checkpoint.

- **Row-Level Verification & Proof Export**
  - **Command**: `maria-ledger verify TABLE_NAME --filter "key:value" [--export proof.json]`
  - **Action**: Narrows the verification down to specific rows matching the filter. If a single row is matched and `--export` is used, it generates a JSON file containing a cryptographic "Merkle proof" that can be independently verified without database access.

**Example:**
```bash
# Check if the ledger history has been tampered with
maria-ledger verify products

# Check if the live 'products' table matches its ledger history
maria-ledger verify products --live

# After making valid changes, create a new trusted checkpoint
maria-ledger verify products --force

# Export a verifiable proof for product with id=1
maria-ledger verify products --filter "id:1" --export product_1_proof.json
```

---

### `verify-chain`

**Purpose**: Performs a low-level check of the hash chain's continuity.

This command walks the ledger entry by entry for a specific table, ensuring that each record's `prev_hash` correctly matches the `chain_hash` of the preceding record.

**Usage:**
```bash
maria-ledger verify-chain TABLE_NAME
```

**What It Does:**
- It iterates through all ledger entries for the given table, ordered chronologically.
- For each entry, it confirms that `hash(previous_entry) == current_entry.prev_hash`.

**Detects**: A very specific and severe form of tampering where an entry has been modified in a way that breaks the cryptographic link to its direct predecessor.

**Example:**
```bash
maria-ledger verify-chain customers
```
**Expected Output:**
- On success: A message indicating that all chain hashes are valid.
- On failure: An error message pinpointing the exact transaction (`tx_order`) where the chain break was detected.

---

## Data Inspection & Forensic Commands

These commands allow you to explore the audit trail and analyze the ledger's history.

### `timeline`

**Purpose**: Displays the chronological audit history of records in a human-readable format.

Use this command to see how a record has changed over time or to view all activity on a table within a specific timeframe.

**Usage:**
```bash
maria-ledger timeline TABLE_NAME [OPTIONS]
```

**Arguments & Options:**
- `TABLE_NAME` (Required): The name of the table whose timeline you want to view.
- `--id RECORD_ID` (Optional): Filters the timeline to show the history of only a single record.
- `--from-tx TX_ORDER` / `--to-tx TX_ORDER` (Optional): Filters the timeline to a specific range of transaction orders.
- `--json` (Optional): Outputs the timeline as a JSON array instead of a formatted table.

**What It Does:**
- Reads the `ledger` table and presents the change history (`INSERT`, `UPDATE`, `DELETE`) in chronological order.
- For `UPDATE` operations, it can show the "diff" of what data changed.

**Example:**
```bash
# Show the complete history for the product with id=3
maria-ledger timeline products --id 3

# Show all activity on the 'customers' table
maria-ledger timeline customers

# Show what happened between transactions 10 and 25
maria-ledger timeline products --from-tx 10 --to-tx 25
```

---

### `reconstruct`

**Purpose**: Reconstructs the current state of a table by replaying its entire history from the ledger.

This command demonstrates the ledger's ability to serve as a single source of truth. The output is what the live table *should* look like if its integrity is intact.

**Usage:**
```bash
maria-ledger reconstruct TABLE_NAME [OPTIONS]
```

**Arguments & Options:**
- `TABLE_NAME` (Required): The table to reconstruct.
- `--out-csv PATH` (Optional): Writes the reconstructed table state to the specified CSV file instead of printing it to the console.
- `--filter "key:value"` (Optional): Reconstructs only the rows matching the filter.

**What It Does:**
1.  Starts with an empty state.
2.  Reads every ledger entry for the table in chronological order.
3.  Applies each operation: adds a row for `INSERT`, modifies it for `UPDATE`, and removes it for `DELETE`.
4.  The final result is the reconstructed state, which is then printed or saved.

**Example:**
```bash
# Print the reconstructed state of the 'products' table to the console
maria-ledger reconstruct products

# Reconstruct only the 'Electronics' category and save it to a file
maria-ledger reconstruct products --filter "category:Electronics" --out-csv electronics.csv
```

---

### `forensic`

**Purpose**: Performs a deep analysis of the ledger to detect anomalies and sophisticated tampering patterns.

This goes beyond simple hash checks to look for suspicious patterns that might indicate a cover-up attempt or a system malfunction.

**Usage:**
```bash
maria-ledger forensic TABLE_NAME [OPTIONS]
```

**Arguments & Options:**
- `TABLE_NAME` (Required): The table to analyze.
- `--out PATH` / `-o PATH` (Optional): Writes the detailed forensic report to the specified file.
- `--json` (Optional): Outputs the report in JSON format.
- `--detail LEVEL` / `-d LEVEL` (Optional): Sets the report's level of detail (1-3), with 3 being the most verbose.

**What It Does:**
- Analyzes the entire transaction chain for the table.
- **Detects Anomalies**:
  - Hash chain breaks.
  - Gaps in the transaction sequence.
  - Non-monotonic timestamps (a transaction appearing to happen before a previous one).
  - Duplicate transaction IDs.
- **Generates a Risk Score**: Provides a score from 0-100 indicating the likelihood of tampering.

**Example:**
```bash
# Run a detailed forensic analysis and save the report
maria-ledger forensic products --detail 3 --out forensic_report.json
```

---

### `snapshot`

**Purpose**: Creates a signed, portable, and immutable snapshot of a table's state at a specific moment.

This is useful for creating a verifiable "receipt" of a table's state that can be shared with external auditors.

**Usage:**
```bash
maria-ledger snapshot TABLE_NAME --out PATH [OPTIONS]
```

**Arguments & Options:**
- `TABLE_NAME` (Required): The table to snapshot.
- `--out PATH` (Required): The file path where the JSON snapshot will be saved.
- `--store-root` (Optional): In addition to creating the file, this also stores the snapshot's Merkle root in the `ledger_roots` table as a new checkpoint.

**What It Does:**
1.  Reconstructs the table's state from the ledger.
2.  Computes the Merkle root of that state.
3.  Uses the project's private key to create a digital signature of the Merkle root.
4.  Exports all of this information (table name, root, signature, timestamp, etc.) into a self-contained JSON file.

**Example:**
```bash
# Create a snapshot of the 'products' table and also save it as a new checkpoint
maria-ledger snapshot products --out products_q1_report.json --store-root
```