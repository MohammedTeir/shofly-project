declare global {
  interface Window { Telegram?: { WebApp: { initData: string; initDataUnsafe: { user?: { language_code?: string } }; ready(): void; expand(): void } } }
}
export interface User { id: string; telegram_id: number; preferred_language: string; role: string }
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type Json = Record<string, any>;
