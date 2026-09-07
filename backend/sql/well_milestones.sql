/* ============================================================
   AL-TASNIM
   WELL SLIPPAGE AI
   ONE WELL - MILESTONE / STATUS HEADER

   INPUT:
       @WellId

   PURPOSE:
       Standalone extraction of the well-level milestone status
       and deadline computation from investigation.sql's
       ActiveWell / WellMilestones CTEs, so the risk-scoring
       layer has an authoritative well header even when the well
       currently has zero flagged tasks in investigation.sql's
       (delayed/at-risk only) result set.

   IMPORTANT:
       This is the SAME deterministic logic as investigation.sql
       sections 1-2. It is not a re-derivation - keep both in
       sync if the milestone rules change.
   ============================================================ */


DECLARE @WellId INT = ?;

DECLARE @Today DATE = CAST(GETDATE() AS DATE);


/* ============================================================
   1. ACTIVE WELL
   ============================================================ */

WITH ActiveWell AS
(
    SELECT

        wm.well_id,
        wm.project_id,

        wm.ex_rig_on_date,
        wm.rig_on_date,

        wm.ex_rig_off_date,
        wm.rig_off_date,

        wm.pegged_date,
        wm.flaf_issue_date,

        wm.eng_completion_date,

        wm.progress AS well_progress_raw,

        wm.flowline_const_progress,

        wm.material_avail_date,

        wm.cluster_code,
        wm.rig_id,
        wm.station_id,
        wm.status_id,
        wm.well_type_id,

        wm.kpi_miss_reason

    FROM [AlTasnimBI].[well].[well_master] AS wm

    WHERE wm.eng_completion_date IS NULL
      AND wm.well_id = @WellId
),


/* ============================================================
   2. WELL MILESTONES
   ============================================================ */

WellMilestones AS
(
    SELECT

        aw.*,


        CASE
            WHEN aw.ex_rig_on_date IS NOT NULL
                THEN DATEADD(day, -60, aw.ex_rig_on_date)
            ELSE NULL
        END AS pegging_deadline,


        CASE
            WHEN aw.ex_rig_on_date IS NOT NULL
                THEN DATEADD(day, -90, aw.ex_rig_on_date)
            ELSE NULL
        END AS flaf_deadline,


        CASE
            WHEN aw.ex_rig_on_date IS NOT NULL
                THEN DATEADD(day, -1, aw.ex_rig_on_date)
            ELSE NULL
        END AS construction_deadline,


        CASE

            WHEN aw.rig_off_date IS NOT NULL
                THEN DATEADD(day, 2, aw.rig_off_date)

            WHEN aw.ex_rig_off_date IS NOT NULL
                THEN DATEADD(day, 2, aw.ex_rig_off_date)

            ELSE NULL

        END AS hookup_deadline,


        CASE

            WHEN aw.ex_rig_on_date IS NULL
                THEN 'DATA_QUALITY_ISSUE'

            WHEN aw.pegged_date IS NULL
             AND @Today >
                 DATEADD(day, -60, aw.ex_rig_on_date)
                THEN 'MISSED'

            WHEN aw.pegged_date IS NULL
                THEN 'PENDING'

            WHEN aw.pegged_date <
                 DATEADD(day, -60, aw.ex_rig_on_date)
                THEN 'AHEAD_OF_SCHEDULE'

            WHEN aw.pegged_date =
                 DATEADD(day, -60, aw.ex_rig_on_date)
                THEN 'ON_SCHEDULE'

            ELSE 'DELAYED'

        END AS pegging_status,


        CASE

            WHEN aw.ex_rig_on_date IS NULL
                THEN 'DATA_QUALITY_ISSUE'

            WHEN aw.flaf_issue_date IS NULL
             AND @Today >
                 DATEADD(day, -90, aw.ex_rig_on_date)
                THEN 'MISSED'

            WHEN aw.flaf_issue_date IS NULL
                THEN 'PENDING'

            WHEN aw.flaf_issue_date <
                 DATEADD(day, -90, aw.ex_rig_on_date)
                THEN 'AHEAD_OF_SCHEDULE'

            WHEN aw.flaf_issue_date =
                 DATEADD(day, -90, aw.ex_rig_on_date)
                THEN 'ON_SCHEDULE'

            ELSE 'DELAYED'

        END AS flaf_status,


        CASE

            WHEN aw.ex_rig_on_date IS NULL
                THEN 'DATA_QUALITY_ISSUE'

            WHEN @Today >
                 DATEADD(day, -1, aw.ex_rig_on_date)
             AND aw.rig_on_date IS NULL
                THEN 'MISSED'

            WHEN aw.rig_on_date IS NULL
                THEN 'PENDING'

            ELSE 'RIG_ON_OCCURRED'

        END AS construction_status,


        CASE

            WHEN aw.eng_completion_date IS NOT NULL
                THEN 'COMPLETED'

            WHEN aw.rig_off_date IS NOT NULL
             AND @Today >
                 DATEADD(day, 2, aw.rig_off_date)
                THEN 'HOOKUP_DEADLINE_PASSED'

            WHEN aw.rig_off_date IS NULL
             AND aw.ex_rig_off_date IS NOT NULL
             AND @Today >
                 DATEADD(day, 2, aw.ex_rig_off_date)
                THEN 'HOOKUP_DEADLINE_FORECAST_PASSED'

            WHEN aw.rig_off_date IS NULL
             AND aw.ex_rig_off_date IS NULL
                THEN 'DATA_QUALITY_ISSUE'

            ELSE 'NOT_YET_DUE'

        END AS hookup_status

    FROM ActiveWell AS aw
)


SELECT * FROM WellMilestones;
