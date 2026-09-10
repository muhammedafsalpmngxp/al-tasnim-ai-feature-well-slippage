import logging

from fastapi import APIRouter, HTTPException

from app.database.connection import get_connection

from app.services.investigation import (
    get_evidence_bundle,
    WellNotFoundError
)
from app.services.llm import (
    build_portfolio_evidence,
    summarize_portfolio,
    summarize_well,
    portfolio_highlight_terms,
    LLMUnavailable,
    MODEL
)
from app.services.slipped_wells import get_slipped_wells
from app.services.summary import get_well_summary


# ============================================================
# ROUTER
# ============================================================

router = APIRouter(
    prefix="/api/insights",
    tags=["Insights"]
)

logger = logging.getLogger(__name__)


# ============================================================
# PORTFOLIO NARRATIVE
# ============================================================

@router.get("/portfolio")
def portfolio_insight():

    connection = None

    try:

        connection = get_connection()

        summary = get_well_summary(connection)

        # Why the non-due wells are non-due, for the narrative.
        df = get_slipped_wells(connection)

        reason_breakdown = {}

        if not df.empty:
            non_due = df[df["due_status"] == "NON_DUE"]

            reason_breakdown = {
                str(reason): int(count)
                for reason, count in (
                    non_due["kpi_miss_reason"]
                    .fillna("(none recorded)")
                    .value_counts()
                    .head(8)
                    .items()
                )
            }

        evidence = build_portfolio_evidence(summary, reason_breakdown)

        return {
            "success": True,
            "model": MODEL,
            "counts": summary,
            "summary": summarize_portfolio(evidence),
            "highlight_terms": portfolio_highlight_terms(reason_breakdown)
        }

    except LLMUnavailable as exc:

        logger.warning("Portfolio insight unavailable: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=f"AI summary unavailable: {exc}"
        ) from exc

    except ValueError as exc:

        logger.warning("Unable to build portfolio insight: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Database configuration is invalid or incomplete."
        ) from exc

    except Exception as exc:

        logger.exception("Portfolio insight failed")
        raise HTTPException(
            status_code=500,
            detail="Unable to build the portfolio summary. Check the server logs."
        ) from exc

    finally:

        if connection is not None:
            connection.close()


# ============================================================
# PER-WELL NARRATIVE
# ============================================================

@router.get("/well/{well_id}")
def well_insight(well_id: int):

    if well_id <= 0:
        raise HTTPException(status_code=400, detail="Invalid well_id")

    connection = None

    try:

        connection = get_connection()

        # One pass through the authoritative SQL. The model is handed the
        # compact AI evidence from the SAME bundle the dashboard renders,
        # so the prose and the dashboard cannot diverge and the database
        # is never interpreted a second time.
        bundle = get_evidence_bundle(connection, well_id)

        return {
            "success": True,
            "well_id": well_id,
            "model": MODEL,
            "summary": summarize_well(bundle["ai"]),
            "highlight_terms": bundle["highlight_terms"]
        }

    except WellNotFoundError as exc:

        logger.warning("Well not found: %s", exc)
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    except LLMUnavailable as exc:

        logger.warning("Well insight unavailable for %s: %s", well_id, exc)
        raise HTTPException(
            status_code=503,
            detail=f"AI summary unavailable: {exc}"
        ) from exc

    except ValueError as exc:

        logger.warning("Unable to build insight for well %s: %s", well_id, exc)
        raise HTTPException(
            status_code=503,
            detail="Database configuration is invalid or incomplete."
        ) from exc

    except Exception as exc:

        logger.exception("Well insight failed for %s", well_id)
        raise HTTPException(
            status_code=500,
            detail="Unable to build the well summary. Check the server logs."
        ) from exc

    finally:

        if connection is not None:
            connection.close()
