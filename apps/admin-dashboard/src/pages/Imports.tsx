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
  const run = (p: Promise<unknown>) => p.then(() => { setErr(null); reload(); }, setErr);
  return (
    <div className="border-t border-white/10 py-3 first:border-0">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="flex items-center gap-2"><Badge text={j.status} tone={statusTone(j.status)} />{j.status === "DOWNLOADING" || j.progress_percent > 0 ? <span className="text-xs text-muted">{j.progress_percent}%</span> : null}
          {j.error_code && <span className="text-xs text-red-300">{j.error_code}</span>}</span>
        <span className="flex gap-2">{RETRYABLE.includes(j.status) && <Btn onClick={() => run(api.post(`/admin/import-jobs/${j.id}/retry`))}>{t("retry_job")}</Btn>}
          {!TERMINAL.includes(j.status) && <Btn tone="danger" onClick={() => window.confirm(t("confirm")) && run(api.post(`/admin/import-jobs/${j.id}/cancel`))}>{t("cancel_job")}</Btn>}</span>
      </div>
      <Mono>{j.id}</Mono>
      {j.status === "NEEDS_REVIEW" && <div className="mt-2 grid gap-2 sm:grid-cols-3">
        <Label text={t("target_kind")}><Select value={kind} onChange={(e) => setKind(e.target.value)}><option value="movie">movie</option><option value="episode">episode</option></Select></Label>
        <Label text={t("target_id")}><Input dir="ltr" value={target} onChange={(e) => setTarget(e.target.value.trim())} /></Label>
        <div className="flex items-end"><Btn tone="accent" disabled={target.length < 32} onClick={() => run(api.post(`/admin/import-jobs/${j.id}/approve`, { candidate_kind: kind, target_id: target }))}>{t("approve")}</Btn></div></div>}
      <ErrorNote error={err} />
    </div>
  );
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
      <Select value={status} onChange={(e) => setStatus(e.target.value)}><option value="">{t("all")}</option>
        {["NEEDS_REVIEW", "READY", "DOWNLOADING", "RETRY_WAIT", "FAILED", "BLOCKED_RIGHTS", "COMPLETED", "CANCELLED"].map((s) => <option key={s}>{s}</option>)}</Select>
      <div className="mt-3 rounded-card bg-surface px-4">
        <LoadBox error={error} loading={loading} reload={reload}>{((data as Json)?.items ?? []).length === 0 ? <Msg text={t("empty")} />
          : (data as Json).items.map((j: Json) => <Job key={j.id} j={j} reload={reload} />)}</LoadBox></div>
    </div>
  );
}
