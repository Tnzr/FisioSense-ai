# Asculto Privacy Policy (draft)

_Last updated: [DATE]. Controller: [LEGAL ENTITY], [ADDRESS]. Contact/DPO: [CONTACT]._

> **Not legal advice.** GDPR-first (plan A2/A10). Anonymous by default: no
> account or identity is required to use the core product.

## 1. Data we process

| Category | Examples | Purpose | Lawful basis |
|---|---|---|---|
| Audio recordings | heart/lung `.wav` uploads | produce a report | contract / consent |
| Report metadata | heads, probabilities, timestamps | deliver & improve the service | contract |
| Optional health context | free-text `patient_context` | personalize the narrative | **explicit consent** |
| Account & billing | email, Stripe customer id | auth, payments | contract |
| Usage/telemetry | quota counters, errors | security, quotas | legitimate interest |

We do **not** require patient identity. Do not upload PHI or third-party health
data without a lawful basis.

## 2. Data residency and transfers
Stored data and compute are pinned to **EU regions** at launch (Neon EU, R2 EU,
EU compute). US processing is added only at expansion, covered by SCCs and the
DPA. Restricted datasets (e.g. MIMIC-family) must never be routed to cloud LLMs.

## 3. Retention
Uploads are processed and deleted after the report is generated unless you opt
into storage. Quota counters expire after ~40 days. [Define report/metadata
retention, e.g. 30/90 days.]

## 4. Processors
Cloudflare (Pages/Workers/R2/Queues), Neon (Postgres), Modal (GPU), Stripe
(payments), and — only when you enable it — an OpenAI-compatible LLM provider or
your own local Ollama. A current sub-processor list is maintained at
`[URL]/subprocessors`.

## 5. Your rights
Access, rectification, erasure, restriction, portability, objection, and
withdrawal of consent; lodge a complaint with your supervisory authority. Contact
[CONTACT]. We respond within one month.

## 6. Security
Encryption in transit and at rest (R2 SSE), signed short-lived upload URLs, per-
tenant quotas, least-privilege secrets, and no keys in source control.

## 7. Children
Not directed at children under [16]. [Age-gate copy.]

## 8. Cookies
See the Cookie Policy. Strictly-necessary cookies only by default; consent for
anything else.
