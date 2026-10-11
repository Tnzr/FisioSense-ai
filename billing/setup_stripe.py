#!/usr/bin/env python3
"""Create/update Asculto Stripe products and prices idempotently.

Reads `billing/products.yaml` and reconciles against Stripe using
`metadata.asculto_tier` as the idempotency key. Prints the price-id -> tier map
to paste into the gateway `PRICE_MAP` var.

Usage:
  STRIPE_SECRET_KEY=sk_test_... .venv/bin/python billing/setup_stripe.py --dry-run
  STRIPE_SECRET_KEY=sk_test_... .venv/bin/python billing/setup_stripe.py
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
CATALOG = ROOT / "products.yaml"


def main() -> int:
    ap = argparse.ArgumentParser(description="Reconcile the Asculto Stripe catalogue")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yaml", default=str(CATALOG))
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.yaml).read_text())
    tiers = {k: v for k, v in cfg["tiers"].items() if float(v["price"]) > 0}

    if args.dry_run:
        print(json.dumps({"tiers": list(tiers), "note": "dry run; no Stripe calls"}, indent=2))
        return 0

    import stripe

    stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
    price_map: dict[str, str] = {}
    existing = stripe.Product.search(query="metadata['asculto_brand']:'Asculto'").data
    by_tier = {p.metadata.get("asculto_tier"): p for p in existing}

    for key, tier in tiers.items():
        product = by_tier.get(key)
        if product is None:
            product = stripe.Product.create(
                name=tier["name"],
                metadata={"asculto_brand": "Asculto", "asculto_tier": key},
            )
        prices = stripe.Price.list(product=product.id, active=True, limit=100).data
        match = next(
            (p for p in prices
             if p.unit_amount == int(float(tier["price"]) * 100)
             and p.recurring and p.recurring.interval == tier.get("interval", "month")),
            None,
        )
        if match is None:
            match = stripe.Price.create(
                product=product.id,
                unit_amount=int(float(tier["price"]) * 100),
                currency="usd",
                recurring={"interval": tier.get("interval", "month")},
                metadata={"asculto_tier": key},
            )
        price_map[match.id] = key
        print(f"[stripe] {key}: product={product.id} price={match.id}")

    print("\nPRICE_MAP=" + json.dumps(price_map))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
