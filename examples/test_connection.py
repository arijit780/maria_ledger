from maria_ledger.db.connection import get_connection

def test_conn():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT VERSION()")
    print("Connected to MariaDB:", cur.fetchone()[0])
    cur.close()
    conn.close()

if __name__ == "__main__":
    test_conn()
