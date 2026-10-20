import { api } from "../api";
import { useAsync } from "../hooks";
import { useTranslation } from "react-i18next";
import { LoadBox, Mono, Msg, Row } from "../components/ui";
import type { Json } from "../types";

export default function Audit() {
  const { t } = useTranslation();
  const { data, error, loading, reload } = useAsync(() => api.get("/admin/audit-logs?limit=100"), []);
  return (
    <div className="rounded-card bg-surface px-4"><LoadBox error={error} loading={loading} reload={reload}>{((data as Json)?.items ?? []).length === 0 ? <Msg text={t("empty")} />
      : (data as Json).items.map((a: Json) => <Row key={a.id}><span>{a.action} <span className="text-xs text-muted">{a.entity_kind}</span></span>
        <span className="text-xs text-muted" dir="ltr">{new Date(a.created_at).toLocaleString()}</span><Mono>{a.actor_id ?? "system"}</Mono></Row>)}</LoadBox></div>
  );
}
