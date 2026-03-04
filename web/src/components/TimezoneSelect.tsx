const COMMON_TIMEZONES = [
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "America/Anchorage",
  "Pacific/Honolulu",
  "UTC",
];

function getAllTimezones(): string[] {
  try {
    // Intl.supportedValuesOf is available in modern browsers but not in all TS libs
    return (Intl as any).supportedValuesOf("timeZone") as string[];
  } catch {
    return COMMON_TIMEZONES;
  }
}

const commonSet = new Set(COMMON_TIMEZONES);
const allTimezones = getAllTimezones().filter((tz) => !commonSet.has(tz));

export function TimezoneSelect({
  value,
  onChange,
  id,
}: {
  value: string;
  onChange: (tz: string) => void;
  id?: string;
}) {
  return (
    <select
      id={id}
      className="form-input"
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      <optgroup label="Common">
        {COMMON_TIMEZONES.map((tz) => (
          <option key={tz} value={tz}>
            {tz.replace(/_/g, " ")}
          </option>
        ))}
      </optgroup>
      <optgroup label="All Timezones">
        {allTimezones.map((tz) => (
          <option key={tz} value={tz}>
            {tz.replace(/_/g, " ")}
          </option>
        ))}
      </optgroup>
    </select>
  );
}
