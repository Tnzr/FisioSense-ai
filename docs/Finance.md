# Asculto — Finance & Unit Economics

> Reproducible from `finance/pricing.yaml` via `finance/model.py` (run `.venv/bin/python finance/model.py`). List prices checked October 2026.

Educational/research positioning; not a medical device. See the deployment plan for the hosting/legal context.

## 1. Blended unit economics (consumer mix)

| Metric | Value |
|---|---|
| Blended ARPU | $12.00/mo |
| Reports / paying user | 36.2/mo |
| COGS / paying user | $0.75/mo |
| Gross margin | **93.8%** |
| Contribution | $11.25/mo |
| Monthly churn | 5.0% |
| CAC (blended) | $45.00 |
| LTV | $225 |
| LTV:CAC | **5.00** (target >= 3.0) |
| CAC payback | **4.0 mo** (target <= 6) |

### Per-tier COGS and margin

| Tier | Price | Reports/mo | Payment fee | COGS/user/mo | Gross margin |
|---|---|---|---|---|---|
| Pro | $9.00 | 25 | $0.56 | $0.65 | 92.8% |
| Research | $29.00 | 100 | $1.14 | $1.33 | 95.4% |
| Free | $0 | 5 | $0.00 | $0.05 (funnel) | n/a |

## 2. Break-even paying subscribers

Contribution per paying user = $11.25/mo; N* = fixed opex / contribution.

| Fixed opex F | Break-even paying subs |
|---|---|
| $2,000 (bootstrap) | **178** |
| $3,000 (early) | **267** |
| $4,000 (founder draw) | **356** |
| $8,000 (with founder draw) | **712** |

## 3. Illustrative self-investing ramp

| Month | Free MAU | Paying | MRR | COGS | Fixed | Net | Cumulative |
|---|---|---|---|---|---|---|---|
| 3 | 1,500 | 45 | $540 | $33.69 | $2,000 | -$1,494 | -$1,494 |
| 6 | 6,000 | 180 | $2,160 | $135 | $2,500 | -$475 | -$1,968 |
| 9 | 15,000 | 450 | $5,400 | $337 | $3,000 | $2,063 | $94.59 |
| 12 | 30,000 | 900 | $10,800 | $674 | $4,000 | $6,126 | $6,221 |
| 18 | 80,000 | 2400 | $28,800 | $1,797 | $7,000 | $20,003 | $26,224 |
| 24 | 200,000 | 6000 | $72,000 | $4,492 | $14,000 | $53,508 | $79,731 |

MoM MRR growth (m9->m12): 26.0%; annualized 1500.0% (illustrative, aggressive). Net margin (m12): 56.7%. Rule of 40 = 35.0% conservative growth + net margin = **92** (target >= 40). Reinvestment at m12: $3,063/mo.

## 4. Sensitivity

| Scenario | ARPU | COGS | Gross margin | Contribution | LTV | LTV:CAC | Payback |
|---|---|---|---|---|---|---|---|
| Churn 5% -> 8% | $12.00 | $0.75 | 93.8% | $11.25 | $141 | 3.13 | 4.0 mo |
| ARPU $12 -> $18 (Pro/Research mix 55/45) | $18.00 | $0.95 | 94.7% | $17.05 | $341 | 7.58 | 2.6 mo |
| CAC $45 -> $90 (paid-ads-heavy) | $12.00 | $0.75 | 93.8% | $11.25 | $225 | 2.50 | 8.0 mo |
| Annual plan adoption 40% (churn -1.5 pts) | $11.20 | $0.73 | 93.5% | $10.47 | $299 | 6.65 | 4.3 mo |
| SEPA/ACH rails on all tiers | $12.00 | $0.20 | 98.4% | $11.80 | $236 | 5.25 | 3.8 mo |
| GPU for all reports | $12.00 | $0.88 | 92.7% | $11.12 | $222 | 4.94 | 4.0 mo |

- **LLM on free tier**: ~$1,000/mo at 200,000 free MAU -> keep LLM gated to paid tiers.
- **GPU for all reports**: COGS/user rises ~8x -> reserve GPU for Research/Enterprise batch or large models only.

## 5. Monthly infra cost floor by stage

| Stage | Floor/mo |
|---|---|
| stage0 poc | $0.00 |
| stage1a demo | $6.00 |
| stage1b beta | $30.00 |
| stage1c 1k reports | $70.00 |
| stage2 k8s | $160 |
| stage2 gpu | $600 |

## 6. Investor metric sheet

| Metric | Value | Target |
|---|---|---|
| Gross margin | 93.8% | >= 90.0% |
| LTV:CAC | 5.00 | >= 3.0 |
| CAC payback | 4.0 mo | <= 6 mo |
| NRR | (target) | > 110.0% |
| Rule of 40 | 92 | >= 40 |
| Burn multiple | (target) | < 1.5 |
| Idle infra | $6.00/mo | capital efficiency |

ARR path (blended ARPU):
- 1,000 paying subs -> **$144,000 ARR**
- 5,000 paying subs -> **$720,000 ARR**
- 6,900 paying subs -> **$993,600 ARR**
