import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ApiError, getSeason, getTitle, requestAccess, requestPlayback, setFavorite } from "../api";
import { useAsync } from "../hooks";
import { ErrorBox, Message, Skeleton } from "../components/ui";
import type { Asset, Episode, Kind } from "../types";

const sizeLabel = (a: Asset) => `${a.quality ? a.quality + " · " : ""}${a.size_bytes >= 1073741824 ? (a.size_bytes / 1073741824).toFixed(1) + " GB" : Math.round(a.size_bytes / 1048576) + " MB"}`;

/** Backend re-checks rights/territory on every request and returns an opaque bot deep link; the bot then delivers the file. */
function SendButton({ asset, className = "" }: { asset: Asset; className?: string }) {
  const { t } = useTranslation();
  const [err, setErr] = useState(false);
  const go = async () => {
    setErr(false);
    try {
      const r = await requestAccess(asset.id);
      if (r.bot_deep_link) window.Telegram?.WebApp.openTelegramLink(r.bot_deep_link); else setErr(true);
    } catch { setErr(true); }
  };
  return <>
    <button onClick={go} className={`min-h-10 rounded-card bg-accent px-3 text-sm font-semibold text-white ${className}`}>📥 {t("send_via_telegram")} ({sizeLabel(asset)})</button>
    {err && <p role="alert" className="pt-1 text-sm text-danger">{t("delivery_failed")}</p>}
  </>;
}

function WatchButton({ asset }: { asset: Asset }) {
  const { i18n } = useTranslation();
  const [url, setUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const watch = async () => {
    setBusy(true); setError(""); setUrl(null);
    try {
      const response = await requestPlayback(asset.id);
      setUrl(response.playback_url);
    } catch (e) {
      setError(e instanceof ApiError && e.code === "STREAMING_NOT_CONFIGURED"
        ? (i18n.language === "ar" ? "المشاهدة داخل التطبيق غير مفعّلة بعد" : "In-app streaming is not enabled yet")
        : (i18n.language === "ar" ? "الفيديو غير متاح للمشاهدة هنا حاليًا" : "This video is not available for in-app playback"));
    } finally { setBusy(false); }
  };
  return <div className="space-y-2">
    <button disabled={busy} onClick={watch} className="min-h-11 w-full rounded-card bg-accent px-3 font-semibold text-white">
      {busy ? "…" : (i18n.language === "ar" ? "▶ شاهد الآن" : "▶ Watch now")}
    </button>
    {url && <video key={url} src={url} controls playsInline preload="metadata"
      className="w-full rounded-card bg-black"
      onError={() => setError(i18n.language === "ar" ? "تعذر تشغيل الفيديو. جرّب إرساله عبر Telegram." : "Playback failed. Try Telegram delivery.")} />}
    {error && <p role="alert" className="text-sm text-danger">{error}</p>}
  </div>;
}

function Season({ id, n }: { id: string; n: number }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [eps, setEps] = useState<Episode[] | "error" | null>(null);
  const toggle = () => {
    setOpen(!open);
    if (!eps) getSeason(id, n).then((d) => setEps(d.episodes), () => setEps("error"));
  };
  return (
    <div className="border-t border-white/10">
      <button onClick={toggle} aria-expanded={open} className="flex min-h-12 w-full items-center justify-between px-4 text-start">
        <span>{n === 0 ? t("specials") : t("season", { n })}</span>
        <span aria-hidden className={`transition-transform ${open ? "rotate-90" : "rtl:rotate-180"}`}>›</span>
      </button>
      {open && (eps === "error" ? <p className="px-4 pb-3 text-danger">{t("load_failed")}</p>
        : !eps ? <p className="px-4 pb-3 text-muted">{t("loading")}</p>
        : !eps.length ? <p className="px-4 pb-3 text-muted">{t("episodes_empty")}</p>
        : <ol className="px-4 pb-3">{eps.map((e) => <li key={e.id} className="py-1 text-sm">{e.episode_number}. {e.title ?? "—"}{e.assets?.[0] && <div className="pt-1"><WatchButton asset={e.assets[0]} /><SendButton asset={e.assets[0]} /></div>}</li>)}</ol>)}
    </div>
  );
}

export default function Detail({ kind, id }: { kind: Kind; id: string }) {
  const { t, i18n } = useTranslation();
  const { data, error, loading, reload } = useAsync(() => getTitle(kind, id), [kind, id, i18n.language]);
  const [fav, setFav] = useState<boolean | null>(null);
  const [favErr, setFavErr] = useState(false);
  useEffect(() => { if (data) setFav(!!data.favorited); }, [data]);

  if (error) return error instanceof ApiError && error.status === 404 ? <Message text={t("unavailable")} /> : <ErrorBox onRetry={reload} />;
  if (loading || !data) return <div className="pt-5"><Skeleton /></div>;

  const toggle = async () => {
    const next = !fav; setFav(next); setFavErr(false);        // optimistic, rolled back on failure
    try { await setFavorite(kind, id, next); } catch { setFav(!next); setFavErr(true); }
  };
  return (
    <article className="px-4 pt-5">
      <h1 className="text-2xl font-bold">{data.title}{data.year ? ` (${data.year})` : ""}</h1>
      {data.original_title !== data.title && <p className="mt-1 text-sm text-muted">{t("original_title")}: {data.original_title}</p>}
      {data.synopsis && <p className="mt-4 leading-relaxed">{data.synopsis}</p>}
      {data.kind === "movie" && (data.assets?.length
        ? <div className="mt-4 space-y-2">{data.assets.map((a) => <div key={a.id} className="space-y-2"><WatchButton asset={a} /><SendButton asset={a} className="w-full" /></div>)}</div>
        : <p className="mt-4 rounded-card bg-surface p-3 text-sm text-muted">{t("playback_pending")}</p>)}
      <button onClick={toggle} aria-pressed={!!fav} className="mt-4 min-h-12 w-full rounded-card bg-accent px-4 font-semibold text-white">
        {fav ? t("remove_fav") : t("add_fav")}
      </button>
      {favErr && <p role="alert" className="pt-2 text-danger">{t("save_failed")}</p>}
      {data.seasons && <div className="-mx-4 mt-6">{data.seasons.map((s) => <Season key={s.season_number} id={id} n={s.season_number} />)}</div>}
    </article>
  );
}
