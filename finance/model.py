#!/usr/bin/env python3
"""Asculto sustainability / unit-economics model.

Reads `finance/pricing.yaml` and reproduces the break-even, ramp, sensitivity and
investor-metric tables from the deployment plan (S6), emitting `docs/Finance.md`.

Usage:
  .venv/bin/python finance/model.py                 # write docs/Finance.md + print summary
  .venv/bin/python finance/model.py --out /tmp/f.md
  .venv/bin/python finance/model.py --yaml other.yaml
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PAYING = ("pro", "research", "enterprise")


def _effective_price(price: float, c: dict) -> float:
    """Annual-plan blended price: adoption share pays (12 - free months)/12."""
    adoption = float(c.get("annual_plan_adoption", 0.0))
    free_months = float(c.get("annual_plan_discount_months", 0))
    discounted = price * (12 - free_months) / 12
    return (1 - adoption) * price + adoption * discounted


def _payment_fee(price: float, c: dict, sepa: bool = False) -> float:
    if sepa:
        return float(c.get("sepa_payment_fee_pct", 0.008)) * price
    pct = float(c.get("payment_fee_pct", 0.029)) + float(c.get("billing_fee_pct", 0.0))
    return pct * price + float(c.get("payment_fee_fixed", 0.30))


def _tier_cogs(tier: dict, price: float, c: dict, *, gpu: bool = False, sepa: bool = False) -> float:
    reports = float(tier["reports_per_month"])
    per_report = float(c["gpu_per_report"] if gpu else c["inference_per_report_cpu"])
    cogs = per_report * reports
    if tier.get("llm"):
        cogs += float(c["llm_per_report"]) * reports
    cogs += float(c["storage_db_egress_per_user_month"])
    cogs += _payment_fee(price, c, sepa=sepa)
    return cogs


def compute(cfg: dict, *, mix: dict | None = None, churn: float | None = None,
            cac: float | None = None, gpu: bool = False, sepa: bool = False,
            billing: float | None = None) -> dict:
    c = dict(cfg["costs"])
    if billing is not None:
        c["billing_fee_pct"] = billing
    mix = mix or cfg["mix"]
    churn = cfg["growth"]["monthly_churn"] if churn is None else churn
    cac = cfg["growth"]["cac"] if cac is None else cac

    arpu = reports = cogs = 0.0
    per_tier = {}
    for key in PAYING:
        share = float(mix.get(key, 0.0))
        if share <= 0:
            continue
        tier = cfg["tiers"][key]
        price = _effective_price(float(tier["price"]), c)
        t_cogs = _tier_cogs(tier, price, c, gpu=gpu, sepa=sepa)
        arpu += share * price
        reports += share * float(tier["reports_per_month"])
        cogs += share * t_cogs
        per_tier[key] = {"share": share, "price": price, "reports": tier["reports_per_month"],
                         "payment_fee": _payment_fee(price, c, sepa=sepa),
                         "cogs": t_cogs,
                         "margin": (price - t_cogs) / price if price else 0.0}

    gm = (arpu - cogs) / arpu if arpu else 0.0
    contribution = arpu - cogs
    ltv = arpu * gm / churn if churn else 0.0
    return {
        "arpu": arpu, "reports": reports, "cogs": cogs, "gm": gm,
        "contribution": contribution, "churn": churn, "cac": cac,
        "ltv": ltv, "ltv_cac": ltv / cac if cac else 0.0,
        "payback": cac / contribution if contribution else 0.0,
        "per_tier": per_tier,
    }


def break_even(cfg: dict, base: dict) -> list[tuple[str, float, int]]:
    rows = []
    for name in cfg.get("break_even_opex", list(cfg["fixed_opex"])):
        fixed = float(cfg["fixed_opex"][name])
        n = math.ceil(fixed / base["contribution"]) if base["contribution"] else 0
        rows.append((name, fixed, n))
    return rows


def ramp(cfg: dict, base: dict) -> list[dict]:
    out, cumulative = [], 0.0
    for row in cfg["ramp"]:
        paying = float(row["paying"])
        fixed = float(row["fixed"])
        mrr = paying * base["arpu"]
        cogs = paying * base["cogs"]
        net = mrr - cogs - fixed
        cumulative += net
        out.append({"month": row["month"], "free_mau": row["free_mau"], "paying": paying,
                    "mrr": mrr, "cogs": cogs, "fixed": fixed, "net": net,
                    "cumulative": cumulative})
    return out


def growth_metrics(cfg: dict, base: dict, rows: list[dict]) -> dict:
    by_month = {r["month"]: r for r in rows}
    m9, m12 = by_month.get(9), by_month.get(12)
    if m9 and m12 and m9["mrr"]:
        monthly = (m12["mrr"] / m9["mrr"]) ** (1 / 3) - 1
    else:
        monthly = 0.0
    annual = (1 + monthly) ** 12 - 1
    net_margin = m12["net"] / m12["mrr"] if m12 and m12["mrr"] else 0.0
    reinvest = max(0.0, m12["net"]) * float(cfg["growth"]["reinvest_rate"]) if m12 else 0.0
    r40_growth = float(cfg["growth"].get("rule_of_40_growth", 0.35))
    return {"monthly_growth": monthly, "annual_growth": annual,
            "net_margin": net_margin,
            "rule_of_40": r40_growth * 100 + net_margin * 100,
            "rule_of_40_growth": r40_growth,
            "reinvestment": reinvest}


def money(x: float) -> str:
    s = f"${abs(x):,.2f}" if abs(x) < 100 else f"${abs(x):,.0f}"
    return f"-{s}" if x < 0 else s


def pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def build_markdown(cfg: dict, base: dict) -> str:
    be = break_even(cfg, base)
    rows = ramp(cfg, base)
    g = growth_metrics(cfg, base, rows)
    t = cfg["targets"]

    # --- sensitivity -----------------------------------------------------------
    mix_arpu18 = {"pro": 0.55, "research": 0.45, "enterprise": 0.0}
    sens = [
        ("Churn 5% -> 8%", compute(cfg, churn=0.08)),
        ("ARPU $12 -> $18 (Pro/Research mix 55/45)", compute(cfg, mix=mix_arpu18)),
        ("CAC $45 -> $90 (paid-ads-heavy)", compute(cfg, cac=cfg["growth"]["cac_paid_ads"])),
        ("Annual plan adoption 40% (churn -1.5 pts)",
         compute(cfg, churn=max(0.0, base["churn"] - 0.015), billing=cfg["costs"]["billing_fee_pct"])),
        ("SEPA/ACH rails on all tiers", compute(cfg, sepa=True)),
        ("GPU for all reports", compute(cfg, gpu=True)),
    ]
    # annual adoption needs the yaml toggle; approximate with a temp override
    cfg_annual = dict(cfg)
    cfg_annual["costs"] = dict(cfg["costs"], annual_plan_adoption=0.40)
    sens[3] = ("Annual plan adoption 40% (churn -1.5 pts)",
               compute(cfg_annual, churn=max(0.0, base["churn"] - 0.015)))

    L = []
    L.append("# Asculto — Finance & Unit Economics\n")
    L.append("> Reproducible from `finance/pricing.yaml` via `finance/model.py` "
             "(run `.venv/bin/python finance/model.py`). List prices checked October 2026.\n")
    L.append("Educational/research positioning; not a medical device. See the deployment "
             "plan for the hosting/legal context.\n")

    L.append("## 1. Blended unit economics (consumer mix)\n")
    L.append("| Metric | Value |")
    L.append("|---|---|")
    L.append(f"| Blended ARPU | {money(base['arpu'])}/mo |")
    L.append(f"| Reports / paying user | {base['reports']:.1f}/mo |")
    L.append(f"| COGS / paying user | {money(base['cogs'])}/mo |")
    L.append(f"| Gross margin | **{pct(base['gm'])}** |")
    L.append(f"| Contribution | {money(base['contribution'])}/mo |")
    L.append(f"| Monthly churn | {pct(base['churn'])} |")
    L.append(f"| CAC (blended) | {money(base['cac'])} |")
    L.append(f"| LTV | {money(base['ltv'])} |")
    L.append(f"| LTV:CAC | **{base['ltv_cac']:.2f}** (target >= {t['ltv_cac_min']:.1f}) |")
    L.append(f"| CAC payback | **{base['payback']:.1f} mo** (target <= {t['cac_payback_max_months']:.0f}) |\n")

    L.append("### Per-tier COGS and margin\n")
    L.append("| Tier | Price | Reports/mo | Payment fee | COGS/user/mo | Gross margin |")
    L.append("|---|---|---|---|---|---|")
    for key in PAYING:
        if key not in base["per_tier"]:
            continue
        d = base["per_tier"][key]
        L.append(f"| {key.capitalize()} | {money(d['price'])} | {d['reports']:.0f} | "
                 f"{money(d['payment_fee'])} | {money(d['cogs'])} | {pct(d['margin'])} |")
    free = cfg["tiers"]["free"]
    free_cogs = (float(cfg["costs"]["inference_per_report_cpu"]) * float(free["reports_per_month"])
                 + float(cfg["costs"]["storage_db_egress_per_user_month"]))
    L.append(f"| Free | $0 | {free['reports_per_month']:.0f} | $0.00 | "
             f"{money(free_cogs)} (funnel) | n/a |\n")

    L.append("## 2. Break-even paying subscribers\n")
    L.append(f"Contribution per paying user = {money(base['contribution'])}/mo; "
             "N* = fixed opex / contribution.\n")
    L.append("| Fixed opex F | Break-even paying subs |")
    L.append("|---|---|")
    for name, fixed, n in be:
        L.append(f"| {money(fixed)} ({name.replace('_', ' ')}) | **{n}** |")
    L.append("")

    L.append("## 3. Illustrative self-investing ramp\n")
    L.append("| Month | Free MAU | Paying | MRR | COGS | Fixed | Net | Cumulative |")
    L.append("|---|---|---|---|---|---|---|---|")
    for r in rows:
        L.append(f"| {r['month']} | {r['free_mau']:,} | {r['paying']:.0f} | {money(r['mrr'])} | "
                 f"{money(r['cogs'])} | {money(r['fixed'])} | {money(r['net'])} | {money(r['cumulative'])} |")
    L.append("")
    L.append(f"MoM MRR growth (m9->m12): {pct(g['monthly_growth'])}; annualized {pct(g['annual_growth'])} "
             f"(illustrative, aggressive). Net margin (m12): {pct(g['net_margin'])}. "
             f"Rule of 40 = {pct(g['rule_of_40_growth'])} conservative growth + net margin = "
             f"**{g['rule_of_40']:.0f}** (target >= {t['rule_of_40_min']:.0f}). "
             f"Reinvestment at m12: {money(g['reinvestment'])}/mo.\n")

    L.append("## 4. Sensitivity\n")
    L.append("| Scenario | ARPU | COGS | Gross margin | Contribution | LTV | LTV:CAC | Payback |")
    L.append("|---|---|---|---|---|---|---|---|")
    for name, s in sens:
        L.append(f"| {name} | {money(s['arpu'])} | {money(s['cogs'])} | {pct(s['gm'])} | "
                 f"{money(s['contribution'])} | {money(s['ltv'])} | {s['ltv_cac']:.2f} | {s['payback']:.1f} mo |")
    free_mau = max((r["free_mau"] for r in rows), default=0)
    L.append("")
    L.append(f"- **LLM on free tier**: ~${0.005 * free_mau:,.0f}/mo at {free_mau:,} free MAU "
             "-> keep LLM gated to paid tiers.")
    L.append("- **GPU for all reports**: COGS/user rises ~8x -> reserve GPU for Research/Enterprise "
             "batch or large models only.\n")

    L.append("## 5. Monthly infra cost floor by stage\n")
    L.append("| Stage | Floor/mo |")
    L.append("|---|---|")
    for name, val in cfg["infra_floors"].items():
        L.append(f"| {name.replace('_', ' ')} | {money(float(val))} |")
    L.append("")

    L.append("## 6. Investor metric sheet\n")
    L.append("| Metric | Value | Target |")
    L.append("|---|---|---|")
    L.append(f"| Gross margin | {pct(base['gm'])} | >= {pct(t['gross_margin_min'])} |")
    L.append(f"| LTV:CAC | {base['ltv_cac']:.2f} | >= {t['ltv_cac_min']:.1f} |")
    L.append(f"| CAC payback | {base['payback']:.1f} mo | <= {t['cac_payback_max_months']:.0f} mo |")
    L.append(f"| NRR | (target) | > {pct(t['nrr_target'])} |")
    L.append(f"| Rule of 40 | {g['rule_of_40']:.0f} | >= {t['rule_of_40_min']:.0f} |")
    L.append("| Burn multiple | (target) | < 1.5 |")
    L.append(f"| Idle infra | {money(float(cfg['infra_floors']['stage1a_demo']))}/mo | capital efficiency |")
    L.append("")
    L.append("ARR path (blended ARPU):")
    for subs in (1000, 5000, 6900):
        L.append(f"- {subs:,} paying subs -> **{money(subs * base['arpu'] * 12)} ARR**")
    L.append("")
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser(description="Asculto finance model")
    ap.add_argument("--yaml", default=str(ROOT / "finance" / "pricing.yaml"))
    ap.add_argument("--out", default=str(ROOT / "docs" / "Finance.md"))
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.yaml).read_text())
    base = compute(cfg)
    md = build_markdown(cfg, base)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")

    print(f"ARPU {money(base['arpu'])} | COGS {money(base['cogs'])} | GM {pct(base['gm'])} | "
          f"contribution {money(base['contribution'])} | LTV:CAC {base['ltv_cac']:.2f} | "
          f"payback {base['payback']:.1f} mo")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
