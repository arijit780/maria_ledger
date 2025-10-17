import smtplib
from email.mime.text import MIMEText
from typing import Optional
from maria_ledger.utils.config import get_alert_config
from maria_ledger.utils.logger import get_logger

logger = get_logger("alerts")

def send_alert(subject: str, body: str) -> None:
    """
    Send an alert via configured channels (email).
    
    Args:
        subject: Alert subject/title
        body: Alert message body
    """
    cfg = get_alert_config()
    
    if not cfg["enabled"]:
        logger.info("Alerts disabled, skipping notification")
        return
        
    email_cfg = cfg["email"]
    if all([email_cfg["smtp_host"], email_cfg["username"], email_cfg["password"]]):
        try:
            msg = MIMEText(body)
            msg["Subject"] = subject
            msg["From"] = email_cfg["from_addr"]
            msg["To"] = ", ".join(email_cfg["to_addrs"])
            
            with smtplib.SMTP(email_cfg["smtp_host"], email_cfg["smtp_port"]) as server:
                server.starttls()
                server.login(email_cfg["username"], email_cfg["password"])
                server.send_message(msg)
                logger.info(f"Alert email sent to {email_cfg['to_addrs']}")
        except Exception as e:
            logger.error(f"Failed to send alert email: {str(e)}")
    else:
        logger.warning("Email alerts not configured properly")
