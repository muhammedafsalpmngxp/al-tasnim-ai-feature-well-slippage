/* ============================================================
   AL-TASNIM
   WELL SLIPPAGE AI
   SLIPPED WELL DETECTION

   PURPOSE:
       Classify EVERY well on record, across all measurable
       milestones — not just rig-on / rig-off.

       One row per well, whatever its state, carrying two verdict
       columns so a single definition of "slipped" serves both the
       slipped-well list and the full well picker:

         is_completed  hook-up recorded (business_rules.md §8)
         is_slipped    a LIVE well that failed a milestone test

       A completed well is never is_slipped: a hooked-up well cannot
       slip. Callers that want only the slipped wells filter on
       is_slipped — see app/services/slipped_wells.py.

   NULL SAFETY:
       Source data is incomplete, so every test below is anchored
       on a column that is reliably populated:

         - ex_rig_on_date  / ex_rig_off_date  are 100% populated
           and are used as the baselines.
         - A test that needs an ACTUAL date only fires when that
           date is present (e.g. hook-up needs rig_off_date).
         - const_complete_date, scr_date and tie_in_ready_date are
           deliberately NOT used as slip tests: they are 34%, 43%
           and 68% populated, so a NULL there means "not recorded"
           far more often than "late".

       Construction therefore uses the same NULL-safe rule as
       investigation.sql: past ex_rig_on - 1 day with no rig_on.

   DUE / NON-DUE:
       kpi_miss_reason attributes the delay. FLAF/SCR/PDO-side
       causes are classified NON_DUE (bonus potential) rather than
       counted as Tasnim-side risk.
   ============================================================ */


DECLARE @Today DATE = CAST(GETDATE() AS DATE);


WITH AllWells AS
(
    /* Every well on record. Completion is carried as a COLUMN
       (eng_completion_date) and turned into a verdict in the final
       SELECT, rather than filtering completed wells out here — the
       dashboard's picker lists them too. */

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

        pegged_date,
        flaf_issue_date,
        eng_completion_date,

        kpi_miss_reason

    FROM [AlTasnimBI].[well].[well_master]
),


Signals AS
(
    SELECT
        lw.*,


        /* ----- RIG-ON: recorded but late ----- */
        CASE
            WHEN lw.ex_rig_on_date IS NOT NULL
             AND lw.rig_on_date IS NOT NULL
             AND lw.rig_on_date > lw.ex_rig_on_date
                THEN DATEDIFF(day, lw.ex_rig_on_date, lw.rig_on_date)
            ELSE 0
        END AS rig_on_late_days,


        /* ----- RIG-ON: not recorded, deadline passed ----- */
        CASE
            WHEN lw.ex_rig_on_date IS NOT NULL
             AND lw.rig_on_date IS NULL
             AND lw.ex_rig_on_date < @Today
                THEN DATEDIFF(day, lw.ex_rig_on_date, @Today)
            ELSE 0
        END AS rig_on_pending_days,


        /* ----- RIG-OFF: recorded but late ----- */
        CASE
            WHEN lw.ex_rig_off_date IS NOT NULL
             AND lw.rig_off_date IS NOT NULL
             AND lw.rig_off_date > lw.ex_rig_off_date
                THEN DATEDIFF(day, lw.ex_rig_off_date, lw.rig_off_date)
            ELSE 0
        END AS rig_off_late_days,


        /* ----- RIG-OFF: not recorded, deadline passed ----- */
        CASE
            WHEN lw.ex_rig_off_date IS NOT NULL
             AND lw.rig_off_date IS NULL
             AND lw.ex_rig_off_date < @Today
                THEN DATEDIFF(day, lw.ex_rig_off_date, @Today)
            ELSE 0
        END AS rig_off_pending_days,


        /* ----- HOOK-UP: rig-off + 2 days passed, not complete -----
           Only fires when rig_off_date exists, so a missing
           rig_off_date can never be mistaken for a slip. */
        CASE
            WHEN lw.rig_off_date IS NOT NULL
             AND @Today > DATEADD(day, 2, lw.rig_off_date)
                THEN DATEDIFF(day, DATEADD(day, 2, lw.rig_off_date), @Today)
            ELSE 0
        END AS hookup_overdue_days,


        /* ----- CONSTRUCTION: past ex_rig_on - 1d, no rig-on ----- */
        CASE
            WHEN lw.ex_rig_on_date IS NOT NULL
             AND lw.rig_on_date IS NULL
             AND @Today > DATEADD(day, -1, lw.ex_rig_on_date)
                THEN DATEDIFF(day, DATEADD(day, -1, lw.ex_rig_on_date), @Today)
            ELSE 0
        END AS construction_overdue_days,


        /* ----- PEGGING: recorded after the -60d deadline ----- */
        CASE
            WHEN lw.ex_rig_on_date IS NOT NULL
             AND lw.pegged_date IS NOT NULL
             AND lw.pegged_date > DATEADD(day, -60, lw.ex_rig_on_date)
                THEN DATEDIFF(
                        day,
                        DATEADD(day, -60, lw.ex_rig_on_date),
                        lw.pegged_date
                     )
            ELSE 0
        END AS pegging_late_days,


        /* ----- PEGGING: not recorded, -60d deadline passed ----- */
        CASE
            WHEN lw.ex_rig_on_date IS NOT NULL
             AND lw.pegged_date IS NULL
             AND @Today > DATEADD(day, -60, lw.ex_rig_on_date)
                THEN DATEDIFF(
                        day,
                        DATEADD(day, -60, lw.ex_rig_on_date),
                        @Today
                     )
            ELSE 0
        END AS pegging_missed_days,


        /* ----- FLAF: issued after the -90d deadline ----- */
        CASE
            WHEN lw.ex_rig_on_date IS NOT NULL
             AND lw.flaf_issue_date IS NOT NULL
             AND lw.flaf_issue_date > DATEADD(day, -90, lw.ex_rig_on_date)
                THEN DATEDIFF(
                        day,
                        DATEADD(day, -90, lw.ex_rig_on_date),
                        lw.flaf_issue_date
                     )
            ELSE 0
        END AS flaf_late_days,


        /* ----- FLAF: not issued, -90d deadline passed ----- */
        CASE
            WHEN lw.ex_rig_on_date IS NOT NULL
             AND lw.flaf_issue_date IS NULL
             AND @Today > DATEADD(day, -90, lw.ex_rig_on_date)
                THEN DATEDIFF(
                        day,
                        DATEADD(day, -90, lw.ex_rig_on_date),
                        @Today
                     )
            ELSE 0
        END AS flaf_missed_days,


        /* ----- DATA QUALITY: impossible date ordering ----- */
        CASE
            WHEN lw.rig_off_date IS NOT NULL
             AND lw.rig_on_date IS NOT NULL
             AND lw.rig_off_date < lw.rig_on_date
                THEN 1
            ELSE 0
        END AS dq_rig_off_before_rig_on,


        CASE
            WHEN lw.ex_rig_on_date IS NULL
              OR lw.ex_rig_off_date IS NULL
                THEN 1
            ELSE 0
        END AS dq_missing_baseline

        /* NOTE - a previous data-quality flag here treated an actual
           date falling well before its baseline as a suspect record.
           business_rules.md §5 is explicit that an actual earlier than
           expected means the work finished AHEAD OF SCHEDULE and must
           never be reported as a delay, a variance problem, a
           data-quality issue or an anomaly. The flag was therefore
           removed rather than re-tuned. Direction is carried by the
           signed variance instead. */

        /* DUE / NON-DUE is derived from kpi_miss_reason in
           app/services/attribution.py — one definition, shared
           with the per-well risk assessment. */

    FROM AllWells AS lw
),


Scored AS
(
    SELECT
        s.*,

        CASE WHEN s.rig_on_late_days > 0
                  OR s.rig_on_pending_days > 0
             THEN 1 ELSE 0 END AS slip_rig_on,

        CASE WHEN s.rig_off_late_days > 0
                  OR s.rig_off_pending_days > 0
             THEN 1 ELSE 0 END AS slip_rig_off,

        CASE WHEN s.hookup_overdue_days > 0
             THEN 1 ELSE 0 END AS slip_hookup,

        CASE WHEN s.construction_overdue_days > 0
             THEN 1 ELSE 0 END AS slip_construction,

        CASE WHEN s.pegging_late_days > 0
                  OR s.pegging_missed_days > 0
             THEN 1 ELSE 0 END AS slip_pegging,

        CASE WHEN s.flaf_late_days > 0
                  OR s.flaf_missed_days > 0
             THEN 1 ELSE 0 END AS slip_flaf,

        /* Worst lateness across every milestone measured. */
        (
            SELECT MAX(value)
            FROM (VALUES
                (s.rig_on_late_days),
                (s.rig_on_pending_days),
                (s.rig_off_late_days),
                (s.rig_off_pending_days),
                (s.hookup_overdue_days),
                (s.construction_overdue_days),
                (s.pegging_late_days),
                (s.pegging_missed_days),
                (s.flaf_late_days),
                (s.flaf_missed_days)
            ) AS milestone_lateness(value)
        ) AS delay_days

    FROM Signals AS s
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

    pegged_date,
    flaf_issue_date,
    eng_completion_date,

    delay_days,

    /* ----- VERDICTS ----- */

    CASE WHEN eng_completion_date IS NOT NULL
         THEN 1 ELSE 0 END AS is_completed,

    /* Scoped to live wells on purpose: a hooked-up well cannot slip
       (business_rules.md §8), so completion suppresses the verdict
       even though the milestone tests above still evaluated. */
    CASE WHEN eng_completion_date IS NULL
          AND (slip_rig_on = 1
            OR slip_rig_off = 1
            OR slip_hookup = 1
            OR slip_construction = 1
            OR slip_pegging = 1
            OR slip_flaf = 1)
         THEN 1 ELSE 0 END AS is_slipped,

    slip_rig_on,
    slip_rig_off,
    slip_hookup,
    slip_construction,
    slip_pegging,
    slip_flaf,

    hookup_overdue_days,
    construction_overdue_days,
    pegging_missed_days,
    flaf_missed_days,

    kpi_miss_reason,

    dq_rig_off_before_rig_on,
    dq_missing_baseline

FROM Scored

/* No WHERE: every well is returned and classified. Filtering to the
   slipped ones is the caller's job (slipped_wells.get_slipped_wells),
   so the slip definition is not written down twice. */

ORDER BY
    well_id;
