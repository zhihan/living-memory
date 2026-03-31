import { auth } from "./firebase";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

async function getToken(): Promise<string> {
  if (!auth.currentUser) throw new Error("Not signed in");
  return auth.currentUser.getIdToken();
}

async function apiFetch(path: string, init?: RequestInit, retryCount = 0): Promise<Response> {
  const token = await getToken();
  const headers: Record<string, string> = {
    Authorization: `Bearer ${token}`,
    ...(init?.headers as Record<string, string>),
  };

  let resp = await fetch(`${BASE_URL}${path}`, { ...init, headers });

  // Retry once on 401 with a fresh token
  if (resp.status === 401 && retryCount === 0) {
    const freshToken = await auth.currentUser!.getIdToken(true);
    headers.Authorization = `Bearer ${freshToken}`;
    resp = await fetch(`${BASE_URL}${path}`, { ...init, headers });
  }

  if (!resp.ok) {
    const body = await resp.json().catch(() => ({ detail: resp.statusText }));
    let detail = body.detail ?? resp.statusText;
    if (Array.isArray(detail)) {
      detail = detail.map((d: { msg?: string }) => d.msg ?? JSON.stringify(d)).join("; ");
    } else if (typeof detail !== "string") {
      detail = JSON.stringify(detail);
    }
    const err = new ApiError(detail, resp.status);
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

// ============================================================
// Workspaces, Series, Occurrences, CheckIns
// ============================================================

export interface WorkspaceSummary {
  workspace_id: string;
  title: string;
  timezone: string;
  owner_uids: string[];
  member_roles: Record<string, string>;
  description: string | null;
  created_at: string;
  updated_at: string;
  series_count?: number;
  series_schedule?: ScheduleRule;
  series_default_time?: string | null;
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
  location_type: "fixed" | "per_occurrence" | "rotation";
  location_rotation: string[] | null;
  check_in_weekdays: number[] | null;
  rotation_mode?: "none" | "host_only" | "host_and_location";
  host_rotation?: string[];
  host_addresses?: Record<string, string>;
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
  location: string | null;
  host?: string;
  overrides: OccurrenceOverrides;
  enable_check_in: boolean;
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
  display_name: string | null;
  status: string;
  checked_in_at: string | null;
  note: string | null;
}

// --- Workspaces ---

export async function createWorkspace(
  title: string,
  type: string = "shared",
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
    location_type?: "fixed" | "per_occurrence" | "rotation";
    location_rotation?: string[];
    check_in_weekdays?: number[];
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

export interface CheckInReport {
  series_id: string;
  occurrences: OccurrenceSummary[];
  check_ins: CheckInSummary[];
  members: Record<string, string>;
  member_profiles: Record<string, { display_name?: string | null; email?: string | null }>;
}

export async function getSeriesCheckInReport(seriesId: string): Promise<CheckInReport> {
  const resp = await apiFetch(`/v2/series/${seriesId}/check-in-report`);
  return resp.json();
}

export async function patchSeries(
  seriesId: string,
  updates: Partial<{
    kind: string;
    title: string;
    description: string;
    default_time: string;
    check_in_weekdays: number[];
    default_duration_minutes: number;
    default_location: string;
    default_online_link: string;
    location_type: "fixed" | "per_occurrence" | "rotation";
    location_rotation: string[];
    rotation_mode: "none" | "host_only" | "host_and_location";
    host_rotation: string[];
    host_addresses: Record<string, string>;
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
  endDate: string,
): Promise<OccurrenceSummary[]> {
  const startDate = new Date().toISOString().slice(0, 10);
  const resp = await apiFetch(`/v2/series/${seriesId}/occurrences/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ start_date: startDate, end_date: endDate }),
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
    location?: string | null;
    host?: string | null;
    overrides?: OccurrenceOverrides;
    enable_check_in?: boolean;
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
  status: string = "confirmed",
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

export async function getMyOccurrenceCheckIn(
  occurrenceId: string,
): Promise<CheckInSummary | null> {
  const resp = await apiFetch(`/v2/occurrences/${occurrenceId}/my-check-in`);
  const data = await resp.json();
  return (data.check_in ?? null) as CheckInSummary | null;
}

export async function deleteCheckIn(checkInId: string): Promise<void> {
  await apiFetch(`/v2/check-ins/${checkInId}`, { method: "DELETE" });
}

export async function deleteOccurrence(occurrenceId: string): Promise<void> {
  await apiFetch(`/v2/occurrences/${occurrenceId}`, { method: "DELETE" });
}

export async function deleteSeries(seriesId: string): Promise<void> {
  await apiFetch(`/v2/series/${seriesId}`, { method: "DELETE" });
}

export async function deleteWorkspace(workspaceId: string): Promise<void> {
  await apiFetch(`/v2/workspaces/${workspaceId}`, { method: "DELETE" });
}

// --- Members & Invites ---

export async function getWorkspaceMembers(
  workspaceId: string,
): Promise<{
  workspace_id: string;
  members: Record<string, string>;
  member_details?: Array<{
    uid: string;
    role: string;
    display_name: string | null;
    email: string | null;
  }>;
}> {
  const resp = await apiFetch(`/v2/workspaces/${workspaceId}/members`);
  return resp.json();
}

export async function removeMember(
  workspaceId: string,
  uid: string,
): Promise<void> {
  await apiFetch(`/v2/workspaces/${workspaceId}/members/${uid}`, {
    method: "DELETE",
  });
}

export interface InviteInfo {
  invite_id: string;
  workspace_id: string;
  role: string;
  created_by: string;
  expires_at: string;
}

export async function createWorkspaceInvite(
  workspaceId: string,
  role: string = "participant",
  expiresInDays: number = 7,
): Promise<InviteInfo> {
  const resp = await apiFetch(`/v2/workspaces/${workspaceId}/invites`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role, expires_in_days: expiresInDays }),
  });
  return resp.json();
}

export async function acceptInvite(
  inviteId: string,
): Promise<{ accepted: boolean; workspace_id: string; role: string }> {
  const resp = await apiFetch(`/v2/invites/${inviteId}/accept`, {
    method: "POST",
  });
  return resp.json();
}

// ============================================================
// Assistant API
// ============================================================

export interface AssistantEvent {
  type: "status" | "text_chunk" | "action_proposal" | "done" | "error";
  message?: string;
  text?: string;
  action_id?: string;
  action_type?: string;
  preview_summary?: string;
  payload?: Record<string, unknown>;
}

/**
 * Send a message to the organizer assistant.
 * Returns a ReadableStream of SSE-encoded AssistantEvent objects.
 * The caller is responsible for consuming the stream.
 */
export async function sendAssistantMessage(
  workspaceId: string,
  message: string,
): Promise<ReadableStream<Uint8Array>> {
  const resp = await apiFetch(`/v2/workspaces/${workspaceId}/assistant`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  if (!resp.body) throw new Error("No response body");
  return resp.body;
}

export async function confirmAssistantAction(
  actionId: string,
): Promise<{ status: string; result: unknown }> {
  const resp = await apiFetch(`/v2/assistant/actions/${actionId}/confirm`, {
    method: "POST",
  });
  return resp.json();
}

export async function cancelAssistantAction(actionId: string): Promise<void> {
  await apiFetch(`/v2/assistant/actions/${actionId}/cancel`, { method: "POST" });
}

export async function regenerateRotationFrom(
  seriesId: string,
  occurrenceId: string,
): Promise<{ updated_count: number }> {
  const resp = await apiFetch(`/v2/series/${seriesId}/occurrences/${occurrenceId}/regenerate-rotation`, {
    method: "POST",
  });
  return resp.json();
}
