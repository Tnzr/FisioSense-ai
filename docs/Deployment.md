# Asculto — Deployment Runbook

Operational companion to `.kilo/plans/1791167801898-deployment-strategy.md`,
`docs/TechStack.md` and `docs/ProductComputeArchitecture.md`. It covers how to
build, provision, deploy, monitor and tear down the Stage-1 stack, and how to
move to Stage 2.

> Prices/regions are list prices checked Oct 2026; data residency is **EU-first**
> (plan A2). Nothing here is clinical software: keep the educational positioning
> and the not-a-medical-device copy.

## 0. Ports and known drift

| Surface | Port | Notes |
|---|---|---|
| FastAPI PoC (`webapp/app/main.py`) | **8010** (README) / 8000 (`webapp/README.md`) | Prefer 8010; the app defaults to 8000 if run without `--port`. Standardize on **8010** locally. |
| Inference worker (`deploy/inference_worker.py`) | **8080** | Container contract. |
| Cloudflare Pages dev | 8788 | `wrangler pages dev`. |
| API gateway Worker | 8787 | `wrangler dev`. |

`webapp/app/main.py` uses the deprecated `@app.on_event("startup")` hook. When
refactoring, migrate to a lifespan context manager; it is not a launch blocker.

## 1. Architecture (Stage 1)

```text
Browser (static SPA on Cloudflare Pages)
      │  presigned PUT (R2)
      ▼
Cloudflare R2 (audio)                Neon Postgres (metadata/results, EU)
      │                                    ▲
      ▼                                    │
Worker + Hono (auth, quotas, jobs, Stripe webhooks)
      │  enqueue
      ▼
Cloudflare Queues
      │
      ▼
Asculto inference worker (Container, scale-to-zero)
  ONNX Runtime CPU · quantized heads · report engine (figures + narrative)
      │
      ├─▶ Modal (GPU) only for batch / large models
      ▼
R2 (figures/reports) + signed result URL
```

Every compute component scales to zero; R2/Workers have **zero egress**; the only
always-on charge is the $5 Workers Paid base (plan §3).

## 2. Prerequisites

- Accounts: Cloudflare (Workers Paid, Pages, R2, Queues), Neon (EU region),
  Modal, Stripe, GitHub. Reserve `vitalsense` fallbacks are moot — brand is
  **Asculto**; complete its own trademark clearance before domain/TM spend.
- Local: Docker, Terraform >= 1.6, `wrangler` (v3+), `modal` CLI, Node 20, `uv`.
- Secrets live in Workers/GitHub/Terraform remote state only. Never commit keys
  (`.gitignore` already excludes `.env`).

## 3. Local development

```bash
./setup.sh                                   # venv + deps + dataset (+ .env ASCULTO_DATA_DIR)
.venv/bin/python -m uvicorn webapp.app.main:app --port 8010   # http://localhost:8010
```

Backend selection: `ASCULTO_BACKEND=torch` (default) or `onnx` with
`ASCULTO_ONNX_DIR` pointing at an export directory.

## 4. Export ONNX serving artifacts

Checkpoints are **not in the repo** (external volume + `ASCULTO_BINARY_OUT` /
`ASCULTO_MC_OUT`). Export once per release and upload to R2 / bake into the
worker image:

```bash
.venv/bin/python -m cardia.export.onnx_serve \
  --binary-out ml/runs \
  --mc-out "$ASCULTO_MC_OUT" \
  --out-dir ml/runs/onnx_serve \
  --quant-cnn fp16 --quant-transformer dynamic \
  --validate-clips /path/to/held-out/wavs
```

Rules (plan §2 / `docs/MobileCompute.md`):

- **CNN (ResNet-18) heads -> FP16 or static QDQ.** Dynamic INT8 regresses CPU
  latency (8.4 ms -> 30.3 ms). Use `--quant-cnn static_qdq --calib-dir <wavs>`
  when a calibration set is available.
- **Transformer heads -> dynamic INT8** (~2 MB, faster on CPU).
- **Validate before shipping**: `onnx_manifest.json` records max probability
  deviation and argmax agreement vs the torch ensemble. Do not ship a head whose
  agreement regresses on held-out folds.

The manifest is the worker/desktop contract: input `1x1x64x376`, output
post-softmax ensemble average.

## 5. Build and run containers

```bash
docker build -f deploy/api.Dockerfile       -t asculto-api .
docker build -f deploy/inference.Dockerfile -t asculto-worker .
docker run -p 8000:8000 asculto-api
docker run -p 8080:8080 -v "$ASCULTO_ONNX_DIR:/models" asculto-worker
```

Worker contract: `GET /health`, `POST /run`, `POST /batch`, or `--queue`
(newline JSON in/out) for Stage-2 pull consumers. The API gateway must **never**
run Python/Torch (plan §2).

## 6. Provision infrastructure (Terraform)

Remote state in R2; one workspace per environment.

```bash
cd infra/terraform/cloudflare && terraform init -backend-config=backend.hcl
terraform plan  -var-file=../../envs/prod.tfvars
terraform apply -var-file=../../envs/prod.tfvars
# then neon/, modal/, github/ modules
```

Order: R2 (state + buckets) -> Cloudflare (Pages/Workers/Queues/DNS) -> Neon ->
Modal -> GitHub. Pin **EU regions at provisioning** for Neon, R2 and compute
(plan A2); adding US later is a transfer question, not a schema change.

## 7. Deploy the API gateway (Worker)

```bash
cd gateway
npm install
npx wrangler secret put STRIPE_SECRET_KEY
npx wrangler secret put STRIPE_WEBHOOK_SECRET
npx wrangler secret put DATABASE_URL
npx wrangler deploy
```

Responsibilities: auth, quotas, presigned R2 uploads, job create -> Queue,
Stripe webhooks (signature verified, idempotency keys, test-mode first), and
proxying `POST /api/analyze` to the inference worker. Keep the JSON contract
versioned (`/v1/...`) for Stage-3 OEM.

## 8. Deploy the frontend (Pages)

```bash
cd frontend
npm install && npm run build          # or: npx wrangler pages deploy dist
```

The static SPA consumes the same `/api/analyze` JSON and renders base64 figures
client-side. The server-rendered Jinja2 app remains the local dev/demo path, so
no capability is lost.

## 9. Secrets

| Secret | Where |
|---|---|
| `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` | Worker secrets |
| `DATABASE_URL` (Neon) | Worker secrets / worker env |
| `ASCULTO_LLM_API_KEY` | Worker + worker env (paid tiers only) |
| Cloudflare/Neon/Modal API tokens | GitHub Actions secrets |
| Terraform state credentials | R2 backend env (`AWS_*`) |

## 10. Observability, alerts, cost control

- Cloudflare Logs (free) + Sentry free tier for errors.
- Cost alerts at **$20 / $50 / $100** (Workers + Neon spend limits).
- Track the idle bill for 30 days; target **< $15/mo** (plan §10). Reconcile
  against `finance/model.py` (`docs/Finance.md`).
- Load-test `POST /api/analyze` (k6/Locust): verify scale-to-zero, cold-start
  (report p95 <= 60 s incl. queue; sync macro <= 15 s with a warm replica), and
  queue back-pressure.

## 11. Stage-2 triggers (plan §8.1)

Move to GKE Autopilot / DOKS + HPA/KEDA + Triton when any holds:

1. sustained >= ~50k reports/mo, or
2. GPU demand >= ~30 GPU-hr/mo, or
3. infra bill > $500/mo and trending up, or
4. cold-start p95 unacceptable for a paid-SLA endpoint.

The same images move unchanged (ONNX + versioned OpenAPI + Postgres/R2 state).

## 12. Mobile (Capacitor / Android)

The cloud/web frontend doubles as a mobile app via **Capacitor 6**, wrapping the
Vite build (`frontend/dist`) in a native Android shell (`frontend/android/`).
The same web UI is the Electron desktop renderer, so one web codebase serves
web + desktop + Android. iOS is not yet added (`npx cap add ios` on a Mac).

### 12.1 Prerequisites

- Node 18+, JDK 17, and an Android SDK. On a dev machine, Android Studio sets
  all of this up; for a headless SDK, install `cmdline-tools`, then
  `platforms;android-34` and `build-tools;34.0.0` (Capacitor 6 template uses
  compile/target SDK 34, minSdk 22).
- The Android project's `local.properties` holds the SDK path and is git-ignored
  (the template's `.gitignore` also ignores `build/`, `.gradle/`, APKs and the
  copied web assets).

### 12.2 Build and run

```bash
cd frontend
npm install
npm run android:apk        # build web + sync + gradle assembleDebug
# -> frontend/android/app/build/outputs/apk/debug/app-debug.apk
```

Run on an emulator (or device):

```bash
VITE_API_BASE=http://10.0.2.2:8787/v1 npm run build   # emulator -> host loopback
npm run android:sync
npm run android:run           # or: npx cap run android (build + install + launch)
```

- `10.0.2.2` is the emulator's alias for the host; run the gateway locally with
  `npx wrangler dev` (port 8787). Without a backend, the landing UI still loads;
  the analyze call fails with a network error.
- Alternative to the emulator IP: `adb reverse tcp:8787 tcp:8787` then
  `VITE_API_BASE=http://localhost:8787/v1` (works on real devices over USB).
- Cleartext HTTP is allowed **only in debug builds** (debug overlay manifest at
  `frontend/android/app/src/debug/AndroidManifest.xml`); release stays HTTPS-only.

### 12.3 Emulator setup (Android Studio)

Create an AVD (Device Manager → Create Device → any recent Pixel + API 34
x86_64 image). **Hardware acceleration (KVM/HAXM) is required** — the emulator
will not boot without it. Then `npm run android:run` launches it.

### 12.4 Test as a PWA (no Android tooling)

The web app is also an installable PWA (`frontend/public/`: `manifest.webmanifest`,
`sw.js`, generated icons) — the fastest way to try it on a phone without the SDK:

```bash
cd frontend
python3 scripts/make-icons.py        # regenerate icons if branding changes
npm run build && npm run preview     # local preview (or deploy to Cloudflare Pages)
```

On the phone, open the deployed HTTPS URL in Chrome → “Add to Home screen” /
“Install app”. PWA install requires HTTPS (localhost is exempt). The service
worker caches the app shell (offline) and never intercepts `/v1/*` API calls.
For testing against a local backend on a physical device, use `adb reverse`
or a tunnel to the host.

### 12.5 Store submission notes

- **Google Play:** `./gradlew bundleRelease` (AAB), one-time **$25**, Play App
  Signing (free), Data Safety form, privacy policy URL.
- **Apple App Store:** `npx cap add ios` on a Mac, Xcode archive, **$99/yr**,
  TestFlight for beta.
- On-device inference later: add `onnxruntime-react-native` and the exported
  int8 ONNX models (see `docs/MobileCompute.md` §6) so the app works offline.

## 13. Teardown

```bash
cd infra/terraform/cloudflare && terraform destroy -var-file=../../envs/prod.tfvars
# repeat for neon/, modal/, github/; empty R2 buckets first if versioned
```

## 14. Validation checklist (release)

- [ ] `./setup.sh` succeeds on a fresh clone; `.env` uses `ASCULTO_DATA_DIR`.
- [ ] `onnx_manifest.json` validation: argmax agreement 1.0, deviation < 0.02.
- [ ] Worker `/health` reports all 5 heads loaded (or explicit errors).
- [ ] Idle bill measured < $15/mo for 30 days.
- [ ] Attribution visible (footer + report credits) and `docs/DatasetLicenses.md`
      signed off for every shipped model.
- [ ] Privacy Policy / ToS / DPA published; EU residency confirmed.
- [ ] Trademark clearance for **Asculto** recorded before any domain/TM spend.
