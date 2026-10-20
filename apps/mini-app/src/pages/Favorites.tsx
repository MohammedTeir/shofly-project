import { useTranslation } from "react-i18next";
import { getFavorites } from "../api";
import { useAsync } from "../hooks";
import { ErrorBox, Grid, Message, Skeleton } from "../components/ui";
import type { Title } from "../types";

export default function Favorites({ open }: { open(t: Title): void }) {
  const { t, i18n } = useTranslation();
  const { data, error, loading, reload } = useAsync(getFavorites, [i18n.language]);
  if (error) return <ErrorBox onRetry={reload} />;
  if (loading) return <div className="pt-5"><Skeleton /></div>;
  if (!data?.items.length) return <Message text={t("favorites_empty")} />;
  return <div className="pt-5"><Grid items={data.items} open={open} /></div>;
}
