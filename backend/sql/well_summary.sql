/* ============================================================
   AL-TASNIM
   WELL SLIPPAGE AI
   HEADLINE COUNTS

   total_wells
       Every well on record (distinct well_id).

   live_wells
       Wells whose Tasnim scope is still open
       (eng_completion_date IS NULL). Slippage detection runs
       over these only — a hooked-up well cannot slip.

   completed_wells
       Hook-up complete; out of scope for slippage.
   ============================================================ */

SELECT
    COUNT(DISTINCT well_id) AS total_wells,

    COUNT(DISTINCT
        CASE WHEN eng_completion_date IS NULL THEN well_id END
    ) AS live_wells,

    COUNT(DISTINCT
        CASE WHEN eng_completion_date IS NOT NULL THEN well_id END
    ) AS completed_wells

FROM [AlTasnimBI].[well].[well_master];
