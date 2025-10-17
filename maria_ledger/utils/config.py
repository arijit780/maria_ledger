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

def get_alert_config():
    """
    Get alert configuration from environment variables or config file.
    Returns dict with alert settings.
    """
    cfg = get_config()
    alerts = cfg.get("alerts", {})
    
    return {
        "enabled": alerts.get("enabled", False),
        "email": {
            "smtp_host": os.getenv("ALERT_SMTP_HOST", alerts.get("smtp_host", "smtp.gmail.com")),
            "smtp_port": int(os.getenv("ALERT_SMTP_PORT", alerts.get("smtp_port", 587))),
            "username": os.getenv("ALERT_EMAIL_USER", alerts.get("email_user", "")),
            "password": os.getenv("ALERT_EMAIL_PASS", alerts.get("email_pass", "")),
            "from_addr": os.getenv("ALERT_FROM_EMAIL", alerts.get("from_email", "")),
            "to_addrs": os.getenv("ALERT_TO_EMAILS", alerts.get("to_emails", "")).split(","),
        }
    }
