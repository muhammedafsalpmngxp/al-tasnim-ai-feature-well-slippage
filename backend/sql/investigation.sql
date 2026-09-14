/*
===============================================================================
AL-TASNIM WELL SLIPPAGE AI
DELAY-FOCUSED INVESTIGATION QUERY

Purpose:
    Return only the database evidence needed to answer:
    "Why is this well delayed?"

Hierarchy:
    WELL
      -> MILESTONES
      -> ACTIVITY / WBS DESCRIPTION
           -> TASK

Important:
    - task_code comes ONLY from [well].[task_daily]
    - activity_id is derived from task_code
    - activity_code / master_crew_code come from [dbo].[mapping_master]
    - activity_group_description is used as the WBS/activity description
      from [dbo].[activity_master_csv]
    - No data-quality columns are returned
    - No WBS master columns are returned
    - READ-ONLY SELECT/CTE query
===============================================================================
*/

DECLARE @WellId INT = 37857;
DECLARE @Today DATE = CAST(GETDATE() AS DATE);


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
        wm.flowline_const_progress

    FROM [AlTasnimBI].[well].[well_master] AS wm

    WHERE wm.eng_completion_date IS NULL
        AND CONVERT(VARCHAR(50), wm.well_id)
            = CONVERT(VARCHAR(50), @WellId)
),


/* ============================================================================
   WELL MILESTONES
   ============================================================================ */

WellMilestones AS
(
    SELECT
        aw.*,

        /* Deadlines */

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


        /* Pegging */

        CASE
            WHEN aw.ex_rig_on_date IS NULL
                THEN 'DATA_QUALITY_ISSUE'

            WHEN aw.pegged_date IS NULL
             AND @Today > DATEADD(day, -60, aw.ex_rig_on_date)
                THEN 'MISSED'

            WHEN aw.pegged_date IS NULL
                THEN 'PENDING'

            WHEN aw.pegged_date < DATEADD(day, -60, aw.ex_rig_on_date)
                THEN 'AHEAD_OF_SCHEDULE'

            WHEN aw.pegged_date = DATEADD(day, -60, aw.ex_rig_on_date)
                THEN 'ON_SCHEDULE'

            ELSE 'DELAYED'
        END AS pegging_status,


        CASE
            WHEN aw.ex_rig_on_date IS NULL
                THEN NULL

            WHEN aw.pegged_date IS NOT NULL
                THEN DATEDIFF(
                    day,
                    DATEADD(day, -60, aw.ex_rig_on_date),
                    aw.pegged_date
                )

            WHEN aw.pegged_date IS NULL
             AND @Today > DATEADD(day, -60, aw.ex_rig_on_date)
                THEN DATEDIFF(
                    day,
                    DATEADD(day, -60, aw.ex_rig_on_date),
                    @Today
                )

            ELSE 0
        END AS pegging_variance_days,


        /* FLAF */

        CASE
            WHEN aw.ex_rig_on_date IS NULL
                THEN 'DATA_QUALITY_ISSUE'

            WHEN aw.flaf_issue_date IS NULL
             AND @Today > DATEADD(day, -90, aw.ex_rig_on_date)
                THEN 'MISSED'

            WHEN aw.flaf_issue_date IS NULL
                THEN 'PENDING'

            WHEN aw.flaf_issue_date < DATEADD(day, -90, aw.ex_rig_on_date)
                THEN 'AHEAD_OF_SCHEDULE'

            WHEN aw.flaf_issue_date = DATEADD(day, -90, aw.ex_rig_on_date)
                THEN 'ON_SCHEDULE'

            ELSE 'DELAYED'
        END AS flaf_status,


        CASE
            WHEN aw.ex_rig_on_date IS NULL
                THEN NULL

            WHEN aw.flaf_issue_date IS NOT NULL
                THEN DATEDIFF(
                    day,
                    DATEADD(day, -90, aw.ex_rig_on_date),
                    aw.flaf_issue_date
                )

            WHEN aw.flaf_issue_date IS NULL
             AND @Today > DATEADD(day, -90, aw.ex_rig_on_date)
                THEN DATEDIFF(
                    day,
                    DATEADD(day, -90, aw.ex_rig_on_date),
                    @Today
                )

            ELSE 0
        END AS flaf_variance_days,


        /* Construction */

        CASE
            WHEN aw.ex_rig_on_date IS NULL
                THEN 'DATA_QUALITY_ISSUE'

            WHEN @Today > DATEADD(day, -1, aw.ex_rig_on_date)
             AND aw.rig_on_date IS NULL
                THEN 'MISSED'

            WHEN aw.rig_on_date IS NULL
                THEN 'PENDING'

            ELSE 'RIG_ON_OCCURRED'
        END AS construction_status,


        CASE
            WHEN aw.ex_rig_on_date IS NULL
                THEN NULL

            WHEN @Today > DATEADD(day, -1, aw.ex_rig_on_date)
             AND aw.rig_on_date IS NULL
                THEN DATEDIFF(
                    day,
                    DATEADD(day, -1, aw.ex_rig_on_date),
                    @Today
                )

            ELSE 0
        END AS construction_lag_days,


        /* Hook-up */

        CASE
            WHEN aw.eng_completion_date IS NOT NULL
                THEN 'COMPLETED'

            WHEN aw.rig_off_date IS NOT NULL
             AND @Today > DATEADD(day, 2, aw.rig_off_date)
                THEN 'HOOKUP_DEADLINE_PASSED'

            WHEN aw.rig_off_date IS NULL
             AND aw.ex_rig_off_date IS NOT NULL
             AND @Today > DATEADD(day, 2, aw.ex_rig_off_date)
                THEN 'HOOKUP_DEADLINE_FORECAST_PASSED'

            WHEN aw.rig_off_date IS NULL
             AND aw.ex_rig_off_date IS NULL
                THEN 'DATA_QUALITY_ISSUE'

            ELSE 'NOT_YET_DUE'
        END AS hookup_status

    FROM ActiveWell AS aw
),


/* ============================================================================
   CURRENT TASK HISTORY
   ============================================================================ */

NormalizedTaskHistory AS
(
    SELECT
        td.id,
        td.ActionOn,

        LTRIM(RTRIM(td.task_code)) AS task_code,

        td.schedule_id,
        td.project_id,
        td.well_id,

        td.planned,
        td.progress,
        td.completed,

        td.target_start,
        td.target_end,

        CASE
            WHEN td.actual_start = '19000101'
                THEN NULL
            ELSE td.actual_start
        END AS actual_start,

        CASE
            WHEN td.actual_end = '19000101'
                THEN NULL
            ELSE td.actual_end
        END AS actual_end,

        /* Crew / resource evidence */
        td.planned_crew,
        td.crew_type_id,
        td.crew_id,
        td.emp_id,

        /* Quantity / productivity evidence */
        td.data_hours,
        td.data_qty,
        td.daily_actual_quantity,
        td.daily_actual_hours

    FROM [AlTasnimBI].[well].[task_daily] AS td

    INNER JOIN ActiveWell AS aw
        ON CONVERT(VARCHAR(50), aw.well_id)
           = CONVERT(VARCHAR(50), td.well_id)

    WHERE td.task_code IS NOT NULL
      AND LTRIM(RTRIM(td.task_code)) <> ''
),


CurrentTasks AS
(
    SELECT *
    FROM
    (
        SELECT
            nth.*,

            ROW_NUMBER() OVER
            (
                PARTITION BY nth.well_id, nth.task_code

                ORDER BY
                    nth.ActionOn DESC,
                    nth.id DESC

            ) AS rn

        FROM NormalizedTaskHistory AS nth
    ) AS ranked

    WHERE ranked.rn = 1
),


/* ============================================================================
   TASK -> ACTIVITY
   ============================================================================ */

TaskActivities AS
(
    SELECT
        ct.*,

        CASE
            WHEN CHARINDEX('-', ct.task_code) > 0
                THEN LEFT(
                    ct.task_code,
                    CHARINDEX('-', ct.task_code) - 1
                )
            ELSE NULL
        END AS activity_id

    FROM CurrentTasks AS ct
),


/* ============================================================================
   ACTIVITY MAPPING
   Keep only values needed for delay explanation.

   mapping_master:
       Activity_ID
       New_Activity_Code
       New_Crew_code
   ============================================================================ */

ActivityMapping AS
(
    SELECT
        CAST(mm.Activity_ID AS NVARCHAR(255)) AS activity_id,

        CASE
            WHEN COUNT(DISTINCT mm.New_Activity_Code) = 1
                THEN MAX(mm.New_Activity_Code)
            ELSE NULL
        END AS activity_code,

        CASE
            WHEN COUNT(DISTINCT mm.New_Crew_code) = 1
                THEN MAX(mm.New_Crew_code)
            ELSE NULL
        END AS master_crew_code

    FROM [AlTasnimBI].[dbo].[mapping_master] AS mm

    GROUP BY
        CAST(mm.Activity_ID AS NVARCHAR(255))
),


/* ============================================================================
   ACTIVITY / WBS DESCRIPTION

   activity_group_description is treated as the WBS/activity description
   for the AI investigation.

   Only return a description when one unique description exists.
   ============================================================================ */

ActivityDescription AS
(
    SELECT
        amc.activity_code,

        CASE
            WHEN COUNT(DISTINCT amc.activity_group_description) = 1
                THEN MAX(amc.activity_group_description)
            ELSE NULL
        END AS activity_group_description

    FROM [AlTasnimBI].[dbo].[activity_master_csv] AS amc

    GROUP BY
        amc.activity_code
),


/* ============================================================================
   ENRICHED DELAY EVIDENCE
   ============================================================================ */

EnrichedTasks AS
(
    SELECT

        /* Well */

        wm.well_id,
        wm.project_id,

        wm.ex_rig_on_date,
        wm.rig_on_date,

        wm.ex_rig_off_date,
        wm.rig_off_date,

        wm.pegged_date,
        wm.pegging_deadline,
        wm.pegging_status,
        wm.pegging_variance_days,

        wm.flaf_issue_date,
        wm.flaf_deadline,
        wm.flaf_status,
        wm.flaf_variance_days,

        wm.construction_deadline,
        wm.construction_status,
        wm.construction_lag_days,

        wm.hookup_deadline,
        wm.hookup_status,

        wm.eng_completion_date,

        wm.well_progress_raw,
        wm.flowline_const_progress,


        /* Task */

        ta.id AS task_daily_id,
        ta.task_code,
        ta.activity_id,
        ta.schedule_id,
        ta.project_id AS task_project_id,
        ta.ActionOn,

        ta.progress,
        CASE
            WHEN ta.progress IS NOT NULL
             AND ta.progress >= 0
             AND ta.progress <= 1
                THEN ta.progress * 100.0
            ELSE NULL
        END AS progress_percent,

        ta.completed,

        ta.target_start,
        ta.target_end,
        ta.actual_start,
        ta.actual_end,


        /* Task crew */

        ta.planned_crew,
        ta.crew_type_id,
        ta.crew_id,
        ta.emp_id,


        /* Activity */

        am.activity_code,
        ad.activity_group_description,
        am.master_crew_code,


        /* Schedule status */

        CASE
            WHEN ta.target_start IS NULL
                THEN 'DATA_ISSUE'

            WHEN ta.actual_start IS NULL
             AND @Today > ta.target_start
                THEN 'NOT_STARTED_START_SLIPPING'

            WHEN ta.actual_start IS NULL
             AND @Today <= ta.target_start
                THEN 'NOT_STARTED_ON_SCHEDULE'

            WHEN ta.actual_start < ta.target_start
                THEN 'STARTED_AHEAD_OF_SCHEDULE'

            WHEN ta.actual_start = ta.target_start
                THEN 'STARTED_ON_SCHEDULE'

            WHEN ta.actual_start > ta.target_start
                THEN 'START_DELAYED'

            ELSE 'DATA_ISSUE'
        END AS start_status,


        CASE
            WHEN ta.actual_start IS NOT NULL
             AND ta.target_start IS NOT NULL
                THEN DATEDIFF(
                    day,
                    ta.target_start,
                    ta.actual_start
                )

            WHEN ta.actual_start IS NULL
             AND ta.target_start IS NOT NULL
             AND @Today > ta.target_start
                THEN DATEDIFF(
                    day,
                    ta.target_start,
                    @Today
                )

            ELSE 0
        END AS start_variance_days,


        CASE
            WHEN ta.target_end IS NULL
                THEN 'DATA_ISSUE'

            WHEN ta.actual_end IS NOT NULL
             AND ta.actual_end < ta.target_end
                THEN 'COMPLETED_EARLY_ACCELERATED'

            WHEN ta.actual_end IS NOT NULL
             AND ta.actual_end = ta.target_end
                THEN 'COMPLETED_ON_SCHEDULE'

            WHEN ta.actual_end IS NOT NULL
             AND ta.actual_end > ta.target_end
                THEN 'COMPLETED_LATE'

            WHEN ta.actual_end IS NULL
             AND @Today < ta.target_end
                THEN 'IN_PROGRESS_NOT_LATE'

            WHEN ta.actual_end IS NULL
             AND @Today = ta.target_end
                THEN 'DUE_TODAY'

            WHEN ta.actual_end IS NULL
             AND @Today > ta.target_end
                THEN 'OVERDUE_CURRENT_TASK_LAGGING'

            ELSE 'DATA_ISSUE'
        END AS end_status,


        CASE
            WHEN ta.actual_end IS NOT NULL
             AND ta.target_end IS NOT NULL
                THEN DATEDIFF(
                    day,
                    ta.target_end,
                    ta.actual_end
                )

            WHEN ta.actual_end IS NULL
             AND ta.target_end IS NOT NULL
             AND @Today > ta.target_end
                THEN DATEDIFF(
                    day,
                    ta.target_end,
                    @Today
                )

            ELSE 0
        END AS end_variance_days,


        CASE
            WHEN ta.actual_end IS NOT NULL
                THEN 'COMPLETED'

            WHEN ta.actual_start IS NULL
             AND ta.target_start IS NOT NULL
             AND @Today < ta.target_start
                THEN 'NOT_STARTED'

            WHEN ta.actual_start IS NULL
             AND ta.target_start IS NOT NULL
             AND @Today >= ta.target_start
                THEN 'NOT_STARTED_LATE'

            WHEN ta.actual_start IS NOT NULL
             AND ta.actual_end IS NULL
                THEN 'IN_PROGRESS'

            ELSE 'UNKNOWN'
        END AS execution_status,


        CASE
            WHEN
                (
                    ta.actual_end IS NULL
                    AND ta.target_end IS NOT NULL
                    AND @Today > ta.target_end
                )
                OR
                (
                    ta.actual_end IS NOT NULL
                    AND ta.target_end IS NOT NULL
                    AND ta.actual_end > ta.target_end
                )
                THEN 'RED_DELAYED'

            WHEN
                ta.actual_start IS NULL
                AND ta.target_start IS NOT NULL
                AND @Today > ta.target_start
                THEN 'AMBER_START_SLIPPING'

            WHEN
                ta.actual_start IS NOT NULL
                AND ta.target_start IS NOT NULL
                AND ta.actual_start > ta.target_start
                THEN 'AMBER_START_DELAYED'

            ELSE 'GREEN_OR_ON_SCHEDULE'
        END AS schedule_risk,


        /* Quantity / productivity */

        CASE
            WHEN ta.data_qty IS NOT NULL
              OR ta.daily_actual_quantity IS NOT NULL
                THEN
                    CASE
                        WHEN ta.data_qty IS NOT NULL
                         AND ta.daily_actual_quantity IS NOT NULL
                         AND ta.data_qty = ta.daily_actual_quantity
                            THEN 'BOTH_SAME'

                        WHEN ta.data_qty IS NOT NULL
                         AND ta.daily_actual_quantity IS NOT NULL
                         AND ta.data_qty <> ta.daily_actual_quantity
                            THEN 'BOTH_CONFLICT'

                        WHEN ta.data_qty IS NOT NULL
                            THEN 'DATA_QTY_ONLY'

                        ELSE 'DAILY_QUANTITY_ONLY'
                    END

            ELSE 'NO_QUANTITY_SOURCE'
        END AS quantity_source,


        CASE
            WHEN ta.data_qty IS NOT NULL
             AND ta.daily_actual_quantity IS NOT NULL
             AND ta.data_qty = ta.daily_actual_quantity
                THEN ta.data_qty

            WHEN ta.data_qty IS NOT NULL
             AND ta.daily_actual_quantity IS NULL
                THEN ta.data_qty

            WHEN ta.data_qty IS NULL
             AND ta.daily_actual_quantity IS NOT NULL
                THEN ta.daily_actual_quantity

            ELSE NULL
        END AS observed_quantity,


        CASE
            WHEN ta.planned IS NOT NULL
             AND ta.data_qty IS NOT NULL
                THEN
                    CASE
                        WHEN ta.planned - ta.data_qty < 0
                            THEN 0
                        ELSE ta.planned - ta.data_qty
                    END

            WHEN ta.planned IS NOT NULL
             AND ta.daily_actual_quantity IS NOT NULL
                THEN
                    CASE
                        WHEN ta.planned - ta.daily_actual_quantity < 0
                            THEN 0
                        ELSE ta.planned - ta.daily_actual_quantity
                    END

            ELSE NULL
        END AS calculated_remaining_quantity,


        CASE
            WHEN ta.data_hours IS NOT NULL
             AND ta.data_hours > 0
             AND ta.data_qty IS NOT NULL
                THEN CAST(
                    ta.data_qty / ta.data_hours
                    AS DECIMAL(18,4)
                )

            WHEN ta.daily_actual_hours IS NOT NULL
             AND ta.daily_actual_hours > 0
             AND ta.daily_actual_quantity IS NOT NULL
                THEN CAST(
                    ta.daily_actual_quantity / ta.daily_actual_hours
                    AS DECIMAL(18,4)
                )

            ELSE NULL
        END AS current_productivity_qty_per_hour,


        CASE
            WHEN ta.data_hours IS NOT NULL
             AND ta.data_hours > 0
             AND ta.data_qty IS NOT NULL
                THEN 'TASK_DAILY_DATA'

            WHEN ta.daily_actual_hours IS NOT NULL
             AND ta.daily_actual_hours > 0
             AND ta.daily_actual_quantity IS NOT NULL
                THEN 'DAILY_EXECUTION_DATA'

            ELSE 'NO_PRODUCTIVITY_SOURCE'
        END AS productivity_source,


        CASE
            WHEN
                (
                    ta.data_hours IS NOT NULL
                    AND ta.data_hours > 0
                    AND ta.data_qty IS NOT NULL
                )
                OR
                (
                    ta.daily_actual_hours IS NOT NULL
                    AND ta.daily_actual_hours > 0
                    AND ta.daily_actual_quantity IS NOT NULL
                )
                THEN 'PRODUCTIVITY_AVAILABLE'

            ELSE 'PRODUCTIVITY_NOT_AVAILABLE'
        END AS productivity_data_status

    FROM WellMilestones AS wm

    INNER JOIN TaskActivities AS ta
        ON CONVERT(VARCHAR(50), ta.well_id)
           = CONVERT(VARCHAR(50), wm.well_id)

    LEFT JOIN ActivityMapping AS am
        ON CAST(am.activity_id AS NVARCHAR(255))
           = CAST(ta.activity_id AS NVARCHAR(255))

    LEFT JOIN ActivityDescription AS ad
        ON ad.activity_code = am.activity_code
)


/* ============================================================================
   FINAL RESULT
   ============================================================================ */

SELECT
    well_id,
    project_id,

    ex_rig_on_date,
    rig_on_date,
    ex_rig_off_date,
    rig_off_date,

    pegged_date,
    pegging_deadline,
    pegging_status,
    pegging_variance_days,

    flaf_issue_date,
    flaf_deadline,
    flaf_status,
    flaf_variance_days,

    construction_deadline,
    construction_status,
    construction_lag_days,

    hookup_deadline,
    hookup_status,

    eng_completion_date,

    well_progress_raw,
    flowline_const_progress,

    task_daily_id,
    task_code,
    activity_id,
    schedule_id,
    task_project_id,
    ActionOn,

    activity_code,
    activity_group_description,
    master_crew_code,

    target_start,
    target_end,
    actual_start,
    actual_end,

    start_status,
    start_variance_days,

    end_status,
    end_variance_days,

    progress,
    progress_percent,
    completed,

    execution_status,
    schedule_risk,

    planned_crew,
    crew_type_id,
    crew_id,
    emp_id,

    quantity_source,
    observed_quantity,
    calculated_remaining_quantity,

    current_productivity_qty_per_hour,
    productivity_source,
    productivity_data_status

FROM EnrichedTasks

ORDER BY
    CASE
        WHEN schedule_risk = 'RED_DELAYED'
            THEN 1
        WHEN schedule_risk IN
            ('AMBER_START_SLIPPING', 'AMBER_START_DELAYED')
            THEN 2
        ELSE 3
    END,

    CASE
        WHEN end_variance_days > 0
            THEN end_variance_days
        ELSE 0
    END DESC,

    CASE
        WHEN start_variance_days > 0
            THEN start_variance_days
        ELSE 0
    END DESC,

    target_end,
    task_code;
