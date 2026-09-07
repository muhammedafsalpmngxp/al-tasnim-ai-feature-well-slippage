SELECT
    well_id,
    project_id,
    rig_id,
    well_type_id,
    station_id,
    ex_rig_on_date,
    rig_on_date,
    ex_rig_off_date,
    rig_off_date
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
ORDER BY
    ex_rig_on_date;