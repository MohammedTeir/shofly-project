import { afterEach, describe, expect, it, vi } from "vitest";
import ar from "../src/locales/ar.json";
import en from "../src/locales/en.json";
import { ApiError, _reset, api, login, qs, setInitData } from "../src/api";
import { canApproveRights, canCatalog, canEnter, isSuper, pagesFor } from "../src/roles";
import { dirFor } from "../src/i18n";

const res = (status: number, body: unknown) => Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) } as Response);
afterEach(() => { vi.unstubAllGlobals(); _reset(); });

describe("roles", () => {
  it("gates pages and actions by role", () => {
    expect(pagesFor("super_admin")).toEqual(["overview", "titles", "imports", "rights", "users", "audit"]);
    expect(pagesFor("content_admin")).toEqual(["overview", "titles", "imports", "rights"]);
    expect(pagesFor("rights_admin")).toEqual(["rights"]);
    expect(pagesFor("member")).toEqual([]);
    expect(canEnter("member")).toBe(false); expect(canEnter("moderator")).toBe(false); expect(canEnter("rights_admin")).toBe(true);
    expect(canApproveRights("content_admin")).toBe(false); expect(canApproveRights("rights_admin")).toBe(true);
    expect(canCatalog("rights_admin")).toBe(false); expect(isSuper("content_admin")).toBe(false);
  });
});

describe("i18n", () => {
  it("ar and en keys match and are non-empty", () => {
    expect(Object.keys(ar).sort()).toEqual(Object.keys(en).sort());
    for (const v of [...Object.values(ar), ...Object.values(en)]) expect(v.trim()).not.toBe("");
    expect(dirFor("ar")).toBe("rtl"); expect(dirFor("en")).toBe("ltr");
  });
  it("has a message for every publish blocker code the backend can return", () => {
    for (const c of ["METADATA_NOT_VERIFIED", "NO_VERIFIED_ASSET", "RIGHTS_NOT_VALID", "NO_DELIVERABLE_EPISODE"]) expect(en).toHaveProperty(`bl_${c}`);
  });
});

describe("api", () => {
  it("surfaces error code and details (publish blockers)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(res(409, { error: { code: "PUBLISH_BLOCKED", details: { blockers: ["NO_VERIFIED_ASSET"] } } })));
    await expect(api.post("/admin/catalog/movie/x/publish")).rejects.toMatchObject({ status: 409, code: "PUBLISH_BLOCKED", details: { blockers: ["NO_VERIFIED_ASSET"] } });
  });
  it("re-logs in once on 401 and retries with the new token", async () => {
    const f = vi.fn().mockReturnValueOnce(res(401, { error: { code: "INVALID_TOKEN" } }))
      .mockReturnValueOnce(res(200, { access_token: "T2", user: {} })).mockReturnValueOnce(res(200, { ok: 1 }));
    vi.stubGlobal("fetch", f); setInitData("x");
    await api.get("/admin/overview");
    expect(f).toHaveBeenCalledTimes(3); expect(f.mock.calls[2][1].headers.Authorization).toBe("Bearer T2");
  });
  it("login sends raw initData; qs drops empty values", async () => {
    const f = vi.fn().mockReturnValue(res(200, { access_token: "T", user: { role: "super_admin" } }));
    vi.stubGlobal("fetch", f); setInitData("a=b&hash=h");
    expect((await login()).role).toBe("super_admin");
    expect(JSON.parse(f.mock.calls[0][1].body)).toEqual({ init_data: "a=b&hash=h" });
    expect(qs({ q: "a b", status: "", n: 0, x: undefined, e: false })).toBe("q=a%20b&n=0");
    expect(ApiError).toBeDefined();
  });
});
