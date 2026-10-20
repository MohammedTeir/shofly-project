import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { SessionProvider, useSession } from "./session";
import { Message, TabBar } from "./components/ui";
import Home from "./pages/Home";
import Search from "./pages/Search";
import Favorites from "./pages/Favorites";
import Settings from "./pages/Settings";
import Detail from "./pages/Detail";
import type { Kind, Title } from "./types";


function Shell() {
  const { t } = useTranslation();
  const { state, retry } = useSession();
  const [tab, setTab] = useState("home");
  const [stack, setStack] = useState<{ kind: Kind; id: string }[]>([]);
  const open = (x: Title) => setStack((s) => [...s, { kind: x.kind, id: x.id }]);
  const back = () => setStack((s) => s.slice(0, -1));

  useEffect(() => {
    const bb = window.Telegram?.WebApp?.BackButton;
    if (!bb) return;
    if (stack.length) { bb.show(); bb.onClick(back); return () => bb.offClick(back); }
    bb.hide();
  }, [stack.length]);

  if (state.status === "no-telegram") return <Message text={t("open_in_telegram")} />;
  if (state.status === "loading") return <Message text={t("loading")} />;
  if (state.status === "error") return (
    <div className="px-4 py-10 text-center"><p className="text-danger">{t("auth_failed")}</p>
      <button onClick={retry} className="mt-3 rounded-card bg-raised px-4 py-2">{t("retry")}</button></div>);

  const top = stack[stack.length - 1];
  return (
    <>
      <main>
        {top ? <Detail key={top.kind + top.id} kind={top.kind} id={top.id} />
          : tab === "search" ? <Search open={open} />
          : tab === "favorites" ? <Favorites open={open} />
          : tab === "settings" ? <Settings />
          : <Home open={open} />}
      </main>
      <TabBar tab={tab} go={(k) => { setStack([]); setTab(k); }} />
    </>
  );
}

export default () => <SessionProvider><Shell /></SessionProvider>;
