# Maria Ledger

Maria Ledger is a tamper-evident database system built on MariaDB. It ensures data integrity using hash chains and Merkle trees, making it suitable for applications requiring strong guarantees of data authenticity.

## Project Structure

```
maria_ledger/
│
├── README.md                   # Project documentation
├── pyproject.toml              # Build system configuration
├── setup.py                    # Python package setup
│
├── maria_ledger/               # Main package
│   ├── __init__.py             # Package initializer
│   │
│   ├── db/                     # Database-related logic
│   │   ├── connection.py       # Connect to MariaDB
│   │   ├── temporal_utils.py   # Helpers for querying historical data
│   │   ├── triggers.sql        # SQL for enabling hash-chain triggers
│   │   └── merkle_service.py   # Computes Merkle root periodically
│   │
│   ├── crypto/                 # Cryptographic utilities
│   │   ├── hash_chain.py       # Row hash chaining logic
│   │   ├── merkle_tree.py      # Merkle tree builder/validator
│   │   └── verifier.py         # Verifies hash chains & Merkle proofs
│   │
│   ├── cli/                    # Command-line interface
│   │   ├── __init__.py         # CLI package initializer
│   │   ├── main.py             # `maria-ledger` entrypoint
│   │   ├── verify.py           # `verify` command
│   │   ├── diff.py             # `diff` command
│   │   └── audit.py            # Scheduled integrity check
│   │
│   ├── utils/                  # Utility functions
│   │   ├── config.py           # Load DB credentials and settings
│   │   ├── logger.py           # Standard logging
│   │   └── formatter.py        # Pretty table & diff rendering
│   │
│   └── web/                    # Optional: Web UI or dashboard
│       ├── app.py              # Web application
│       └── templates/          # HTML templates
│
├── examples/                   # Example scripts and notebooks
│   ├── setup_ledger.sql        # Example trigger setup
│   └── demo_notebook.ipynb     # Walk-through demo
│
└── tests/                      # Unit tests
    ├── test_hash_chain.py      # Tests for hash chaining
    ├── test_merkle_tree.py     # Tests for Merkle tree logic
    ├── test_cli_verify.py      # Tests for CLI verification
    └── test_diff_view.py       # Tests for diff rendering
```

## Features

- **Tamper-Evident Database**: Uses hash chains to ensure data integrity.
- **Merkle Trees**: Efficiently validate large datasets.
- **System Versioning**: Tracks historical changes to data.
- **CLI Tools**: Verify, audit, and diff database states.
- **Extensible Design**: Modular components for cryptography, database, and utilities.

## Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Set Up Database**:
   - Create the `ledger_customers` table and triggers using `triggers.sql`.
   - Example:
     ```sql
     SOURCE examples/setup_ledger.sql;
     ```

3. **Run Tests**:
   ```bash
   pytest tests/
   ```

4. **Run Verifier**:
   ```bash
   python -m maria_ledger.crypto.verifier ledger_customers
   ```

## Usage

- **Verify Hash Chain**:
  ```bash
  python -m maria_ledger.crypto.verifier ledger_customers
  ```

- **Compute Merkle Root**:
  ```bash
  python -m maria_ledger.db.merkle_service
  ```

- **Audit Database**:
  ```bash
  python -m maria_ledger.cli.audit
  ```

## Theory

### Hash Chains
A hash chain is a sequence of hashes where each hash depends on the previous one. This ensures that any modification to a single element in the chain invalidates all subsequent hashes. In this project:
- Each row in the `ledger_customers` table contains a `row_hash` and a `prev_hash`.
- The `row_hash` is computed using the row's data and the `prev_hash`.
- This creates a tamper-evident chain of records.

### Merkle Trees
Merkle trees are a data structure used to efficiently verify the integrity of large datasets. They work by:
- Hashing individual data blocks (leaves).
- Pairing and hashing these hashes recursively to form a tree.
- The root hash (Merkle root) represents the entire dataset.

In this project:
- The `merkle_service.py` computes the Merkle root for the `ledger_customers` table.
- This root can be stored in the `ledger_roots` table for later verification.

### System Versioning
System versioning ensures that historical changes to data are tracked. In MariaDB:
- The `WITH SYSTEM VERSIONING` clause enables automatic tracking of row versions.
- This allows querying historical states of the table, which is essential for verifying the integrity of past data.

### Use Case
The combination of hash chains, Merkle trees, and system versioning makes this project suitable for:
- Auditing financial transactions.
- Ensuring the integrity of sensitive data.
- Detecting unauthorized modifications in databases.

## Contributing

Contributions are welcome! Please fork the repository and submit a pull request.






# working
INSERT/UPDATE --> Trigger computes row_hash = SHA256(data + prev_hash)
      ↓
ledger_customers : chain of hashes per row
      ↓
Nightly job --> builds Merkle root of all row_hashes
      ↓
ledger_roots : stores root_hash checkpoints
      ↓
Verifier --> recomputes root and compares to stored checkpoint
      ↓
Tamper Detected?  ✅ or ❌




















Phase 3+ (Hardening / Scaling):
→ Optionally rebuild the verifier daemon in **Go** for:

Better parallelism verifying large tables.

Stronger deployment story (binary + no dependency hell).

Phase 1:

- `triggers.sql`: Create temporal table + trigger hooks to maintain a hash chain.
- `hash_chain.py`: Compute row hashes and chain logic in Python (same algo DB uses).
- `verifier.py`: Pull rows from DB, recompute hashes, verify integrity.
- `connection.py`: Minimal connector for verification script.

