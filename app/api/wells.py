import math
import logging

import pandas as pd

from fastapi import APIRouter
from fastapi import HTTPException

from app.database.connection import (
    get_connection
)

from app.services.slipped_wells import (
    get_slipped_wells
)


router = APIRouter(
    prefix="/api",
    tags=["Wells"]
)

logger = logging.getLogger(__name__)


# ============================================================
# JSON CLEANER
# ============================================================

def clean_value(value):

    if value is None:
        return None

    try:

        if pd.isna(value):
            return None

    except Exception:
        pass

    if isinstance(value, float):

        if math.isnan(value):
            return None

        if math.isinf(value):
            return None

    if hasattr(value, "isoformat"):

        return value.isoformat()

    return value


# ============================================================
# GET SLIPPED WELLS
# ============================================================

@router.get("/slipped-wells")
def slipped_wells():

    connection = None

    try:

        connection = get_connection()

        df = get_slipped_wells(
            connection
        )

        records = []

        for row in df.to_dict(
            orient="records"
        ):

            clean_row = {
                key: clean_value(value)
                for key, value
                in row.items()
            }

            records.append(
                clean_row
            )

        return {
            "success": True,
            "count": len(records),
            "wells": records
        }

    except ValueError as exc:
        logger.warning("Unable to load slipped wells: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Database configuration is invalid or incomplete."
        ) from exc

    except Exception:
        logger.exception("Unable to load slipped wells")

        raise HTTPException(
            status_code=500,
            detail="Unable to load slipped wells. Check the server logs."
        )

    finally:

        if connection:

            connection.close()
