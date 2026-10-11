# Asculto billing

- `products.yaml` — the subscription catalogue (Free/Pro/Research/Enterprise).
- `setup_stripe.py` — idempotently creates/updates Stripe products and prices.

```bash
STRIPE_SECRET_KEY=sk_test_... .venv/bin/python billing/setup_stripe.py --dry-run
STRIPE_SECRET_KEY=sk_test_... .venv/bin/python billing/setup_stripe.py
```

The script prints a `PRICE_MAP` JSON to set as the gateway var; the gateway's
`gateway/src/stripe.ts` maps a Stripe price id to a tier and upserts the
entitlement in KV.

Guardrails (plan §8.2): webhook signature verification, idempotent upserts,
test-mode first, annual plans for lower churn, SEPA/ACH rails to cut the fixed
$0.30 per-charge cost (see `docs/Finance.md` sensitivity).
