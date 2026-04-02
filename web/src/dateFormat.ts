/**
 * Timezone-aware date formatting.
 *
 * When the user's local timezone matches the room timezone, show a single
 * formatted date. When they differ, show both:
 *   "Fri, Jan 3, 5:00 PM (EST) / Sat, Jan 4, 6:00 AM (CST)"
 */

const userTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;

export function getUserTimezone(): string {
  return userTimezone;
}

export function timezonesMatch(roomTimezone: string): boolean {
  // Compare by formatting the same instant — two IANA zones can map to the
  // same rules (e.g. "Asia/Taipei" and "Asia/Shanghai").  Comparing names
  // would produce false negatives.  Instead we normalise both names via the
  // Intl API and check string equality.
  try {
    const a = Intl.DateTimeFormat("en-US", { timeZone: roomTimezone }).resolvedOptions().timeZone;
    const b = Intl.DateTimeFormat("en-US", { timeZone: userTimezone }).resolvedOptions().timeZone;
    return a === b;
  } catch {
    return false;
  }
}

interface FormatOptions {
  weekday?: "short" | "long";
  year?: "numeric";
  month?: "short" | "long";
  day?: "numeric";
  hour?: "numeric";
  minute?: "2-digit";
}

function formatInTz(iso: string, tz: string, opts: FormatOptions): string {
  return new Date(iso).toLocaleString("en-US", { timeZone: tz, ...opts });
}

function tzAbbr(iso: string, tz: string): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: tz,
    timeZoneName: "short",
  }).formatToParts(new Date(iso));
  return parts.find((p) => p.type === "timeZoneName")?.value ?? tz;
}

/**
 * Format a date, showing dual timezone when the user's timezone differs from
 * the room's.  If roomTimezone is omitted the user's local timezone is used
 * (single format).
 */
export function formatDate(
  iso: string,
  roomTimezone?: string,
  opts: FormatOptions = {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  },
): string {
  const roomTz = roomTimezone ?? userTimezone;
  const roomStr = formatInTz(iso, roomTz, opts);

  if (!roomTimezone || timezonesMatch(roomTimezone)) {
    return roomStr;
  }

  const userStr = formatInTz(iso, userTimezone, opts);
  const roomAbbr = tzAbbr(iso, roomTz);
  const userAbbr = tzAbbr(iso, userTimezone);
  return `${roomStr} (${roomAbbr}) / ${userStr} (${userAbbr})`;
}

/**
 * Short date (month/day only) — used in report tables.
 * No dual format needed since it's date-only and usually the same.
 */
export function formatShortDate(iso: string, roomTimezone?: string): string {
  const tz = roomTimezone ?? userTimezone;
  return new Date(iso).toLocaleDateString("en-US", {
    timeZone: tz,
    month: "short",
    day: "numeric",
  });
}
