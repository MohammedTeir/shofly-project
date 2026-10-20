import type { Json, User } from "./types";

const BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "";
let token: string | null = null;
let initData = "";

export class ApiError extends Error {
  constructor(public status: number, public code: string, public details: Json = {}) { super(`${status} ${code}`); }
}
export const setInitData = (d: string) => { initData = d; };
export const _reset = () => { token = null; initData = ""; };

async function raw<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const r = await fetch(`${BASE}/api/v1${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  if (!r.ok) {
    let code = "HTTP_ERROR"; let details: Json = {};
    try { const e = (await r.json()).error; code = e.code; details = e.details ?? {}; } catch { /* non-JSON */ }
    throw new ApiError(r.status, code, details);
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
    if (e instanceof ApiError && e.status === 401 && initData) { await login(); return raw<T>(method, path, body); }
    throw e;
  }
}

export const api = {
  get: <T = Json>(p: string) => call<T>("GET", p),
  post: <T = Json>(p: string, b: unknown = {}) => call<T>("POST", p, b),
  put: <T = Json>(p: string, b: unknown = {}) => call<T>("PUT", p, b),
  patch: <T = Json>(p: string, b: unknown = {}) => call<T>("PATCH", p, b),
};
export const qs = (o: Record<string, string | number | undefined | null | false>) =>
  Object.entries(o).filter(([, v]) => v !== undefined && v !== null && v !== "" && v !== false).map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`).join("&");
