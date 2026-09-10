import math
import logging

import pandas as pd

from fastapi import APIRouter
from fastapi import HTTPException

from app.database.connection import (
    get_connection
)

from app.services.slipped_wells import (
    get_slipped_wells,
    get_well_list
)

from app.services.summary import (
    get_well_summary
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
# GET WELL SUMMARY
# ============================================================

@router.get("/wells/summary")
def wells_summary():

    connection = None

    try:

        connection = get_connection()

        return get_well_summary(
            connection
        )

    except ValueError as exc:
        logger.warning("Unable to load well summary: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Database configuration is invalid or incomplete."
        ) from exc

    except Exception:
        logger.exception("Unable to load well summary")

        raise HTTPException(
            status_code=500,
            detail="Unable to load well summary. Check the server logs."
        )

    finally:

        if connection:

            connection.close()


# ============================================================
# GET ALL WELLS (PICKER)
# ============================================================
#
# Every well on record with its category, ascending by well_id. The
# picker shows the id alone, so nothing else is returned.

@router.get("/wells/list")
def wells_list():

    connection = None

    try:

        connection = get_connection()

        wells = get_well_list(connection)

        return {
            "success": True,
            "count": len(wells),
            "wells": wells
        }

    except ValueError as exc:
        logger.warning("Unable to load the well list: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Database configuration is invalid or incomplete."
        ) from exc

    except Exception:
        logger.exception("Unable to load the well list")

        raise HTTPException(
            status_code=500,
            detail="Unable to load the well list. Check the server logs."
        )

    finally:

        if connection:

            connection.close()


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
