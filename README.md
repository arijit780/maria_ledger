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




IDEA AFTER PHASE 5 
:
Perfect mindset 💥 — that’s *exactly* what wins hackathons.

✅ You already have a **solid end-to-end core system** (ledger + crypto + CLI).
Now the goal isn’t just polish — it’s **technical flair** that proves:

> “I didn’t just make it work; I made it *smart, secure, and insightful*.”

Let’s plan a *Phase 5+ roadmap* — advanced features that build directly on your current architecture (no UI fluff, just deep backend brilliance).

---

## ⚡️ Phase 5+ — “Pro Mode” Features for Hackathon

These are modular, technically impressive add-ons that *show mastery* of cryptography, databases, and systems thinking.

---

### 🧩 **1. Ledger Cross-Verification (Proof-of-Trust between Tables)**

**Concept:**
Build a cross-table integrity proof — e.g. `ledger_customers` and `ledger_orders` reference each other’s latest Merkle roots.
If one is altered, the proof chain breaks in both.

**Why it’s cool:**
Shows “interlinked ledger integrity” — a step toward blockchain-like multi-table verification.

**Implementation:**

* Add `reference_root` column in `ledger_roots` that stores another table’s last root.
* CLI command:

  ```bash
  maria-ledger trustmap ledger_customers ledger_orders
  ```

  → verifies the pair’s cross-proof integrity.

---

### 🔄 **2. Chain Continuity Validator**

**Concept:**
Detect *silent history rewrites* — e.g., if someone backdated a record or reinserted old hashes.

**Why it’s cool:**
Moves beyond data validation → **forensic detection of tampering attempts**.

**Implementation:**

* Scan all rows ordered by `valid_from`.
* Check `prev_hash` consistency **and** continuity timestamps.
* Detect retroactive inserts (`valid_from` < last verified root timestamp).
* CLI:

  ```bash
  maria-ledger forensic ledger_customers
  ```

  → flags any time gaps or forked chains.

---

### 🌲 **3. Merkle Proof Export / Verification API**

**Concept:**
Generate portable Merkle proofs for audit verification without DB access.

**Why it’s cool:**
Lets auditors verify a single record’s authenticity cryptographically — like a *mini blockchain proof*.

**Implementation:**

* Extend `merkle_tree.py` to export:

  ```python
  {
    "leaf": "<hash>",
    "path": ["hash1", "hash2", ...],
    "root": "<merkle_root>"
  }
  ```
* CLI command:

  ```bash
  maria-ledger proof ledger_customers --id 1234
  ```

  → exports JSON proof
* Validator tool:

  ```bash
  maria-ledger verify-proof proof.json
  ```

---

### 📦 **4. Immutable Export — “Ledger Snapshot Manifest”**

**Concept:**
Generate a signed manifest (JSON or YAML) summarizing the entire ledger state with its Merkle root and SHA256 signature.

**Why it’s cool:**

* Makes your ledger externally portable and provable.
* Auditors can re-verify offline.

**Implementation:**

* Use Python `hashlib` + `cryptography` to sign manifest.
* CLI:

  ```bash
  maria-ledger snapshot ledger_customers --out manifest.json
  maria-ledger verify-snapshot manifest.json
  ```

---

### 🧠 **5. Machine-Readable Integrity Metrics**

**Concept:**
Emit structured metadata on ledger health for automated monitoring.

**Why it’s cool:**
Turns your ledger into a **self-reporting system**.

**Output example:**

```json
{
  "table": "ledger_customers",
  "rows_verified": 15023,
  "broken_links": 0,
  "latest_merkle_root": "abc123...",
  "last_verified": "2025-10-11T02:00:00Z"
}
```

* CLI flag:

  ```bash
  maria-ledger verify ledger_customers --json
  ```
* Combine with dashboards or monitoring scripts.

---

### ⚙️ **6. Audit Lineage Replay (Optional but killer demo)**

**Concept:**
Replay the *entire evolution* of a row, like a “Git log” for data.

**Why it’s cool:**
Auditors can time-travel through changes interactively.

**CLI:**

```bash
maria-ledger timeline ledger_customers --id 123
```

→ prints:

```
[2024-01-02] name=Alice email=alice@x.com
[2024-06-14] name=Alice M. email=alice@x.com
[2025-01-05] name=Alice M. email=alice.m@example.com
```

---

## 🧭 Suggested Next 12-Day Sprint Plan

| Day Range     | Focus                                        | Output                                  |
| ------------- | -------------------------------------------- | --------------------------------------- |
| **Day 1–2**   | Finish Phase 4 (audit.py + nightly verifier) | Automated trust checker                 |
| **Day 3–4**   | Chain continuity validator                   | `maria-ledger forensic`                 |
| **Day 5–6**   | Merkle proof export + verify                 | `proof` + `verify-proof`                |
| **Day 7–8**   | Snapshot manifest export + signature         | Portable proof file                     |
| **Day 9–10**  | Ledger timeline diff                         | `timeline` command                      |
| **Day 11–12** | Polish + final demo script                   | `demo_notebook.ipynb` + README showcase |

---

## 💡 Hackathon Pitch Line (you can literally use this)

> “Maria-Ledger brings verifiable history to MariaDB — every row is cryptographically chained, every snapshot is provable, and every audit trail is portable. It’s like Git for your data, but with cryptographic trust.”

---

Would you like me to start with **Phase 4 (audit + auto-verifier)** next, or skip straight to one of the *showcase features* (like forensic check or proof export)?
