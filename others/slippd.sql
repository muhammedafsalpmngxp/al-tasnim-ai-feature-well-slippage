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
FROM [AlTasnimBI].[well].[well_master]
WHERE
    (
        ex_rig_on_date IS NOT NULL
        AND
        (
            rig_on_date > ex_rig_on_date
            OR
            (
                rig_on_date IS NULL
                AND ex_rig_on_date < CAST(GETDATE() AS DATE)
            )
        )
    )
    OR
    (
        ex_rig_off_date IS NOT NULL
        AND
        (
            rig_off_date > ex_rig_off_date
            OR
            (
                rig_off_date IS NULL
                AND ex_rig_off_date < CAST(GETDATE() AS DATE)
            )
        )
    )
    OR
    (
        -- Hook-up milestone: business-rule deadline is rig_off_date + 2 days
        -- once the rig is off, otherwise the planned ex_rig_off_date + 2 days.
        -- A well is not slipped here once eng_completion_date is recorded.
        eng_completion_date IS NULL
        AND
        (
            CASE
                WHEN rig_off_date IS NOT NULL
                    THEN DATEADD(day, 2, rig_off_date)
                ELSE DATEADD(day, 2, ex_rig_off_date)
            END
        ) < CAST(GETDATE() AS DATE)
    )
ORDER BY
    ex_rig_on_date;