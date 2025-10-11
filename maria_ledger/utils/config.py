import yaml
import os

def get_config(path=None):
    """
    Loads YAML configuration from either:
      - explicit path argument, or
      - environment variable MARIA_LEDGER_CONFIG, or
      - default file ./config.yaml
    """
    path = path or os.getenv("MARIA_LEDGER_CONFIG", "config.yaml")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path) as f:
        return yaml.safe_load(f)
    

def get_db_config():
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", 3306)),
        "user": os.getenv("DB_USER", "arijitsen"),
        "password": os.getenv("DB_PASSWORD", "123"),  # same as you set above
        "name": os.getenv("DB_NAME", "ledger_customers"),
    }
