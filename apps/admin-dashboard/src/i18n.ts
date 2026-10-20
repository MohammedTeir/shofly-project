import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import ar from "./locales/ar.json";
import en from "./locales/en.json";

export const dirFor = (l: string) => (l.split("-")[0] === "ar" ? "rtl" : "ltr");
const saved = (() => { try { return localStorage.getItem("shofly_admin_lang"); } catch { return null; } })();
const apply = (l: string) => {
  if (typeof document === "undefined") return;
  document.documentElement.lang = l; document.documentElement.dir = dirFor(l); document.title = i18n.t("app_name");
};
i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, ar: { translation: ar } }, lng: saved === "ar" ? "ar" : "en", fallbackLng: "en",
  interpolation: { escapeValue: false },
});
i18n.on("languageChanged", (l) => { try { localStorage.setItem("shofly_admin_lang", l); } catch { /* private mode */ } apply(l); });
apply(i18n.language);
export default i18n;
