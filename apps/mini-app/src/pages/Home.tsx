import { useTranslation } from "react-i18next";
import { listTitles } from "../api";
import { useAsync } from "../hooks";
import { ErrorBox, Grid, Heading, Message, Skeleton } from "../components/ui";
import type { Title } from "../types";

export default function Home({ open }: { open(t: Title): void }) {
  const { t, i18n } = useTranslation();
  const { data, error, loading, reload } = useAsync(
    () => Promise.all([listTitles("movie"), listTitles("series")]), [i18n.language]);
  if (error) return <ErrorBox onRetry={reload} />;
  if (loading || !data) return <><Heading>{t("movies")}</Heading><Skeleton /></>;
  const [movies, series] = data;
  if (!movies.items.length && !series.items.length) return <Message text={t("empty")} />;
  return (
    <>
      {movies.items.length > 0 && <><Heading>{t("movies")}</Heading><Grid items={movies.items} open={open} /></>}
      {series.items.length > 0 && <><Heading>{t("series")}</Heading><Grid items={series.items} open={open} /></>}
    </>
  );
}
