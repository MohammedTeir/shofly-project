import { useState } from "react";
import { useTranslation } from "react-i18next";
import { SessionProvider, useSession } from "./session";
import { pagesFor } from "./roles";
import { Btn, Msg } from "./components/ui";
import Overview from "./pages/Overview";
import Titles from "./pages/Titles";
import Imports from "./pages/Imports";
import Rights from "./pages/Rights";
import Users from "./pages/Users";
import Audit from "./pages/Audit";

const PAGES: Record<string, () => JSX.Element> = { overview: Overview, titles: Titles, imports: Imports, rights: Rights, users: Users, audit: Audit };

function Shell() {
  const { t, i18n } = useTranslation();
  const { state, retry } = useSession();
  const [page, setPage] = useState<string | null>(null);
  if (state.status === "no-telegram") return <Msg text={t("open_in_telegram")} />;
  if (state.status === "loading") return <Msg text={t("loading")} />;
  if (state.status === "denied") return <Msg text={t("access_denied")} />;
  if (state.status === "error") return <div className="py-8 text-center"><p className="text-danger">{t("auth_failed")}</p><Btn onClick={retry} className="mt-2">{t("retry")}</Btn></div>;
  const allowed = pagesFor(state.user.role);  // server enforces too; this only hides what the role can't use
  const cur = page && allowed.includes(page) ? page : allowed[0];
  const Page = PAGES[cur];
  return (
    <div className="mx-auto max-w-4xl px-4 pb-10">
      <header className="sticky top-0 z-10 -mx-4 mb-4 flex items-center justify-between gap-2 bg-bg/95 px-4 py-3">
        <h1 className="text-lg font-bold">{t("app_name")}</h1>
        <Btn onClick={() => i18n.changeLanguage(i18n.language === "ar" ? "en" : "ar")} aria-label={t("language")}>{i18n.language === "ar" ? "English" : "العربية"}</Btn>
      </header>
      <nav className="mb-4 flex gap-2 overflow-x-auto" aria-label="Sections">
        {allowed.map((k) => <Btn key={k} tone={k === cur ? "accent" : "default"} aria-current={k === cur ? "page" : undefined} onClick={() => setPage(k)}>{t(`nav_${k}`)}</Btn>)}
      </nav>
      <main><Page key={cur} /></main>
    </div>
  );
}

export default () => <SessionProvider><Shell /></SessionProvider>;
