"""
JSON-safety helpers shared by the evidence, UI and AI-evidence layers.

Extracted so that the transformation modules and the risk scorer can all
use them without importing each other (the previous arrangement had
risk.py importing from investigation.py and investigation.py importing
risk.py back inside a function body).

These functions FORMAT values. They never calculate anything.
"""

import math


def clean_value(value):

    """Make a database value safe for json.dump, without changing it."""

    if value is None:
        return None

    if isinstance(value, dict):
        return {str(key): clean_value(item) for key, item in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [clean_value(item) for item in value]

    # --------------------------------------------------------
    # date / datetime / time / datetimeoffset-like objects
    # --------------------------------------------------------

    if hasattr(value, "isoformat"):
        return value.isoformat()

    # --------------------------------------------------------
    # Bytes
    # --------------------------------------------------------

    if isinstance(value, bytes):

        try:
            return value.decode("utf-8")

        except UnicodeDecodeError:

            try:
                return value.decode("utf-16")

            except UnicodeDecodeError:
                return value.hex()

    # --------------------------------------------------------
    # Integers stay integers — IDs must not become 14.0
    # --------------------------------------------------------

    if isinstance(value, (bool, int)):
        return value

    # --------------------------------------------------------
    # Decimal and similar numeric objects
    # --------------------------------------------------------

    if hasattr(value, "__float__") and not isinstance(value, str):

        try:
            numeric_value = float(value)

            if math.isnan(numeric_value) or math.isinf(numeric_value):
                return None

            return numeric_value

        except (TypeError, ValueError):
            pass

    return value


def to_number(value):

    """
    Keep whole numbers whole: SQL DECIMAL and pandas float columns would
    otherwise render a whole day count with a trailing ".0", and a whole
    progress percentage with a long decimal tail.
    """

    if value is None or isinstance(value, bool):
        return value

    if isinstance(value, int):
        return value

    if isinstance(value, float):

        if math.isnan(value) or math.isinf(value):
            return None

        return int(value) if value.is_integer() else round(value, 2)

    # Decimal from SQL Server
    if hasattr(value, "__float__") and not isinstance(value, str):

        try:
            return to_number(float(value))

        except (TypeError, ValueError):
            return value

    return value


def clean_date(value):

    """Date-only ISO string, or None. Never invents a date."""

    cleaned = clean_value(value)

    if isinstance(cleaned, str) and cleaned:
        return cleaned.split("T")[0]

    return cleaned


def normalize_text(value):

    """
    Collapse whitespace in free-text database content — activity
    descriptions in the source data contain embedded newlines.
    """

    if not isinstance(value, str):
        return value

    return " ".join(value.split()) or None
