import mysql.connector
from maria_ledger.utils.config import get_config

def get_connection():
    cfg = get_config()
    db = cfg.get("db", {})
    return mysql.connector.connect(
        host=db.get("host", "localhost"),
        port=db.get("port", 3306),
        user=db["user"],
        password=db["password"],
        database=db["name"]
    )
