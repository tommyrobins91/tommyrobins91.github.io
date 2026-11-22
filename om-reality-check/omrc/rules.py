"""Red-flag rules: compare OM claims against the public record and NYC law.

Each rule is a small function that returns zero or more `Flag`s. Rules never
raise on missing data; if the OM or the record lacks what a rule needs, the rule
stays silent. Add a rule by writing a function and listing it in RULES.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Callable, List, Optional

from . import config
from .claims import OMClaims
from .profile import PropertyProfile, current_fiscal_year
from .underwrite import expense_floor, max_iai_bump, project_taxes, rgb_growth_path

HIGH, MEDIUM, LOW, INFO = "high", "medium", "low", "info"
SEVERITY_ORDER = {HIGH: 0, MEDIUM: 1, LOW: 2, INFO: 3}


@dataclass
class Flag:
    rule: str
    severity: str
    category: str
    title: str
    detail: str
    om_value: Optional[str] = None
    record_value: Optional[str] = None
    noi_impact: Optional[float] = None   # annual $, negative = OM overstates NOI
    source: Optional[str] = None
    om_quote: Optional[str] = None

    def to_dict(self):
        return asdict(self)


def _money(x) -> str:
    return f"-${-x:,.0f}" if x < 0 else f"${x:,.0f}"


def _pct_diff(a: float, b: float) -> float:
    return abs(a - b) / b if b else 0.0


# ---------------------------------------------------------------------------
# Physical facts
# ---------------------------------------------------------------------------

def rule_unit_count(c: OMClaims, p: PropertyProfile) -> List[Flag]:
    om = c.residential_count()
    if om is None or not p.units_res or om == p.units_res:
        return []
    more = om > p.units_res
    return [Flag(
        "unit_count", HIGH if more else MEDIUM, "Physical",
        "Residential unit count doesn't match city records",
        (f"OM markets {om} units; the city records {p.units_res} legal residential units. "
         + ("Extra units may be illegal conversions that can't be legally rented and can be "
            "ordered vacated." if more else "Check for combined units or vacant/warehoused space.")),
        om_value=str(om), record_value=str(p.units_res),
        source="NYC MapPLUTO (UnitsRes); confirm with the Certificate of Occupancy on DOB BIS",
    )]


def rule_gross_sf(c: OMClaims, p: PropertyProfile) -> List[Flag]:
    if not c.gross_sf or not p.bldg_area:
        return []
    diff = _pct_diff(c.gross_sf, p.bldg_area)
    if diff <= config.TOLERANCE_PCT:
        return []
    return [Flag(
        "gross_sf", MEDIUM if c.gross_sf > p.bldg_area else LOW, "Physical",
        "Building square footage is overstated" if c.gross_sf > p.bldg_area else "Building square footage differs",
        f"OM states {c.gross_sf:,.0f} SF vs {p.bldg_area:,.0f} SF in city records ({diff:.0%} off). "
        "Price-per-SF comps built on the OM figure will be wrong.",
        om_value=f"{c.gross_sf:,.0f} SF", record_value=f"{p.bldg_area:,.0f} SF",
        source="NYC MapPLUTO (BldgArea)",
    )]


def rule_year_built(c: OMClaims, p: PropertyProfile) -> List[Flag]:
    if not c.year_built or not p.year_built or abs(c.year_built - p.year_built) <= 2:
        return []
    crosses = (c.year_built >= config.RS_BUILT_BEFORE) != (p.year_built >= config.RS_BUILT_BEFORE)
    return [Flag(
        "year_built", HIGH if crosses else LOW, "Physical",
        "Year built doesn't match city records",
        f"OM says {c.year_built}; city records say {p.year_built}."
        + (" This moves the building across the 1974 rent-stabilization line." if crosses else ""),
        om_value=str(c.year_built), record_value=str(p.year_built), source="NYC MapPLUTO (YearBuilt)",
    )]


def rule_air_rights(c: OMClaims, p: PropertyProfile) -> List[Flag]:
    if not c.air_rights_sf or not p.lot_area:
        return []
    avail = p.unused_res_far_sf
    if c.air_rights_sf <= avail * (1 + config.TOLERANCE_PCT):
        return []
    return [Flag(
        "air_rights", HIGH if avail == 0 else MEDIUM, "Zoning",
        "Claimed air rights exceed what zoning allows",
        f"OM claims {c.air_rights_sf:,.0f} SF of air rights. Under {p.zoning} (residential FAR "
        f"{p.resid_far:.2f}) on a {p.lot_area:,.0f} SF lot, with built FAR {p.built_far:.2f}, about "
        f"{avail:,.0f} SF is unused. The difference would need a bonus (e.g. City of Yes UAP), a "
        "landmark transfer or a zoning lot merger. Ask the broker for the zoning analysis.",
        om_value=f"{c.air_rights_sf:,.0f} SF", record_value=f"~{avail:,.0f} SF as-of-right",
        source="NYC MapPLUTO (ResidFAR, BuiltFAR, LotArea); approximate, not a zoning opinion",
    )]


# ---------------------------------------------------------------------------
# Rent regulation
# ---------------------------------------------------------------------------

def rule_rs_status(c: OMClaims, p: PropertyProfile) -> List[Flag]:
    rs = c.rs_count()
    units = c.residential_count() or p.units_res
    if not p.likely_rent_stabilized or rs is None or not units or rs >= units:
        return []
    fm_units = [u.unit for u in c.rent_roll if u.status == "FM"]
    reasons = "; ".join(p.rs_reasons)
    q = c.quote_for("rs_units")
    if rs < units * 0.5:
        return [Flag(
            "rs_status", HIGH, "Rent regulation",
            "Building is likely rent stabilized, but the OM treats most units as free market",
            f"OM shows {rs} of {units} units as stabilized. Public records point to stabilization: {reasons}. "
            "Since HSTPA (June 2019) units can't leave stabilization through vacancy or high rent. "
            "Free-market status needs proof (a pre-2019 deregulation with DHCR registration history).",
            om_value=f"{rs} RS units", record_value="Likely stabilized",
            source="MapPLUTO year built & units; DOF exemptions; HSTPA 2019",
            om_quote=q.text if q else None,
        )]
    return [Flag(
        "rs_verify", MEDIUM, "Rent regulation",
        f"Verify deregulation of the {units - rs} free-market units",
        f"This building is presumptively stabilized: {reasons}. The OM calls "
        + (f"units {', '.join(fm_units)}" if fm_units else f"{units - rs} units")
        + " free market. That's only valid if each unit was lawfully deregulated before June 14, 2019. "
        "Request DHCR rent registration histories; an improper deregulation can mean rent rollbacks and treble damages.",
        om_value=f"{units - rs} FM units", record_value="Presumptively stabilized",
        source="MapPLUTO; HSTPA 2019; Regina Metropolitan Co. v. DHCR (2020) lookback rules",
        om_quote=q.text if q else None,
    )]


def rule_deregulation_upside(c: OMClaims, p: PropertyProfile) -> List[Flag]:
    if not c.claims_deregulation_upside:
        return []
    q = c.quote_for("claims_deregulation_upside")
    return [Flag(
        "deregulation_upside", HIGH, "Rent regulation",
        "OM promises upside from taking stabilized units to market",
        "The Housing Stability and Tenant Protection Act of 2019 repealed high-rent vacancy "
        "deregulation, high-income deregulation and the vacancy bonus. Stabilized units stay "
        "stabilized on turnover, so this upside is not legally available.",
        om_value="Deregulation upside", record_value="Not permitted since 6/14/2019",
        source="HSTPA 2019 (NYS L.2019 c.36)", om_quote=q.text if q else None,
    )]


def rule_rs_rent_growth(c: OMClaims, p: PropertyProfile) -> List[Flag]:
    if c.rs_rent_growth is None:
        return []
    path = rgb_growth_path(config.DEFAULT_HOLD_YEARS)
    allowed = (1 + sum(path) / len(path)) - 1
    if c.rs_rent_growth <= allowed + 0.0025:
        return []
    rs_income = sum((u.current_rent or 0) for u in c.rent_roll if u.status == "RS") * 12
    impact = None
    if rs_income:
        n = config.DEFAULT_HOLD_YEARS
        impact = -(rs_income * ((1 + c.rs_rent_growth) ** n - (1 + allowed) ** n))
    return [Flag(
        "rs_rent_growth", HIGH if c.rs_rent_growth - allowed > 0.01 else MEDIUM, "Rent regulation",
        "Stabilized rent growth exceeds what the Rent Guidelines Board allows",
        f"OM grows stabilized rents {c.rs_rent_growth:.1%}/yr. RGB Order #58 froze renewals at 0% "
        f"for leases starting Oct 2026-Sep 2027; at {config.RGB_FORWARD_ASSUMPTION:.0%} in later years "
        f"the 5-year average is ~{allowed:.1%}/yr."
        + (f" By year 5 that overstates stabilized income by about {_money(-impact)}/yr." if impact else ""),
        om_value=f"{c.rs_rent_growth:.1%}/yr", record_value=f"~{allowed:.1%}/yr",
        noi_impact=impact, source="NYC Rent Guidelines Board Orders #57-58",
    )]


def rule_proforma_rs_rents(c: OMClaims, p: PropertyProfile) -> List[Flag]:
    """Per-unit check: stabilized pro forma rents above what the law allows.

    Occupied units: renewals are capped at the RGB guideline off the rent the tenant
    pays today. Since HSTPA, a preferential rent stays the renewal base for the whole
    tenancy, so a higher "legal rent" isn't collectible until the unit turns over.
    Vacant units: legal rent plus the maximum IAI increase.
    """
    if not c.rent_roll:
        return []
    g1 = rgb_growth_path(1)[0]
    units_in_bldg = c.residential_count() or p.units_res or 0
    iai = max_iai_bump(units_in_bldg)
    over, pref = [], []
    excess = 0.0
    for u in c.rent_roll:
        if u.status != "RS" or not u.proforma_rent:
            continue
        if u.current_rent:
            cap = u.current_rent * (1 + g1)
            if u.proforma_rent > cap * 1.005:
                (pref if (u.legal_rent and u.proforma_rent <= u.legal_rent * 1.01) else over).append(
                    (u.unit, u.current_rent, u.proforma_rent, cap))
                excess += (u.proforma_rent - cap) * 12
        else:
            cap = (u.legal_rent or u.proforma_rent) + iai
            if u.proforma_rent > cap * 1.02:
                over.append((u.unit, 0, u.proforma_rent, cap))
                excess += (u.proforma_rent - cap) * 12
    if not (over or pref):
        return []
    rs_income = sum((u.current_rent or 0) for u in c.rent_roll if u.status == "RS") * 12
    big = any(pf > mx * 1.10 for _, _, pf, mx in over + pref) or (rs_income and excess > 0.10 * rs_income)
    fmt = lambda rows: "; ".join(f"#{n}: {_money(cur)} to {_money(pf)} (max {_money(mx)})" for n, cur, pf, mx in rows[:4])
    parts = []
    if pref:
        parts.append(f"{len(pref)} occupied unit(s) are projected at their DHCR legal rent, but they pay a lower "
                     f"preferential rent. Since HSTPA, renewals are capped at the RGB increase ({g1:.0%} under "
                     f"Order #58) off the preferential rent until the tenant leaves: {fmt(pref)}.")
    if over:
        parts.append(f"{len(over)} unit(s) exceed the legal path even allowing the RGB increase and, for vacant "
                     f"units, a full IAI (+{_money(iai)}/mo): {fmt(over)}.")
    return [Flag(
        "proforma_rs_rents", HIGH if big else MEDIUM, "Rent regulation",
        f"{len(over) + len(pref)} stabilized units are projected above their legal renewal rent",
        " ".join(parts),
        om_value=f"{len(over) + len(pref)} units", record_value="RGB renewal cap",
        noi_impact=-excess, source="HSTPA 2019 (preferential rents); RGB Order #58; HCR Operational Bulletin 2024-2",
    )]


def rule_renovation_bump(c: OMClaims, p: PropertyProfile) -> List[Flag]:
    if not c.renovation_rent_bump:
        return []
    units_in_bldg = c.residential_count() or p.units_res or 0
    iai = max_iai_bump(units_in_bldg)
    iai_hi = max_iai_bump(units_in_bldg, config.IAI_CAP_ENHANCED)
    if c.renovation_rent_bump <= iai_hi * 1.02:
        return []
    rs = c.rs_count() or 0
    return [Flag(
        "renovation_bump", HIGH, "Rent regulation",
        "Renovation rent premium exceeds the IAI cap for stabilized units",
        f"OM assumes +{_money(c.renovation_rent_bump)}/mo after renovating stabilized units. The IAI "
        f"rule caps this at about {_money(iai)}/mo ($30k cap) or {_money(iai_hi)}/mo ($50k cap for "
        "units occupied 25+ years or long-vacant).",
        om_value=f"+{_money(c.renovation_rent_bump)}/mo", record_value=f"max ~{_money(iai_hi)}/mo",
        noi_impact=-(c.renovation_rent_bump - iai_hi) * 12 * rs if rs else None,
        source="NYS FY2025 budget IAI changes; HCR Operational Bulletin 2024-2",
    )]


# ---------------------------------------------------------------------------
# Taxes
# ---------------------------------------------------------------------------

def rule_tax_understated(c: OMClaims, p: PropertyProfile) -> List[Flag]:
    if c.real_estate_taxes is None or p.assessment is None:
        return []
    actual = p.assessment.est_annual_tax
    if actual <= c.real_estate_taxes * (1 + config.TOLERANCE_PCT):
        return []
    gap = actual - c.real_estate_taxes
    return [Flag(
        "tax_understated", HIGH if gap / max(actual, 1) > 0.15 else MEDIUM, "Taxes",
        "Real estate taxes are understated",
        f"OM shows {_money(c.real_estate_taxes)}. The FY{p.assessment.roll_year} roll implies "
        f"{_money(actual)}: net taxable AV {_money(p.assessment.net_taxable_av)} x Class "
        f"{p.assessment.tax_class} rate {p.assessment.tax_rate:.3%}.",
        om_value=_money(c.real_estate_taxes), record_value=_money(actual),
        noi_impact=-gap, source=f"NYC DOF assessment roll; {config.TAX_RATE_FISCAL_YEAR} tax rates",
    )]


def rule_abatement_expiry(c: OMClaims, p: PropertyProfile) -> List[Flag]:
    out = []
    fy = current_fiscal_year()
    horizon = fy + config.DEFAULT_HOLD_YEARS
    for e in p.exemptions:
        if e.program == "OTHER" or e.end_year is None or e.end_year > horizon:
            continue
        undisclosed = not c.abatement_expiry_disclosed
        rs_note = ""
        if e.program in ("421A", "485X") and p.year_built >= config.RS_BUILT_BEFORE:
            rs_note = (" For 421-a buildings, check the lease riders: units stabilized only because of "
                       "the benefit may deregulate when it ends, and units may not if riders were missing.")
        when = "already ended" if e.end_year <= fy else f"ends in FY{e.end_year}"
        out.append(Flag(
            "abatement_expiry", HIGH if undisclosed else MEDIUM, "Taxes",
            f"{e.program} tax benefit {when}",
            f"The {e.description} benefit (started {e.start_year}, {e.years} years) {when}, inside a "
            f"{config.DEFAULT_HOLD_YEARS}-year hold. Taxes step up by about {_money(e.annual_tax_savings)}/yr "
            "at today's rate (phase-outs can spread this over the final years)."
            + ("" if not undisclosed else " The OM doesn't disclose the expiry.") + rs_note,
            om_value="Not disclosed" if undisclosed else "Disclosed",
            record_value=f"Ends FY{e.end_year}",
            noi_impact=-e.annual_tax_savings, source="NYC DOF Property Exemption Detail",
        ))
    return out


def rule_tax_trajectory(c: OMClaims, p: PropertyProfile) -> List[Flag]:
    """Tax growth from assessment phase-ins alone (exemption roll-offs are their own rule)."""
    a = p.assessment
    if a is None or not a.est_annual_tax:
        return []
    proj = project_taxes(p)
    if len(proj) < 2:
        return []
    phase_in = (proj[-1].taxable_av - proj[0].taxable_av) * a.tax_rate
    growth = phase_in / a.est_annual_tax
    if growth < 0.15:
        return []
    capped = a.tax_class.upper() in config.CAPPED_CLASSES
    yrs = len(proj) - 1
    return [Flag(
        "tax_trajectory", MEDIUM, "Taxes",
        f"Assessment phase-in adds ~{growth:.0%} to taxes over {yrs} years",
        f"Taxable AV ({_money(a.taxable_av)}) is below actual AV ({_money(a.actual_av)}). "
        + ("The Class " + a.tax_class + " cap lets it rise up to 8%/yr and 30% per 5 years"
           if capped else "Prior market-value increases phase in over 5 years")
        + f", adding about {_money(phase_in)}/yr by FY{proj[-1].fiscal_year} at today's rate, before any "
        "exemption roll-off. NYC doesn't reassess on sale; this increase is already locked into the roll.",
        om_value=(f"{c.expense_growth:.0%}/yr expense growth" if c.expense_growth else None),
        record_value=f"+{growth:.0%} over {yrs} yrs",
        noi_impact=-phase_in, source="NYC DOF assessment roll; RPTL 1805 caps",
    )]


# ---------------------------------------------------------------------------
# Operations and pricing
# ---------------------------------------------------------------------------

def rule_expense_ratio(c: OMClaims, p: PropertyProfile) -> List[Flag]:
    egi = c.egi_current()
    if not egi or c.total_expenses is None:
        return []
    ratio = c.total_expenses / egi
    units = c.residential_count() or p.units_res or 0
    rs = c.rs_count()
    rs_share = (rs / units) if (rs is not None and units) else (1.0 if p.likely_rent_stabilized else 0.0)
    floor = expense_floor(rs_share)
    if ratio >= floor - config.EXPENSE_FLAG_GAP:
        return []
    impact = -(floor * egi - c.total_expenses)
    per_unit = c.total_expenses / units if units else None
    return [Flag(
        "expense_ratio", HIGH if ratio < floor - 0.12 else MEDIUM, "Operations",
        "Operating expenses look too low",
        f"OM expenses are {ratio:.0%} of effective income"
        + (f" ({_money(per_unit)}/unit)" if per_unit else "")
        + f". A buyer's floor for this building is ~{floor:.0%}; RGB's 2026 study found a "
        f"{config.RGB_COST_TO_INCOME_100_RS:.0%} cost-to-income ratio for fully stabilized buildings "
        f"({config.RGB_COST_TO_INCOME_ALL:.0%} citywide). Common omissions: management fee, payroll, "
        "repairs, reserves, Local Law 97 compliance.",
        om_value=f"{ratio:.0%}", record_value=f">= {floor:.0%}", noi_impact=impact,
        source="NYC RGB 2026 Income & Expense Study",
    )]


def rule_vacancy(c: OMClaims, p: PropertyProfile) -> List[Flag]:
    if c.vacancy_pct is None or c.vacancy_pct >= 0.02 or not c.gross_income_current:
        return []
    return [Flag(
        "vacancy", LOW, "Operations", "Vacancy and credit loss assumption is very low",
        f"OM uses {c.vacancy_pct:.1%}. Lenders typically underwrite at least 2-3% plus collection loss.",
        om_value=f"{c.vacancy_pct:.1%}", record_value=">= 3%",
        noi_impact=-(config.DEFAULT_VACANCY - c.vacancy_pct) * c.gross_income_current,
    )]


def rule_cap_rate_math(c: OMClaims, p: PropertyProfile) -> List[Flag]:
    if not (c.asking_price and c.stated_cap_rate):
        return []
    cur = c.noi_current_or_estimate()
    cur_cap = cur / c.asking_price if cur is not None else None
    pf_cap = c.noi_proforma / c.asking_price if c.noi_proforma else None
    tol = 0.0025
    if cur_cap is not None and abs(cur_cap - c.stated_cap_rate) <= tol:
        return []
    estimated = c.noi_current is None and cur is not None
    cur_txt = (f"{cur_cap:.2%} on current NOI of {_money(cur)}"
               + (" (current EGI less the OM's expenses; the OM doesn't show current NOI)" if estimated else "")
               ) if cur_cap is not None else None
    if pf_cap is not None and abs(pf_cap - c.stated_cap_rate) <= tol:
        return [Flag(
            "cap_rate_basis", MEDIUM, "Pricing", "Headline cap rate is on pro forma, not in-place, income",
            f"The {c.stated_cap_rate:.2%} headline equals the OM's pro forma NOI ({_money(c.noi_proforma)}) over "
            f"the ask. In place, the deal is "
            + (cur_txt or "lower") + ". The gap is lease-up and rent growth the buyer pays for upfront.",
            om_value=f"{c.stated_cap_rate:.2%}", record_value=f"{cur_cap:.2%} in place" if cur_cap else None,
            om_quote=(c.quote_for("stated_cap_rate").text if c.quote_for("stated_cap_rate") else None),
        )]
    implied = ", ".join(x for x in [
        cur_txt,
        f"{pf_cap:.2%} on pro forma NOI of {_money(c.noi_proforma)}" if pf_cap is not None else None,
    ] if x)
    if not implied:
        return []
    return [Flag(
        "cap_rate_math", MEDIUM, "Pricing", "Stated cap rate doesn't match the OM's own numbers",
        f"OM states a cap rate of {c.stated_cap_rate:.2%} on {_money(c.asking_price)}, but its own figures give {implied}. "
        "Ask the broker which NOI the headline uses.",
        om_value=f"{c.stated_cap_rate:.2%}", record_value=implied.split(" on ")[0],
        om_quote=(c.quote_for("stated_cap_rate").text if c.quote_for("stated_cap_rate") else None),
    )]


def rule_violations(c: OMClaims, p: PropertyProfile) -> List[Flag]:
    out = []
    c_cls = p.hpd_open.get("C", 0)
    total = sum(p.hpd_open.values())
    if total:
        out.append(Flag(
            "hpd_violations", HIGH if c_cls >= 5 else (MEDIUM if c_cls else LOW), "Condition",
            f"{total} open HPD violations ({c_cls} immediately hazardous)",
            "Open violations by class: " + ", ".join(f"{k}: {v}" for k, v in sorted(p.hpd_open.items()))
            + ". Class C violations can block rent increases and signal deferred capex.",
            record_value=f"{total} open", source="HPD Housing Maintenance Code Violations",
        ))
    if p.ecb_open_count or p.ecb_balance_due > 1000:
        out.append(Flag(
            "ecb_violations", MEDIUM if p.ecb_balance_due > 10000 else LOW, "Condition",
            f"{p.ecb_open_count} active DOB/ECB violations",
            f"Outstanding ECB penalties total about {_money(p.ecb_balance_due)}. These become liens "
            "and should be cleared or credited at closing.",
            record_value=_money(p.ecb_balance_due), source="DOB ECB Violations",
        ))
    return out


def rule_basis_context(c: OMClaims, p: PropertyProfile) -> List[Flag]:
    out = []
    if c.asking_price and p.mortgages:
        latest = p.mortgages[0]
        if latest.amount >= c.asking_price * 0.85:
            out.append(Flag(
                "debt_vs_ask", INFO, "Pricing", "Recorded debt is close to (or above) the asking price",
                f"A {latest.doc_type} for {_money(latest.amount)} was recorded {latest.recorded}. With the ask at "
                f"{_money(c.asking_price)}, the seller may need this price to clear the loan, which can "
                "mean motivation or a discounted note sale.",
                record_value=_money(latest.amount), source="ACRIS",
            ))
    deed = p.last_deed
    if deed and deed.amount > 100_000:
        recorded = date.fromisoformat(deed.recorded)
        if (date.today() - recorded).days <= 365:
            vs = f" ({deed.amount / c.asking_price - 1:+.0%} vs. the OM's ask)" if c.asking_price else ""
            out.append(Flag(
                "recent_sale", MEDIUM, "Pricing", "Property already traded in the last 12 months",
                f"ACRIS shows a deed recorded {deed.recorded} for {_money(deed.amount)}{vs}. The listing may be "
                "stale or a re-trade; either way, this is the most relevant comp for the deal.",
                record_value=f"{_money(deed.amount)} on {deed.recorded}", source="ACRIS",
            ))
        elif c.asking_price:
            out.append(Flag(
                "last_sale", INFO, "Pricing", "Last recorded sale",
                f"Deed recorded {deed.recorded} for {_money(deed.amount)} vs. ask {_money(c.asking_price)}.",
                record_value=_money(deed.amount), source="ACRIS",
            ))
    return out


def rule_tax_class(c: OMClaims, p: PropertyProfile) -> List[Flag]:
    if not c.stated_tax_class or p.assessment is None:
        return []
    om, rec = c.stated_tax_class.upper().replace(" ", ""), p.assessment.tax_class.upper()
    if om == rec:
        return []
    q = c.quote_for("stated_tax_class")
    return [Flag(
        "tax_class", LOW, "Taxes", "Tax class in the OM doesn't match the DOF roll",
        f"OM says Class {om}; DOF has Class {rec}. The class sets the tax rate and whether the 8%/30% "
        "assessment cap applies, so confirm which is right.",
        om_value=om, record_value=rec, source="NYC DOF assessment roll", om_quote=q.text if q else None,
    )]


def rule_overbuilt(c: OMClaims, p: PropertyProfile) -> List[Flag]:
    if not p.lot_area or not p.resid_far or p.built_far <= p.resid_far * 1.10:
        return []
    return [Flag(
        "overbuilt", LOW, "Zoning", "Building is overbuilt for its zoning",
        f"Built FAR {p.built_far:.2f} vs. {p.resid_far:.2f} allowed under {p.zoning}. The building is legal "
        "non-complying: there are no air rights, and if it's substantially destroyed it may not be rebuilt at "
        "today's size. Check insurance (ordinance or law coverage) and the lender's view.",
        record_value=f"FAR {p.built_far:.2f} / {p.resid_far:.2f}", source="NYC MapPLUTO",
    )]


RULES: List[Callable[[OMClaims, PropertyProfile], List[Flag]]] = [
    rule_unit_count, rule_gross_sf, rule_year_built, rule_air_rights, rule_overbuilt,
    rule_rs_status, rule_deregulation_upside, rule_rs_rent_growth, rule_proforma_rs_rents,
    rule_renovation_bump, rule_tax_understated, rule_abatement_expiry, rule_tax_trajectory,
    rule_tax_class, rule_expense_ratio, rule_vacancy, rule_cap_rate_math, rule_violations, rule_basis_context,
]


def run_rules(c: OMClaims, p: PropertyProfile) -> List[Flag]:
    flags: List[Flag] = []
    for rule in RULES:
        flags.extend(rule(c, p))
    # Within a severity, deal-specific findings come before ones most buildings share.
    generic = {"tax_trajectory", "last_sale", "vacancy"}
    flags.sort(key=lambda f: (SEVERITY_ORDER[f.severity], f.rule in generic, f.noi_impact or 0))
    return flags
