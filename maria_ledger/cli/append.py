import typer
import json
from maria_ledger.db.connection import get_connection
from maria_ledger.utils.logger import get_logger

logger = get_logger("cli-append")

def append_record_command(table: str, data: str):
    """Append a new record to a ledger table."""
    try:
        record = json.loads(data)
    except json.JSONDecodeError:
        typer.echo("Error: Invalid JSON data", err=True)
        raise typer.Exit(1)
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Build INSERT query dynamically from JSON keys
    columns = list(record.keys())
    values = [record[col] for col in columns]
    placeholders = ["%s"] * len(columns)
    
    query = f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join(placeholders)})"
    
    try:
        cursor.execute(query, values)
        conn.commit()
        typer.echo(f"✓ Record added to {table}")
    except Exception as e:
        logger.error(f"Failed to insert record: {e}")
        typer.echo(f"Error: {str(e)}", err=True)
        raise typer.Exit(1)
    finally:
        cursor.close()
        conn.close()