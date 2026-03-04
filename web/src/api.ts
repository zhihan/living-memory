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

export async function createMemory(
  slug: string,
  message: string,
): Promise<{ action: string; id: string; memory: MemoryItem }> {
  const resp = await apiFetch(`/api/pages/${slug}/memories`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  return resp.json();
}
