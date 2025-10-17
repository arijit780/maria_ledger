from datetime import datetime
from typing import Union

def pretty_time(dt: Union[datetime, str]) -> str:
    """
    Format a datetime object or ISO timestamp string into a human-readable format.
    
    Args:
        dt: datetime object or ISO format string
        
    Returns:
        Formatted string like "2025-10-14 14:30:00 UTC"
    """
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
    
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")