/* ============================================================
   AL-TASNIM
   WELL SLIPPAGE AI
   CREW / SUPERVISOR / EMPLOYEE ROSTER FOR ONE WELL

   PURPOSE:
       Resolve the people behind a well's work:

           well_id
             -> well.task_daily.crew_id       crews that worked the well
                -> ref.crew.code              crew code
                -> ref.crew.supervisor_id     the crew's supervisor
                   -> ref.employee.emp_name   supervisor name
                -> bridge.crew_employee       crew membership
                   -> ref.employee            employee id + name

   JOIN KEYS:
       ref.employee.id is the key both bridge.crew_employee.employee_id
       and ref.crew.supervisor_id point at. Verified against the data:
       every non-NULL supervisor_id and every membership row resolves.

   DEDUPLICATION:
       A well has many task_daily rows and the same crew repeats across
       them, so the crew set is taken DISTINCT before anything is joined
       to it, and the final projection is DISTINCT too. Each crew,
       supervisor and employee is therefore reported once.

   NULL SAFETY:
       LEFT JOINs throughout. A crew with no ref.crew row, no supervisor
       or no membership row still returns, with NULLs. A missing value
       means it is not recorded — never that the crew is empty, and
       never a value to fill in.

   PARAMETER:
       @WellId — bound positionally (?) by the caller.
   ============================================================ */


DECLARE @WellId INT = ?;


WITH WellCrews AS
(
    /* Every distinct crew recorded against this well's tasks. */
    SELECT DISTINCT
        td.crew_id

    FROM [AlTasnimBI].[well].[task_daily] AS td

    WHERE td.well_id = @WellId
      AND td.crew_id IS NOT NULL
)


SELECT DISTINCT
    wc.crew_id,
    rc.code                 AS crew_code,

    rc.supervisor_id,
    supervisor.emp_name     AS supervisor_name,

    employee.id             AS employee_id,
    employee.emp_name       AS employee_name

FROM WellCrews AS wc

LEFT JOIN [AlTasnimBI].[ref].[crew] AS rc
       ON rc.crew_id = wc.crew_id

LEFT JOIN [AlTasnimBI].[ref].[employee] AS supervisor
       ON supervisor.id = rc.supervisor_id

LEFT JOIN [AlTasnimBI].[bridge].[crew_employee] AS bce
       ON bce.crew_id = wc.crew_id

LEFT JOIN [AlTasnimBI].[ref].[employee] AS employee
       ON employee.id = bce.employee_id

/* Aliases, not the underlying expressions: SELECT DISTINCT requires
   every ORDER BY item to be in the select list. */
ORDER BY
    crew_code,
    crew_id,
    employee_name,
    employee_id;
