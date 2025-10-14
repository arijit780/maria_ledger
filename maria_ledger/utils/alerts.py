import smtplib
from email.mime.text import MIMEText
import requests
from maria_ledger.utils.config import get_alert_config

def send_alert(subject: str, body: str):
    cfg = get_alert_config()
    if cfg.get("teams_webhook"):
        requests.post(cfg["teams_webhook"], json={"text": f"**{subject}**\n{body}"})
    if cfg.get("email"):
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = cfg["email"]["from"]
        msg["To"] = ", ".join(cfg["email"]["to"])
        with smtplib.SMTP(cfg["email"]["host"], cfg["email"]["port"]) as server:
            server.sendmail(cfg["email"]["from"], cfg["email"]["to"], msg.as_string())
