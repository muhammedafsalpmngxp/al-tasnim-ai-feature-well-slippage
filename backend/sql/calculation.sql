SELECT
    COUNT(*) AS total_wells,
    SUM
    (
        CASE
            WHEN eng_completion_date IS NULL THEN 1
            ELSE 0
        END
    ) AS live_wells
FROM [well].[well_master];