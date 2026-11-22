"""Render an Audit as a Markdown memo (for download, email or a deal folder)."""
from __future__ import annotations

from datetime import date

from .analyze import Audit

ICON = {"high": "🔴", "medium": "🟠", "low": "🟡", "info": "🔵"}


def _m(x):
    return "n/a" if x is None else (f"-${-x:,.0f}" if x < 0 else f"${x:,.0f}")


def to_markdown(a: Audit) -> str:
    c, p, uw = a.claims, a.profile, a.uw
    L = [
        f"# OM Reality Check: {p.address}",
        f"BBL {p.bbl} · {p.borough} · generated {date.today():%B %d, %Y}",
        "",
        f"**Grade: {a.grade}** · {len(a.high)} high, {len(a.medium)} medium severity flags",
        "",
        "## Headline",
        "| | OM | Adjusted |",
        "|---|---:|---:|",
        f"| NOI ({uw.basis}) | {_m(uw.om_noi_basis)} | {_m(uw.adjusted_noi_basis)} |",
        f"| Year-1 NOI, in place | {_m(c.noi_current_or_estimate())} | {_m(uw.adjusted_noi_year1)} |",
        f"| Value | {_m(c.asking_price)} (ask) | {_m(uw.value_at_om_cap)} at OM's implied cap |",
        "",
        "## Red flags",
    ]
    for f in a.flags:
        L.append(f"### {ICON[f.severity]} {f.title}")
        L.append(f.detail)
        bits = []
        if f.om_value:
            bits.append(f"OM: {f.om_value}")
        if f.record_value:
            bits.append(f"Record: {f.record_value}")
        if f.noi_impact:
            bits.append(f"NOI impact: {_m(f.noi_impact)}/yr")
        if bits:
            L.append("*" + " · ".join(bits) + "*")
        if f.om_quote:
            L.append(f"> OM says: \"{f.om_quote}\"")
        if f.source:
            L.append(f"<sub>Source: {f.source}</sub>")
        L.append("")
    L += [
        "## Public record",
        f"- {p.units_res} residential / {p.units_total} total units, {p.bldg_area:,.0f} SF, built {p.year_built}, "
        f"{p.floors:.0f} floors, class {p.bldg_class}, zoning {p.zoning}",
        f"- Owner of record: {p.owner}",
    ]
    if p.assessment:
        s = p.assessment
        L.append(f"- FY{s.roll_year} tax class {s.tax_class}: market value {_m(s.market_value)}, taxable AV "
                 f"{_m(s.taxable_av)}, exempt {_m(s.exempt_av)}, est. tax {_m(s.est_annual_tax)}")
    for e in p.exemptions:
        L.append(f"- Exemption {e.code} {e.description}: {e.start_year}-{e.end_year}, saves ~{_m(e.annual_tax_savings)}/yr")
    if p.likely_rent_stabilized:
        L.append("- Likely rent stabilized: " + "; ".join(p.rs_reasons))
    L += ["", "## Adjusted projection", "| Yr | EGI | Taxes | Other opex | NOI |", "|---:|---:|---:|---:|---:|"]
    for y in uw.projection:
        L.append(f"| {y.year} | {_m(y.egi)} | {_m(y.taxes)} | {_m(y.other_expenses)} | {_m(y.noi)} |")
    L += ["", "Assumptions: " + ", ".join(f"{k}={v}" for k, v in uw.assumptions.items())]
    for n in uw.notes:
        L.append(f"- {n}")
    L += ["", "---",
          "*Automated screen built on NYC public data. Not an appraisal, legal or zoning opinion. "
          "Verify rent-stabilization status with DHCR rent histories and zoning with an expediter.*"]
    if p.warnings:
        L += ["", "Data warnings: " + "; ".join(p.warnings)]
    return "\n".join(L)
