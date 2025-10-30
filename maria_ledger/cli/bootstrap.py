import typer
from rich.console import Console
import json

from maria_ledger.db.connection import get_connection
from maria_ledger.db.merkle_service import compute_and_store_merkle_root
from maria_ledger.cli.reconstruct import json_serial

console = Console()

def get_trigger_sql(table_name: str) -> str:
    """Generates the SQL for all three triggers for a given table."""
    return f"""
    CREATE TRIGGER {table_name}_after_insert
    AFTER INSERT ON {table_name} FOR EACH ROW
    BEGIN
        INSERT INTO ledger (table_name, record_id, op_type, new_payload)
        VALUES ('{table_name}', NEW.id, 'INSERT', JSON_OBJECT(
            'id', NEW.id, 'name', NEW.name, 'email', NEW.email
            -- Add other columns from your table here
        ));
    END;
    
    CREATE TRIGGER {table_name}_after_update
    AFTER UPDATE ON {table_name} FOR EACH ROW
    BEGIN
        INSERT INTO ledger (table_name, record_id, op_type, old_payload, new_payload)
        VALUES ('{table_name}', NEW.id, 'UPDATE',
            JSON_OBJECT('id', OLD.id, 'name', OLD.name, 'email', OLD.email),
            JSON_OBJECT('id', NEW.id, 'name', NEW.name, 'email', NEW.email)
            -- Add other columns from your table here
        );
    END;

    CREATE TRIGGER {table_name}_after_delete
    AFTER DELETE ON {table_name} FOR EACH ROW
    BEGIN
        INSERT INTO ledger (table_name, record_id, op_type, old_payload)
        VALUES ('{table_name}', OLD.id, 'DELETE', JSON_OBJECT(
            'id', OLD.id, 'name', OLD.name, 'email', OLD.email
            -- Add other columns from your table here
        ));
    END;
    """

def bootstrap_command(
    table_name: str = typer.Argument(..., help="The existing table to bring under ledger control."),
):
    """
    Bootstrap an existing table by snapshotting its data into the ledger,
    attaching triggers, and creating an initial Merkle root checkpoint.
    """
    console.print(f"Bootstrapping table [bold cyan]{table_name}[/]...")
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Step 1: Snapshot existing data into the ledger
        console.print("  - Step 1: Snapshotting existing data...")
        cursor.execute(f"SELECT * FROM {table_name}")
        rows = cursor.fetchall()

        if not rows:
            console.print(f"  - [yellow]Warning:[/yellow] Table '{table_name}' is empty. Skipping snapshot.")
        else:
            snapshot_data = []
            for row in rows:
                record_id = row.get('id')
                if not record_id:
                    raise ValueError("Table must have an 'id' column to be bootstrapped.")
                
                # Convert row to a JSON-serializable format
                payload_str = json.dumps(row, default=json_serial)
                snapshot_data.append((table_name, str(record_id), 'INSERT', payload_str))

            # Bulk insert the snapshot
            insert_sql = "INSERT INTO ledger (table_name, record_id, op_type, new_payload) VALUES (%s, %s, %s, %s)"
            cursor.executemany(insert_sql, snapshot_data)
            conn.commit()
            console.print(f"  - [green]✓[/green] Snapshotted {len(rows)} records into the ledger.")

        # Step 2: Attach triggers
        console.print("  - Step 2: Attaching database triggers...")
        # Note: This is a simplified example. A real implementation would need to
        # dynamically generate the JSON_OBJECT based on the table's columns.
        # For now, it assumes a 'id', 'name', 'email' schema.
        trigger_sql = get_trigger_sql(table_name)
        for statement in trigger_sql.split(';'):
            if statement.strip():
                cursor.execute(statement)
        conn.commit()
        console.print("  - [green]✓[/green] Attached INSERT, UPDATE, and DELETE triggers.")

        # Step 3: Create initial Merkle root checkpoint
        console.print("  - Step 3: Creating initial Merkle root checkpoint...")
        root = compute_and_store_merkle_root(table_name)
        if root:
            console.print(f"  - [green]✓[/green] Initial checkpoint created. Root: [bold white]{root}[/bold white]")
        else:
            console.print("  - [yellow]Warning:[/yellow] Could not create checkpoint, table might be empty.")

        console.print(f"\n[bold green]✅ Bootstrap Complete![/bold green] Table '{table_name}' is now under ledger control.")

    except Exception as e:
        conn.rollback()
        console.print(f"\n[bold red]❌ ERROR:[/bold red] {e}")
        console.print("Bootstrap failed. Any changes have been rolled back.")
        raise typer.Exit(code=1)
    finally:
        cursor.close()
        conn.close()