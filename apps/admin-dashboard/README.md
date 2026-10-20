# Shofly Admin | إدارة شوفلي (React + TS + Vite + Tailwind)

Setup: `npm install && cp .env.example .env` · Dev: `npm run dev` · Check: `npm run build && npm test`
Deploy like the Mini App (HTTPS static hosting, origin added to backend `CORS_ORIGINS`).

Sign-in: Telegram initData, so it must be opened from Telegram (for example as a Mini App from the bot, for admin accounts).
The backend decides who is admin (users.role); this UI only hides what a role cannot use. A plain-browser login
(Telegram Login Widget) is not built.

Pages: Overview · Titles (create, verify metadata, publish/unpublish with blocker list, ar/en translations, seasons/episodes,
files, rights) · Imports (create, approve with target, retry, cancel) · Rights (create, approve/revoke, expiring filter) ·
Users (roles/suspend, super admin) · Audit log (super admin). Arabic RTL and English LTR.

Not built: TMDB/AI match review screen (Milestone 3), content-request queue, billing screens, collections editor,
poster upload, pagination controls ("load more"). Verified: typecheck, build, 6 logic tests. Not verified: rendering in Telegram.
