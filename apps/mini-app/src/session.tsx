import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from "react";
import i18n from "./i18n";
import * as api from "./api";

type State = { status: "loading" } | { status: "no-telegram" } | { status: "error" } | { status: "ready" };
const Ctx = createContext<{ state: State; retry(): void; setLang(l: string): Promise<boolean> }>(null as never);
export const useSession = () => useContext(Ctx);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>({ status: "loading" });
  const start = useCallback(() => {
    const wa = window.Telegram?.WebApp;
    if (!wa?.initData) return setState({ status: "no-telegram" });  // never fake a login outside Telegram
    wa.ready(); wa.expand();
    api.setInitData(wa.initData);
    setState({ status: "loading" });
    api.login()
      .then((u) => { i18n.changeLanguage(u.preferred_language); setState({ status: "ready" }); }) // server preference wins (I18N-10)
      .catch(() => setState({ status: "error" }));
  }, []);
  useEffect(start, [start]);

  const setLang = useCallback(async (l: string) => {
    const prev = i18n.language;
    await i18n.changeLanguage(l);                       // optimistic
    try { await api.setLanguage(l); return true; }
    catch { await i18n.changeLanguage(prev); return false; } // rollback on failure
  }, []);
  return <Ctx.Provider value={{ state, retry: start, setLang }}>{children}</Ctx.Provider>;
}
