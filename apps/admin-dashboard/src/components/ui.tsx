import { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";
import { useTranslation } from "react-i18next";
import { ApiError } from "../api";

const field = "w-full rounded-card bg-raised px-3 py-2 text-text placeholder:text-muted";

export function Btn({ tone = "default", className = "", ...p }: ButtonHTMLAttributes<HTMLButtonElement> & { tone?: "default" | "accent" | "danger" }) {
  const c = { default: "bg-raised", accent: "bg-accent text-white", danger: "bg-danger text-white" }[tone];
  return <button {...p} className={`min-h-10 rounded-card px-3 text-sm disabled:opacity-50 ${c} ${className}`} />;
}
export const Input = (p: InputHTMLAttributes<HTMLInputElement>) => <input {...p} className={field} />;
export const Select = (p: SelectHTMLAttributes<HTMLSelectElement>) => <select {...p} className={field} />;
export const Label = ({ text, children }: { text: string; children: ReactNode }) => (
  <label className="block text-sm"><span className="mb-1 block text-muted">{text}</span>{children}</label>
);
export const Section = ({ title, children }: { title: string; children: ReactNode }) => (
  <section className="mb-5 rounded-card bg-surface p-4"><h2 className="mb-3 font-semibold">{title}</h2>{children}</section>
);
export const Row = ({ children }: { children: ReactNode }) => (
  <div className="flex flex-wrap items-center justify-between gap-2 border-t border-white/10 py-2 first:border-0">{children}</div>
);
export function Badge({ text, tone = "muted" }: { text: string; tone?: "ok" | "warn" | "muted" | "bad" }) {
  const c = { ok: "bg-green-900/50 text-green-300", warn: "bg-yellow-900/50 text-yellow-300", bad: "bg-red-900/50 text-red-300", muted: "bg-raised text-muted" }[tone];
  return <span className={`rounded px-2 py-0.5 text-xs ${c}`}>{text}</span>;
}
export const statusTone = (s: string) =>
  (["published", "APPROVED", "COMPLETED", "active", "READY"].includes(s) ? "ok" : ["FAILED", "BLOCKED_RIGHTS", "REVOKED", "suspended", "EXPIRED_SOURCE", "REJECTED"].includes(s) ? "bad"
    : ["NEEDS_REVIEW", "PENDING", "RETRY_WAIT", "draft"].includes(s) ? "warn" : "muted") as "ok" | "bad" | "warn" | "muted";
export const Mono = ({ children }: { children: string }) => <code dir="ltr" className="break-all text-xs text-muted">{children}</code>;
export const Msg = ({ text }: { text: string }) => <p className="py-8 text-center text-muted">{text}</p>;

export function ErrorNote({ error }: { error: unknown }) {
  const { t } = useTranslation();
  if (!error) return null;
  const code = error instanceof ApiError ? error.code : "";
  const blockers: string[] = error instanceof ApiError ? error.details.blockers ?? [] : [];
  return (
    <div role="alert" className="my-2 rounded-card bg-red-950/60 p-3 text-sm text-red-300">
      {t(`err_${code}`, { defaultValue: t("err_generic") })}
      {blockers.length > 0 && <ul className="mt-1 list-disc ps-5">{blockers.map((b) => <li key={b}>{t(`bl_${b}`, { defaultValue: b })}</li>)}</ul>}
    </div>
  );
}

export function LoadBox({ error, loading, reload, children }: { error: unknown; loading: boolean; reload(): void; children: ReactNode }) {
  const { t } = useTranslation();
  if (error) return <div className="py-8 text-center"><p className="text-danger">{t("load_failed")}</p><Btn onClick={reload} className="mt-2">{t("retry")}</Btn></div>;
  if (loading) return <Msg text={t("loading")} />;
  return <>{children}</>;
}
