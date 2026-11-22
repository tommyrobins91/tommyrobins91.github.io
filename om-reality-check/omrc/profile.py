"""Build a `PropertyProfile`: everything the public record says about one lot."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import List, Optional

from . import config
from .nyc_data import DataError, exemption_descriptions, geocode, socrata, split_bbl


def _f(v, default=0.0) -> float:
    try:
        return float(str(v).replace("+", ""))
    except (TypeError, ValueError):
        return default


def _i(v, default=0) -> int:
    return int(_f(v, default))


def tax_rate_for(tax_class: str) -> float:
    return config.TAX_RATES.get((tax_class or "2")[0], config.TAX_RATES["2"])


@dataclass
class Exemption:
    code: str
    program: str
    description: str
    start_year: Optional[int]
    years: Optional[int]
    end_year: Optional[int]
    exempt_av: float
    annual_tax_savings: float
    requires_rs: bool


@dataclass
class Assessment:
    roll_year: int
    tax_class: str
    market_value: float
    actual_av: float
    transitional_av: float
    taxable_av: float
    exempt_av: float
    net_taxable_av: float
    tax_rate: float
    est_annual_tax: float


@dataclass
class Transaction:
    doc_type: str
    recorded: str
    amount: float


@dataclass
class PropertyProfile:
    bbl: str
    address: str
    borough: str
    zoning: str = ""
    bldg_class: str = ""
    lot_area: float = 0
    bldg_area: float = 0
    res_area: float = 0
    com_area: float = 0
    units_res: int = 0
    units_total: int = 0
    year_built: int = 0
    floors: float = 0
    built_far: float = 0
    resid_far: float = 0
    comm_far: float = 0
    facil_far: float = 0
    owner: str = ""
    assessment: Optional[Assessment] = None
    exemptions: List[Exemption] = field(default_factory=list)
    hpd_open: dict = field(default_factory=dict)
    ecb_open_count: int = 0
    ecb_balance_due: float = 0
    last_deed: Optional[Transaction] = None
    mortgages: List[Transaction] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # ---- derived -----------------------------------------------------------
    @property
    def likely_rent_stabilized(self) -> bool:
        return bool(self.rs_reasons)

    @property
    def rs_reasons(self) -> List[str]:
        reasons = []
        if self.units_res >= config.RS_MIN_UNITS and 0 < self.year_built < config.RS_BUILT_BEFORE:
            reasons.append(
                f"{self.units_res} residential units built in {self.year_built} "
                f"(6+ units, pre-1974 buildings are presumptively stabilized)"
            )
        for e in self.exemptions:
            if e.requires_rs:
                reasons.append(f"Receives {e.program} ({e.description}), which requires rent stabilization")
        return reasons

    @property
    def unused_res_far_sf(self) -> float:
        """Unused floor area under the as-of-right residential FAR in PLUTO.

        Approximate: PLUTO's BuiltFAR uses gross building area (not zoning floor
        area), and City of Yes (Dec 2024) bonuses such as UAP are not included.
        """
        max_far = self.resid_far if self.units_res > 0 else max(self.comm_far, self.facil_far)
        return max(0.0, (max_far - self.built_far) * self.lot_area)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["likely_rent_stabilized"] = self.likely_rent_stabilized
        d["rs_reasons"] = self.rs_reasons
        d["unused_res_far_sf"] = self.unused_res_far_sf
        return d


# ---------------------------------------------------------------------------

def _program_for(code: str):
    for name, spec in config.EXEMPTION_PROGRAMS.items():
        if any(code.startswith(p) for p in spec["prefixes"]):
            return name, spec["requires_rs"]
    return None, False


def _load_pluto(p: PropertyProfile):
    rows = socrata("pluto", bbl=p.bbl)
    if not rows:
        p.warnings.append("No PLUTO record for this BBL (condo units and new lots can be missing).")
        return
    r = rows[0]
    p.address = r.get("address") or p.address
    p.zoning = r.get("zonedist1", "")
    p.bldg_class = r.get("bldgclass", "")
    p.lot_area = _f(r.get("lotarea"))
    p.bldg_area = _f(r.get("bldgarea"))
    p.res_area = _f(r.get("resarea"))
    p.com_area = _f(r.get("comarea"))
    p.units_res = _i(r.get("unitsres"))
    p.units_total = _i(r.get("unitstotal"))
    p.year_built = _i(r.get("yearbuilt"))
    p.floors = _f(r.get("numfloors"))
    p.built_far = _f(r.get("builtfar"))
    p.resid_far = _f(r.get("residfar"))
    p.comm_far = _f(r.get("commfar"))
    p.facil_far = _f(r.get("facilfar"))
    p.owner = r.get("ownername", "")


def _load_assessment(p: PropertyProfile):
    rows = socrata("assessment", parid=p.bbl, **{"$order": "year DESC, period DESC", "$limit": 1})
    if not rows:
        p.warnings.append("No DOF assessment record found.")
        return
    r = rows[0]
    tax_class = r.get("curtaxclass") or r.get("pytaxclass") or "2"
    taxable = _f(r.get("curtxbtot"))
    exempt = _f(r.get("curtxbextot"))
    rate = tax_rate_for(tax_class)
    net = max(0.0, taxable - exempt)
    p.assessment = Assessment(
        roll_year=_i(r.get("year")),
        tax_class=tax_class,
        market_value=_f(r.get("curmkttot")),
        actual_av=_f(r.get("curacttot")),
        transitional_av=_f(r.get("curtrntot")),
        taxable_av=taxable,
        exempt_av=exempt,
        net_taxable_av=net,
        tax_rate=rate,
        est_annual_tax=round(net * rate),
    )


def _load_exemptions(p: PropertyProfile):
    rows = socrata("exemptions", parid=p.bbl, **{"$order": "year DESC, period DESC", "$limit": 200})
    if not rows:
        return
    latest = max(_i(r.get("year")) for r in rows)
    descs = exemption_descriptions()
    seen = set()
    rate = p.assessment.tax_rate if p.assessment else config.TAX_RATES["2"]
    for r in rows:
        if _i(r.get("year")) != latest:
            continue
        code = r.get("exmp_code", "")
        if code in seen:
            continue
        seen.add(code)
        program, requires_rs = _program_for(code)
        start = _i(r.get("benftstart")) or None
        years = _i(r.get("no_years")) or None
        exempt_av = _f(r.get("curexmptot"))
        p.exemptions.append(Exemption(
            code=code,
            program=program or "OTHER",
            description=descs.get(code, code),
            start_year=start,
            years=years,
            end_year=(start + years) if (start and years) else None,
            exempt_av=exempt_av,
            annual_tax_savings=round(exempt_av * rate),
            requires_rs=requires_rs,
        ))


def _load_violations(p: PropertyProfile):
    rows = socrata("hpd_violations", bbl=p.bbl, violationstatus="Open",
                   **{"$select": "class, count(*) AS n", "$group": "class"})
    p.hpd_open = {r["class"]: _i(r["n"]) for r in rows if r.get("class")}
    boro, block, lot = split_bbl(p.bbl)
    try:
        ecb = socrata("ecb_violations", boro=str(boro), block=f"{block:05d}", lot=f"{lot:04d}",
                      **{"$select": "ecb_violation_status, balance_due", "$limit": 2000})
    except DataError:
        ecb = []
    active = [r for r in ecb if (r.get("ecb_violation_status") or "").upper() == "ACTIVE"]
    p.ecb_open_count = len(active)
    p.ecb_balance_due = sum(_f(r.get("balance_due")) for r in ecb)


def _load_acris(p: PropertyProfile):
    boro, block, lot = split_bbl(p.bbl)
    legals = socrata("acris_legals", borough=str(boro), block=str(block), lot=str(lot),
                     **{"$select": "document_id", "$limit": 500})
    ids = sorted({r["document_id"] for r in legals})
    if not ids:
        return
    docs = []
    for i in range(0, len(ids), 100):
        chunk = ",".join(f"'{d}'" for d in ids[i:i + 100])
        docs += socrata("acris_master", **{
            "$where": f"document_id in({chunk}) AND doc_type in('DEED','MTGE','AGMT','SAT')",
            "$select": "doc_type, recorded_datetime, document_amt",
            "$limit": 500,
        })
    docs.sort(key=lambda r: r.get("recorded_datetime", ""), reverse=True)
    for r in docs:
        t = Transaction(r["doc_type"], (r.get("recorded_datetime") or "")[:10], _f(r.get("document_amt")))
        if t.doc_type == "DEED" and p.last_deed is None and t.amount > 0:
            p.last_deed = t
        elif t.doc_type in ("MTGE", "AGMT") and len(p.mortgages) < 5 and t.amount > 0:
            p.mortgages.append(t)


def build_profile(address: Optional[str] = None, bbl: Optional[str] = None) -> PropertyProfile:
    if not (address or bbl):
        raise ValueError("Provide an address or a BBL")
    geo = {}
    if not bbl:
        geo = geocode(address)
        bbl = geo["bbl"]
    p = PropertyProfile(bbl=str(bbl), address=geo.get("label") or address or "", borough=geo.get("borough", ""))
    for loader in (_load_pluto, _load_assessment, _load_exemptions, _load_violations, _load_acris):
        try:
            loader(p)
        except DataError as e:
            p.warnings.append(f"{loader.__name__[6:]} data unavailable: {e}")
    return p


def current_fiscal_year(today: Optional[date] = None) -> int:
    today = today or date.today()
    return today.year + 1 if today.month >= 7 else today.year
