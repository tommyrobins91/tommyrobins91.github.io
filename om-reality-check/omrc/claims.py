"""What the offering memorandum says. Every field is optional: OMs vary widely."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import List, Optional


@dataclass
class Unit:
    unit: str
    status: str = "FM"                    # RS (rent stabilized), FM (free market), VACANT, COMM
    current_rent: Optional[float] = None  # monthly
    proforma_rent: Optional[float] = None  # monthly
    legal_rent: Optional[float] = None    # DHCR legal regulated rent, if stated


@dataclass
class Quote:
    field: str
    text: str
    page: Optional[int] = None


@dataclass
class OMClaims:
    address: Optional[str] = None
    source: Optional[str] = None                     # where the OM came from (URL / note)
    bbl: Optional[str] = None
    asking_price: Optional[float] = None
    stated_cap_rate: Optional[float] = None          # decimal, on current NOI unless noted
    stated_proforma_cap_rate: Optional[float] = None
    units_res: Optional[int] = None
    units_commercial: Optional[int] = None
    gross_sf: Optional[float] = None
    year_built: Optional[int] = None
    rs_units: Optional[int] = None
    fm_units: Optional[int] = None
    stated_tax_class: Optional[str] = None

    gross_income_current: Optional[float] = None     # annual potential rent + other income
    gross_income_proforma: Optional[float] = None
    vacancy_pct: Optional[float] = None
    real_estate_taxes: Optional[float] = None
    total_expenses: Optional[float] = None           # incl. taxes
    noi_current: Optional[float] = None
    noi_proforma: Optional[float] = None

    rs_rent_growth: Optional[float] = None           # annual, assumed for stabilized units
    fm_rent_growth: Optional[float] = None
    expense_growth: Optional[float] = None
    claims_deregulation_upside: bool = False         # "units can go to market", "destabilize"
    renovation_rent_bump: Optional[float] = None     # $/mo per RS unit claimed after renovation
    air_rights_sf: Optional[float] = None
    mentions_tax_abatement: bool = False
    abatement_expiry_disclosed: bool = False

    rent_roll: List[Unit] = field(default_factory=list)
    quotes: List[Quote] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "OMClaims":
        names = {f.name for f in fields(cls)}
        kwargs = {k: v for k, v in d.items() if k in names and k not in ("rent_roll", "quotes")}
        if "_source" in d and "source" not in kwargs:
            kwargs["source"] = d["_source"]
        kwargs["rent_roll"] = [Unit(**u) for u in d.get("rent_roll") or []]
        kwargs["quotes"] = [Quote(**q) for q in d.get("quotes") or []]
        return cls(**kwargs)

    # ---- derived -----------------------------------------------------------
    def rs_count(self) -> Optional[int]:
        if self.rent_roll:
            return sum(1 for u in self.rent_roll if u.status == "RS")
        return self.rs_units

    def residential_count(self) -> Optional[int]:
        if self.units_res is not None:
            return self.units_res
        if self.rent_roll:
            return sum(1 for u in self.rent_roll if u.status != "COMM")
        return None

    def egi_current(self) -> Optional[float]:
        if self.gross_income_current is None:
            return None
        return self.gross_income_current * (1 - (self.vacancy_pct or 0))

    def noi_current_or_estimate(self) -> Optional[float]:
        """OM's current NOI, or current EGI minus the OM's own expenses if it only shows pro forma."""
        if self.noi_current is not None:
            return self.noi_current
        egi = self.egi_current()
        if egi is not None and self.total_expenses is not None:
            return egi - self.total_expenses
        return None

    def quote_for(self, field_name: str) -> Optional[Quote]:
        return next((q for q in self.quotes if q.field == field_name), None)
