import { useTranslation } from "react-i18next";
import type { Title } from "../types";

export function Card({ item, onOpen }: { item: Title; onOpen(): void }) {
  const hue = [...item.id].reduce((a, c) => a + c.charCodeAt(0), 0) % 360;
  return (
    <button onClick={onOpen} className="w-full min-w-0 text-start">
      <div aria-hidden className="grid aspect-[2/3] place-items-center rounded-card text-4xl font-bold"
        style={{ background: `linear-gradient(160deg,hsl(${hue} 40% 28%),hsl(${hue} 50% 12%))` }}>{[...item.title][0]}</div>
      <div className="mt-2 line-clamp-2 text-sm">{item.title}</div>
      {item.year && <div className="text-xs text-muted">{item.year}</div>}
    </button>
  );
}

export const Grid = ({ items, open }: { items: Title[]; open(t: Title): void }) => (
  <div className="grid grid-cols-3 gap-3 px-4">{items.map((i) => <Card key={`${i.kind}${i.id}`} item={i} onOpen={() => open(i)} />)}</div>
);

export const Skeleton = () => (
  <div className="grid grid-cols-3 gap-3 px-4" aria-busy="true">
    {[0, 1, 2].map((i) => <div key={i} className="skeleton aspect-[2/3] rounded-card" />)}
  </div>
);

export const Message = ({ text }: { text: string }) => <p className="px-4 py-10 text-center text-muted">{text}</p>;

export function ErrorBox({ onRetry }: { onRetry(): void }) {
  const { t } = useTranslation();
  return (
    <div className="px-4 py-10 text-center">
      <p className="text-danger">{t("load_failed")}</p>
      <button onClick={onRetry} className="mt-3 rounded-card bg-raised px-4 py-2">{t("retry")}</button>
    </div>
  );
}

export const Heading = ({ children }: { children: string }) => <h2 className="px-4 pb-3 pt-5 text-lg font-semibold">{children}</h2>;

export function TabBar({ tab, go }: { tab: string; go(t: string): void }) {
  const { t } = useTranslation();
  const tabs = [["home", "🏠"], ["search", "🔎"], ["favorites", "❤️"], ["settings", "⚙️"]];
  return (
    <nav className="fixed inset-x-0 bottom-0 flex border-t border-white/10 bg-surface"
      style={{ paddingBottom: "env(safe-area-inset-bottom, 0px)" }}>
      {tabs.map(([k, icon]) => (
        <button key={k} onClick={() => go(k)} aria-current={tab === k ? "page" : undefined}
          className={`flex min-h-12 flex-1 flex-col items-center py-2 text-xs ${tab === k ? "text-accent" : "text-muted"}`}>
          <span aria-hidden className="text-lg">{icon}</span>{t(`tab_${k}`)}
        </button>
      ))}
    </nav>
  );
}
