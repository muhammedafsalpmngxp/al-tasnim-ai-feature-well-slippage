import math
import logging
import time

import pandas as pd

from fastapi import APIRouter
from fastapi import HTTPException

from app.database.connection import (
    get_connection
)

from app.services.console_log import log_stage

from app.services.slipped_wells import (
    get_slipped_wells
)
from app.services.calculation import (
    calculate_well_metrics
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

        query_started_at = time.monotonic()

        df = get_slipped_wells(
            connection
        )

        log_stage(
            "Wells",
            f"exec ok: {len(df)} slipped well(s) in {time.monotonic() - query_started_at:.2f}s",
            ok=True,
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

        calc_started_at = time.monotonic()

        calculations = calculate_well_metrics(
            connection,
            records,
        )

        log_stage(
            "Calculation",
            f"ok: total={calculations['total_wells']} live={calculations['live_wells']} "
            f"slipped={calculations['slipped_wells']} in "
            f"{time.monotonic() - calc_started_at:.2f}s",
            ok=True,
        )

        return {
            "success": True,
            "count": len(records),
            "calculations": calculations,
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
