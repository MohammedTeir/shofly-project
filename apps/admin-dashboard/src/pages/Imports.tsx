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
  const { data, error, loading, reload } = useAsync(() => api.get(`/admin/import-jobs?${qs({ status })}`), [status]);
  const create = () => api.post("/admin/import-jobs", { source_type: "direct_url", source_ref: url, idempotency_key: crypto.randomUUID() })
    .then(() => { setErr(null); setUrl(""); reload(); }, setErr);
  return (
    <div>
      <Section title={t("new_import")}>
        <Label text={t("source_url")}><Input dir="ltr" value={url} onChange={(e) => setUrl(e.target.value.trim())} placeholder="https://" /></Label>
        <p className="my-2 text-xs text-muted">{t("import_hint")}</p>
        <Btn tone="accent" disabled={!url.startsWith("https://")} onClick={create}>{t("create")}</Btn><ErrorNote error={err} />
      </Section>
      <Select value={status} onChange={(e) => setStatus(e.target.value)}><option value="">{t("all")}</option>
        {["NEEDS_REVIEW", "READY", "DOWNLOADING", "RETRY_WAIT", "FAILED", "BLOCKED_RIGHTS", "COMPLETED", "CANCELLED"].map((s) => <option key={s}>{s}</option>)}</Select>
      <div className="mt-3 rounded-card bg-surface px-4">
        <LoadBox error={error} loading={loading} reload={reload}>{((data as Json)?.items ?? []).length === 0 ? <Msg text={t("empty")} />
          : (data as Json).items.map((j: Json) => <Job key={j.id} j={j} reload={reload} />)}</LoadBox></div>
    </div>
  );
}
