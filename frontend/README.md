# Asculto static frontend (Cloudflare Pages)

A Vite/TypeScript SPA that consumes the gateway/worker JSON contract and renders
reports (narrative, head probabilities, base64 figures) entirely client-side. The
server-rendered Jinja2 app in `webapp/` remains the local dev/demo path.

## Develop

```bash
npm install
VITE_API_BASE=http://localhost:8787/v1 npm run dev
```

## Build & deploy

```bash
npm run build            # -> dist/
npx wrangler pages deploy dist --project-name asculto-web
```

`VITE_API_BASE` is baked in at build time (`/v1` default). The gateway injects
`Authorization: Bearer <key>`; the SPA reads the key from `localStorage`
(`asculto_api_key`).

## Pages to port from the Jinja2 app

- Landing/upload (this file)
- Report viewer (narrative + figures)
- `game.html` -> `public/game.html` (calls `/v1/game/*` once exposed by the gateway)
