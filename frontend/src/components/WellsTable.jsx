import { formatDate, formatSlippage } from "../utils.js";

const COLUMN_ORDER = [
  "well_id",
  "project_id",
  "rig_id",
  "well_type_id",
  "station_id",
  "ex_rig_on_date",
  "rig_on_date",
  "rig_on_slip_days",
  "ex_rig_off_date",
  "rig_off_date",
  "rig_off_slip_days",
];

const COLUMN_LABELS = {
  well_id: "Well ID",
  project_id: "Project ID",
  rig_id: "Rig",
  well_type_id: "Well Type",
  station_id: "Station",
  ex_rig_on_date: "Expected Rig On",
  rig_on_date: "Actual Rig On",
  rig_on_slip_days: "Rig-On Slip",
  ex_rig_off_date: "Expected Rig Off",
  rig_off_date: "Actual Rig Off",
  rig_off_slip_days: "Rig-Off Slip",
};

const DATE_COLUMNS = new Set([
  "ex_rig_on_date",
  "rig_on_date",
  "ex_rig_off_date",
  "rig_off_date",
]);

const SLIP_COLUMNS = new Set(["rig_on_slip_days", "rig_off_slip_days"]);

export default function WellsTable({ wells }) {
  if (wells.length === 0) {
    return null;
  }

  const availableColumns = COLUMN_ORDER.filter((column) =>
    wells.some((well) => column in well)
  );

  if (availableColumns.length === 0) {
    return null;
  }

  return (
    <section>
      <h2>Slipped Wells</h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {availableColumns.map((column) => (
                <th key={column}>{COLUMN_LABELS[column]}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {wells.map((well, index) => (
              <tr key={`${well.well_id}-${index}`}>
                {availableColumns.map((column) => {
                  if (SLIP_COLUMNS.has(column)) {
                    const slipDays = well[column];

                    return (
                      <td
                        key={column}
                        className={
                          typeof slipDays === "number" && slipDays > 0
                            ? "slip-late"
                            : undefined
                        }
                      >
                        {formatSlippage(slipDays)}
                      </td>
                    );
                  }

                  return (
                    <td key={column}>
                      {DATE_COLUMNS.has(column)
                        ? formatDate(well[column])
                        : well[column] ?? "—"}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
