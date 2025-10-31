# import typer
# from tabulate import tabulate
# from maria_ledger.db.connection import get_connection
# from maria_ledger.crypto.hash_chain import compute_row_hash
# from maria_ledger.utils.logger import get_logger

# logger = get_logger("cli-verify-rows")

# def verify_rows_command(
#     table: str,
#     verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed verification info"),
#     json_output: bool = typer.Option(False, "--json", help="Output result in JSON format")
# ):
#     """Verify individual row hashes and chain integrity."""
#     conn = get_connection()
#     cursor = conn.cursor(dictionary=True)
    
#     try:
#         cursor.execute(f"""
#             SELECT id, name, email, valid_from, row_hash, prev_hash 
#             FROM {table} 
#             ORDER BY valid_from ASC
#         """)
#         rows = cursor.fetchall()
        
#         if not rows:
#             typer.echo(f"No rows found in table {table}")
#             return
        
#         issues = []
#         last_hash = "0" * 64  # genesis hash
        
#         for row in rows:
#             # Get row data without hash fields
#             data = {
#                 k: v for k, v in row.items()
#                 if k not in ("row_hash", "prev_hash")
#             }
            
#             # Compute expected hash
#             expected_hash = compute_row_hash(data, row['prev_hash'])
            
#             # Check both hash correctness and chain continuity
#             hash_ok = expected_hash == row['row_hash']
#             chain_ok = row['prev_hash'] == last_hash
            
#             if not (hash_ok and chain_ok):
#                 issues.append({
#                     'id': row['id'],
#                     'type': 'hash_mismatch' if not hash_ok else 'chain_break',
#                     'stored_hash': row['row_hash'],
#                     'computed_hash': expected_hash,
#                     'valid_from': row['valid_from']
#                 })
                
#             if verbose:
#                 status = "✓" if (hash_ok and chain_ok) else "✗"
#                 typer.echo(f"[{status}] Row {row['id']} ({row['valid_from']})")
#                 if not hash_ok:
#                     typer.echo(f"    Expected hash: {expected_hash}")
#                     typer.echo(f"    Stored hash:   {row['row_hash']}")
#                 if not chain_ok:
#                     typer.echo(f"    Chain break: prev_hash != last_hash")
                    
#             last_hash = row['row_hash']
        
#         if json_output:
#             import json
#             typer.echo(json.dumps({
#                 'table': table,
#                 'total_rows': len(rows),
#                 'issues': issues
#             }, default=str, indent=2))
#         else:
#             if not issues:
#                 typer.echo(f"[✓] All {len(rows)} rows verified successfully")
#             else:
#                 typer.echo(f"[!] Found {len(issues)} integrity issues:")
#                 issues_table = [
#                     [i['id'], i['type'], i['valid_from']]
#                     for i in issues
#                 ]
#                 typer.echo(tabulate(
#                     issues_table,
#                     headers=['Row ID', 'Issue Type', 'Valid From'],
#                     tablefmt='psql'
#                 ))
                
#     finally:
#         cursor.close()
#         conn.close()