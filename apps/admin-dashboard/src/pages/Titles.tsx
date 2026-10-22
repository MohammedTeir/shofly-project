import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api, qs } from "../api";
import { useAsync } from "../hooks";
import { Badge, Btn, ErrorNote, Input, Label, LoadBox, Mono, Msg, Row, Section, Select, statusTone } from "../components/ui";
import type { Json } from "../types";

type Sel = { kind: "movie" | "series"; id: string };

function Translations({ sel, d }: { sel: Sel; d: Json }) {
  const { t } = useTranslation();
  const [err, setErr] = useState<unknown>(null);
  const [ok, setOk] = useState(false);
  return (
    <Section title={t("translations")}>
      {["ar", "en"].map((lang) => {
        const cur = d.translations.find((x: Json) => x.language === lang);
        let title = cur?.title ?? "", syn = "";
        return (
          <div key={lang} className="mb-3 space-y-2">
            <Label text={`${lang.toUpperCase()} — ${t("title_orig")}`}><Input defaultValue={title} onChange={(e) => (title = e.target.value)} dir={lang === "ar" ? "rtl" : "ltr"} /></Label>
            <Label text={t("synopsis")}><Input onChange={(e) => (syn = e.target.value)} dir={lang === "ar" ? "rtl" : "ltr"} /></Label>
            <Btn onClick={() => api.put(`/admin/catalog/${sel.kind}/${sel.id}/translations/${lang}`, { title, synopsis: syn || null })
              .then(() => { setOk(true); setErr(null); }, setErr)}>{t("save")}</Btn>
          </div>);
      })}
      {ok && <p className="text-sm text-green-400">{t("saved")}</p>}<ErrorNote error={err} />
    </Section>
  );
}

function SeriesParts({ id, d, reload }: { id: string; d: Json; reload(): void }) {
  const { t } = useTranslation();
  const [sn, setSn] = useState("1"); const [seasonId, setSeasonId] = useState(""); const [en, setEn] = useState("1"); const [title, setTitle] = useState("");
  const [err, setErr] = useState<unknown>(null);
  const run = (p: Promise<unknown>) => p.then(() => { setErr(null); reload(); }, setErr);
  return (
    <Section title={t("seasons")}>
      {d.seasons.map((s: Json) => <Row key={s.id}><span>{s.season_number === 0 ? "★" : `S${s.season_number}`}</span><Mono>{s.id}</Mono></Row>)}
      <div className="mt-3 flex items-end gap-2"><Label text={t("season_number")}><Input type="number" min={0} value={sn} onChange={(e) => setSn(e.target.value)} /></Label>
        <Btn onClick={() => run(api.post(`/admin/catalog/series/${id}/seasons`, { season_number: Number(sn) }))}>{t("add_season")}</Btn></div>
      <h3 className="mb-1 mt-5 text-sm text-muted">{t("episodes")}</h3>
      {d.episodes.map((e: Json) => (
        <Row key={e.id}><span>S{e.season_number}E{e.episode_number} {e.title ?? ""}</span>
          <span className="flex items-center gap-2"><Badge text={e.deliverable ? t("deliverable") : "—"} tone={e.deliverable ? "ok" : "muted"} /><Mono>{e.id}</Mono></span></Row>))}
      <div className="mt-3 grid gap-2 sm:grid-cols-3">
        <Label text={t("seasons")}><Select value={seasonId} onChange={(e) => setSeasonId(e.target.value)}><option value="" />{d.seasons.map((s: Json) =>
          <option key={s.id} value={s.id}>{s.season_number}</option>)}</Select></Label>
        <Label text={t("episode_number")}><Input type="number" min={1} value={en} onChange={(e) => setEn(e.target.value)} /></Label>
        <Label text={t("title_orig")}><Input value={title} onChange={(e) => setTitle(e.target.value)} /></Label></div>
      <Btn className="mt-2" disabled={!seasonId} onClick={() => run(api.post(`/admin/catalog/seasons/${seasonId}/episodes`, { episode_number: Number(en), title: title || null }))}>{t("add_episode")}</Btn>
      <ErrorNote error={err} />
    </Section>
  );
}

function Detail({ sel, back }: { sel: Sel; back(): void }) {
  const { t } = useTranslation();
  const { data, error, loading, reload } = useAsync(() => api.get(`/admin/catalog/${sel.kind}/${sel.id}`), [sel.id]);
  const [err, setErr] = useState<unknown>(null);
  const d = data as Json | undefined;
  const deleteAll = () => {
    if (!window.confirm(`Permanently delete ${d?.original_title}? Telegram files will be removed by the worker, then the title, import jobs, and metadata will be deleted. This cannot be undone.`)) return;
    api.post(`/admin/catalog/movie/${sel.id}/delete-all`).then(() => { setErr(null); back(); }, setErr);
  };
  const act = (path: string) => api.post(`/admin/catalog/${sel.kind}/${sel.id}/${path}`).then(() => { setErr(null); reload(); }, (e) => { setErr(e); reload(); });
  return (
    <div>
      <Btn onClick={back} className="mb-3">← {t("back")}</Btn>
      <LoadBox error={error} loading={loading || !d} reload={reload}>{d && <>
        <Section title={d.original_title}>
          <div className="flex flex-wrap gap-2"><Badge text={d.status} tone={statusTone(d.status)} />
            <Badge text={d.metadata_ok ?? d.metadata_verified ? t("metadata_ok") : "—"} tone={d.metadata_verified ? "ok" : "warn"} /></div>
          <Mono>{d.id}</Mono>
          {d.blockers.length > 0 && d.status !== "published" && <div className="mt-3 text-sm text-yellow-300">{t("blockers")}
            <ul className="list-disc ps-5">{d.blockers.map((b: string) => <li key={b}>{t(`bl_${b}`, { defaultValue: b })}</li>)}</ul></div>}
          <div className="mt-3 flex flex-wrap gap-2">
            {!d.metadata_verified && <Btn onClick={() => act("verify-metadata")}>{t("verify_metadata")}</Btn>}
            {d.status !== "published" ? <Btn tone="accent" onClick={() => act("publish")}>{t("publish")}</Btn>
              : <Btn tone="danger" onClick={() => window.confirm(t("confirm")) && act("unpublish")}>{t("unpublish")}</Btn>}
            {sel.kind === "movie" && <Btn tone="danger" onClick={deleteAll}>Delete movie &amp; Telegram files</Btn>}
          </div><ErrorNote error={err} />
        </Section>
        <Translations sel={sel} d={d} />
        {sel.kind === "series" && <SeriesParts id={sel.id} d={d} reload={reload} />}
        <Section title={t("assets")}>{d.assets.length === 0 ? <Msg text={t("empty")} /> : d.assets.map((a: Json) => (
          <Row key={a.id}><span>{a.quality ?? "?"} · {a.codec ?? "?"} · {(a.size_bytes / 1048576).toFixed(1)} MB · {a.provider}</span><Badge text={a.upload_status} tone={statusTone(a.upload_status === "verified" ? "APPROVED" : "PENDING")} /></Row>))}</Section>
        <Section title={t("rights")}>{d.rights.length === 0 ? <Msg text={t("empty")} /> : d.rights.map((r: Json) => (
          <Row key={r.id}><span>{r.license_type} → {new Date(r.valid_until).toLocaleDateString()}</span><Badge text={r.review_status} tone={statusTone(r.review_status)} /></Row>))}</Section>
      </>}</LoadBox>
    </div>
  );
}

export default function Titles() {
  const { t } = useTranslation();
  const [kind, setKind] = useState<"movie" | "series">("movie");
  const [q, setQ] = useState(""); const [status, setStatus] = useState("");
  const [sel, setSel] = useState<Sel | null>(null);
  const [form, setForm] = useState({ title: "", year: "" }); const [err, setErr] = useState<unknown>(null);
  const { data, error, loading, reload } = useAsync(() => api.get(`/admin/catalog/${kind}?${qs({ q, status })}`), [kind, q, status]);
  if (sel) return <Detail sel={sel} back={() => { setSel(null); reload(); }} />;
  const create = () => api.post(`/admin/catalog/${kind === "movie" ? "movies" : "series"}`,
    { original_title: form.title, ...(kind === "movie" && form.year ? { release_year: Number(form.year) } : {}) })
    .then((r) => { setErr(null); setForm({ title: "", year: "" }); setSel({ kind, id: String((r as Json).id) }); }, setErr);
  return (
    <div>
      <div className="mb-3 flex gap-2">{(["movie", "series"] as const).map((k) => <Btn key={k} tone={kind === k ? "accent" : "default"} onClick={() => setKind(k)}>{t(k === "movie" ? "movies" : "series")}</Btn>)}</div>
      <Section title={t("new_title")}>
        <div className="grid gap-2 sm:grid-cols-3"><Label text={t("title_orig")}><Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></Label>
          {kind === "movie" && <Label text={t("year")}><Input type="number" value={form.year} onChange={(e) => setForm({ ...form, year: e.target.value })} /></Label>}
          <div className="flex items-end"><Btn tone="accent" disabled={!form.title.trim()} onClick={create}>{t("create")}</Btn></div></div><ErrorNote error={err} />
      </Section>
      <div className="mb-3 grid gap-2 sm:grid-cols-2"><Input placeholder={t("search")} value={q} onChange={(e) => setQ(e.target.value)} />
        <Select value={status} onChange={(e) => setStatus(e.target.value)}><option value="">{t("all")}</option><option value="draft">draft</option><option value="published">published</option></Select></div>
      <LoadBox error={error} loading={loading} reload={reload}>
        <div className="rounded-card bg-surface px-4">{((data as Json)?.items ?? []).length === 0 ? <Msg text={t("empty")} /> : (data as Json).items.map((i: Json) => (
          <Row key={i.id}><button className="text-start" onClick={() => setSel({ kind, id: i.id })}>{i.title}{i.year ? ` (${i.year})` : ""}</button>
            <span className="flex gap-2">{i.metadata_verified && <Badge text="✓" tone="ok" />}<Badge text={i.status} tone={statusTone(i.status)} /></span></Row>))}</div>
      </LoadBox>
    </div>
  );
}
