WITH DistinctWells AS
(
    SELECT
        wm.*,
        ROW_NUMBER() OVER
        (
            PARTITION BY wm.well_id
            ORDER BY wm.rig_on_date DESC
        ) AS rn
    FROM [AlTasnimBI].[well].[well_master] AS wm
    WHERE wm.well_id IS NOT NULL
      AND wm.eng_completion_date IS NULL
),

LatestWells AS
(
    SELECT
        well_id,
        project_id,
        rig_id,
        well_type_id,
        station_id,

        ex_rig_on_date,
        rig_on_date,

        ex_rig_off_date,
        rig_off_date,

        eng_completion_date
    FROM DistinctWells
    WHERE rn = 1
)

SELECT
    well_id,
    project_id,
    rig_id,
    well_type_id,
    station_id,

    ex_rig_on_date,
    rig_on_date,

    ex_rig_off_date,
    rig_off_date,

    eng_completion_date

FROM LatestWells

WHERE
    /* ============================================================
       1. RIG-ON SLIPPAGE
       ============================================================ */
    (
        ex_rig_on_date IS NOT NULL
        AND
        (
            /* Actual date exists but happened after expected */
            (
                rig_on_date IS NOT NULL
                AND rig_on_date > ex_rig_on_date
            )

            OR

            /* Expected date has passed but actual date is missing */
            (
                rig_on_date IS NULL
                AND ex_rig_on_date < CAST(GETDATE() AS DATE)
            )
        )
    )

    OR

    /* ============================================================
       2. RIG-OFF SLIPPAGE
       ============================================================ */
    (
        ex_rig_off_date IS NOT NULL
        AND
        (
            /* Actual date exists but happened after expected */
            (
                rig_off_date IS NOT NULL
                AND rig_off_date > ex_rig_off_date
            )

            OR

            /* Expected date has passed but actual date is missing */
            (
                rig_off_date IS NULL
                AND ex_rig_off_date < CAST(GETDATE() AS DATE)
            )
        )
    )

    OR

    /* ============================================================
       3. HOOK-UP / WELL COMPLETION SLIPPAGE
       ============================================================ */
    (
        eng_completion_date IS NULL
        AND
        (
            /* Actual rig-off exists:
               Hook-up deadline = actual rig-off + 2 days */
            (
                rig_off_date IS NOT NULL
                AND DATEADD(day, 2, rig_off_date) < CAST(GETDATE() AS DATE)
            )

            OR

            /* Actual rig-off missing:
               Expected rig-off exists and its hook-up deadline
               has already passed */
            (
                rig_off_date IS NULL
                AND ex_rig_off_date IS NOT NULL
                AND DATEADD(day, 2, ex_rig_off_date) < CAST(GETDATE() AS DATE)
            )
        )
    )

ORDER BY
    ex_rig_on_date ASC;