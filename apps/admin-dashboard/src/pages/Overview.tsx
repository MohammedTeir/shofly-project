import { useTranslation } from "react-i18next";
import { api } from "../api";
import { useAsync } from "../hooks";
import { LoadBox } from "../components/ui";
import type { Json } from "../types";

const Stat = ({ label, value, sub }: { label: string; value: number | string; sub?: string }) => (
  <div className="rounded-card bg-surface p-4"><div className="text-sm text-muted">{label}</div>
    <div className="text-3xl font-bold">{value}</div>{sub && <div className="text-xs text-muted">{sub}</div>}</div>
);

export default function Overview() {
  const { t } = useTranslation();
  const { data, error, loading, reload } = useAsync(() => api.get("/admin/overview"), []);
  const d = data as Json | undefined;
  return (
    <LoadBox error={error} loading={loading || !d} reload={reload}>
      {d && <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
        <Stat label={t("movies")} value={d.movies.total} sub={`${d.movies.published} ${t("ov_published")} · ${d.movies.draft} ${t("ov_draft")}`} />
        <Stat label={t("series")} value={d.series.total} sub={`${d.series.published} ${t("ov_published")} · ${d.series.draft} ${t("ov_draft")}`} />
        <Stat label={t("ov_users")} value={d.users} />
        <Stat label={t("ov_rights_expiring")} value={d.rights_expiring_14d} />
        <Stat label={t("ov_rights_pending")} value={d.rights_pending} />
        <Stat label={t("ov_jobs")} value={Object.values(d.jobs as Record<string, number>).reduce((a, b) => a + b, 0)}
          sub={Object.entries(d.jobs as Record<string, number>).map(([k, v]) => `${k}: ${v}`).join(" · ")} />
      </div>}
    </LoadBox>
  );
}
