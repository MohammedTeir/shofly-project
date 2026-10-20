import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api, qs } from "../api";
import { useAsync } from "../hooks";
import { canApproveRights } from "../roles";
import { useSession } from "../session";
import { Badge, Btn, ErrorNote, Input, Label, LoadBox, Mono, Msg, Row, Section, Select, statusTone } from "../components/ui";
import type { Json } from "../types";

const iso = (d: string) => (d ? new Date(d).toISOString() : "");

export default function Rights() {
  const { t } = useTranslation();
  const st = useSession().state; const role = st.status === "ready" ? st.user.role : "";
  const [status, setStatus] = useState(""); const [exp, setExp] = useState(false); const [err, setErr] = useState<unknown>(null);
  const [f, setF] = useState({ kind: "movie", id: "", license: "", proof: "", terr: "ALL", from: "", until: "", tg: true, web: false, com: false });
  const { data, error, loading, reload } = useAsync(() => api.get(`/admin/rights?${qs({ status, expiring_days: exp && 30 })}`), [status, exp]);
  const run = (p: Promise<unknown>) => p.then(() => { setErr(null); reload(); }, setErr);
  const create = () => run(api.post("/admin/rights", { content_kind: f.kind, content_id: f.id, license_type: f.license, proof_ref: f.proof,
    territories: f.terr.split(",").map((x) => x.trim()).filter(Boolean), valid_from: iso(f.from), valid_until: iso(f.until),
    telegram_allowed: f.tg, web_allowed: f.web, commercial_allowed: f.com }));
  const ok = f.id.length >= 32 && f.license && f.proof.length >= 3 && f.from && f.until && f.terr.trim();
  const chk = (k: "tg" | "web" | "com", label: string) => <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.checked })} />{label}</label>;
  return (
    <div>
      <Section title={t("new_right")}>
        <div className="grid gap-2 sm:grid-cols-2">
          <Label text={t("target_kind")}><Select value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}><option value="movie">movie</option><option value="episode">episode</option></Select></Label>
          <Label text={t("target_id")}><Input dir="ltr" value={f.id} onChange={(e) => setF({ ...f, id: e.target.value.trim() })} /></Label>
          <Label text={t("license_type")}><Input value={f.license} onChange={(e) => setF({ ...f, license: e.target.value })} /></Label>
          <Label text={t("proof_ref")}><Input value={f.proof} onChange={(e) => setF({ ...f, proof: e.target.value })} /></Label>
          <Label text={t("valid_from")}><Input type="date" value={f.from} onChange={(e) => setF({ ...f, from: e.target.value })} /></Label>
          <Label text={t("valid_until")}><Input type="date" value={f.until} onChange={(e) => setF({ ...f, until: e.target.value })} /></Label>
          <Label text={t("territories")}><Input dir="ltr" value={f.terr} onChange={(e) => setF({ ...f, terr: e.target.value })} /></Label></div>
        <div className="my-3 flex flex-wrap gap-4">{chk("tg", t("telegram_allowed"))}{chk("web", t("web_allowed"))}{chk("com", t("commercial_allowed"))}</div>
        <Btn tone="accent" disabled={!ok} onClick={create}>{t("create")}</Btn><ErrorNote error={err} />
      </Section>
      <div className="mb-3 flex flex-wrap items-center gap-3"><Select value={status} onChange={(e) => setStatus(e.target.value)}><option value="">{t("all")}</option>
        {["PENDING", "APPROVED", "REVOKED"].map((s) => <option key={s}>{s}</option>)}</Select>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={exp} onChange={(e) => setExp(e.target.checked)} />{t("expiring_only")}</label></div>
      <div className="rounded-card bg-surface px-4"><LoadBox error={error} loading={loading} reload={reload}>{((data as Json)?.items ?? []).length === 0 ? <Msg text={t("empty")} />
        : (data as Json).items.map((r: Json) => (
          <Row key={r.id}><div><div>{r.label} <span className="text-xs text-muted">({r.content_kind})</span></div>
            <div className="text-xs text-muted">{r.license_type} · {new Date(r.valid_from).toLocaleDateString()} → {new Date(r.valid_until).toLocaleDateString()}</div><Mono>{r.content_id}</Mono></div>
            <span className="flex items-center gap-2"><Badge text={r.review_status} tone={statusTone(r.review_status)} />
              {canApproveRights(role) && r.review_status === "PENDING" && <Btn tone="accent" onClick={() => run(api.post(`/admin/rights/${r.id}/approve`))}>{t("approve_right")}</Btn>}
              {canApproveRights(role) && r.review_status !== "REVOKED" && <Btn tone="danger" onClick={() => window.confirm(t("confirm")) && run(api.post(`/admin/rights/${r.id}/revoke`))}>{t("revoke_right")}</Btn>}</span></Row>))}
      </LoadBox></div>
    </div>
  );
}
