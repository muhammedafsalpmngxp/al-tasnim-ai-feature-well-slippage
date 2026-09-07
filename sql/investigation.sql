/* ============================================================
   AL-TASNIM
   WELL SLIPPAGE AI
   ONE WELL - DETERMINISTIC EXTRACTION / AI EVIDENCE LAYER
   ============================================================

   INPUT:
       @WellId

   PURPOSE:
       Provide a clean deterministic evidence layer for the
       Well Slippage AI.

   CURRENT SCOPE:
       - Active well filtering
       - Well milestone status
       - Current logical task extraction
       - Planner schedule variance
       - Activity mapping
       - Activity classification
       - WBS mapping
       - Quantity evidence
       - Productivity evidence
       - Resource-data evidence
       - Data-quality detection
       - Deterministic AI schedule classification

   NOT YET INCLUDED:
       - activity_task_plan integration
       - historical productivity model
       - task forecast date
       - activity forecast
       - WBS forecast
       - well forecast
       - resource shortage inference
       - root-cause inference
       - recovery forecast
       - recovery recommendation

   IMPORTANT:
       This query is an evidence/extraction layer.
       It does not silently repair questionable database data.
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
        wm.well_type_id

    FROM [AlTasnimBI].[well].[well_master] AS wm

    /* ========================================================
       COMPLETED-WELL EXCLUSION MUST BE FIRST
       ======================================================== */

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


        /* ====================================================
           DEADLINES
           ==================================================== */

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


        /* ====================================================
           PEGGING STATUS
           ==================================================== */

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


        /* ====================================================
           PEGGING VARIANCE
           ==================================================== */

        CASE

            WHEN aw.ex_rig_on_date IS NULL
                THEN NULL

            WHEN aw.pegged_date IS NOT NULL

                THEN DATEDIFF
                (
                    day,
                    DATEADD(day, -60, aw.ex_rig_on_date),
                    aw.pegged_date
                )

            WHEN aw.pegged_date IS NULL
             AND @Today >
                 DATEADD(day, -60, aw.ex_rig_on_date)

                THEN DATEDIFF
                (
                    day,
                    DATEADD(day, -60, aw.ex_rig_on_date),
                    @Today
                )

            ELSE 0

        END AS pegging_variance_days,


        /* ====================================================
           FLAF STATUS
           ==================================================== */

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


        /* ====================================================
           FLAF VARIANCE
           ==================================================== */

        CASE

            WHEN aw.ex_rig_on_date IS NULL
                THEN NULL

            WHEN aw.flaf_issue_date IS NOT NULL

                THEN DATEDIFF
                (
                    day,
                    DATEADD(day, -90, aw.ex_rig_on_date),
                    aw.flaf_issue_date
                )

            WHEN aw.flaf_issue_date IS NULL
             AND @Today >
                 DATEADD(day, -90, aw.ex_rig_on_date)

                THEN DATEDIFF
                (
                    day,
                    DATEADD(day, -90, aw.ex_rig_on_date),
                    @Today
                )

            ELSE 0

        END AS flaf_variance_days,


        /* ====================================================
           CONSTRUCTION STATUS

           This is NOT actual construction completion.

           Approved rule:
               today > ex_rig_on_date - 1
               AND rig_on_date IS NULL
               => MISSED
           ==================================================== */

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


        /* ====================================================
           CONSTRUCTION LAG
           ==================================================== */

        CASE

            WHEN aw.ex_rig_on_date IS NULL
                THEN NULL

            WHEN @Today >
                 DATEADD(day, -1, aw.ex_rig_on_date)
             AND aw.rig_on_date IS NULL

                THEN DATEDIFF
                (
                    day,
                    DATEADD(day, -1, aw.ex_rig_on_date),
                    @Today
                )

            ELSE 0

        END AS construction_lag_days,


        /* ====================================================
           HOOK-UP STATUS
           ==================================================== */

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

        END AS hookup_status,


        /* ====================================================
           WELL MASTER DATA QUALITY
           ==================================================== */

        CASE
            WHEN aw.ex_rig_on_date IS NULL
                THEN 1
            ELSE 0
        END AS dq_missing_ex_rig_on_date,


        CASE
            WHEN aw.project_id IS NULL
                THEN 1
            ELSE 0
        END AS dq_missing_master_project,


        CASE

            WHEN aw.rig_on_date IS NOT NULL
             AND aw.ex_rig_on_date IS NOT NULL
             AND aw.rig_on_date < aw.ex_rig_on_date
                THEN 1

            ELSE 0

        END AS dq_rig_on_before_expected,


        CASE

            WHEN aw.rig_off_date IS NOT NULL
             AND aw.rig_on_date IS NOT NULL
             AND aw.rig_off_date < aw.rig_on_date
                THEN 1

            ELSE 0

        END AS dq_rig_off_before_rig_on

    FROM ActiveWell AS aw
),


/* ============================================================
   3. NORMALIZED TASK HISTORY
   ============================================================ */

NormalizedTaskHistory AS
(
    SELECT

        td.id,

        td.ActionOn,

        LTRIM(RTRIM(td.task_code)) AS task_code,

        td.schedule_id,
        td.project_id,

        td.required,
        td.planned,
        td.duration,
        td.remaining_duration,

        td.progress,

        td.ready,
        td.completed,

        td.[plan],

        td.committed_start,
        td.committed_end,

        td.target_start,
        td.target_end,


        /* 1900-01-01 -> NULL */

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


        /* P6 secondary */

        td.startDate AS p6_start_date,
        td.endDate AS p6_end_date,


        /* Resources */

        td.planned_crew,

        td.well_id,

        td.data_hours,
        td.data_qty,

        td.data_employees,

        td.task_assignee,
        td.supervisor_email,

        td.url,

        td.task_data,
        td.daily_data,

        td.created_at,
        td.updated_at,

        td.daily_ph_name,

        td.daily_equipment_ids,
        td.daily_employee_ids,

        td.daily_actual_quantity,
        td.daily_actual_hours,

        td.daily_completed,

        td.time_stamp,

        td.crew_type_id,
        td.crew_id,
        td.emp_id,
        td.uom_id

    FROM [AlTasnimBI].[well].[task_daily] AS td

    INNER JOIN ActiveWell AS aw
        ON aw.well_id = td.well_id

    WHERE td.task_code IS NOT NULL
      AND LTRIM(RTRIM(td.task_code)) <> ''
),


/* ============================================================
   4. CURRENT LOGICAL TASKS
   ============================================================ */

CurrentTaskRanking AS
(
    SELECT

        nth.*,

        ROW_NUMBER() OVER
        (
            PARTITION BY
                nth.well_id,
                nth.task_code

            ORDER BY
                nth.ActionOn DESC,
                nth.updated_at DESC,
                nth.id DESC

        ) AS rn

    FROM NormalizedTaskHistory AS nth
),


CurrentTasks AS
(
    SELECT

        ctr.*

    FROM CurrentTaskRanking AS ctr

    WHERE ctr.rn = 1
),


/* ============================================================
   5. TASK -> ACTIVITY ID
   ============================================================ */

TaskActivities AS
(
    SELECT

        ct.*,

        CASE

            WHEN CHARINDEX('-', ct.task_code) > 0

                THEN LEFT
                (
                    ct.task_code,

                    CHARINDEX('-', ct.task_code) - 1
                )

            ELSE NULL

        END AS activity_id

    FROM CurrentTasks AS ct
),


/* ============================================================
   6. ACTIVITY MAPPING DIAGNOSTIC
   ============================================================ */

ActivityMappingDiagnostic AS
(
    SELECT

        amm.activity_id,

        COUNT(*) AS mapping_row_count,

        COUNT(DISTINCT amm.activity_code)
            AS distinct_activity_code_count,

        COUNT(DISTINCT amm.project_type)
            AS distinct_project_type_count,

        COUNT(DISTINCT amm.composition_code)
            AS distinct_composition_code_count,

        COUNT(DISTINCT amm.uom)
            AS distinct_uom_count,

        COUNT(DISTINCT amm.norms)
            AS distinct_norms_count,

        COUNT(DISTINCT amm.class_b_ptw)
            AS distinct_class_b_ptw_count,

        COUNT(DISTINCT amm.rfi)
            AS distinct_rfi_count

    FROM [AlTasnimBI].[dbo].[activity_master_mapping] AS amm

    GROUP BY
        amm.activity_id
),


/* ============================================================
   7. ACTIVITY MAPPING VALUES
   ============================================================ */

ActivityMapping AS
(
    SELECT

        amd.activity_id,

        amd.mapping_row_count,

        amd.distinct_activity_code_count,
        amd.distinct_project_type_count,
        amd.distinct_composition_code_count,

        amd.distinct_uom_count,
        amd.distinct_norms_count,
        amd.distinct_class_b_ptw_count,
        amd.distinct_rfi_count,


        CASE

            WHEN amd.distinct_activity_code_count = 1

                THEN
                (
                    SELECT TOP (1)
                        amm.activity_code

                    FROM [AlTasnimBI].[dbo].[activity_master_mapping] AS amm

                    WHERE amm.activity_id = amd.activity_id
                      AND amm.activity_code IS NOT NULL
                )

            ELSE NULL

        END AS activity_code,


        CASE

            WHEN amd.distinct_project_type_count = 1

                THEN
                (
                    SELECT TOP (1)
                        amm.project_type

                    FROM [AlTasnimBI].[dbo].[activity_master_mapping] AS amm

                    WHERE amm.activity_id = amd.activity_id
                      AND amm.project_type IS NOT NULL
                )

            ELSE NULL

        END AS project_type,


        CASE

            WHEN amd.distinct_composition_code_count = 1

                THEN
                (
                    SELECT TOP (1)
                        amm.composition_code

                    FROM [AlTasnimBI].[dbo].[activity_master_mapping] AS amm

                    WHERE amm.activity_id = amd.activity_id
                      AND amm.composition_code IS NOT NULL
                )

            ELSE NULL

        END AS composition_code,


        CASE

            WHEN amd.distinct_uom_count = 1

                THEN
                (
                    SELECT TOP (1)
                        amm.uom

                    FROM [AlTasnimBI].[dbo].[activity_master_mapping] AS amm

                    WHERE amm.activity_id = amd.activity_id
                      AND amm.uom IS NOT NULL
                )

            ELSE NULL

        END AS activity_uom,


        CASE

            WHEN amd.distinct_norms_count = 1

                THEN
                (
                    SELECT TOP (1)
                        amm.norms

                    FROM [AlTasnimBI].[dbo].[activity_master_mapping] AS amm

                    WHERE amm.activity_id = amd.activity_id
                      AND amm.norms IS NOT NULL
                )

            ELSE NULL

        END AS norms,


        CASE

            WHEN amd.distinct_class_b_ptw_count = 1

                THEN
                (
                    SELECT TOP (1)
                        amm.class_b_ptw

                    FROM [AlTasnimBI].[dbo].[activity_master_mapping] AS amm

                    WHERE amm.activity_id = amd.activity_id
                      AND amm.class_b_ptw IS NOT NULL
                )

            ELSE NULL

        END AS class_b_ptw,


        CASE

            WHEN amd.distinct_rfi_count = 1

                THEN
                (
                    SELECT TOP (1)
                        amm.rfi

                    FROM [AlTasnimBI].[dbo].[activity_master_mapping] AS amm

                    WHERE amm.activity_id = amd.activity_id
                      AND amm.rfi IS NOT NULL
                )

            ELSE NULL

        END AS rfi

    FROM ActivityMappingDiagnostic AS amd
),


/* ============================================================
   8. ACTIVITY CSV DIAGNOSTIC
   ============================================================ */

ActivityCSVDiagnostic AS
(
    SELECT

        amc.activity_code,

        COUNT(*) AS csv_row_count,

        COUNT(DISTINCT amc.activity_group_description)
            AS distinct_description_count,

        COUNT(DISTINCT amc.crew_code)
            AS distinct_crew_code_count

    FROM [AlTasnimBI].[dbo].[activity_master_csv] AS amc

    GROUP BY
        amc.activity_code
),


/* ============================================================
   9. ACTIVITY CSV VALUES
   ============================================================ */

ActivityCSV AS
(
    SELECT

        acd.activity_code,

        acd.csv_row_count,

        acd.distinct_description_count,
        acd.distinct_crew_code_count,


        CASE

            WHEN acd.distinct_description_count = 1

                THEN
                (
                    SELECT TOP (1)
                        amc.activity_group_description

                    FROM [AlTasnimBI].[dbo].[activity_master_csv] AS amc

                    WHERE amc.activity_code = acd.activity_code
                      AND amc.activity_group_description IS NOT NULL
                )

            ELSE NULL

        END AS activity_group_description,


        CASE

            WHEN acd.distinct_crew_code_count = 1

                THEN
                (
                    SELECT TOP (1)
                        amc.crew_code

                    FROM [AlTasnimBI].[dbo].[activity_master_csv] AS amc

                    WHERE amc.activity_code = acd.activity_code
                      AND amc.crew_code IS NOT NULL
                )

            ELSE NULL

        END AS master_crew_code

    FROM ActivityCSVDiagnostic AS acd
),


/* ============================================================
   10. WBS ACTIVITY MASTER DIAGNOSTIC
   ============================================================ */

WBSActivityDiagnostic AS
(
    SELECT

        wam.Activity_code,

        COUNT(DISTINCT wam.Activity_id)
            AS distinct_wbs_activity_id_count,

        COUNT(DISTINCT wam.Activity)
            AS distinct_wbs_activity_name_count

    FROM [AlTasnimBI].[wbs].[activity_master] AS wam

    GROUP BY
        wam.Activity_code
),


/* ============================================================
   11. WBS ACTIVITY MASTER VALUES
   ============================================================ */

WBSActivity AS
(
    SELECT

        wad.Activity_code,

        wad.distinct_wbs_activity_id_count,
        wad.distinct_wbs_activity_name_count,


        CASE

            WHEN wad.distinct_wbs_activity_name_count = 1

                THEN
                (
                    SELECT TOP (1)
                        wam.Activity

                    FROM [AlTasnimBI].[wbs].[activity_master] AS wam

                    WHERE wam.Activity_code = wad.Activity_code
                      AND wam.Activity IS NOT NULL
                )

            ELSE NULL

        END AS wbs_activity_name

    FROM WBSActivityDiagnostic AS wad
),


/* ============================================================
   12. WELL WBS DIAGNOSTIC
   ============================================================ */

WellWBSDiagnostic AS
(
    SELECT

        TRY_CONVERT
        (
            INT,
            w.Well_ID_Project_PO
        ) AS well_id,

        w.Activity_code,

        COUNT(*) AS wbs_row_count,

        COUNT(DISTINCT w.WBS_Code)
            AS distinct_wbs_count,

        COUNT(DISTINCT w.Project_Def)
            AS distinct_project_def_count,

        COUNT(DISTINCT w.WD_PRJ)
            AS distinct_wd_prj_count,

        COUNT(DISTINCT w.Plant_Code)
            AS distinct_plant_code_count,

        COUNT(DISTINCT w.Cluster_code)
            AS distinct_cluster_code_count,

        COUNT(DISTINCT w.Well_ID_Project_PO)
            AS distinct_well_id_project_po_count,

        COUNT(DISTINCT w.Category)
            AS distinct_category_count

    FROM [AlTasnimBI].[wbs].[WBS_master] AS w

    INNER JOIN ActiveWell AS aw

        ON TRY_CONVERT
           (
               INT,
               w.Well_ID_Project_PO
           )
           =
           aw.well_id

    GROUP BY

        TRY_CONVERT
        (
            INT,
            w.Well_ID_Project_PO
        ),

        w.Activity_code
),


/* ============================================================
   13. WELL WBS VALUES
   ============================================================ */

WellWBS AS
(
    SELECT

        wd.well_id,
        wd.Activity_code,


        /* ====================================================
           WBS CODE
           ==================================================== */

        CASE

            WHEN wd.distinct_wbs_count = 1

                THEN
                (
                    SELECT TOP (1)
                        w.WBS_Code

                    FROM [AlTasnimBI].[wbs].[WBS_master] AS w

                    WHERE TRY_CONVERT
                          (
                              INT,
                              w.Well_ID_Project_PO
                          )
                          = wd.well_id

                      AND w.Activity_code = wd.Activity_code

                      AND w.WBS_Code IS NOT NULL
                )

            ELSE NULL

        END AS WBS_Code,


        /* ====================================================
           PROJECT DEF
           ==================================================== */

        CASE

            WHEN wd.distinct_project_def_count = 1

                THEN
                (
                    SELECT TOP (1)
                        w.Project_Def

                    FROM [AlTasnimBI].[wbs].[WBS_master] AS w

                    WHERE TRY_CONVERT
                          (
                              INT,
                              w.Well_ID_Project_PO
                          )
                          = wd.well_id

                      AND w.Activity_code = wd.Activity_code

                      AND w.Project_Def IS NOT NULL
                )

            ELSE NULL

        END AS Project_Def,


        /* ====================================================
           WD PRJ
           ==================================================== */

        CASE

            WHEN wd.distinct_wd_prj_count = 1

                THEN
                (
                    SELECT TOP (1)
                        w.WD_PRJ

                    FROM [AlTasnimBI].[wbs].[WBS_master] AS w

                    WHERE TRY_CONVERT
                          (
                              INT,
                              w.Well_ID_Project_PO
                          )
                          = wd.well_id

                      AND w.Activity_code = wd.Activity_code

                      AND w.WD_PRJ IS NOT NULL
                )

            ELSE NULL

        END AS WD_PRJ,


        /* ====================================================
           PLANT
           ==================================================== */

        CASE

            WHEN wd.distinct_plant_code_count = 1

                THEN
                (
                    SELECT TOP (1)
                        w.Plant_Code

                    FROM [AlTasnimBI].[wbs].[WBS_master] AS w

                    WHERE TRY_CONVERT
                          (
                              INT,
                              w.Well_ID_Project_PO
                          )
                          = wd.well_id

                      AND w.Activity_code = wd.Activity_code

                      AND w.Plant_Code IS NOT NULL
                )

            ELSE NULL

        END AS Plant_Code,


        /* ====================================================
           CLUSTER
           ==================================================== */

        CASE

            WHEN wd.distinct_cluster_code_count = 1

                THEN
                (
                    SELECT TOP (1)
                        w.Cluster_code

                    FROM [AlTasnimBI].[wbs].[WBS_master] AS w

                    WHERE TRY_CONVERT
                          (
                              INT,
                              w.Well_ID_Project_PO
                          )
                          = wd.well_id

                      AND w.Activity_code = wd.Activity_code

                      AND w.Cluster_code IS NOT NULL
                )

            ELSE NULL

        END AS Cluster_code,


        /* ====================================================
           WELL ID / PROJECT PO
           ==================================================== */

        CASE

            WHEN wd.distinct_well_id_project_po_count = 1

                THEN
                (
                    SELECT TOP (1)
                        w.Well_ID_Project_PO

                    FROM [AlTasnimBI].[wbs].[WBS_master] AS w

                    WHERE TRY_CONVERT
                          (
                              INT,
                              w.Well_ID_Project_PO
                          )
                          = wd.well_id

                      AND w.Activity_code = wd.Activity_code

                      AND w.Well_ID_Project_PO IS NOT NULL
                )

            ELSE NULL

        END AS Well_ID_Project_PO,


        /* ====================================================
           CATEGORY
           ==================================================== */

        CASE

            WHEN wd.distinct_category_count = 1

                THEN
                (
                    SELECT TOP (1)
                        w.Category

                    FROM [AlTasnimBI].[wbs].[WBS_master] AS w

                    WHERE TRY_CONVERT
                          (
                              INT,
                              w.Well_ID_Project_PO
                          )
                          = wd.well_id

                      AND w.Activity_code = wd.Activity_code

                      AND w.Category IS NOT NULL
                )

            ELSE NULL

        END AS Category,


        /* ====================================================
           COUNTS
           ==================================================== */

        wd.wbs_row_count,

        wd.distinct_wbs_count,

        wd.distinct_project_def_count,
        wd.distinct_wd_prj_count,
        wd.distinct_plant_code_count,
        wd.distinct_cluster_code_count,
        wd.distinct_well_id_project_po_count,
        wd.distinct_category_count,


        /* ====================================================
           CONFLICT FLAGS
           ==================================================== */

        CASE
            WHEN wd.distinct_wbs_count > 1
                THEN 1
            ELSE 0
        END AS dq_wbs_mapping_conflict,


        CASE
            WHEN wd.distinct_project_def_count > 1
                THEN 1
            ELSE 0
        END AS dq_wbs_project_def_conflict,


        CASE
            WHEN wd.distinct_wd_prj_count > 1
                THEN 1
            ELSE 0
        END AS dq_wbs_wd_prj_conflict,


        CASE
            WHEN wd.distinct_plant_code_count > 1
                THEN 1
            ELSE 0
        END AS dq_wbs_plant_conflict,


        CASE
            WHEN wd.distinct_cluster_code_count > 1
                THEN 1
            ELSE 0
        END AS dq_wbs_cluster_conflict,


        CASE
            WHEN wd.distinct_well_id_project_po_count > 1
                THEN 1
            ELSE 0
        END AS dq_wbs_well_reference_conflict,


        CASE
            WHEN wd.distinct_category_count > 1
                THEN 1
            ELSE 0
        END AS dq_wbs_category_conflict

    FROM WellWBSDiagnostic AS wd
),


/* ============================================================
   14. ENRICHED TASKS
   ============================================================ */

EnrichedTasks AS
(
    SELECT

        /* ====================================================
           WELL
           ==================================================== */

        aw.well_id,
        aw.project_id,


        /* ====================================================
           MASTER DATES
           ==================================================== */

        aw.ex_rig_on_date,
        aw.rig_on_date,

        aw.ex_rig_off_date,
        aw.rig_off_date,


        /* ====================================================
           MILESTONES
           ==================================================== */

        aw.pegged_date,
        aw.pegging_deadline,
        aw.pegging_status,
        aw.pegging_variance_days,

        aw.flaf_issue_date,
        aw.flaf_deadline,
        aw.flaf_status,
        aw.flaf_variance_days,

        aw.construction_deadline,
        aw.construction_status,
        aw.construction_lag_days,

        aw.hookup_deadline,
        aw.hookup_status,

        aw.eng_completion_date,


        /* ====================================================
           WELL PROGRESS
           ==================================================== */

        aw.well_progress_raw,
        aw.flowline_const_progress,

        aw.material_avail_date,


        /* ====================================================
           WELL DQ
           ==================================================== */

        aw.dq_missing_ex_rig_on_date,
        aw.dq_missing_master_project,
        aw.dq_rig_on_before_expected,
        aw.dq_rig_off_before_rig_on,


        /* ====================================================
           TASK
           ==================================================== */

        ta.id AS task_daily_id,

        ta.task_code,
        ta.activity_id,

        ta.schedule_id,

        ta.project_id AS task_project_id,

        ta.ActionOn,


        /* ====================================================
           PLANNING
           ==================================================== */

        ta.required,
        ta.planned,

        ta.duration,
        ta.remaining_duration,

        ta.progress,

        ta.ready,
        ta.completed,

        ta.[plan],


        /* ====================================================
           DATES
           ==================================================== */

        ta.committed_start,
        ta.committed_end,

        ta.target_start,
        ta.target_end,

        ta.actual_start,
        ta.actual_end,


        /* ====================================================
           P6 REFERENCE
           ==================================================== */

        ta.p6_start_date,
        ta.p6_end_date,


        /* ====================================================
           RESOURCES
           ==================================================== */

        ta.planned_crew,

        ta.crew_type_id,
        ta.crew_id,
        ta.emp_id,
        ta.uom_id,

        ta.data_employees,

        ta.daily_employee_ids,
        ta.daily_equipment_ids,

        ta.daily_ph_name,


        /* ====================================================
           EXECUTION
           ==================================================== */

        ta.data_hours,
        ta.data_qty,

        ta.daily_actual_quantity,
        ta.daily_actual_hours,

        ta.daily_completed,


        /* ====================================================
           ASSIGNMENT
           ==================================================== */

        ta.task_assignee,
        ta.supervisor_email,


        /* ====================================================
           RAW DETAILS
           ==================================================== */

        ta.url,

        ta.task_data,
        ta.daily_data,

        ta.created_at,
        ta.updated_at,

        ta.time_stamp,


        /* ====================================================
           ACTIVITY MAPPING
           ==================================================== */

        am.project_type,
        am.activity_code,

        am.composition_code,
        am.activity_uom,
        am.norms,

        am.class_b_ptw,
        am.rfi,

        am.mapping_row_count,

        am.distinct_activity_code_count,
        am.distinct_project_type_count,
        am.distinct_composition_code_count,

        am.distinct_uom_count,
        am.distinct_norms_count,
        am.distinct_class_b_ptw_count,
        am.distinct_rfi_count,


        /* ====================================================
           ACTIVITY CSV
           ==================================================== */

        ac.activity_group_description,
        ac.master_crew_code,

        ac.csv_row_count,

        ac.distinct_description_count,
        ac.distinct_crew_code_count,


        /* ====================================================
           WBS

           IMPORTANT:
           WBS DQ columns are NOT selected here.

           They are exposed exactly once below with ISNULL().
           ==================================================== */

        wbs.WBS_Code,

        wbs.Project_Def,
        wbs.WD_PRJ,

        wbs.Plant_Code,
        wbs.Cluster_code,

        wbs.Well_ID_Project_PO,

        wbs.Activity_code AS wbs_activity_code,

        wbs.Category,

        wbs.wbs_row_count,
        wbs.distinct_wbs_count,

        wa.wbs_activity_name,


        /* ====================================================
           ACTIVITY TYPE
           ==================================================== */

        CASE

            WHEN ta.activity_id IS NULL
                THEN 'UNKNOWN'

            WHEN am.activity_id IS NULL
                THEN 'UNKNOWN'

            WHEN am.mapping_row_count = 0
                THEN 'UNKNOWN'

            WHEN am.distinct_project_type_count > 1
                THEN 'AMBIGUOUS_MAPPING'

            WHEN am.project_type IS NULL
                THEN 'UNKNOWN'

            WHEN UPPER(LTRIM(RTRIM(am.project_type))) =
                 'FLOWLINE'
                THEN 'FLOWLINE'

            WHEN UPPER(LTRIM(RTRIM(am.project_type))) =
                 'LOCATION'
                THEN 'LOCATION'

            WHEN UPPER(LTRIM(RTRIM(am.project_type)))
                 IN
                 (
                     'SNLP',
                     'CONVERSION WITHOUT FLOWLINE'
                 )
                THEN 'OTHER_AMBIGUOUS_PROJECT_TYPE'

            ELSE 'OTHER'

        END AS activity_type,


        /* ====================================================
           START STATUS
           ==================================================== */

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


        /* ====================================================
           START VARIANCE
           ==================================================== */

        CASE

            WHEN ta.actual_start IS NOT NULL
             AND ta.target_start IS NOT NULL

                THEN DATEDIFF
                (
                    day,
                    ta.target_start,
                    ta.actual_start
                )

            WHEN ta.actual_start IS NULL
             AND ta.target_start IS NOT NULL
             AND @Today > ta.target_start

                THEN DATEDIFF
                (
                    day,
                    ta.target_start,
                    @Today
                )

            ELSE 0

        END AS start_variance_days,


        /* ====================================================
           END STATUS
           ==================================================== */

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


        /* ====================================================
           END VARIANCE
           ==================================================== */

        CASE

            WHEN ta.actual_end IS NOT NULL
             AND ta.target_end IS NOT NULL

                THEN DATEDIFF
                (
                    day,
                    ta.target_end,
                    ta.actual_end
                )

            WHEN ta.actual_end IS NULL
             AND ta.target_end IS NOT NULL
             AND @Today > ta.target_end

                THEN DATEDIFF
                (
                    day,
                    ta.target_end,
                    @Today
                )

            ELSE 0

        END AS end_variance_days,


        /* ====================================================
           EXECUTION STATUS
           ==================================================== */

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


        /* ====================================================
           SCHEDULE RISK
           ==================================================== */

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


        /* ====================================================
           PROGRESS %
           ==================================================== */

        CASE

            WHEN ta.progress IS NOT NULL
             AND ta.progress >= 0
             AND ta.progress <= 1

                THEN ta.progress * 100.0

            ELSE NULL

        END AS progress_percent,


        /* ====================================================
           QUANTITY SOURCE
           ==================================================== */

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

            WHEN ta.daily_actual_quantity IS NOT NULL

                THEN 'DAILY_QUANTITY_ONLY'

            ELSE 'NO_QUANTITY_SOURCE'

        END AS quantity_source,


        /* ====================================================
           OBSERVED QUANTITY

           If both sources conflict, return NULL.
           ==================================================== */

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


        /* ====================================================
           REMAINING QUANTITY
           ==================================================== */

        CASE

            WHEN ta.planned IS NULL
                THEN NULL

            WHEN ta.data_qty IS NOT NULL
             AND ta.daily_actual_quantity IS NOT NULL
             AND ta.data_qty <> ta.daily_actual_quantity

                THEN NULL

            WHEN ta.data_qty IS NOT NULL
             AND ta.planned - ta.data_qty < 0

                THEN 0

            WHEN ta.data_qty IS NOT NULL

                THEN ta.planned - ta.data_qty

            WHEN ta.daily_actual_quantity IS NOT NULL
             AND ta.planned - ta.daily_actual_quantity < 0

                THEN 0

            WHEN ta.daily_actual_quantity IS NOT NULL

                THEN
                    ta.planned -
                    ta.daily_actual_quantity

            ELSE NULL

        END AS calculated_remaining_quantity,


        /* ====================================================
           QUANTITY CONFLICT
           ==================================================== */

        CASE

            WHEN
                ta.data_qty IS NOT NULL
                AND ta.daily_actual_quantity IS NOT NULL
                AND ta.data_qty <> ta.daily_actual_quantity

                THEN 1

            ELSE 0

        END AS dq_quantity_source_conflict,


        /* ====================================================
           PRODUCTIVITY CANDIDATE 1
           ==================================================== */

        CASE

            WHEN ta.data_hours IS NOT NULL
             AND ta.data_hours > 0
             AND ta.data_qty IS NOT NULL

                THEN CAST
                (
                    ta.data_qty / ta.data_hours
                    AS DECIMAL(18,4)
                )

            ELSE NULL

        END AS data_productivity_qty_per_hour,


        /* ====================================================
           PRODUCTIVITY CANDIDATE 2
           ==================================================== */

        CASE

            WHEN ta.daily_actual_hours IS NOT NULL
             AND ta.daily_actual_hours > 0
             AND ta.daily_actual_quantity IS NOT NULL

                THEN CAST
                (
                    ta.daily_actual_quantity /
                    ta.daily_actual_hours
                    AS DECIMAL(18,4)
                )

            ELSE NULL

        END AS daily_productivity_qty_per_hour,


        /* ====================================================
           PRODUCTIVITY SOURCE
           ==================================================== */

        CASE

            WHEN
                ta.data_hours IS NOT NULL
                AND ta.data_hours > 0
                AND ta.data_qty IS NOT NULL

                AND
                (
                    ta.daily_actual_hours IS NULL
                    OR ta.daily_actual_hours <= 0
                    OR ta.daily_actual_quantity IS NULL
                )

                THEN 'TASK_DAILY_DATA'


            WHEN
                (
                    ta.data_hours IS NULL
                    OR ta.data_hours <= 0
                    OR ta.data_qty IS NULL
                )

                AND
                ta.daily_actual_hours IS NOT NULL
                AND ta.daily_actual_hours > 0
                AND ta.daily_actual_quantity IS NOT NULL

                THEN 'DAILY_EXECUTION_DATA'


            WHEN
                ta.data_hours IS NOT NULL
                AND ta.data_hours > 0
                AND ta.data_qty IS NOT NULL

                AND
                ta.daily_actual_hours IS NOT NULL
                AND ta.daily_actual_hours > 0
                AND ta.daily_actual_quantity IS NOT NULL

                AND
                (
                    ta.data_qty / ta.data_hours
                )
                =
                (
                    ta.daily_actual_quantity /
                    ta.daily_actual_hours
                )

                THEN 'BOTH_SAME'


            WHEN
                ta.data_hours IS NOT NULL
                AND ta.data_hours > 0
                AND ta.data_qty IS NOT NULL

                AND
                ta.daily_actual_hours IS NOT NULL
                AND ta.daily_actual_hours > 0
                AND ta.daily_actual_quantity IS NOT NULL

                AND
                (
                    ta.data_qty / ta.data_hours
                )
                <>
                (
                    ta.daily_actual_quantity /
                    ta.daily_actual_hours
                )

                THEN 'BOTH_CONFLICT'


            ELSE 'NO_PRODUCTIVITY_SOURCE'

        END AS productivity_source,


        /* ====================================================
           CURRENT PRODUCTIVITY

           Only exposed if one valid source exists or both
           sources agree.
           ==================================================== */

        CASE

            WHEN
                ta.data_hours IS NOT NULL
                AND ta.data_hours > 0
                AND ta.data_qty IS NOT NULL

                AND
                (
                    ta.daily_actual_hours IS NULL
                    OR ta.daily_actual_hours <= 0
                    OR ta.daily_actual_quantity IS NULL
                )

                THEN CAST
                (
                    ta.data_qty / ta.data_hours
                    AS DECIMAL(18,4)
                )


            WHEN
                (
                    ta.data_hours IS NULL
                    OR ta.data_hours <= 0
                    OR ta.data_qty IS NULL
                )

                AND
                ta.daily_actual_hours IS NOT NULL
                AND ta.daily_actual_hours > 0
                AND ta.daily_actual_quantity IS NOT NULL

                THEN CAST
                (
                    ta.daily_actual_quantity /
                    ta.daily_actual_hours
                    AS DECIMAL(18,4)
                )


            WHEN
                ta.data_hours IS NOT NULL
                AND ta.data_hours > 0
                AND ta.data_qty IS NOT NULL

                AND
                ta.daily_actual_hours IS NOT NULL
                AND ta.daily_actual_hours > 0
                AND ta.daily_actual_quantity IS NOT NULL

                AND
                (
                    ta.data_qty / ta.data_hours
                )
                =
                (
                    ta.daily_actual_quantity /
                    ta.daily_actual_hours
                )

                THEN CAST
                (
                    ta.data_qty / ta.data_hours
                    AS DECIMAL(18,4)
                )


            ELSE NULL

        END AS current_productivity_qty_per_hour,


        /* ====================================================
           PRODUCTIVITY DATA STATUS
           ==================================================== */

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

        END AS productivity_data_status,


        /* ====================================================
           PRODUCTIVITY CONFLICT
           ==================================================== */

        CASE

            WHEN
                ta.data_hours IS NOT NULL
                AND ta.data_hours > 0
                AND ta.data_qty IS NOT NULL

                AND
                ta.daily_actual_hours IS NOT NULL
                AND ta.daily_actual_hours > 0
                AND ta.daily_actual_quantity IS NOT NULL

                AND
                (
                    ta.data_qty / ta.data_hours
                )
                <>
                (
                    ta.daily_actual_quantity /
                    ta.daily_actual_hours
                )

                THEN 1

            ELSE 0

        END AS dq_productivity_source_conflict,


        /* ====================================================
           TARGET ACHIEVABILITY
           ==================================================== */

        CASE

            WHEN ta.target_end IS NULL
                THEN 'NO_TARGET_END'

            WHEN ta.actual_end IS NOT NULL
             AND ta.actual_end <= ta.target_end
                THEN 'ACHIEVED'

            WHEN ta.actual_end IS NOT NULL
             AND ta.actual_end > ta.target_end
                THEN 'MISSED'

            WHEN ta.actual_end IS NULL
             AND @Today > ta.target_end
                THEN 'CURRENTLY_MISSED'

            WHEN ta.actual_end IS NULL
             AND @Today <= ta.target_end
                THEN 'CURRENTLY_WITHIN_TARGET'

            ELSE 'UNKNOWN'

        END AS target_achievability,


        /* ====================================================
           DAYS TO TARGET END
           ==================================================== */

        CASE

            WHEN ta.target_end IS NOT NULL

                THEN DATEDIFF
                (
                    day,
                    @Today,
                    ta.target_end
                )

            ELSE NULL

        END AS days_to_target_end,


        /* ====================================================
           TASK DATA QUALITY
           ==================================================== */

        CASE
            WHEN ta.target_start IS NULL
                THEN 1
            ELSE 0
        END AS dq_missing_target_start,


        CASE
            WHEN ta.target_end IS NULL
                THEN 1
            ELSE 0
        END AS dq_missing_target_end,


        CASE

            WHEN ta.target_start IS NOT NULL
             AND ta.target_end IS NOT NULL
             AND ta.target_end < ta.target_start

                THEN 1

            ELSE 0

        END AS dq_target_end_before_start,


        CASE

            WHEN ta.actual_start IS NOT NULL
             AND ta.actual_end IS NOT NULL
             AND ta.actual_end < ta.actual_start

                THEN 1

            ELSE 0

        END AS dq_actual_end_before_start,


        CASE

            WHEN ta.progress IS NOT NULL
             AND
             (
                 ta.progress < 0
                 OR ta.progress > 1
             )

                THEN 1

            ELSE 0

        END AS dq_invalid_progress,


        /* ====================================================
           COMPLETION / PROGRESS
           ==================================================== */

        CASE

            WHEN ta.completed = 1
             AND ta.progress IS NOT NULL
             AND ta.progress <> 1

                THEN 1

            ELSE 0

        END AS dq_completed_progress_conflict,


        CASE

            WHEN ta.actual_end IS NOT NULL
             AND ta.completed = 0

                THEN 1

            ELSE 0

        END AS dq_actual_end_completed_flag_conflict,


        CASE

            WHEN ta.daily_completed = 1
             AND ta.actual_end IS NULL

                THEN 1

            ELSE 0

        END AS dq_daily_completed_without_actual_end,


        CASE

            WHEN ta.progress IS NOT NULL
             AND ta.progress = 1
             AND ta.actual_end IS NULL

                THEN 1

            ELSE 0

        END AS dq_progress_complete_without_actual_end,


        /* ====================================================
           ACTIVITY MAPPING DQ
           ==================================================== */

        CASE

            WHEN ta.activity_id IS NULL
                THEN 1

            WHEN am.activity_id IS NULL
                THEN 1

            WHEN am.mapping_row_count = 0
                THEN 1

            ELSE 0

        END AS dq_missing_activity_mapping,


        CASE

            WHEN am.distinct_activity_code_count > 1
                THEN 1

            ELSE 0

        END AS dq_activity_code_mapping_conflict,


        CASE

            WHEN am.distinct_project_type_count > 1
                THEN 1

            ELSE 0

        END AS dq_project_type_mapping_conflict,


        CASE

            WHEN am.distinct_composition_code_count > 1
                THEN 1

            ELSE 0

        END AS dq_composition_mapping_conflict,


        CASE

            WHEN am.distinct_uom_count > 1
                THEN 1

            ELSE 0

        END AS dq_activity_uom_conflict,


        CASE

            WHEN am.distinct_norms_count > 1
                THEN 1

            ELSE 0

        END AS dq_activity_norms_conflict,


        CASE

            WHEN am.distinct_class_b_ptw_count > 1
                THEN 1

            ELSE 0

        END AS dq_activity_class_b_ptw_conflict,


        CASE

            WHEN am.distinct_rfi_count > 1
                THEN 1

            ELSE 0

        END AS dq_activity_rfi_conflict,


        /* ====================================================
           CSV DQ
           ==================================================== */

        CASE

            WHEN am.activity_code IS NOT NULL
             AND ac.activity_code IS NULL

                THEN 1

            ELSE 0

        END AS dq_missing_activity_csv,


        CASE

            WHEN ac.distinct_description_count > 1
                THEN 1

            ELSE 0

        END AS dq_activity_description_conflict,


        CASE

            WHEN ac.distinct_crew_code_count > 1
                THEN 1

            ELSE 0

        END AS dq_activity_crew_code_conflict,


        /* ====================================================
           WBS DQ

           These are defined ONLY ONCE in EnrichedTasks.
           ==================================================== */

        CASE

            WHEN wbs.WBS_Code IS NULL
                THEN 1

            ELSE 0

        END AS dq_missing_wbs,


        ISNULL
        (
            wbs.dq_wbs_mapping_conflict,
            0
        ) AS dq_wbs_mapping_conflict,


        ISNULL
        (
            wbs.dq_wbs_project_def_conflict,
            0
        ) AS dq_wbs_project_def_conflict,


        ISNULL
        (
            wbs.dq_wbs_wd_prj_conflict,
            0
        ) AS dq_wbs_wd_prj_conflict,


        ISNULL
        (
            wbs.dq_wbs_plant_conflict,
            0
        ) AS dq_wbs_plant_conflict,


        ISNULL
        (
            wbs.dq_wbs_cluster_conflict,
            0
        ) AS dq_wbs_cluster_conflict,


        ISNULL
        (
            wbs.dq_wbs_well_reference_conflict,
            0
        ) AS dq_wbs_well_reference_conflict,


        ISNULL
        (
            wbs.dq_wbs_category_conflict,
            0
        ) AS dq_wbs_category_conflict,


        /* ====================================================
           PROJECT DQ
           ==================================================== */

        CASE

            WHEN aw.project_id IS NULL
                THEN 1

            ELSE 0

        END AS dq_missing_master_project_id,


        CASE

            WHEN ta.project_id IS NULL
                THEN 1

            ELSE 0

        END AS dq_missing_task_project_id,


        CASE

            WHEN
                aw.project_id IS NOT NULL
                AND ta.project_id IS NOT NULL
                AND aw.project_id <> ta.project_id

                THEN 1

            ELSE 0

        END AS dq_task_project_mismatch,


        /* ====================================================
           RESOURCE DATA STATUS
           ==================================================== */

        CASE

            WHEN
                ta.planned_crew IS NOT NULL
                OR ta.crew_id IS NOT NULL
                OR ta.crew_type_id IS NOT NULL
                OR ta.emp_id IS NOT NULL
                OR ta.daily_employee_ids IS NOT NULL
                OR ta.daily_equipment_ids IS NOT NULL

                THEN 'RESOURCE_DATA_AVAILABLE'

            ELSE 'RESOURCE_DATA_NOT_AVAILABLE'

        END AS resource_data_status,


        /* ====================================================
           CURRENT TASK ROW DQ
           ==================================================== */

        CASE

            WHEN ta.ActionOn IS NULL
                THEN 1

            ELSE 0

        END AS dq_missing_action_date,


        CASE

            WHEN ta.duration IS NOT NULL
             AND ta.duration < 0

                THEN 1

            ELSE 0

        END AS dq_negative_duration,


        CASE

            WHEN ta.remaining_duration IS NOT NULL
             AND ta.remaining_duration < 0

                THEN 1

            ELSE 0

        END AS dq_negative_remaining_duration

    FROM WellMilestones AS aw

    INNER JOIN TaskActivities AS ta
        ON ta.well_id = aw.well_id


    LEFT JOIN ActivityMapping AS am
        ON am.activity_id = ta.activity_id


    LEFT JOIN ActivityCSV AS ac
        ON ac.activity_code = am.activity_code


    LEFT JOIN WBSActivity AS wa
        ON wa.Activity_code = am.activity_code


    LEFT JOIN WellWBS AS wbs

        ON wbs.well_id = aw.well_id

       AND wbs.Activity_code = am.activity_code

),


/* ============================================================
   15. FINAL CLASSIFICATION
   ============================================================ */

FinalResult AS
(
    SELECT

        et.*,


        /* ====================================================
           OVERALL DATA QUALITY
           ==================================================== */

        CASE

            WHEN
                et.dq_missing_ex_rig_on_date = 1

                OR et.dq_rig_on_before_expected = 1
                OR et.dq_rig_off_before_rig_on = 1

                OR et.dq_missing_target_start = 1
                OR et.dq_missing_target_end = 1

                OR et.dq_target_end_before_start = 1
                OR et.dq_actual_end_before_start = 1

                OR et.dq_invalid_progress = 1

                OR et.dq_completed_progress_conflict = 1
                OR et.dq_actual_end_completed_flag_conflict = 1

                OR et.dq_daily_completed_without_actual_end = 1
                OR et.dq_progress_complete_without_actual_end = 1

                OR et.dq_activity_code_mapping_conflict = 1
                OR et.dq_project_type_mapping_conflict = 1
                OR et.dq_composition_mapping_conflict = 1

                OR et.dq_activity_uom_conflict = 1
                OR et.dq_activity_norms_conflict = 1
                OR et.dq_activity_class_b_ptw_conflict = 1
                OR et.dq_activity_rfi_conflict = 1

                OR et.dq_activity_description_conflict = 1
                OR et.dq_activity_crew_code_conflict = 1

                OR et.dq_wbs_mapping_conflict = 1
                OR et.dq_wbs_project_def_conflict = 1
                OR et.dq_wbs_wd_prj_conflict = 1
                OR et.dq_wbs_plant_conflict = 1
                OR et.dq_wbs_cluster_conflict = 1
                OR et.dq_wbs_well_reference_conflict = 1
                OR et.dq_wbs_category_conflict = 1

                OR et.dq_task_project_mismatch = 1

                OR et.dq_quantity_source_conflict = 1
                OR et.dq_productivity_source_conflict = 1

                OR et.dq_negative_duration = 1
                OR et.dq_negative_remaining_duration = 1

                THEN 1

            ELSE 0

        END AS has_data_quality_issue,


        /* ====================================================
           AI SCHEDULE CLASSIFICATION

           Schedule delay is kept separate from DQ.
           ==================================================== */

        CASE

            WHEN et.schedule_risk = 'RED_DELAYED'
                THEN 'DELAYED'

            WHEN et.schedule_risk IN
                 (
                     'AMBER_START_SLIPPING',
                     'AMBER_START_DELAYED'
                 )

                THEN 'AT_RISK'

            ELSE 'ON_SCHEDULE'

        END AS ai_schedule_classification,


        /* ====================================================
           SCHEDULE EVIDENCE LEVEL
           ==================================================== */

        CASE

            WHEN
                et.schedule_risk = 'RED_DELAYED'
                AND
                (
                    et.end_variance_days > 0
                    OR et.start_variance_days > 0
                )

                THEN 'HIGH'


            WHEN
                et.schedule_risk IN
                (
                    'AMBER_START_SLIPPING',
                    'AMBER_START_DELAYED'
                )

                THEN 'MEDIUM'


            WHEN
                et.dq_missing_target_start = 0
                AND et.dq_missing_target_end = 0
                AND et.actual_end IS NOT NULL

                THEN 'MEDIUM'


            WHEN
                et.dq_missing_target_start = 0
                AND et.dq_missing_target_end = 0

                THEN 'MEDIUM'


            ELSE 'LOW'

        END AS schedule_evidence_level,


        /* ====================================================
           DATA EVIDENCE LEVEL
           ==================================================== */

        CASE

            WHEN
                et.dq_missing_target_start = 0
                AND et.dq_missing_target_end = 0
                AND et.dq_invalid_progress = 0

                AND et.dq_activity_code_mapping_conflict = 0
                AND et.dq_project_type_mapping_conflict = 0

                AND et.dq_task_project_mismatch = 0

                AND et.dq_quantity_source_conflict = 0
                AND et.dq_productivity_source_conflict = 0

                AND
                (
                    et.productivity_data_status =
                    'PRODUCTIVITY_AVAILABLE'

                    OR

                    et.execution_status =
                    'COMPLETED'
                )

                THEN 'HIGH'


            WHEN
                et.dq_missing_target_start = 0
                AND et.dq_missing_target_end = 0
                AND et.dq_invalid_progress = 0

                THEN 'MEDIUM'


            ELSE 'LOW'

        END AS data_evidence_level

    FROM EnrichedTasks AS et
)


/* ============================================================
   16. FINAL OUTPUT
   ============================================================ */

SELECT

    /* ========================================================
       WELL
       ======================================================== */

    fr.well_id,
    fr.ex_rig_on_date,
    fr.rig_on_date,
    fr.ex_rig_off_date,
    fr.rig_off_date,

    fr.pegged_date,
    fr.flaf_issue_date,
    fr.eng_completion_date,

    fr.well_progress_raw AS well_progress,
    fr.flowline_const_progress AS flowline_progress,
    fr.material_avail_date,


    /* ========================================================
       MILESTONES
       ======================================================== */

    fr.pegging_status,
    fr.flaf_status,
    fr.construction_status,
    fr.hookup_status,


    /* ========================================================
       DELAYED ACTIVITY
       ======================================================== */

    fr.task_daily_id AS task_id,

    fr.project_type,

    fr.activity_id,
    fr.activity_code,

    fr.activity_group_description AS activity,

    COALESCE(
        fr.master_crew_code,
        fr.planned_crew
    ) AS crew,

    fr.progress_percent,

    fr.completed,

    fr.target_start,
    fr.target_end,

    fr.actual_start,
    fr.actual_end,

    fr.remaining_duration,

    fr.end_status,

    fr.end_variance_days AS delay_days,

    fr.execution_status,

    fr.schedule_risk,

    fr.target_achievability,


    /* ========================================================
       PRODUCTIVITY
       ======================================================== */

    fr.productivity_data_status AS productivity_status,


    /* ========================================================
       RESOURCE
       ======================================================== */

    fr.resource_data_status AS resource_status,


    /* ========================================================
       DATA QUALITY / AI EVIDENCE
       ======================================================== */

    fr.has_data_quality_issue,

    fr.ai_schedule_classification,

    fr.schedule_evidence_level,

    fr.data_evidence_level


FROM FinalResult AS fr


/* ============================================================
   ONLY DELAYED / AT-RISK ACTIVITIES
   ============================================================ */

WHERE
    fr.schedule_risk = 'RED_DELAYED'
    OR fr.end_status = 'OVERDUE_CURRENT_TASK_LAGGING'
    OR fr.ai_schedule_classification = 'DELAYED'


/* ============================================================
   PRIORITIZATION
   ============================================================ */

ORDER BY

    CASE

        WHEN fr.ai_schedule_classification = 'DELAYED'
            THEN 1

        WHEN fr.ai_schedule_classification = 'AT_RISK'
            THEN 2

        WHEN fr.has_data_quality_issue = 1
            THEN 3

        ELSE 4

    END,


    CASE

        WHEN fr.end_variance_days > 0
            THEN fr.end_variance_days

        ELSE 0

    END DESC,


    CASE

        WHEN fr.start_variance_days > 0
            THEN fr.start_variance_days

        ELSE 0

    END DESC,


    fr.target_end,

    fr.task_code;
