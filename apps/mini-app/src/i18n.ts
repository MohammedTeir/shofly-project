import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import ar from "./locales/ar.json";
import en from "./locales/en.json";

export const SUPPORTED = ["ar", "en"] as const;
const RTL = new Set(["ar", "he", "fa", "ur"]);
export const dirFor = (lang: string) => (RTL.has(lang.split("-")[0]) ? "rtl" : "ltr");

export function initialLanguage(telegramCode?: string): string {
  const base = telegramCode?.toLowerCase().split("-")[0];
  return base && (SUPPORTED as readonly string[]).includes(base) ? base : "ar";
}

function apply(lang: string) {
  if (typeof document === "undefined") return;
  document.documentElement.lang = lang;
  document.documentElement.dir = dirFor(lang);
  document.title = i18n.t("app_name");
}

i18n.use(initReactI18next).init({
  resources: { ar: { translation: ar }, en: { translation: en } },
  lng: initialLanguage(typeof window !== "undefined" ? window.Telegram?.WebApp?.initDataUnsafe?.user?.language_code : undefined),
  fallbackLng: "en", interpolation: { escapeValue: false },
});
i18n.on("languageChanged", apply);
apply(i18n.language);
export default i18n;
