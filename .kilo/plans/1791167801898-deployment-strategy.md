# Deployment, Hosting & Sustainability Plan — VitalSense WebApp

> Companion to `docs/TechStack.md`, `docs/ProductComputeArchitecture.md`,
> `docs/WebApp.md`, `docs/LLM_Integration.md`, `docs/MobileCompute.md`,
> `docs/BusinessPlan.md`.
>
> Goal: take the Stage-1 FastAPI PoC to a **serverless, scale-to-zero cloud
> product** (paid subscription) plus a **free offline desktop app**, with a
> hosting/legal cost audit and a fundraising-grade unit-economics model.
>
> All prices below were checked **October 2026** and are list prices; every
> number is parameterized in `finance/pricing.yaml` so the model can be re-run.

---

## 0. Scope

In scope:

- Staged deployment architecture: **serverless API + hosted frontend** (Stage 1)
  → **managed Kubernetes + GPU + Terraform** (Stage 2) → multi-region (Stage 3).
- Hosting "best deal" audit and a personalized-domain recommendation.
- Legal/compliance cost audit with **hard gates** (dataset licensing, medical
  claims, privacy).
- A self-investing **sustainability model**: COGS, gross margin, break-even
  subscriber count, CAC/LTV, growth reinvestment, and the metrics investors
  will underwrite.
- Free desktop app packaging/distribution plan.

Out of scope (separate tracks): clinical validation, custom PCB, mobile app,
OEM SDK. This plan only fixes the software deployment/economics boundary.

---

## 1. Decisions and assumptions (defaults — override in `finance/pricing.yaml`)

| # | Decision | Recommended default | Rationale |
|---|---|---|---|
| A1 | Cloud strategy | **Cloudflare-first + Neon Postgres + Modal for GPU** | Lowest idle cost, zero egress, one edge vendor; GPU only when needed |
| A2 | Region / legal basis | **Locked: Global, EU-first, US-capable** | Delaware C-Corp (VC-friendly) + GDPR/EU residency first, US expansion later |
| A3 | Pricing | **Locked: consumer-friendly** — Free desktop/cloud tier; Pro **$9/mo**; Research **$29/mo**; Enterprise/OEM custom | Broad funnel for education/consumer mission; ~93% GM still achievable |
| A4 | Desktop | **Electron + ONNX Runtime** (reuse TS UI, ship int8 models) | Fastest path from current stack; true offline/humanitarian |
| A5 | Inference location | **CPU on-demand (scale-to-zero) now; GPU only for batch/large models** | Models are 2–11 MB int8, ~430 GFLOPs full sweep; CPU is cheaper than 1 GPU-second |
| A6 | Kubernetes | **GKE Autopilot** (alt: DigitalOcean DOKS) when sustained load justifies | Per-pod billing, $74.40/mo free tier covers one cluster, GPU node pools |
| A7 | IaC | **Terraform** (remote state in R2), modules per provider | Portability + fundraising diligence |
| A8 | LLM narrative | Offline synthesizer default; LLM gated to paid tiers | Removes variable cost from free users |
| A9 | Brand name | **Locked: VitalSense** (rename everywhere; GitHub canonical name is `Tnzr/FisioSense-ai`, `cardiasense-ai` is a legacy redirect) | **Trademark clearance required first** — "VitalSense" collides with existing health-tech marks (Philips VitalSense wearable, VitalConnect); gate domain/TM spend on a USPTO/EUIPO + common-law search, with fallback names ready |
| A10 | Entity | **Delaware C-Corp (locked), GDPR-first**; EU GmbH deferred | VC-friendly + US expansion; ~$500–1,000 setup, ~$450–850/yr recurring |
| A11 | Dataset licensing | **Verified cleared for the current models** (below) | Commercial use OK with attribution |
| A12 | Frontend architecture | Static build on Pages + JSON API; Jinja2 kept for local dev | Zero-egress static hosting; report JSON already exists |
| A13 | Inference latency posture | Async report path (queue → worker → signed result URL) | Absorbs container cold starts; sync only for macro single head |

Assumptions to confirm with the user (see §12): final brand and pricing are
**locked (VitalSense; consumer-friendly $9/$29)** pending trademark clearance;
founder budget/draw and marketing budget remain overridable.

---

## 2. Target architecture (staged)

### Stage 0 — today (PoC, $0)

Single Python/FastAPI process, in-process Torch inference, server-rendered
Jinja2. No change; keep as the local dev/demo path.

### Stage 1 — MVP launch (serverless, target idle **< $15/mo**)

```text
Browser (static SPA on Cloudflare Pages)
      │  presigned upload
      ▼
Cloudflare R2 (audio)                    Neon Postgres (metadata/results)
      │                                        ▲
      ▼                                        │
Workers + Hono (API gateway: auth, quotas, job create, Stripe webhooks)
      │  queue
      ▼
Cloudflare Queues
      │
      ▼
Inference worker (Cloudflare Container, scale-to-zero)
  • ONNX Runtime CPU, int8 heads, multi-scale
  • report engine: figures + narrative (+ LLM if paid)
      │
      ├─▶ Modal (serverless GPU) for batch / large models only
      ▼
R2 (figures/reports) + signed result URL back to Workers
```

Why this is the "best deal": every compute component scales to zero, there is
**no egress fee** (R2/Workers), static hosting is unmetered, and the only
always-on charge is the $5 Workers Paid base.

**Frontend migration (Jinja2 → static):** keep the Python report engine
(matplotlib figures + narrative) in the inference worker; move the page chrome
(landing, upload, game, report viewer) to static assets on Pages that consume
the existing `/api/analyze` JSON (already returns per-head probabilities +
base64 figures per `docs/WALKTHROUGH.md`). The Jinja2 server-rendered app stays
as the local dev/demo path, so no capability is lost.

**Cold-start strategy:** container scale-to-zero implies 5–15 s cold starts for
model warm-load. The report path is async by design (queue → worker → signed
result URL, client polls), so cold start is absorbed. For the sync macro
single-head path, keep one warm replica or a 2–20 min keep-alive window on the
worker when idle cost analysis (below) permits. Never run inference in the API
gateway.

**Data residency (EU-first, per A2):** Neon project + R2 bucket + inference
worker pinned to EU regions at launch; US region added at expansion. Privacy
Policy/DPA/SCCs cover the EU→US transfer later; the app remains anonymous by
default so no PHI crosses borders.

### Stage 2 — scale (managed Kubernetes + GPU + Terraform)

- Terraform provisions **GKE Autopilot** (or DOKS) with CPU + optional GPU node
  pools; inference workers become `Deployment` + `HorizontalPodAutoscaler` /
  KEDA scale-to-zero.
- **Triton** serves ONNX/TensorRT GPU models; Modal retained for burst GPU and
  training/batch.
- Cloudflare remains the edge (Pages/Workers/R2/Queues); Postgres via Neon
  (read replicas at scale).
- Trigger to move: sustained concurrency where always-on pods beat per-request
  serverless, or GPU inference demand > burst.

### Stage 3 — enterprise / OEM

Multi-region (EU + US) with data residency, read replicas, DR, SOC 2 / ISO 27001
readiness, SLAs, and a stable versioned API for OEM integrations.

---

## 3. Hosting cost audit — best deal

### 3.1 Recommended Stage-1 stack

| Component | Choice | Idle/mo | ~1k paid reports/mo | Notes |
|---|---|---|---|---|
| Frontend | Cloudflare Pages | $0 | $0 | static bandwidth unmetered; 500 builds/mo free |
| API gateway | Cloudflare Workers (Hono) | $5 (account min) | $5 | 10M req + 30M CPU-ms included |
| CPU inference | Cloudflare Containers | ~$0 (sleeps) | ~$1–5 | 375 vCPU-min/mo included; $0.00002/vCPU-s after |
| GPU (later) | Modal (A10G/H100) | $0 | $1–50 | per-second, scale-to-zero; A10G ≈ $0.000305/s, H100 ≈ $0.001097/s |
| Object storage | Cloudflare R2 | $0 (10 GB free) | ~$1 | $0.015/GB-mo, **zero egress** |
| Database | Neon Postgres (Launch) | $0 free tier | ~$5–20 | scale-to-zero, $0.106/CU-hr |
| Queue | Cloudflare Queues | $0 | ~$0–1 | 10k ops/day free |
| Auth | Clerk / Better Auth / Neon Auth | $0 | ~$0–25 | generous free MAU tiers |
| LLM narrative | OpenAI-compatible / Ollama | $0 (offline synth) | ~$1 | ~$0.001/report; paid tiers only |
| Payments | Stripe | $0 | 2.9% + $0.30 (+0.7% Billing) | no monthly fee |
| Email | Cloudflare Email Routing / Resend | $0 | ~$0–10 | |
| Monitoring | Cloudflare + Sentry free | $0 | $0–26 | |
| Domain | Cloudflare Registrar | $0.87–6.7 | same | `.com` $10.46/yr; `.ai` $80/yr (2-yr min) |
| **Total** | | **≈ $6–15/mo** | **≈ $15–70/mo** | meets "very affordable if not in active usage" |

### 3.2 True monthly cost floor by stage (planning numbers)

| Stage | Monthly floor | Scenario |
|---|---|---|
| 0 — PoC (local) | $0 | dev machine only |
| 1a — Demo/hosting only | **$5–7/mo** | Workers Paid $5 + `.com` domain $0.87/mo; DB/R2 in free tiers |
| 1b — Beta with traffic | **$15–40/mo** | adds Neon Launch usage, Sentry, auth MAU |
| 1c — ~1k paid reports/mo | **$40–100/mo** | inference + LLM + storage at scale |
| 2 — K8s (GKE Autopilot / DOKS) | **$73–250/mo** | cluster fee within free tier (GKE) or $12/mo (DOKS) + pod/node usage |
| 2 — with GPU node pool | **$250–1,000/mo** | only when batch/large-model demand justifies; Modal burst cheaper below ~30 GPU-hr/mo |

Cloudflare Containers CPU cost sanity check: a 10 s full multi-scale all-head
report ≈ 10 vCPU-s × $0.00002 + memory ≈ **$0.0003/report**; 1,000 reports ≈
$0.30. GPU is **not** the cheap path for these models — a 1 s Modal H100
inference ($0.0011) costs ~4× the CPU job, so GPU is reserved for large/batch
models only.

### 3.3 Alternatives considered (for diligence / negotiation)

| Provider | K8s control plane | Notable cost driver | Verdict |
|---|---|---|---|
| **Cloudflare-first (rec.)** | n/a (serverless) | none idle; no egress | Best idle economics, simplest ops |
| AWS | EKS **$73/mo** | egress + NAT + RDS; Fargate $0.04048/vCPU-hr | Use only if HIPAA/enterprise forces it; take AWS Activate credits |
| GCP | GKE Standard $73/mo; **Autopilot covered by $74.40 free tier** | per-pod + GPU | Best Stage-2 K8s choice |
| Azure | AKS free (no SLA) / $73 Standard | Functions + ACI | Viable; weaker edge story |
| DigitalOcean DOKS | **$0 control plane**, nodes from **$12/mo**, GPU scale-to-zero | simplest cheap K8s | Strong Stage-2 alternative |
| Hetzner / OVH (EU) | self-managed | dedicated GPU from ~€184–214/mo; RTX 4000 ≈ €0.34/hr | Cheapest raw GPU, EU residency, more ops |
| Modal / Baseten / Beam / Runware / Koyeb | managed | per-second GPU | Serverless GPU; Runware from $0.63/GPU-hr |
| Neon vs Supabase | managed Postgres | Neon: pay-as-you-go, scale-to-zero; Supabase: $25/mo flat | Neon cheaper at low/steady scale |

### 3.4 Startup credits to pursue (materially cuts Stage 1–2 burn)

GCP for Startups (up to **$350k** AI tier), AWS Activate, Microsoft for
Startups, **DigitalOcean Hatch**, OVHcloud Startup (**€10k–100k** + engineer
hours, EU), Scaleway (**€1k–36k**, EU), Cloudflare Workers for Students (12
months free, US `.edu`). Add these to the fundraising narrative as
non-dilutive runway.

---

## 4. Domain, DNS & edge

- **Registrar:** Cloudflare Registrar — at-cost pricing, free WHOIS privacy,
  free DNS, native Pages/Workers/R2 integration.
- **Brand (locked): VitalSense.** Candidate domains: `vitalsense.com`
  ($10.46/yr), `vitalsense.ai` ($80/yr, **2-year minimum = $160**),
  `vitalsense.health` (~$62/yr renewal). **Check availability at registration
  time (task 1)** and reserve 2–3 fallback names.
- **Gate before spending:** run the trademark clearance search first (USPTO +
  EUIPO + common-law/domain-name check) because "VitalSense" is already used by
  health-tech companies. If clearance is red, adopt a fallback brand before
  registering domains or filing.
- **Email:** Cloudflare Email Routing (free) → forwarding; or Google Workspace
  ($6/user/mo) for transactional/`hello@`/`security@`.
- **TLS:** Cloudflare Universal SSL / Let's Encrypt — free.
- **Rename prerequisite:** README references are verified — clone URL
  `Tnzr/FisioSense-ai.git` and `cd FisioSense-ai` are correct (that is the
  canonical GitHub name; `cardiasense-ai` is a legacy 301 redirect). Only
  `FisioSense_DATA_DIR` in the README text is stale vs the `CARDIASENSE_*`
  env vars — fix in the rename task below.

### 4.1 VitalSense rename scope

| Change | What | Keep (no user impact) |
|---|---|---|
| User-facing strings | README title/clone/`cd`, doc titles (`WebApp`, `WALKTHROUGH`, `webapp/README`), FastAPI title, HTML templates, Electron app name | — |
| Env var prefix | `CARDIASENSE_*` → `VITALSENSE_*` in `webapp/app/config.py`, `setup.sh`, README, docs (pre-launch, no compat shim needed) | — |
| Jupyter kernel | `cardiasense` → `vitalsense` (cosmetic, `setup.sh`) | — |
| Internal package | `ml/cardia/` ML lib, `cardiasense-hls-cmds` dist name | Keep — domain library, no user value in renaming |
| Data/checkpoint paths | `/media/tnzr/AuxVolume/cardiasense-runs` | Keep — external volume paths, no user value |
| GitHub repo | canonical name is `Tnzr/FisioSense-ai` (live, 200); `Tnzr/cardiasense-ai` is a legacy 301 redirect; local `origin` still works via the redirect | — (rename to the VitalSense brand repo is part of task 1) |

Fresh-clone check after rename: `./setup.sh` succeeds, `.env` uses
`VITALSENSE_DATA_DIR`, kernel named `vitalsense`, README clone/cd match the
remote.

---

## 5. Legal & compliance cost audit

### 5.1 Hard gates (must clear before charging money)

| Gate | Why | Action |
|---|---|---|
| **Dataset commercial license** | Models are trained on **HLS-CMDS**. **Status: cleared** — CC BY 4.0 permits commercial use with attribution (§5.3). Other registry datasets remain flagged. | Implement attribution (footer + report credits + `docs/DatasetLicenses.md`); review ICBHI/BMD-HS before use |
| **No clinical claims** | Avoids MDR/SaMD + EU AI Act high-risk regime now | Keep "educational/research, not a medical device" copy; legal review of all UI/marketing text |
| **Privacy/consent** | User-provided `patient_context` is health data | Explicit consent, encryption, retention policy, DPA, no PHI by default |
| **Brand/trademark** | Domain + TM | Clear the name (A9), then file |

### 5.2 Cost table (checked Oct 2026)

| Area | One-time | Recurring | When |
|---|---|---|---|
| Delaware C-Corp (**locked**) | $109 state + $427–819 (Clerky) / $500 (Stripe Atlas) / $1,500–5,000 (attorney) | franchise tax $400–500 + $50 report + registered agent $50–300/yr | Before VC round |
| EU GmbH (deferred) | ~€1,000–3,000 (notary + register) | accounting ~€1,000–3,000/yr | Only if EU operational entity needed later |
| Trademark | Clearance search first ($150–400 via search service/attorney); then $250–350/class USPTO (+$300–800 attorney); EUIPO from ~€850 | renewal | Before launch (gates domain spend) |
| GDPR/CCPA pack (**required at launch**) | $500–2,500 (templates) → $5,000+ (attorney): policy, DPA, cookie consent, SCCs; EU data residency for stored data | DPO only if required (~€500–2,000/mo) | Before public launch |
| HIPAA | Avoid by design (anonymous); BAA only when US clinical expansion starts (Supabase HIPAA add-on / Neon Scale) | per-provider | US clinical track only |
| EU AI Act / MDR | **Defer.** AI Act incremental ≈ **€24k–40k** with an existing QMS; MDR Class IIa certification typically €30k–100k+ | QMS maintenance | Only if making diagnostic claims |
| ToS / Privacy / DPA | $500–2,000 | — | Launch |
| OSS license compliance | $0 (FOSSA/scan in CI) | — | CI |
| E&O / cyber insurance | — | $1,000–3,000/yr early | Before paid |
| Accessibility (EAA/ADA, WCAG 2.2 AA) | audit $2,000–10,000 | — | Before EU launch |

**Positioning rule:** staying in "educational/research" keeps the product out
of the MDR/EU-AI-Act high-risk path (deadlines: standalone Annex III high-risk
**2 Dec 2027**; Annex I embedded **2 Aug 2028**). Revisit only when funded for a
regulated clinical track.

### 5.3 Dataset license registry (verified October 2026)

| Dataset | License | Commercial use | Notes |
|---|---|---|---|
| **HLS-CMDS** (current models, incl. game audio) | **CC BY 4.0** (Zenodo 15376628) | **Yes, with attribution** | Include attribution in app footer + report credits |
| PhysioNet/CinC 2016 | **ODC-BY 1.0** | **Yes, with attribution** | Benchmarks only today |
| CirCor DigiScope | **ODC-BY 1.0** | **Yes, with attribution** | Benchmarks only today |
| ICBHI 2017 | **Unverified** — research-only terms reported | **Assume no until reviewed** | Do not use for commercial training |
| BMD-HS | **Unverified** | **Assume no until reviewed** | Do not use for commercial training |

Rule: a dataset enters the commercial pipeline only after a dated sign-off in
`docs/DatasetLicenses.md`. Also note PhysioNet's MIMIC-family DUA prohibits
third-party LLM/API processing — do not route restricted data through cloud
LLMs; the offline synthesizer and local Ollama paths keep this safe.

---

## 6. Sustainability & unit-economics model

Implement as `finance/pricing.yaml` (inputs) + `finance/model.py` (formulas),
so the fundraising deck and break-even are reproducible.

### 6.1 Formulas

```text
ARPU            = weighted mean monthly revenue per paying user
COGS/user       = inference + LLM + storage/DB + payment fees
Gross margin    = (ARPU − COGS) / ARPU
Contribution    = ARPU − COGS
Fixed opex F    = infra base + tooling + legal amortization + marketing + founder draw
Break-even N*   = F / Contribution
LTV             = ARPU × Gross margin / monthly churn
LTV:CAC         = LTV / CAC          (target ≥ 3)
CAC payback(mo) = CAC / Contribution  (target ≤ 6)
Rule of 40      = revenue growth % + profit margin %   (target ≥ 40)
Reinvestment    = profit × reinvest_rate, deployed to marketing while LTV:CAC ≥ 3
Growth (self-funding) g = reinvest_rate × ROAS, sustained while LTV:CAC ≥ 3
                          and CAC payback ≤ 6 months   ← the "profitable-to-growth" rule
```

### 6.2 Recommended inputs

| Input | Value |
|---|---|
| Pro / Research price | $9 / $29 per month |
| Blended ARPU | $12/mo |
| Reports per paying user | ~25/mo (consumer) |
| Inference cost/report (CPU) | ~$0.0004 |
| LLM cost/report | ~$0.001 |
| Storage/DB/egress/user | ~$0.05/mo |
| Payment fees | 2.9% + $0.30 — **on $9 that is ~6.2%**; mitigate with annual plan, SEPA/ACH rails (0.8%) |
| **COGS / paying user** | **≈ $0.80/mo** |
| **Gross margin** | **≈ 93%** |
| Monthly churn | 5% |
| Paid conversion (of MAU) | 3% (consumer funnel) |
| CAC (content/community blended) | $45 |
| Founder draw (bootstrap → post-seed) | $0 → $4,000/mo |

Derived: **Contribution ≈ $11.2**, **LTV ≈ $224**, **LTV:CAC ≈ 5.0**,
**CAC payback ≈ 4.0 months**.

### 6.3 Break-even

| Fixed opex F | Break-even paying subscribers |
|---|---|
| $2,000/mo (bootstrap: $1.5k marketing, tools/legal, no salary) | **~179** |
| $3,000/mo | **~268** |
| $4,000/mo | **~357** |
| $8,000/mo (adds founder draw) | **~714** |

### 6.4 Illustrative self-investing ramp (override in `pricing.yaml`)

| Month | Free MAU | Paying | MRR | COGS | Fixed | Net | Cumulative |
|---|---|---|---|---|---|---|---|
| 3 | 1,500 | 45 | $540 | $36 | $2,000 | −$1,496 | −$1,496 |
| 6 | 6,000 | 180 | $2,160 | $144 | $2,500 | −$484 | −$1,980 |
| 9 | 15,000 | 450 | $5,400 | $360 | $3,000 | **+$2,040** | +$60 |
| 12 | 30,000 | 900 | $10,800 | $720 | $4,000 | +$6,080 | +$6,140 |
| 18 | 80,000 | 2,400 | $28,800 | $1,920 | $7,000 | +$19,880 | +$26,020 |
| 24 | 200,000 | 6,000 | $72,000 | $4,800 | $14,000 | +$53,200 | +$79,220 |

Reading: **cash-flow positive at ~180–360 paying subs (≈ month 8–9)** with only
**~$2–4k of initial self-investment**; every month after, profit is reinvested
in marketing while LTV:CAC stays ≥ 3, which is the "profitable-to-growth"
engine. ARR ≈ **$144k at 1,000 subs**, **$720k at 5,000 subs**, **~$1M at
~6,900 subs**.

### 6.5 Fundraising framing

- Capital efficiency: idle infra ~$10/mo → dollars go to growth, not servers.
- Metrics to show: **GM > 90%**, **LTV:CAC > 3**, **CAC payback < 6 mo**,
  target **NRR > 110%**, clear path to **$1M ARR (~month 22–26, ≈ 6,900 subs)**.
- Consumer model needs volume marketing (content/education/community channels
  first) to hold CAC ≈ $45; if paid-ads CAC pushes LTV:CAC below 3, cut spend.
- Suggested seed use of funds: marketing 45%, product/ML 30%, legal/regulatory
  10%, infra 5%, buffer 10%.
- Non-dilutive: startup cloud credits (§3.4) + grants (open-source hardware,
  STEM education, global health, per `docs/BusinessPlan.md` §30).

### 6.6 Per-tier COGS and margin

| Tier | Price | Est. usage/mo | COGS/user/mo (incl. payment) | Gross margin |
|---|---|---|---|---|
| Cloud Free | $0 | 5 reports, offline synth | ~$0.05 (no payment fee) | n/a (funnel) |
| Pro | $9 | 25 reports + LLM | ~$0.65 (incl. ~6.2% payment) | **≈ 93%** |
| Research | $29 | 100 reports + LLM + batch API | ~$1.33 (incl. ~4.7% payment) | **≈ 95%** |
| Enterprise/OEM | custom ≥ $500 | quota/SLA-based | ~$10–25 | **> 95%** |

The $0.30 fixed Stripe fee makes **Pro's payment cost ~6.2%** — the largest
COGS line. Mitigate: annual plan (2 months free → effective $7.5/mo, churn
drops ~1–2 pts), SEPA/ACH direct debit (0.8%), or bundle billing. Include as
toggles in `pricing.yaml`.

### 6.7 Sensitivity (build as `finance/model.py` scenarios)

| Scenario | Effect |
|---|---|
| Churn 5% → 8% | LTV $224 → $140; N\* up ~10% |
| ARPU $12 → $18 (better Pro/Research mix) | N\* down ~33% at same F |
| CAC $45 → $90 (paid-ads-heavy) | LTV:CAC 5.0 → **2.5 (below 3 → cut spend)** |
| Annual plan adoption 40% | effective ARPU ≈ $11, churn −1.5 pts → LTV up ~20% |
| SEPA/ACH rails on Pro | payment COGS ~6.2% → ~3.9% → GM up ~2 pts |
| LLM on free tier | adds ~$0.005×free-MAU to COGS → keep gated |
| GPU for all reports | COGS/user ~×8 → only for Research/Enterprise |

### 6.8 Investor metric sheet (emit from the model)

GM > 90% (≈93%), LTV:CAC ≈ 5.0, CAC payback ≈ 4.0 mo, NRR target > 110%, Rule
of 40 ≥ 40, burn multiple < 1.5, idle infra ≈ $10/mo (capital efficiency), ARR
path: **$144k @ 1k subs**, **$720k @ 5k subs**, **~$1M @ ~6.9k subs**.

---

## 7. Free desktop app plan

- **Form:** Electron + ONNX Runtime, reusing the TypeScript UI; ship the int8
  heads (ResNet-18 ~11 MB, Transformer ~2 MB; all 5 ≈ 36 MB) as release
  artifacts downloaded on first run (checksum-verified).
- **Inference:** local CPU; default macro pass + optional meso sweep per
  `docs/MobileCompute.md`. Offline synthesizer for narrative; optional
  user-supplied API key / local Ollama for LLM.
- **Cost to the company:** $0 per user (no cloud); only build/signing costs.
- **Auto-update:** `electron-updater` against GitHub Releases (signed).
- **Signing/distribution:** Apple Developer **$99/yr** (+ notarization, free);
  Windows **Microsoft Store MSIX re-signs free**, or **Azure Artifact Signing
  ~$9.99/mo**, or OV cert $150–300/yr. Distribute via GitHub Releases and/or
  the stores.
- **Model licensing:** weights trained on CC BY 4.0 data ship with attribution;
  release app source under MIT/Apache-2.0 per the open-source strategy; keep
  later clinical-grade fine-tuned weights proprietary.
- **Cloud bridge (optional):** desktop app can link an account to upgrade to
  cloud sync/batch/LLM — the funnel from free offline to paid cloud.
- **Strategic role:** funnel into paid cloud, satisfies the humanitarian/offline
  mission, and demonstrates the hardware-independent platform.

---

## 8. Docker → Kubernetes → Terraform path

| Phase | Containerization | Orchestration | IaC |
|---|---|---|---|
| Stage 1 | Dockerfiles for API gateway + inference worker + desktop build | Cloudflare Containers (scale-to-zero) + Modal | Terraform (Cloudflare, Neon, Modal, GitHub) |
| Stage 2 | same images | GKE Autopilot (or DOKS), HPA/KEDA, Triton for GPU | Terraform GKE module + node pools; remote state in R2 |
| Stage 3 | same images | multi-region clusters, read replicas, DR | Terraform workspaces per region |

Portability rules: keep inference behind ONNX (no framework lock-in), keep the
API behind a versioned OpenAPI contract, keep state in Postgres/R2, and avoid
proprietary-only APIs so Stage 2 migration is a re-hosting, not a rewrite.

### 8.1 Stage-2 triggers (quantified)

Move from serverless containers/pods to always-on Kubernetes when any holds:

1. Sustained load ≥ **~50k reports/mo** (serverless per-request still fine, but
   committed capacity + Savings Plans beat it), **or**
2. GPU demand ≥ **~30 GPU-hr/mo** (Modal burst ≈ break-even vs an owned GPU
   node; below that, burst wins), **or**
3. Infra bill > **$500/mo** and trending up, **or**
4. Cold-start p95 unacceptable for a paid-SLA endpoint (warm pools then, HPA
   min-replicas 1, KEDA on queue length).

Always-on vs serverless sanity rule: always-on wins when
`utilization × (pod cost/hr) < (per-report cost × throughput)`, i.e. once
pods are busy > ~30–40% of the hour.

### 8.2 Security, secrets & observability (all stages)

- Secrets: Cloudflare Workers secrets / GitHub Actions secrets / Terraform
  remote-state encryption (R2 state backend); no keys in repo (`.gitignore`).
- R2: SSE encryption, signed upload URLs with expiry + size limits, per-tenant
  quotas; Workers rate limits; Cloudflare DDoS/WAF (free tier) at the edge.
- LLM path: only non-restricted data; zero-retention config if any provider is
  used (offline synthesizer / local Ollama avoid this entirely).
- Observability: Cloudflare Logs (free), Sentry free tier for errors, cost
  alerts (Workers + Neon spend limits) — target bill drift alerts at
  $20/$50/$100 thresholds.
- Stripe: webhook signature verification, idempotency keys, test-mode first.

---

## 9. Ordered implementation tasks

1. **Brand: VitalSense.** Run trademark clearance (USPTO/EUIPO/common-law) —
   "VitalSense" collides with existing health-tech marks; if red, adopt a
   fallback before spending. Then: rename the GitHub repo to the VitalSense
   brand and update README clone/cd accordingly, `CARDIASENSE_*` →
   `VITALSENSE_*`, doc/app titles, FastAPI title, templates, kernel; keep
   `ml/cardia` + data paths per §4.1, register the domain (§4), complete
   `docs/DatasetLicenses.md` (§5.3) and implement attribution (app footer +
   report credits). *Blocks paid launch.*
2. **Containerize:** `deploy/api.Dockerfile`, `deploy/inference.Dockerfile`
   (Python + ONNX Runtime), `deploy/worker-modal.py`; add `export/onnx_serve.py`.
3. **Stage-1 Terraform:** `infra/terraform/cloudflare/` (Pages, Workers, R2,
   Queues, DNS, domain), `infra/terraform/neon/`, `infra/terraform/modal/`,
   `infra/terraform/github/`; R2 remote state.
4. **API gateway:** TypeScript/Hono Worker — auth, quotas, Stripe webhooks,
   presigned uploads, job create → Queue; extract the `/api/analyze` handler
   per `docs/TechStack.md`.
5. **Frontend:** static build of the current UI → Cloudflare Pages consuming the
   `/api/analyze` JSON (report viewer renders base64 figures client-side); keep
   the server-rendered Jinja2 app for local dev/demo.
6. **Inference worker:** ONNX Runtime CPU, scale-to-zero, queue pull-consumer;
   Modal path for batch. Warm-pool option for sync macro path.
7. **Billing:** Stripe products (Free/Pro/Research/Enterprise), entitlements,
   LLM gated to paid.
8. **CI/CD:** `.github/workflows/ci.yml`, `deploy-web.yml`, `deploy-api.yml`,
   `deploy-infra.yml`; OSS/license + secret scanning.
9. **Desktop:** `desktop/` Electron + ONNX, build/sign/notarize scripts,
   `release-desktop.yml` with auto-update.
10. **Finance model:** `finance/pricing.yaml` + `finance/model.py` implementing
    §6; emit `docs/Finance.md` (tables + sensitivity + investor metric sheet).
11. **Legal pack:** ToS, Privacy Policy, DPA, cookie consent; trademark filing;
    insurance quotes.
12. **Stage-2 (deferred):** Terraform GKE/DOKS + HPA/KEDA + Triton when a §8.1
    trigger is met.
13. **Docs:** `docs/Deployment.md` runbook + cost-monitoring dashboard/alerts.

---

## 10. Validation plan

- **Cost:** deploy Stage 1, measure the idle bill for 30 days (target **< $15/mo**)
  and the per-report cost; reconcile against `finance/model.py`; verify the
  §3.2 cost floor at each stage.
- **Load:** k6/Locust against `/api/analyze`; verify scale-to-zero, cold-start
  latency (target report p95 ≤ 60 s incl. queue; sync macro ≤ 15 s with warm
  pool), and queue back-pressure; compare CPU vs Modal GPU break-even.
- **Finance:** model reproduces break-even and ramp; run §6.7 sensitivity on
  churn, ARPU, CAC, and LLM usage.
- **Legal:** dataset registry sign-off recorded (`docs/DatasetLicenses.md`),
  attribution implemented; privacy/ToS/DPA published; trademark filed.
- **Desktop:** installs and runs offline on Windows/macOS/Linux; signed and
  notarized; no SmartScreen/Gatekeeper warnings; auto-update end-to-end.
- **Terraform:** `plan` clean and `apply`/`destroy` verified in a sandbox
  account; state encryption confirmed.

---

## 11. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Unverified datasets (ICBHI/BMD-HS) enter commercial pipeline | Registry sign-off gate (§5.3); current models unaffected (HLS-CMDS CC BY 4.0) |
| Cold-start latency (~5–15 s CPU) | Async report path, macro-only default, warm pool for sync, GPU later |
| LLM cost creep | Offline synthesizer default, cache, paid-only, local Ollama |
| Regulatory creep (MDR/AI Act) | Educational positioning + legal copy review; defer regulated track |
| Vendor lock-in (Cloudflare) | Docker + Terraform + ONNX + Postgres/R2 portability |
| Brand conflict / trademark collision (VitalSense) | Clearance search before domain/TM spend; fallback names ready (task 1) |
| Privacy exposure from health context | Consent, encryption, retention, anonymous default, DPA |
| Egress/DB surprises | R2 zero egress; Neon scale-to-zero; cost alerts |

---

## 12. Open decisions to confirm

Resolved: **region/legal basis — Global, EU-first, US-capable** (Delaware
C-Corp + GDPR-first; EU data residency: Neon EU region, R2 EU bucket, EU
compute). Resolved: **brand — VitalSense** (rename scoped in §4.1; GitHub repo
canonical name currently `Tnzr/FisioSense-ai`, with `cardiasense-ai` as a
legacy redirect — rename to the VitalSense brand in task 1), **pending
trademark clearance** ("VitalSense" collides with existing health-tech marks). Resolved: dataset
licensing for the current models (**HLS-CMDS = CC BY 4.0**, commercial OK with
attribution; CinC 2016 & CirCor = ODC-BY 1.0; ICBHI/BMD-HS flagged).

Remaining:

1. **Trademark clearance outcome** for "VitalSense" (execution-time gate; needs
   a USPTO/EUIPO/common-law search + fallback names if red).
2. **Founder budget/draw and marketing ramp** — model uses $0 draw and
   $1.5k→$4k/mo marketing as overridable defaults (§6).
