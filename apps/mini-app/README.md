# Shofly | شوفلي — Mini App (React + TS + Vite + Tailwind)

Setup: `npm install && cp .env.example .env` (set VITE_API_BASE_URL) · Dev: `npm run dev` · Check: `npm run build && npm test`
Deploy: host `dist/` on HTTPS static hosting; add that origin to backend `CORS_ORIGINS`; set it as the bot's Mini App URL
(@BotFather) and as `PUBLIC_APP_URL` in the bot's .env.

Works: Telegram initData login, server-persisted ar/en with RTL/LTR (optimistic with rollback), Home rails, debounced search,
detail with favorites toggle, series seasons/episodes, favorites, settings, Telegram BackButton, safe areas, reduced motion.
Not yet: posters (no poster data in backend; placeholders), "see all"/infinite scroll, playback (shows an honest notice),
requests, subscription, continue watching. Outside Telegram it shows "open from Telegram" instead of a fake login.
Verified: typecheck, production build, 5 logic tests. Not verified: rendering inside a real Telegram client.
