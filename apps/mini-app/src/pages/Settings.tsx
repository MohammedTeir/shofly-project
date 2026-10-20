import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useSession } from "../session";
import { Heading } from "../components/ui";

const LANGS = [["ar", "العربية"], ["en", "English"]];

export default function Settings() {
  const { t, i18n } = useTranslation();
  const { setLang } = useSession();
  const [failed, setFailed] = useState(false);
  return (
    <>
      <Heading>{t("language")}</Heading>
      <div role="radiogroup" aria-label={t("language")} className="mx-4 overflow-hidden rounded-card bg-surface">
        {LANGS.map(([code, name]) => (
          <button key={code} role="radio" aria-checked={i18n.language === code}
            onClick={async () => setFailed(!(await setLang(code)))}
            className="flex min-h-12 w-full items-center justify-between px-4 text-start">
            <span>{name}</span>{i18n.language === code && <span aria-hidden className="text-accent">✓</span>}
          </button>
        ))}
      </div>
      {failed && <p role="alert" className="px-4 pt-3 text-danger">{t("save_failed")}</p>}
    </>
  );
}
