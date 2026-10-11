# Asculto API gateway (Cloudflare Worker + Hono)

Auth, quotas, presigned uploads, async jobs, Stripe webhooks, and a thin proxy to
the Python inference worker. **No inference runs here** (plan §2).

## Routes

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | liveness |
| POST | `/v1/uploads/presign` | presigned R2 PUT (900 s) |
| POST | `/v1/analyze` | sync report (proxies worker `/run`) |
| POST | `/v1/jobs` | enqueue async report -> Queue |
| GET | `/v1/jobs/:id` | poll; returns signed result URL when done |
| POST | `/webhooks/stripe` | subscription lifecycle -> entitlements |

Auth: `Authorization: Bearer <api-key>`; keys are stored hashed in KV
(`apikey:<sha256>`). Usage is counted per user per month in KV.

## Secrets

```bash
npx wrangler secret put STRIPE_SECRET_KEY
npx wrangler secret put STRIPE_WEBHOOK_SECRET
npx wrangler secret put R2_ACCESS_KEY_ID
npx wrangler secret put R2_SECRET_ACCESS_KEY
# DATABASE_URL when the Neon metadata layer is wired in
```

`PRICE_MAP` (a var) maps Stripe price ids to tiers, e.g.
`{"price_pro":"pro","price_research":"research"}`.

## Develop / deploy

```bash
npm install
npm run dev       # wrangler dev (port 8787)
npm run typecheck
npm run deploy
```

Bindings (`AUDIO`, `REPORTS`, `QUOTAS`, `USERS`, `JOBS`) and `INFERENCE_URL` are
declared in `wrangler.toml`; ids come from `infra/terraform/cloudflare`.
