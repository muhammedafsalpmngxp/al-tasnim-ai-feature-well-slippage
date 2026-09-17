WITH WellMilestones AS
(
    SELECT
        wm.well_id,
        wm.project_id,

        wm.station_id,
        wm.well_type_id,

        wm.ex_rig_on_date,
        wm.rig_on_date,

        wm.ex_rig_off_date,
        wm.rig_off_date,

        wm.pegged_date,
        wm.flaf_issue_date,

        wm.eng_completion_date

    FROM [well].[well_master] AS wm

    /* ============================================================
       Only wells not yet completed are part of the active
       slippage investigation.
       ============================================================ */

    WHERE wm.eng_completion_date IS NULL
)

SELECT
    wms.well_id,
    wms.project_id,

    wms.station_id,
    wms.well_type_id,

    /* ============================================================
       1. RIG-ON
       ============================================================ */

    wms.ex_rig_on_date,
    wms.rig_on_date,

    CASE
        WHEN wms.ex_rig_on_date IS NULL
            THEN 'NO_EXPECTED_DATE'

        WHEN wms.rig_on_date IS NOT NULL
         AND wms.rig_on_date > wms.ex_rig_on_date
            THEN 'DELAYED'

        WHEN wms.rig_on_date IS NOT NULL
         AND wms.rig_on_date < wms.ex_rig_on_date
            THEN 'AHEAD'

        WHEN wms.rig_on_date IS NOT NULL
            THEN 'ON_SCHEDULE'

        WHEN wms.rig_on_date IS NULL
         AND CAST(GETDATE() AS DATE) > wms.ex_rig_on_date
            THEN 'DELAYED'

        ELSE 'NOT_YET_DUE'
    END AS rig_on_status,

    CASE
        WHEN wms.ex_rig_on_date IS NULL
            THEN NULL

        WHEN wms.rig_on_date IS NOT NULL
            THEN DATEDIFF(DAY, wms.ex_rig_on_date, wms.rig_on_date)

        WHEN CAST(GETDATE() AS DATE) > wms.ex_rig_on_date
            THEN DATEDIFF(DAY, wms.ex_rig_on_date, CAST(GETDATE() AS DATE))

        ELSE NULL
    END AS rig_on_delay_days,

    /* ============================================================
       2. FLAF  (checked before pegging: its deadline is
          ex_rig_on_date - 90 days, earlier than pegging's -60)
       ============================================================ */

    wms.flaf_issue_date,

    CASE
        WHEN wms.ex_rig_on_date IS NOT NULL
            THEN DATEADD(DAY, -90, wms.ex_rig_on_date)
        ELSE NULL
    END AS flaf_deadline,

    CASE
        WHEN wms.ex_rig_on_date IS NULL
            THEN 'DATA_QUALITY_ISSUE'

        WHEN wms.flaf_issue_date IS NULL
         AND CAST(GETDATE() AS DATE) > DATEADD(DAY, -90, wms.ex_rig_on_date)
            THEN 'MISSED'

        WHEN wms.flaf_issue_date IS NULL
            THEN 'PENDING'

        WHEN wms.flaf_issue_date < DATEADD(DAY, -90, wms.ex_rig_on_date)
            THEN 'AHEAD_OF_SCHEDULE'

        WHEN wms.flaf_issue_date = DATEADD(DAY, -90, wms.ex_rig_on_date)
            THEN 'ON_SCHEDULE'

        ELSE 'DELAYED'
    END AS flaf_status,

    CASE
        WHEN wms.ex_rig_on_date IS NULL
            THEN NULL

        WHEN wms.flaf_issue_date IS NOT NULL
            THEN DATEDIFF(DAY, DATEADD(DAY, -90, wms.ex_rig_on_date), wms.flaf_issue_date)

        WHEN CAST(GETDATE() AS DATE) > DATEADD(DAY, -90, wms.ex_rig_on_date)
            THEN DATEDIFF(DAY, DATEADD(DAY, -90, wms.ex_rig_on_date), CAST(GETDATE() AS DATE))

        ELSE 0
    END AS flaf_variance_days,

    /* ============================================================
       3. PEGGING
       ============================================================ */

    wms.pegged_date,

    CASE
        WHEN wms.ex_rig_on_date IS NOT NULL
            THEN DATEADD(DAY, -60, wms.ex_rig_on_date)
        ELSE NULL
    END AS pegging_deadline,

    CASE
        WHEN wms.ex_rig_on_date IS NULL
            THEN 'DATA_QUALITY_ISSUE'

        WHEN wms.pegged_date IS NULL
         AND CAST(GETDATE() AS DATE) > DATEADD(DAY, -60, wms.ex_rig_on_date)
            THEN 'MISSED'

        WHEN wms.pegged_date IS NULL
            THEN 'PENDING'

        WHEN wms.pegged_date < DATEADD(DAY, -60, wms.ex_rig_on_date)
            THEN 'AHEAD_OF_SCHEDULE'

        WHEN wms.pegged_date = DATEADD(DAY, -60, wms.ex_rig_on_date)
            THEN 'ON_SCHEDULE'

        ELSE 'DELAYED'
    END AS pegging_status,

    CASE
        WHEN wms.ex_rig_on_date IS NULL
            THEN NULL

        WHEN wms.pegged_date IS NOT NULL
            THEN DATEDIFF(DAY, DATEADD(DAY, -60, wms.ex_rig_on_date), wms.pegged_date)

        WHEN CAST(GETDATE() AS DATE) > DATEADD(DAY, -60, wms.ex_rig_on_date)
            THEN DATEDIFF(DAY, DATEADD(DAY, -60, wms.ex_rig_on_date), CAST(GETDATE() AS DATE))

        ELSE 0
    END AS pegging_variance_days,

    /* ============================================================
       4. RIG-OFF
       ============================================================ */

    wms.ex_rig_off_date,
    wms.rig_off_date,

    CASE
        WHEN wms.ex_rig_off_date IS NULL
            THEN 'NO_EXPECTED_DATE'

        WHEN wms.rig_off_date IS NOT NULL
         AND wms.rig_off_date > wms.ex_rig_off_date
            THEN 'DELAYED'

        WHEN wms.rig_off_date IS NOT NULL
         AND wms.rig_off_date < wms.ex_rig_off_date
            THEN 'AHEAD'

        WHEN wms.rig_off_date IS NOT NULL
            THEN 'ON_SCHEDULE'

        WHEN wms.rig_off_date IS NULL
         AND CAST(GETDATE() AS DATE) > wms.ex_rig_off_date
            THEN 'DELAYED'

        ELSE 'NOT_YET_DUE'
    END AS rig_off_status,

    CASE
        WHEN wms.ex_rig_off_date IS NULL
            THEN NULL

        WHEN wms.rig_off_date IS NOT NULL
            THEN DATEDIFF(DAY, wms.ex_rig_off_date, wms.rig_off_date)

        WHEN CAST(GETDATE() AS DATE) > wms.ex_rig_off_date
            THEN DATEDIFF(DAY, wms.ex_rig_off_date, CAST(GETDATE() AS DATE))

        ELSE NULL
    END AS rig_off_delay_days,

    /* ============================================================
       5. HOOK-UP
          Deadline: actual rig-off + 2 days once known, otherwise
          the planned rig-off + 2 days. Actual takes precedence.
          eng_completion_date is always NULL here (see WHERE above
          on WellMilestones), so a "completed" branch is not
          reachable and is intentionally not included.
       ============================================================ */

    wms.eng_completion_date,

    CASE
        WHEN wms.rig_off_date IS NOT NULL
            THEN DATEADD(DAY, 2, wms.rig_off_date)
        WHEN wms.ex_rig_off_date IS NOT NULL
            THEN DATEADD(DAY, 2, wms.ex_rig_off_date)
        ELSE NULL
    END AS hookup_deadline,

    CASE
        WHEN wms.rig_off_date IS NULL AND wms.ex_rig_off_date IS NULL
            THEN 'NO_EXPECTED_DATE'

        WHEN wms.rig_off_date IS NOT NULL
         AND CAST(GETDATE() AS DATE) > DATEADD(DAY, 2, wms.rig_off_date)
            THEN 'DELAYED'

        WHEN wms.rig_off_date IS NULL
         AND CAST(GETDATE() AS DATE) > DATEADD(DAY, 2, wms.ex_rig_off_date)
            THEN 'DELAYED'

        ELSE 'NOT_YET_DUE'
    END AS hookup_status,

    CASE
        WHEN wms.rig_off_date IS NULL AND wms.ex_rig_off_date IS NULL
            THEN NULL

        WHEN wms.rig_off_date IS NOT NULL
         AND CAST(GETDATE() AS DATE) > DATEADD(DAY, 2, wms.rig_off_date)
            THEN DATEDIFF(DAY, DATEADD(DAY, 2, wms.rig_off_date), CAST(GETDATE() AS DATE))

        WHEN wms.rig_off_date IS NULL
         AND CAST(GETDATE() AS DATE) > DATEADD(DAY, 2, wms.ex_rig_off_date)
            THEN DATEDIFF(DAY, DATEADD(DAY, 2, wms.ex_rig_off_date), CAST(GETDATE() AS DATE))

        ELSE 0
    END AS hookup_delay_days,

    /* ============================================================
       WELL SLIPPAGE STATUS
       Priority order, first match wins:
         rig-on -> flaf -> pegging -> rig-off -> hook-up
       Task-level delay is intentionally not checked here.
       ============================================================ */

    CASE

        WHEN wms.ex_rig_on_date IS NOT NULL
         AND
         (
             (wms.rig_on_date IS NOT NULL AND wms.rig_on_date > wms.ex_rig_on_date)
             OR
             (wms.rig_on_date IS NULL AND wms.ex_rig_on_date < CAST(GETDATE() AS DATE))
         )
            THEN 'SLIPPED - RIG ON'

        WHEN wms.ex_rig_on_date IS NOT NULL
         AND
         (
             (
                 wms.flaf_issue_date IS NULL
                 AND CAST(GETDATE() AS DATE) > DATEADD(DAY, -90, wms.ex_rig_on_date)
             )
             OR
             wms.flaf_issue_date > DATEADD(DAY, -90, wms.ex_rig_on_date)
         )
            THEN 'SLIPPED - FLAF'

        WHEN wms.ex_rig_on_date IS NOT NULL
         AND
         (
             (
                 wms.pegged_date IS NULL
                 AND CAST(GETDATE() AS DATE) > DATEADD(DAY, -60, wms.ex_rig_on_date)
             )
             OR
             wms.pegged_date > DATEADD(DAY, -60, wms.ex_rig_on_date)
         )
            THEN 'SLIPPED - PEGGING'

        WHEN wms.ex_rig_off_date IS NOT NULL
         AND
         (
             (wms.rig_off_date IS NOT NULL AND wms.rig_off_date > wms.ex_rig_off_date)
             OR
             (wms.rig_off_date IS NULL AND wms.ex_rig_off_date < CAST(GETDATE() AS DATE))
         )
            THEN 'SLIPPED - RIG OFF'

        WHEN
        (
            wms.rig_off_date IS NOT NULL
            AND CAST(GETDATE() AS DATE) > DATEADD(DAY, 2, wms.rig_off_date)
        )
        OR
        (
            wms.rig_off_date IS NULL
            AND wms.ex_rig_off_date IS NOT NULL
            AND CAST(GETDATE() AS DATE) > DATEADD(DAY, 2, wms.ex_rig_off_date)
        )
            THEN 'SLIPPED - HOOK-UP'

        ELSE 'NOT SLIPPED'

    END AS well_slippage_status

FROM WellMilestones AS wms

WHERE
    /* RIG-ON */
    (
        wms.ex_rig_on_date IS NOT NULL
        AND
        (
            (wms.rig_on_date IS NOT NULL AND wms.rig_on_date > wms.ex_rig_on_date)
            OR
            (wms.rig_on_date IS NULL AND wms.ex_rig_on_date < CAST(GETDATE() AS DATE))
        )
    )

    OR

    /* FLAF */
    (
        wms.ex_rig_on_date IS NOT NULL
        AND
        (
            (
                wms.flaf_issue_date IS NULL
                AND CAST(GETDATE() AS DATE) > DATEADD(DAY, -90, wms.ex_rig_on_date)
            )
            OR
            wms.flaf_issue_date > DATEADD(DAY, -90, wms.ex_rig_on_date)
        )
    )

    OR

    /* PEGGING */
    (
        wms.ex_rig_on_date IS NOT NULL
        AND
        (
            (
                wms.pegged_date IS NULL
                AND CAST(GETDATE() AS DATE) > DATEADD(DAY, -60, wms.ex_rig_on_date)
            )
            OR
            wms.pegged_date > DATEADD(DAY, -60, wms.ex_rig_on_date)
        )
    )

    OR

    /* RIG-OFF */
    (
        wms.ex_rig_off_date IS NOT NULL
        AND
        (
            (wms.rig_off_date IS NOT NULL AND wms.rig_off_date > wms.ex_rig_off_date)
            OR
            (wms.rig_off_date IS NULL AND wms.ex_rig_off_date < CAST(GETDATE() AS DATE))
        )
    )

    OR

    /* HOOK-UP */
    (
        (
            wms.rig_off_date IS NOT NULL
            AND CAST(GETDATE() AS DATE) > DATEADD(DAY, 2, wms.rig_off_date)
        )
        OR
        (
            wms.rig_off_date IS NULL
            AND wms.ex_rig_off_date IS NOT NULL
            AND CAST(GETDATE() AS DATE) > DATEADD(DAY, 2, wms.ex_rig_off_date)
        )
    )

ORDER BY
    wms.ex_rig_on_date ASC,
    wms.well_id ASC;
