import logging

from fastapi import APIRouter, HTTPException

from app.database.connection import get_connection

from app.services.investigation import (
    get_well_risk_assessment,
    update_investigation_json,
    WellNotFoundError
)


# ============================================================
# ROUTER
# ============================================================

router = APIRouter(
    prefix="/api",
    tags=["Investigation"]
)

logger = logging.getLogger(__name__)


# ============================================================
# INVESTIGATION ENDPOINT
# ============================================================

@router.get(
    "/well/{well_id}/investigation"
)
def investigate_well(
    well_id: int
):

    # --------------------------------------------------------
    # Validate well ID
    # --------------------------------------------------------

    if well_id <= 0:

        raise HTTPException(
            status_code=400,
            detail="Invalid well_id"
        )


    connection = None


    try:

        logger.info("Starting investigation for well %s", well_id)


        # ----------------------------------------------------
        # DATABASE CONNECTION
        # ----------------------------------------------------

        connection = get_connection()


        logger.info("Database connection established")


        # ----------------------------------------------------
        # BUILD RISK ASSESSMENT
        # ----------------------------------------------------

        summary = get_well_risk_assessment(
            connection,
            well_id
        )


        # ----------------------------------------------------
        # UPDATE JSON
        # ----------------------------------------------------

        update_investigation_json(
            summary
        )


        logger.info("Investigation completed successfully for well %s", well_id)


        # ----------------------------------------------------
        # API RESPONSE
        # ----------------------------------------------------

        return summary


    except WellNotFoundError as exc:

        logger.warning("Well not found: %s", exc)
        raise HTTPException(
            status_code=404,
            detail=str(exc)
        ) from exc

    except ValueError as exc:

        logger.warning("Unable to investigate well %s: %s", well_id, exc)
        raise HTTPException(
            status_code=503,
            detail="Database configuration is invalid or incomplete."
        ) from exc

    except Exception as exc:

        logger.exception("Investigation failed for well %s", well_id)
        raise HTTPException(
            status_code=500,
            detail="Unable to investigate this well. Check the server logs."
        ) from exc


    finally:

        # ----------------------------------------------------
        # CLOSE DATABASE CONNECTION
        # ----------------------------------------------------

        if connection is not None:

            connection.close()

            logger.info("Database connection closed")
