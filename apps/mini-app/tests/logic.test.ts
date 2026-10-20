import { afterEach, describe, expect, it, vi } from "vitest";
import ar from "../src/locales/ar.json";
import en from "../src/locales/en.json";
import { ApiError, _reset, listTitles, login, requestAccess, setInitData } from "../src/api";
import { dirFor, initialLanguage } from "../src/i18n";

const res = (status: number, body: unknown) => Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) } as Response);
afterEach(() => { vi.unstubAllGlobals(); _reset(); });

describe("i18n", () => {
  it("ar and en have identical keys and non-empty values", () => {
    expect(Object.keys(ar).sort()).toEqual(Object.keys(en).sort());
    for (const v of [...Object.values(ar), ...Object.values(en)]) expect(v.trim()).not.toBe("");
  });
  it("direction and initial language", () => {
    expect(dirFor("ar")).toBe("rtl"); expect(dirFor("en-US")).toBe("ltr");
    expect(initialLanguage("en-GB")).toBe("en"); expect(initialLanguage("fr")).toBe("ar"); expect(initialLanguage()).toBe("ar");
  });
});

describe("api client", () => {
  it("logs in with raw initData and sends the bearer token afterwards", async () => {
    const f = vi.fn()
      .mockReturnValueOnce(res(200, { access_token: "T1", user: { preferred_language: "en" } }))
      .mockReturnValueOnce(res(200, { items: [], next_cursor: null }));
    vi.stubGlobal("fetch", f); setInitData("raw=init&hash=h");
    expect((await login()).preferred_language).toBe("en");
    await listTitles("movie");
    expect(JSON.parse(f.mock.calls[0][1].body)).toEqual({ init_data: "raw=init&hash=h" });
    expect(f.mock.calls[1][1].headers.Authorization).toBe("Bearer T1");
  });
  it("re-logs in once on 401 then retries", async () => {
    const f = vi.fn()
      .mockReturnValueOnce(res(401, { error: { code: "INVALID_TOKEN" } }))
      .mockReturnValueOnce(res(200, { access_token: "T2", user: {} }))
      .mockReturnValueOnce(res(200, { items: [], next_cursor: null }));
    vi.stubGlobal("fetch", f); setInitData("x");
    await listTitles("series");
    expect(f).toHaveBeenCalledTimes(3);
    expect(f.mock.calls[2][1].headers.Authorization).toBe("Bearer T2");
  });
  it("surfaces the backend error code and does not loop forever", async () => {
    const f = vi.fn().mockImplementation(() => res(401, { error: { code: "INVALID_INIT_DATA" } }));
    vi.stubGlobal("fetch", f); setInitData("x");
    await expect(listTitles("movie")).rejects.toMatchObject({ status: 401, code: "INVALID_INIT_DATA" });
    expect(f.mock.calls.length).toBeLessThanOrEqual(3);
  });
  it("requests access via POST and exposes only the opaque deep link", async () => {
    const f = vi.fn().mockReturnValue(res(200, { delivery_type: "telegram_bot", bot_deep_link: "https://t.me/ShoflyBot?start=dl_abc" }));
    vi.stubGlobal("fetch", f); setInitData("x");
    expect((await requestAccess("a1")).bot_deep_link).toContain("start=dl_");
    expect(f.mock.calls[0][0]).toContain("/api/v1/media/a1/access"); expect(f.mock.calls[0][1].method).toBe("POST");
  });
  it("surfaces delivery denial codes", async () => {
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(res(403, { error: { code: "RIGHTS_NOT_AVAILABLE" } })));
    await expect(requestAccess("a1")).rejects.toMatchObject({ status: 403, code: "RIGHTS_NOT_AVAILABLE" });
  });
});
