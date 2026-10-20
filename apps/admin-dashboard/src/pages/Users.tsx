import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api, qs } from "../api";
import { useAsync } from "../hooks";
import { Badge, Btn, ErrorNote, Input, LoadBox, Msg, Row, Select, statusTone } from "../components/ui";
import type { Json } from "../types";

const ROLES = ["member", "moderator", "content_admin", "rights_admin", "super_admin"];

export default function Users() {
  const { t } = useTranslation();
  const [q, setQ] = useState(""); const [err, setErr] = useState<unknown>(null);
  const { data, error, loading, reload } = useAsync(() => api.get(`/admin/users?${qs({ q })}`), [q]);
  const patch = (id: string, body: Json) => api.patch(`/admin/users/${id}`, body).then(() => { setErr(null); reload(); }, (e) => { setErr(e); reload(); });
  return (
    <div>
      <Input placeholder={t("search")} value={q} onChange={(e) => setQ(e.target.value)} /><ErrorNote error={err} />
      <div className="mt-3 rounded-card bg-surface px-4"><LoadBox error={error} loading={loading} reload={reload}>{((data as Json)?.items ?? []).length === 0 ? <Msg text={t("empty")} />
        : (data as Json).items.map((u: Json) => (
          <Row key={u.id}><div><div>{u.display_name ?? u.username ?? u.telegram_id}</div><div className="text-xs text-muted">@{u.username ?? "—"} · {u.preferred_language}</div></div>
            <span className="flex items-center gap-2"><Badge text={u.status} tone={statusTone(u.status)} />
              <Select value={u.role} onChange={(e) => window.confirm(t("confirm")) && patch(u.id, { role: e.target.value })}>{ROLES.map((r) => <option key={r}>{r}</option>)}</Select>
              <Btn onClick={() => patch(u.id, { status: u.status === "active" ? "suspended" : "active" })}>{u.status === "active" ? t("suspend") : t("activate")}</Btn></span></Row>))}
      </LoadBox></div>
    </div>
  );
}
