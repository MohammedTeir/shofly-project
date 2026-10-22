import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api, qs } from "../api";
import { useAsync } from "../hooks";
import { Badge, Btn, ErrorNote, Input, Label, LoadBox, Mono, Msg, Row, Section, Select, statusTone } from "../components/ui";
import type { Json } from "../types";

const TERMINAL = ["COMPLETED", "CANCELLED"];
const RETRYABLE = ["FAILED", "BLOCKED_RIGHTS", "EXPIRED_SOURCE"];

function Job({ j, reload }: { j: Json; reload(): void }) {
  const { t } = useTranslation();
  const [kind, setKind] = useState("movie"); const [target, setTarget] = useState(""); const [err, setErr] = useState<unknown>(null);
  const [refreshing, setRefreshing] = useState(false); const [newUrl, setNewUrl] = useState(""); const [saving, setSaving] = useState(false);
  const canRefresh = ["FAILED", "EXPIRED_SOURCE", "RETRY_WAIT"].includes(j.status) && j.source_type === "direct_url";
  const saveSource = async () => {
    if (saving || !newUrl.startsWith("https://")) return;
    setSaving(true); setErr(null);
    try { await api.post(`/admin/import-jobs/${j.id}/refresh-source`, { source_ref: newUrl }); setNewUrl(""); setRefreshing(false); reload(); }
    catch (e) { setErr(e); }
    finally { setSaving(false); }
  };
  const run = (p: Promise<unknown>) => p.then(() => { setErr(null); reload(); }, setErr);
  return (
    <div className="border-t border-white/10 py-3 first:border-0">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="flex items-center gap-2"><Badge text={j.status} tone={statusTone(j.status)} />{j.status === "DOWNLOADING" || j.progress_percent > 0 ? <span className="text-xs text-muted">{j.progress_percent}%</span> : null}
          {j.error_code && <span className="text-xs text-red-300">{j.error_code}</span>}</span>
        <span className="flex gap-2">{canRefresh && <Btn onClick={() => setRefreshing(!refreshing)}>{t("refresh_source_url")}</Btn>}{RETRYABLE.includes(j.status) && <Btn onClick={() => run(api.post(`/admin/import-jobs/${j.id}/retry`))}>{t("retry_job")}</Btn>}
          {!TERMINAL.includes(j.status) && <Btn tone="danger" onClick={() => window.confirm(t("confirm")) && run(api.post(`/admin/import-jobs/${j.id}/cancel`))}>{t("cancel_job")}</Btn>}</span>
      </div>
      <Mono>{j.id}</Mono>
      {refreshing && canRefresh && <div className="mt-2 grid gap-2 rounded-card border border-white/10 p-3">
        <Label text={t("new_source_url")}><Input dir="ltr" type="url" value={newUrl} onChange={(e) => setNewUrl(e.target.value.trim())} placeholder="https://" /></Label>
        <p className="text-xs text-muted">{t("refresh_source_hint")}</p>
        <div><Btn tone="accent" disabled={saving || !newUrl.startsWith("https://")} onClick={saveSource}>{saving ? t("loading") : t("save_and_retry")}</Btn></div>
      </div>}
      {j.status === "NEEDS_REVIEW" && <div className="mt-2 grid gap-2 sm:grid-cols-3">
        <Label text={t("target_kind")}><Select value={kind} onChange={(e) => setKind(e.target.value)}><option value="movie">movie</option><option value="episode">episode</option></Select></Label>
        <Label text={t("target_id")}><Input dir="ltr" value={target} onChange={(e) => setTarget(e.target.value.trim())} /></Label>
        <div className="flex items-end"><Btn tone="accent" disabled={target.length < 32} onClick={() => run(api.post(`/admin/import-jobs/${j.id}/approve`, { candidate_kind: kind, target_id: target }))}>{t("approve")}</Btn></div></div>}
      <ErrorNote error={err} />
    </div>
  );
}


function StoredMedia({ kind, targetId }: { kind: "movie" | "episode"; targetId: string }) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState<string | null>(null);
  const [replacement, setReplacement] = useState<Record<string, string>>({});
  const [actionError, setActionError] = useState<unknown>(null);
  const { data, error, loading, reload } = useAsync(
    () => targetId ? api.get(`/admin/import-jobs/assets/${kind}/${targetId}`) : Promise.resolve({ items: [] }),
    [kind, targetId]);
  const change = async (id: string, action: "deactivate" | "restore") => {
    if (busy || (action === "deactivate" && !window.confirm(t("media_deactivate_confirm", { defaultValue: "Disable this video for viewers? The Telegram file will be retained." })))) return;
    setBusy(id); setActionError(null);
    try { await api.post(`/admin/import-jobs/assets/${id}/${action}`); reload(); }
    catch (e) { setActionError(e); }
    finally { setBusy(null); }
  };
  const cleanup = async (asset: Json) => {
    if (busy) return;
    const pending = asset.upload_status === "cleanup_pending";
    if (!pending && !window.confirm(t("media_cleanup_confirm", { defaultValue: "Request storage cleanup for this disabled file? This does not delete Telegram messages yet." }))) return;
    setBusy(asset.id); setActionError(null);
    try { await api.post(`/admin/import-jobs/assets/${asset.id}/${pending ? "cancel-cleanup" : "request-cleanup"}`); reload(); }
    catch (e) { setActionError(e); }
    finally { setBusy(null); }
  };
  const replace = async (oldId: string) => {
    const replacementId = replacement[oldId];
    if (!replacementId || busy || !window.confirm(t("media_replace_confirm", { defaultValue: "Switch viewers to the selected verified file? The old Telegram message will be retained." }))) return;
    setBusy(oldId); setActionError(null);
    try { await api.post(`/admin/import-jobs/assets/${oldId}/replace`, { replacement_asset_id: replacementId }); reload(); }
    catch (e) { setActionError(e); }
    finally { setBusy(null); }
  };
  return <Section title={t("stored_media", { defaultValue: "Stored video files" })}>
    {!targetId ? <p className="text-sm text-muted">{t("media_select_target", { defaultValue: "Select a movie or episode above to manage its files." })}</p> :
      <LoadBox error={error} loading={loading} reload={reload}>
        {((data as Json)?.items ?? []).length === 0 ? <Msg text={t("empty")} /> :
          ((data as Json).items as Json[]).map((asset) => <Row key={asset.id}>
            <div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2">
              <Badge text={asset.upload_status} tone={asset.upload_status === "verified" ? "ok" : "warn"} />
              <span className="text-sm">{asset.quality || "Video"}{asset.edition ? ` · ${asset.edition}` : ""}</span>
              <span className="text-xs text-muted">{(asset.size_bytes / 1048576).toFixed(1)} MB</span>
            </div><Mono>{asset.id}</Mono></div>
            {asset.upload_status === "verified" && ((data as Json)?.items ?? []).some((a: Json) => a.id !== asset.id && a.upload_status === "verified") &&
              <div className="flex flex-wrap gap-2"><Select aria-label={t("select_replacement", { defaultValue: "Replacement video" })}
                value={replacement[asset.id] || ""} onChange={(e) => setReplacement({ ...replacement, [asset.id]: e.target.value })}>
                <option value="">{t("select_replacement", { defaultValue: "Select replacement" })}</option>
                {((data as Json).items as Json[]).filter((a) => a.id !== asset.id && a.upload_status === "verified").map((a) =>
                  <option key={a.id} value={a.id}>{a.quality || "Video"} · {a.id.slice(0, 8)}</option>)}
              </Select><Btn disabled={busy !== null || !replacement[asset.id]} onClick={() => replace(asset.id)}>
                {t("replace_video", { defaultValue: "Replace" })}</Btn></div>}
            {["inactive", "cleanup_pending"].includes(asset.upload_status) &&
              <Btn disabled={busy !== null} onClick={() => cleanup(asset)}>
                {asset.upload_status === "cleanup_pending"
                  ? t("cancel_cleanup", { defaultValue: "Cancel cleanup" })
                  : t("request_cleanup", { defaultValue: "Request cleanup" })}
              </Btn>}
            {asset.upload_status !== "cleanup_pending" && <Btn disabled={busy !== null} tone={asset.upload_status === "verified" ? "danger" : "accent"}
              onClick={() => change(asset.id, asset.upload_status === "verified" ? "deactivate" : "restore")}>
              {busy === asset.id ? t("loading") : asset.upload_status === "verified"
                ? t("disable_video", { defaultValue: "Disable" }) : t("restore_video", { defaultValue: "Restore" })}
            </Btn>}
          </Row>)}
      </LoadBox>}
    <p className="mt-2 text-xs text-muted">{t("media_retained_notice", { defaultValue: "Disabling a video blocks delivery but does not delete its Telegram storage message." })}</p>
    <ErrorNote error={actionError} />
  </Section>;
}

export default function Imports() {
  const { t } = useTranslation();
  const [status, setStatus] = useState(""); const [url, setUrl] = useState(""); const [err, setErr] = useState<unknown>(null);
  const [kind, setKind] = useState<"movie" | "episode">("movie");
  const [movieId, setMovieId] = useState("");
  const [seriesId, setSeriesId] = useState("");
  const [episodeId, setEpisodeId] = useState("");
  const [busy, setBusy] = useState(false);
  const { data: movies, error: moviesError, loading: moviesLoading, reload: reloadMovies } = useAsync(() => api.get("/admin/catalog/movie?limit=100"), []);
  const { data: series, error: seriesError, loading: seriesLoading, reload: reloadSeries } = useAsync(() => api.get("/admin/catalog/series?limit=100"), []);
  const { data: seriesDetail, error: episodeError, loading: episodeLoading, reload: reloadEpisodes } = useAsync(
    () => seriesId ? api.get(`/admin/catalog/series/${seriesId}`) : Promise.resolve({ episodes: [] }), [seriesId]);
  const selectedId = kind === "movie" ? movieId : episodeId;
  const { data, error, loading, reload } = useAsync(() => api.get(`/admin/import-jobs?${qs({ status })}`), [status]);
  const create = async () => {
    if (!selectedId || busy) return;
    setBusy(true); setErr(null);
    try {
      const job = await api.post("/admin/import-jobs", { source_type: "direct_url", source_ref: url, idempotency_key: crypto.randomUUID() });
      try {
        await api.post(`/admin/import-jobs/${job.id}/approve`, { candidate_kind: kind, target_id: selectedId });
        setUrl("");
      } catch (approvalError) {
        // Keep the created job visible for manual review rather than hiding a partial success.
        setErr(approvalError);
      }
      reload();
    } catch (e) { setErr(e); }
    finally { setBusy(false); }
  };
  return (
    <div>
      <Section title={t("new_import")}>
        <div className="mb-3 grid gap-3 sm:grid-cols-2">
          <Label text={t("target_kind")}><Select value={kind} onChange={(e) => setKind(e.target.value as "movie" | "episode")}>
            <option value="movie">{t("movies")}</option><option value="episode">{t("episodes")}</option>
          </Select></Label>
          {kind === "movie" ?
            <Label text={t("select_title")}><Select value={movieId} onChange={(e) => setMovieId(e.target.value)}>
              <option value="">{t("select_title")}</option>
              {((movies as Json)?.items ?? []).map((m: Json) => <option key={m.id} value={m.id}>{m.title}{m.year ? ` (${m.year})` : ""}</option>)}
            </Select></Label> :
            <Label text={t("select_series")}><Select value={seriesId} onChange={(e) => { setSeriesId(e.target.value); setEpisodeId(""); }}>
              <option value="">{t("select_series")}</option>
              {((series as Json)?.items ?? []).map((s: Json) => <option key={s.id} value={s.id}>{s.title}</option>)}
            </Select></Label>}
        </div>
        {kind === "episode" && <Label text={t("select_episode")}><Select value={episodeId} onChange={(e) => setEpisodeId(e.target.value)} disabled={!seriesId || episodeLoading}>
          <option value="">{t("select_episode")}</option>
          {((seriesDetail as Json)?.episodes ?? []).map((e: Json) =>
            <option key={e.id} value={e.id}>{`S${e.season_number}E${e.episode_number}`}{e.title ? ` — ${e.title}` : ""}</option>)}
        </Select></Label>}
        <ErrorNote error={kind === "movie" ? moviesError : seriesError || episodeError} />
        {(moviesLoading && kind === "movie") || (seriesLoading && kind === "episode") ? <p className="text-xs text-muted">{t("loading")}</p> : null}
        <Label text={t("source_url")}><Input dir="ltr" value={url} onChange={(e) => setUrl(e.target.value.trim())} placeholder="https://" /></Label>
        <p className="my-2 text-xs text-muted">{t("import_hint_select")}</p>
        <Btn tone="accent" disabled={busy || !selectedId || !url.startsWith("https://")} onClick={create}>{busy ? t("loading") : t("create")}</Btn>
        <div className="mt-2 flex gap-2"><Btn onClick={kind === "movie" ? reloadMovies : reloadSeries}>{t("retry")}</Btn>{kind === "episode" && <Btn onClick={reloadEpisodes}>{t("retry_job")}</Btn>}</div>
        <ErrorNote error={err} />
      </Section>
      <StoredMedia kind={kind} targetId={selectedId} />
      <Select value={status} onChange={(e) => setStatus(e.target.value)}><option value="">{t("all")}</option>
        {["NEEDS_REVIEW", "READY", "DOWNLOADING", "RETRY_WAIT", "FAILED", "BLOCKED_RIGHTS", "COMPLETED", "CANCELLED"].map((s) => <option key={s}>{s}</option>)}</Select>
      <div className="mt-3 rounded-card bg-surface px-4">
        <LoadBox error={error} loading={loading} reload={reload}>{((data as Json)?.items ?? []).length === 0 ? <Msg text={t("empty")} />
          : (data as Json).items.map((j: Json) => <Job key={j.id} j={j} reload={reload} />)}</LoadBox></div>
    </div>
  );
}
