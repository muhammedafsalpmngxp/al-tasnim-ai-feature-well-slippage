export function toDateOnly(value) {
  const date = value instanceof Date ? value : new Date(value);

  if (Number.isNaN(date.getTime())) {
    return null;
  }

  return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()));
}

export function daysBetween(laterValue, earlierValue) {
  const later = toDateOnly(laterValue);
  const earlier = toDateOnly(earlierValue);

  if (later === null || earlier === null) {
    return null;
  }

  return Math.round((later.getTime() - earlier.getTime()) / 86400000);
}

export function today() {
  return toDateOnly(new Date());
}

export function formatDate(value) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }

  return String(value).split("T")[0];
}

// Days a milestone slipped: positive = late, negative = early, 0 = on time.
// When the actual date is missing, an expected date already in the past counts
// as currently slipping by that many days.
export function milestoneSlippageDays(expectedValue, actualValue) {
  if (!expectedValue) {
    return null;
  }

  if (actualValue) {
    return daysBetween(actualValue, expectedValue);
  }

  const pendingDays = daysBetween(today(), expectedValue);

  if (pendingDays === null) {
    return null;
  }

  return pendingDays > 0 ? pendingDays : 0;
}

export function wellSlippage(well) {
  const rigOn = milestoneSlippageDays(well.ex_rig_on_date, well.rig_on_date);
  const rigOff = milestoneSlippageDays(well.ex_rig_off_date, well.rig_off_date);

  const known = [rigOn, rigOff].filter((value) => typeof value === "number");

  return {
    rigOn,
    rigOff,
    max: known.length > 0 ? Math.max(...known) : 0,
  };
}

export function formatSlippage(value) {
  if (typeof value !== "number") {
    return "—";
  }

  if (value > 0) {
    return `+${value}d`;
  }

  if (value < 0) {
    return `${value}d`;
  }

  return "0";
}
