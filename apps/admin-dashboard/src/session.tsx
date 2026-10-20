import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from "react";
import * as client from "./api";
import { canEnter } from "./roles";
import type { User } from "./types";

type State = { status: "loading" } | { status: "no-telegram" } | { status: "error" } | { status: "denied" } | { status: "ready"; user: User };
const Ctx = createContext<{ state: State; retry(): void }>(null as never);
export const useSession = () => useContext(Ctx);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>({ status: "loading" });
  const start = useCallback(() => {
    const wa = window.Telegram?.WebApp;
    if (!wa?.initData) return setState({ status: "no-telegram" }); // never fake a login
    wa.ready(); wa.expand(); client.setInitData(wa.initData);
    setState({ status: "loading" });
    client.login().then((user) => setState(canEnter(user.role) ? { status: "ready", user } : { status: "denied" }),
      () => setState({ status: "error" }));
  }, []);
  useEffect(start, [start]);
  return <Ctx.Provider value={{ state, retry: start }}>{children}</Ctx.Provider>;
}
