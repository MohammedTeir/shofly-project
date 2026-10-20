import { useState } from "react";
import { useTranslation } from "react-i18next";
import { search } from "../api";
import { useAsync, useDebounced } from "../hooks";
import { ErrorBox, Grid, Message, Skeleton } from "../components/ui";
import type { Title } from "../types";

export default function Search({ open }: { open(t: Title): void }) {
  const { t, i18n } = useTranslation();
  const [q, setQ] = useState("");
  const dq = useDebounced(q.trim());
  const { data, error, loading, reload } = useAsync(() => (dq ? search(dq) : Promise.resolve({ items: [] as Title[] })), [dq, i18n.language]);
  return (
    <div className="pt-4">
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("search_placeholder")} aria-label={t("tab_search")}
        maxLength={100} className="mx-4 mb-4 w-[calc(100%-2rem)] rounded-card bg-surface px-4 py-3 text-text placeholder:text-muted" />
      {error ? <ErrorBox onRetry={reload} />
        : loading ? <Skeleton />
        : dq && !data?.items.length ? <Message text={t("no_results")} />
        : <Grid items={data?.items ?? []} open={open} />}
    </div>
  );
}
