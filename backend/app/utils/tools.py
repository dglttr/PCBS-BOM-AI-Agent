from datetime import datetime
from typing import List, Dict


def get_weekday_names(dates: List[str]) -> Dict[str, str]:
    """Gets the weekday name for each date.
    
    Args:
        dates (List[str]): List of dates to check in YYYY-MM-DD format.
        
    Returns:
        Dict[str, str]: Dictionary mapping each date to its weekday name (Monday, Tuesday, etc.).
    """
    result = {}
    for date in dates:
        weekday = datetime.strptime(date, "%Y-%m-%d").strftime("%A")
        result[date] = weekday
    return result 