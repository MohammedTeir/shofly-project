export type Kind = "movie" | "series";
export interface Asset { id: string; quality: string | null; audio_language: string | null; duration_sec: number | null; size_bytes: number }
export interface Title {
  id: string; kind: Kind; title: string; synopsis: string | null; title_language: string;
  original_title: string; year: number | null; favorited?: boolean;
  assets?: Asset[];
  seasons?: { season_number: number; title: string | null }[];
}
export interface User { id: string; telegram_id: number; preferred_language: string; language_source: string | null; role: string }
export interface Episode { id: string; episode_number: number; title: string | null; air_date: string | null; assets?: Asset[] }
export interface Page { items: Title[]; next_cursor: string | null }
declare global {
  interface Window { Telegram?: { WebApp: {
    initData: string; initDataUnsafe: { user?: { language_code?: string } };
    ready(): void; expand(): void;
    openTelegramLink(url: string): void;
    BackButton: { show(): void; hide(): void; onClick(f: () => void): void; offClick(f: () => void): void };
  } } }
}
