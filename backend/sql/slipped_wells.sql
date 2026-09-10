SELECT
    wm.well_id,
    wm.project_id,
    wm.rig_id,
    wm.well_type_id,
    wm.station_id,

    wm.ex_rig_on_date,
    wm.rig_on_date,

    wm.ex_rig_off_date,
    wm.rig_off_date,

    wm.eng_completion_date,

    /* ============================================================
       RIG-ON STATUS
       ============================================================ */
    CASE
        WHEN wm.ex_rig_on_date IS NULL
            THEN 'NO_EXPECTED_DATE'

        WHEN wm.rig_on_date IS NOT NULL
             AND wm.rig_on_date > wm.ex_rig_on_date
            THEN 'DELAYED'

        WHEN wm.rig_on_date IS NOT NULL
             AND wm.rig_on_date = wm.ex_rig_on_date
            THEN 'ON_SCHEDULE'

        WHEN wm.rig_on_date IS NOT NULL
             AND wm.rig_on_date < wm.ex_rig_on_date
            THEN 'AHEAD'

        WHEN wm.rig_on_date IS NULL
             AND wm.ex_rig_on_date < CAST(GETDATE() AS DATE)
            THEN 'DELAYED'

        WHEN wm.rig_on_date IS NULL
             AND wm.ex_rig_on_date >= CAST(GETDATE() AS DATE)
            THEN 'NOT_YET_DUE'
    END AS rig_on_status,

    /* ============================================================
       RIG-ON DELAY DAYS
       ============================================================ */
    CASE
        WHEN wm.ex_rig_on_date IS NULL
            THEN NULL

        WHEN wm.rig_on_date IS NOT NULL
            THEN DATEDIFF(
                    day,
                    wm.ex_rig_on_date,
                    wm.rig_on_date
                 )

        WHEN wm.rig_on_date IS NULL
             AND wm.ex_rig_on_date < CAST(GETDATE() AS DATE)
            THEN DATEDIFF(
                    day,
                    wm.ex_rig_on_date,
                    CAST(GETDATE() AS DATE)
                 )

        ELSE NULL
    END AS rig_on_delay_days,

    /* ============================================================
       RIG-OFF STATUS
       ============================================================ */
    CASE
        WHEN wm.ex_rig_off_date IS NULL
            THEN 'NO_EXPECTED_DATE'

        WHEN wm.rig_off_date IS NOT NULL
             AND wm.rig_off_date > wm.ex_rig_off_date
            THEN 'DELAYED'

        WHEN wm.rig_off_date IS NOT NULL
             AND wm.rig_off_date = wm.ex_rig_off_date
            THEN 'ON_SCHEDULE'

        WHEN wm.rig_off_date IS NOT NULL
             AND wm.rig_off_date < wm.ex_rig_off_date
            THEN 'AHEAD'

        WHEN wm.rig_off_date IS NULL
             AND wm.ex_rig_off_date < CAST(GETDATE() AS DATE)
            THEN 'DELAYED'

        WHEN wm.rig_off_date IS NULL
             AND wm.ex_rig_off_date >= CAST(GETDATE() AS DATE)
            THEN 'NOT_YET_DUE'
    END AS rig_off_status,

    /* ============================================================
       RIG-OFF DELAY DAYS
       ============================================================ */
    CASE
        WHEN wm.ex_rig_off_date IS NULL
            THEN NULL

        WHEN wm.rig_off_date IS NOT NULL
            THEN DATEDIFF(
                    day,
                    wm.ex_rig_off_date,
                    wm.rig_off_date
                 )

        WHEN wm.rig_off_date IS NULL
             AND wm.ex_rig_off_date < CAST(GETDATE() AS DATE)
            THEN DATEDIFF(
                    day,
                    wm.ex_rig_off_date,
                    CAST(GETDATE() AS DATE)
                 )

        ELSE NULL
    END AS rig_off_delay_days,

    /* ============================================================
       HOOK-UP DEADLINE
       ============================================================ */
    CASE
        WHEN wm.rig_off_date IS NOT NULL
            THEN DATEADD(day, 2, wm.rig_off_date)

        WHEN wm.rig_off_date IS NULL
             AND wm.ex_rig_off_date IS NOT NULL
            THEN DATEADD(day, 2, wm.ex_rig_off_date)

        ELSE NULL
    END AS hookup_deadline,

    /* ============================================================
       HOOK-UP / COMPLETION STATUS
       ============================================================ */
    CASE
        WHEN wm.eng_completion_date IS NOT NULL
            THEN 'COMPLETED'

        WHEN wm.rig_off_date IS NOT NULL
             AND DATEADD(day, 2, wm.rig_off_date)
                 < CAST(GETDATE() AS DATE)
            THEN 'DELAYED'

        WHEN wm.rig_off_date IS NULL
             AND wm.ex_rig_off_date IS NOT NULL
             AND DATEADD(day, 2, wm.ex_rig_off_date)
                 < CAST(GETDATE() AS DATE)
            THEN 'DELAYED'

        WHEN wm.rig_off_date IS NOT NULL
             AND DATEADD(day, 2, wm.rig_off_date)
                 >= CAST(GETDATE() AS DATE)
            THEN 'NOT_YET_DUE'

        WHEN wm.rig_off_date IS NULL
             AND wm.ex_rig_off_date IS NOT NULL
             AND DATEADD(day, 2, wm.ex_rig_off_date)
                 >= CAST(GETDATE() AS DATE)
            THEN 'NOT_YET_DUE'

        ELSE 'NO_EXPECTED_DATE'
    END AS hookup_status,

    /* ============================================================
       HOOK-UP DELAY DAYS
       ============================================================ */
    CASE
        WHEN wm.eng_completion_date IS NOT NULL
            THEN NULL

        WHEN wm.rig_off_date IS NOT NULL
             AND DATEADD(day, 2, wm.rig_off_date)
                 < CAST(GETDATE() AS DATE)
            THEN DATEDIFF(
                    day,
                    DATEADD(day, 2, wm.rig_off_date),
                    CAST(GETDATE() AS DATE)
                 )

        WHEN wm.rig_off_date IS NULL
             AND wm.ex_rig_off_date IS NOT NULL
             AND DATEADD(day, 2, wm.ex_rig_off_date)
                 < CAST(GETDATE() AS DATE)
            THEN DATEDIFF(
                    day,
                    DATEADD(day, 2, wm.ex_rig_off_date),
                    CAST(GETDATE() AS DATE)
                 )

        ELSE NULL
    END AS hookup_delay_days

FROM [AlTasnimBI].[well].[well_master] AS wm

WHERE
    /* ============================================================
       FIRST CONDITION:
       WELL MUST NOT BE COMPLETED
       ============================================================ */
    wm.eng_completion_date IS NULL

    AND

    /* ============================================================
       WELL MUST HAVE AT LEAST ONE DELAYED MILESTONE
       ============================================================ */
    (
        /* ---------------------------------------------------------
           1. RIG-ON DELAY
           --------------------------------------------------------- */
        (
            wm.ex_rig_on_date IS NOT NULL
            AND
            (
                (
                    wm.rig_on_date IS NOT NULL
                    AND wm.rig_on_date > wm.ex_rig_on_date
                )
                OR
                (
                    wm.rig_on_date IS NULL
                    AND wm.ex_rig_on_date < CAST(GETDATE() AS DATE)
                )
            )
        )

        OR

        /* ---------------------------------------------------------
           2. RIG-OFF DELAY
           --------------------------------------------------------- */
        (
            wm.ex_rig_off_date IS NOT NULL
            AND
            (
                (
                    wm.rig_off_date IS NOT NULL
                    AND wm.rig_off_date > wm.ex_rig_off_date
                )
                OR
                (
                    wm.rig_off_date IS NULL
                    AND wm.ex_rig_off_date < CAST(GETDATE() AS DATE)
                )
            )
        )

        OR

        /* ---------------------------------------------------------
           3. HOOK-UP DELAY
           --------------------------------------------------------- */
        (
            (
                wm.rig_off_date IS NOT NULL
                AND DATEADD(day, 2, wm.rig_off_date)
                    < CAST(GETDATE() AS DATE)
            )

            OR

            (
                wm.rig_off_date IS NULL
                AND wm.ex_rig_off_date IS NOT NULL
                AND DATEADD(day, 2, wm.ex_rig_off_date)
                    < CAST(GETDATE() AS DATE)
            )
        )
    )

ORDER BY
    wm.ex_rig_on_date ASC;