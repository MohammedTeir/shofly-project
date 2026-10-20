import type { Episode, Kind, Page, Title, User } from "./types";

const BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "";
let token: string | null = null;
let initData = "";

export class ApiError extends Error {
  constructor(public status: number, public code: string) { super(`${status} ${code}`); }
}
export const setInitData = (d: string) => { initData = d; };
export const _reset = () => { token = null; initData = ""; };

async function raw<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const r = await fetch(`${BASE}/api/v1${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  if (!r.ok) {
    let code = "HTTP_ERROR";
    try { code = (await r.json()).error.code; } catch { /* non-JSON error */ }
    throw new ApiError(r.status, code);
  }
  return r.json() as Promise<T>;
}

export async function login(): Promise<User> {
  const r = await raw<{ access_token: string; user: User }>("POST", "/auth/telegram", { init_data: initData });
  token = r.access_token;
  return r.user;
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  try { return await raw<T>(method, path, body); }
  catch (e) {
    if (e instanceof ApiError && e.status === 401 && initData) { await login(); return raw<T>(method, path, body); } // token expired: one silent re-login
    throw e;
  }
}

const seg = (k: Kind) => (k === "movie" ? "movies" : "series");
export const setLanguage = (l: string) => call<{ preferred_language: string }>("PATCH", "/me/preferences", { preferred_language: l });
export const listTitles = (k: Kind) => call<Page>("GET", `/catalog/${seg(k)}?limit=20`);
export const search = (q: string) => call<{ items: Title[] }>("GET", `/catalog/search?q=${encodeURIComponent(q)}&limit=30`);
export const getTitle = (k: Kind, id: string) => call<Title>("GET", `/${seg(k)}/${id}`);
export const getSeason = (id: string, n: number) => call<{ season_number: number; episodes: Episode[] }>("GET", `/catalog/series/${id}/seasons/${n}`);
export const getFavorites = () => call<Page>("GET", "/me/favorites?limit=50");
export const setFavorite = (k: Kind, id: string, on: boolean) => call<{ favorited: boolean }>(on ? "PUT" : "DELETE", `/me/favorites/${k}/${id}`);
export const requestAccess = (assetId: string) => call<{ delivery_type: string; bot_deep_link?: string }>("POST", `/media/${assetId}/access`, {});
