import { auth } from "./firebase";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

async function getToken(): Promise<string> {
  if (!auth.currentUser) throw new Error("Not signed in");
  return auth.currentUser.getIdToken();
}

async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const token = await getToken();
  const headers: Record<string, string> = {
    Authorization: `Bearer ${token}`,
    ...(init?.headers as Record<string, string>),
  };

  let resp = await fetch(`${BASE_URL}${path}`, { ...init, headers });

  // Retry once on 401 with a fresh token
  if (resp.status === 401) {
    const freshToken = await auth.currentUser!.getIdToken(true);
    headers.Authorization = `Bearer ${freshToken}`;
    resp = await fetch(`${BASE_URL}${path}`, { ...init, headers });
  }

  if (!resp.ok) {
    const body = await resp.json().catch(() => ({ detail: resp.statusText }));
    const err = new ApiError(body.detail || resp.statusText, resp.status);
    throw err;
  }

  return resp;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export interface UserProfile {
  uid: string;
  display_name: string | null;
  photo_url: string | null;
  default_personal_page_id: string | null;
  created_at: string;
}

export interface PageSummary {
  slug: string;
  title: string;
  visibility: string;
  owner_uids: string[];
  description: string | null;
  timezone: string | null;
  created_at: string;
  updated_at: string;
}

export interface MemoryItem {
  id: string;
  title: string | null;
  content: string;
  target: string | null;
  expires: string | null;
  time: string | null;
  place: string | null;
  attachments: string[];
  visibility: string;
}

export async function getMe(): Promise<UserProfile> {
  const resp = await apiFetch("/api/users/me");
  const data = await resp.json();
  return data.user;
}

export async function getMyPages(): Promise<PageSummary[]> {
  const resp = await apiFetch("/api/users/me/pages");
  const data = await resp.json();
  return data.pages;
}

export async function getPage(slug: string): Promise<PageSummary> {
  const resp = await apiFetch(`/api/pages/${slug}`);
  const data = await resp.json();
  return data.page;
}

export async function getPageMemories(slug: string): Promise<MemoryItem[]> {
  const resp = await apiFetch(`/api/pages/${slug}/memories`);
  const data = await resp.json();
  return data.memories;
}

export async function createPage(
  slug: string,
  title: string,
  visibility: string,
  description?: string,
  timezone?: string,
): Promise<PageSummary> {
  const resp = await apiFetch("/api/pages", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ slug, title, visibility, description, timezone }),
  });
  const data = await resp.json();
  return data.page;
}

export async function patchPage(
  slug: string,
  updates: { title?: string; description?: string; timezone?: string },
): Promise<PageSummary> {
  const resp = await apiFetch(`/api/pages/${encodeURIComponent(slug)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
  const data = await resp.json();
  return data.page;
}

export async function deleteMemory(
  slug: string,
  memoryId: string,
): Promise<void> {
  await apiFetch(`/api/pages/${encodeURIComponent(slug)}/memories/${encodeURIComponent(memoryId)}`, {
    method: "DELETE",
  });
}

export async function createMemory(
  slug: string,
  message: string,
  visibility: string = "public",
): Promise<{ action: string; id: string; memory: MemoryItem }> {
  const resp = await apiFetch(`/api/pages/${slug}/memories`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, visibility }),
  });
  return resp.json();
}

// ============================================================
// V2 API — Workspaces, Series, Occurrences, CheckIns
// ============================================================

export interface WorkspaceSummary {
  workspace_id: string;
  type: string;
  title: string;
  timezone: string;
  owner_uids: string[];
  member_roles: Record<string, string>;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface SeriesSummary {
  series_id: string;
  workspace_id: string;
  kind: string;
  title: string;
  description: string | null;
  schedule_rule: ScheduleRule;
  default_time: string | null;
  default_duration_minutes: number | null;
  default_location: string | null;
  default_online_link: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface ScheduleRule {
  /** "daily" | "weekly" | "weekdays" | "custom" | "once" */
  frequency: string;
  /** ISO weekday integers: 1=Mon … 7=Sun */
  weekdays?: number[];
  interval?: number;
  until?: string;
  count?: number;
}

export interface OccurrenceSummary {
  occurrence_id: string;
  series_id: string;
  workspace_id: string;
  scheduled_for: string;
  status: string;
  overrides: OccurrenceOverrides;
  created_at: string;
  updated_at: string;
}

export interface OccurrenceOverrides {
  title?: string | null;
  location?: string | null;
  online_link?: string | null;
  duration_minutes?: number | null;
  notes?: string | null;
}

export interface CheckInSummary {
  check_in_id: string;
  occurrence_id: string;
  user_id: string;
  status: string;
  checked_in_at: string | null;
  note: string | null;
}

// --- Workspaces ---

export async function createWorkspace(
  title: string,
  type: string = "meeting",
  timezone?: string,
): Promise<WorkspaceSummary> {
  const resp = await apiFetch("/v2/workspaces", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title,
      type,
      timezone: timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone,
    }),
  });
  return resp.json();
}

export async function getWorkspace(id: string): Promise<WorkspaceSummary> {
  const resp = await apiFetch(`/v2/workspaces/${id}`);
  return resp.json();
}

export async function getMyWorkspaces(): Promise<WorkspaceSummary[]> {
  const resp = await apiFetch("/v2/workspaces");
  const data = await resp.json();
  return (data.workspaces ?? []) as WorkspaceSummary[];
}

export async function patchWorkspace(
  id: string,
  updates: { title?: string; timezone?: string },
): Promise<WorkspaceSummary> {
  const resp = await apiFetch(`/v2/workspaces/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
  return resp.json();
}

// --- Series ---

export async function createSeries(
  workspaceId: string,
  payload: {
    title: string;
    kind?: string;
    description?: string;
    schedule_rule: ScheduleRule;
    default_time?: string;
    default_duration_minutes?: number;
    default_location?: string;
    default_online_link?: string;
  },
): Promise<SeriesSummary> {
  const resp = await apiFetch(`/v2/workspaces/${workspaceId}/series`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind: "meeting", ...payload }),
  });
  return resp.json();
}

export async function getWorkspaceSeries(workspaceId: string): Promise<SeriesSummary[]> {
  const resp = await apiFetch(`/v2/workspaces/${workspaceId}/series`);
  const data = await resp.json();
  return (data.series ?? []) as SeriesSummary[];
}

export async function getSeries(seriesId: string): Promise<SeriesSummary> {
  const resp = await apiFetch(`/v2/series/${seriesId}`);
  return resp.json();
}

export async function patchSeries(
  seriesId: string,
  updates: Partial<{
    title: string;
    description: string;
    default_time: string;
    default_duration_minutes: number;
    default_location: string;
    default_online_link: string;
    schedule_rule: ScheduleRule;
    status: string;
  }>,
): Promise<SeriesSummary> {
  const resp = await apiFetch(`/v2/series/${seriesId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
  return resp.json();
}

// --- Occurrences ---

export async function generateOccurrences(
  seriesId: string,
  windowDays: number = 60,
): Promise<OccurrenceSummary[]> {
  const resp = await apiFetch(`/v2/series/${seriesId}/occurrences/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ window_days: windowDays }),
  });
  const data = await resp.json();
  return (data.occurrences ?? []) as OccurrenceSummary[];
}

export async function getSeriesOccurrences(seriesId: string): Promise<OccurrenceSummary[]> {
  const resp = await apiFetch(`/v2/series/${seriesId}/occurrences`);
  const data = await resp.json();
  return (data.occurrences ?? []) as OccurrenceSummary[];
}

export async function getOccurrence(occurrenceId: string): Promise<OccurrenceSummary> {
  const resp = await apiFetch(`/v2/occurrences/${occurrenceId}`);
  return resp.json();
}

export async function patchOccurrence(
  occurrenceId: string,
  updates: {
    status?: string;
    overrides?: OccurrenceOverrides;
  },
): Promise<OccurrenceSummary> {
  const resp = await apiFetch(`/v2/occurrences/${occurrenceId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
  return resp.json();
}

// --- CheckIns ---

export async function createCheckIn(
  occurrenceId: string,
  status: string = "present",
  note?: string,
): Promise<CheckInSummary> {
  const resp = await apiFetch(`/v2/occurrences/${occurrenceId}/check-ins`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status, note }),
  });
  return resp.json();
}

export async function getOccurrenceCheckIns(occurrenceId: string): Promise<CheckInSummary[]> {
  const resp = await apiFetch(`/v2/occurrences/${occurrenceId}/check-ins`);
  const data = await resp.json();
  return (data.check_ins ?? []) as CheckInSummary[];
}
