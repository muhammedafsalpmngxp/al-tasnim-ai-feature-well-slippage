/* ============================================================
   AL-TASNIM
   WELL SLIPPAGE AI
   ALL PROJECT IDs FOR ONE WELL

   INPUT:
       @WellId

   PURPOSE:
       well_master carries exactly one project_id per well, but
       task_daily rows for the same well frequently reference a
       DIFFERENT project_id — usually because separate scopes of
       work (e.g. Flowline vs Location) are tracked as separate
       projects against the same physical well. Some wells carry
       three or more distinct project_id values across their
       tasks; most carry one.

       This returns the UNION of every project_id seen for the
       well (well_master + task_daily), resolved to a human name
       via project.project_mstr where a match exists. A project_id
       with no match there still returns its own row, with
       project_code/project_name as NULL, rather than being
       silently dropped.
   ============================================================ */


DECLARE @WellId INT = ?;


WITH WellProjectIds AS
(
    SELECT project_id
    FROM [AlTasnimBI].[well].[well_master]
    WHERE well_id = @WellId
      AND project_id IS NOT NULL

    UNION

    SELECT project_id
    FROM [AlTasnimBI].[well].[task_daily]
    WHERE well_id = @WellId
      AND project_id IS NOT NULL
)


SELECT

    wpi.project_id,

    pm.project_code,
    pm.project_name

FROM WellProjectIds AS wpi

LEFT JOIN [AlTasnimBI].[project].[project_mstr] AS pm
    ON pm.project_id = wpi.project_id

ORDER BY
    pm.project_code,
    wpi.project_id;
