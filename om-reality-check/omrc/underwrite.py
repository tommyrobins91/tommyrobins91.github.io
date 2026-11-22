"""Corrected underwriting: legal rent paths, tax projections, adjusted NOI."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

from . import config
from .claims import OMClaims
from .profile import PropertyProfile, current_fiscal_year


# ---------------------------------------------------------------------------
# Rent stabilization
# ---------------------------------------------------------------------------

def rgb_growth_path(years: int, today: Optional[date] = None) -> List[float]:
    """Max one-year renewal increase for each projection year.

    Year 1 uses the RGB order in effect today; later years use the long-run
    forward assumption because those orders have not been voted yet.
    """
    today = today or date.today()
    in_effect = next(
        (o for o in config.RGB_ORDERS if date.fromisoformat(o["lease_start"]) <= today),
        config.RGB_ORDERS[-1],
    )
    return [in_effect["one_year"]] + [config.RGB_FORWARD_ASSUMPTION] * (years - 1)


def max_iai_bump(units_in_building: int, cost: float = config.IAI_CAP_STANDARD) -> float:
    """Max permanent monthly rent increase from an Individual Apartment Improvement."""
    divisor = config.IAI_DIVISOR_SMALL if units_in_building <= 35 else config.IAI_DIVISOR_LARGE
    return min(cost, config.IAI_CAP_ENHANCED) / divisor


# ---------------------------------------------------------------------------
# Taxes
# ---------------------------------------------------------------------------

@dataclass
class TaxYear:
    fiscal_year: int
    taxable_av: float
    exempt_av: float
    tax: float
    note: str = ""


def project_taxes(p: PropertyProfile, years: int = config.DEFAULT_HOLD_YEARS) -> List[TaxYear]:
    """Project property taxes from today's roll, holding the tax rate flat.

    - Capped classes (1, 2A/2B/2C): taxable AV grows up to the 30%-per-5-year cap
      until it reaches actual AV.
    - Other classes (2, 4): the gap between transitional and actual AV phases in
      over 5 years.
    - Exemptions drop off in the fiscal year their benefit period ends.
    Market value is held flat, so this is a conservative-to-neutral path.
    """
    a = p.assessment
    if a is None:
        return []
    fy0 = current_fiscal_year()
    out = []
    capped = a.tax_class.upper() in config.CAPPED_CLASSES
    for t in range(0, years + 1):
        if capped:
            growth = (1 + config.CAP_FIVE_YEAR) ** (t / 5)
            taxable = min(a.actual_av, a.taxable_av * min(growth, (1 + config.CAP_ANNUAL) ** t))
        else:
            gap = a.actual_av - a.taxable_av
            taxable = a.taxable_av + max(gap, 0) * min(1.0, t / 5) if gap > 0 else a.actual_av
        fy = fy0 + t
        exempt = 0.0
        notes = []
        for e in p.exemptions:
            if e.end_year is None or fy < e.end_year:
                exempt += e.exempt_av
            elif fy == e.end_year:
                notes.append(f"{e.program} ends")
        if not p.exemptions:
            exempt = a.exempt_av if t == 0 else 0.0
        exempt = min(exempt, taxable)
        tax = (taxable - exempt) * a.tax_rate
        out.append(TaxYear(fy, round(taxable), round(exempt), round(tax), ", ".join(notes)))
    return out


# ---------------------------------------------------------------------------
# Adjusted NOI
# ---------------------------------------------------------------------------

@dataclass
class ProjectionYear:
    year: int
    rs_income: float
    fm_income: float
    other_income: float
    vacancy: float
    egi: float
    taxes: float
    other_expenses: float
    noi: float


@dataclass
class Underwriting:
    assumptions: dict
    om_noi_current: Optional[float]
    om_noi_proforma: Optional[float]
    adjusted_noi_year1: float
    adjusted_noi_exit: float
    projection: List[ProjectionYear] = field(default_factory=list)
    taxes: List[TaxYear] = field(default_factory=list)
    value_at_om_cap: Optional[float] = None
    adjusted_cap_on_ask: Optional[float] = None
    notes: List[str] = field(default_factory=list)
    adjusted_noi_proforma: Optional[float] = None
    # Which OM figure the headline comparison uses: "current" or "pro forma".
    basis: str = "current"
    om_noi_basis: Optional[float] = None
    adjusted_noi_basis: Optional[float] = None


def _income_split(c: OMClaims, p: PropertyProfile):
    """Return annual (RS, FM, other) gross income for today."""
    if c.rent_roll:
        rs = sum((u.current_rent or 0) for u in c.rent_roll if u.status == "RS") * 12
        fm = sum((u.current_rent or 0) for u in c.rent_roll if u.status in ("FM", "COMM")) * 12
        gross = c.gross_income_current or (rs + fm)
        return rs, fm, max(0.0, gross - rs - fm)
    gross = c.gross_income_current or 0.0
    units = c.residential_count() or p.units_res or 0
    rs_n = c.rs_units if c.rs_units is not None else (units if p.likely_rent_stabilized else 0)
    share = (rs_n / units) if units else 0.0
    return gross * share, gross * (1 - share), 0.0


def expense_floor(rs_share: float) -> float:
    if rs_share > 0.5:
        return config.EXPENSE_RATIO_FLOOR["rs_majority"]
    if rs_share > 0:
        return config.EXPENSE_RATIO_FLOOR["mixed"]
    return config.EXPENSE_RATIO_FLOOR["free_market"]


def underwrite(c: OMClaims, p: PropertyProfile, years: int = config.DEFAULT_HOLD_YEARS) -> Underwriting:
    notes = []
    rs0, fm0, other0 = _income_split(c, p)
    gross0 = rs0 + fm0 + other0
    rs_share = rs0 / gross0 if gross0 else 0.0

    vacancy = c.vacancy_pct if (c.vacancy_pct or 0) >= 0.02 else config.DEFAULT_VACANCY
    if c.vacancy_pct is not None and c.vacancy_pct < 0.02:
        notes.append(f"OM vacancy {c.vacancy_pct:.1%} raised to {vacancy:.0%}.")
    fm_growth = min(c.fm_rent_growth if c.fm_rent_growth is not None else 0.03, 0.03)
    exp_growth = max(c.expense_growth or 0.03, 0.03)
    rs_path = rgb_growth_path(years + 1)

    taxes = project_taxes(p, years)
    tax_by_t = [t.tax for t in taxes] or [c.real_estate_taxes or 0.0] * (years + 1)

    egi0 = gross0 * (1 - vacancy)
    om_opex_ex_tax = None
    if c.total_expenses is not None:
        om_opex_ex_tax = c.total_expenses - (c.real_estate_taxes or 0.0)
    floor = expense_floor(rs_share)
    floor_ex_tax = max(0.0, floor * egi0 - tax_by_t[0])
    if om_opex_ex_tax is None:
        opex0 = floor_ex_tax
        notes.append(f"OM gives no expenses; used {floor:.0%} of EGI floor.")
    elif om_opex_ex_tax < floor_ex_tax:
        opex0 = floor_ex_tax
        notes.append(
            f"OM non-tax expenses ${om_opex_ex_tax:,.0f} raised to ${floor_ex_tax:,.0f} "
            f"so total expenses reach the {floor:.0%} of EGI floor."
        )
    else:
        opex0 = om_opex_ex_tax
    reserve = config.DEFAULT_REPLACEMENT_RESERVE_PER_UNIT * (c.residential_count() or p.units_res or 0)

    proj = []
    rs, fm, other = rs0, fm0, other0
    for t in range(0, years + 1):
        if t > 0:
            rs *= 1 + rs_path[t - 1]
            fm *= 1 + fm_growth
            other *= 1 + fm_growth
        gross = rs + fm + other
        vac = gross * vacancy
        egi = gross - vac
        opex = opex0 * (1 + exp_growth) ** t + reserve
        tax = tax_by_t[min(t, len(tax_by_t) - 1)]
        proj.append(ProjectionYear(t, round(rs), round(fm), round(other), round(vac), round(egi),
                                   round(tax), round(opex), round(egi - opex - tax)))

    y1 = proj[1] if len(proj) > 1 else proj[0]
    uw = Underwriting(
        assumptions={
            "vacancy": vacancy,
            "rs_growth_path": rs_path[:years],
            "fm_growth": fm_growth,
            "expense_growth": exp_growth,
            "expense_floor": floor,
            "rs_income_share": rs_share,
            "replacement_reserve": reserve,
            "tax_rates": config.TAX_RATE_FISCAL_YEAR,
        },
        om_noi_current=c.noi_current,
        om_noi_proforma=c.noi_proforma,
        adjusted_noi_year1=y1.noi,
        adjusted_noi_exit=proj[-1].noi,
        projection=proj,
        taxes=taxes,
        notes=notes,
    )
    # Adjusted pro forma: the OM's stabilized income with stabilized units held
    # to their legal path, plus corrected taxes and expenses.
    pf_gross = _proforma_gross(c, rs_path[0])
    if pf_gross:
        pf_egi = pf_gross * (1 - vacancy)
        tax1 = tax_by_t[min(1, len(tax_by_t) - 1)]
        pf_opex = max(om_opex_ex_tax or 0.0, floor * pf_egi - tax1) + reserve
        uw.adjusted_noi_proforma = round(pf_egi - tax1 - pf_opex)

    # Compare like with like. If the OM gives current NOI, compare current; if it
    # only gives pro forma, compare pro forma. Value at the cap rate the OM's own
    # pricing implies (its NOI / ask).
    if c.noi_current is not None:
        uw.basis, uw.om_noi_basis, uw.adjusted_noi_basis = "current", c.noi_current, y1.noi
    elif c.noi_proforma is not None and uw.adjusted_noi_proforma is not None:
        uw.basis, uw.om_noi_basis, uw.adjusted_noi_basis = "pro forma", c.noi_proforma, uw.adjusted_noi_proforma
    else:
        uw.adjusted_noi_basis = y1.noi
    cap = (uw.om_noi_basis / c.asking_price) if (uw.om_noi_basis and c.asking_price) else c.stated_cap_rate
    if cap:
        uw.assumptions["valuation_cap_rate"] = cap
        uw.value_at_om_cap = round(uw.adjusted_noi_basis / cap)
    if c.asking_price:
        uw.adjusted_cap_on_ask = y1.noi / c.asking_price
    return uw


def _proforma_gross(c: OMClaims, rs_growth_y1: float) -> Optional[float]:
    """Annual pro forma gross income with stabilized units held to legal rents.

    Occupied stabilized units renew at the RGB guideline off today's rent: since
    HSTPA, a preferential rent is the base for renewals for the life of the
    tenancy, so the higher "legal rent" is only reachable on vacancy.
    """
    if c.rent_roll and any(u.proforma_rent for u in c.rent_roll):
        total = om_total = 0.0
        for u in c.rent_roll:
            om_pf = u.proforma_rent or u.current_rent or 0.0
            om_total += om_pf
            if u.status == "RS" and u.current_rent:
                total += min(om_pf, u.current_rent * (1 + rs_growth_y1))
            elif u.status == "RS":
                total += min(om_pf, u.legal_rent or om_pf)
            else:
                total += om_pf
        other = max(0.0, (c.gross_income_proforma or 0.0) - om_total * 12)
        return total * 12 + other
    return c.gross_income_proforma
