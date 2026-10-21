# Shofly streaming gateway (opt-in, not deployed)

Telegram remains the only storage. This is a **separate always-on service**, not a Colab notebook or a Render static site.

## Required environment

- `SHOFLY_API_URL`: backend base URL, e.g. https://shofly-backend.onrender.com
- `STREAMING_INTERNAL_SECRET`: long random value, identical to backend
- `MINI_APP_ORIGIN`: exact HTTPS Mini App origin (no trailing slash)
- `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_SESSION`: writable persistent volume, e.g. /data/shofly_stream

Backend additionally needs `STREAMING_GATEWAY_URL` (public HTTPS origin), `STREAMING_SIGNING_KEY` (separate random 32+ byte secret), and `STREAMING_INTERNAL_SECRET`. **Until all are set, playback returns 503 and Telegram delivery is unchanged.**

Build with repository root as Docker context and `services/stream-gateway/Dockerfile`. Ensure outbound TCP to Telegram MTProto, and HTTPS ingress. Do not use a service that sleeps between requests.

## Security and limitations

Each playback request obtains a signed time-limited capability. The gateway calls the backend for fresh user/rights/territory checks on every HTTP range. Tickets are bearer credentials: avoid request query logging, analytics capture, third-party player SDKs and URL sharing. The Dockerfile disables Uvicorn access logs. Configure your ingress/CDN not to log query strings and not to cache stream responses. Rate-limit the gateway at the edge and limit simultaneous connections. CORS is restricted to the Mini App origin. No DRM; viewers can still capture content. Use only media you are authorized to distribute.

A single response is capped at 8 MiB and returns HTTP 206 with Content-Range. Browser-compatible MP4 (H.264/AAC, faststart moov) is recommended; MKV and multipart segmented assets may not play. Each HTTP range makes Telegram MTProto calls and consumes gateway bandwidth. This implementation is an **initial integration requiring live end-to-end tests** before production. Do not enable publicly without verifying seeks, disconnects, session expiry, and multiple viewers.

## Costs

The repository code has no license fee, but an always-on gateway requires a server with outbound Telegram access, persistent session storage, and sufficient outbound transfer. Pricing varies by provider/region and bandwidth quota. For reference, 100 viewers each watching 1 GB results in about 100 GB egress from the gateway, plus Telegram inbound traffic. Colab is not suitable for 24/7 serving. Render's current backend should not proxy the video bytes.

## Rollback

Unset `STREAMING_GATEWAY_URL` on backend to disable playback; existing Telegram delivery continues working.
