from datetime import datetime
from typing import List, Dict
import math


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


def calculator(expressions: List[str]) -> List[str]:
    """
    Evaluates a list of basic mathematical expressions passed as strings.

    Supports: +, -, *, /, %, **, (), and basic arithmetic.

    Args:
        expressions (List[str]): A list of strings, each containing a mathematical expression.

    Returns:
        List[str]: A list of results for each evaluated expression or error messages.
    """
    allowed_names = {
        k: v for k, v in math.__dict__.items() if not k.startswith("__")
    }

    results = []
    for expression in expressions:
        try:
            result = eval(expression, {"__builtins__": None}, allowed_names)
            results.append(str(result))
        except Exception as e:
            results.append(f"Error: {str(e)}")
    return results
