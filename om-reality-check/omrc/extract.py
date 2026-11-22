"""Read an offering memorandum PDF and pull out the claims the rules engine checks.

Claude reads the PDF directly (layout, tables and rent rolls included) and returns
JSON validated against `ExtractedOM`. Every number comes back with the exact
OM wording and page it came from, so the report can quote the broker.

Needs Anthropic credentials (ANTHROPIC_API_KEY). Without them, enter claims by
hand in the app or load a JSON file.
"""
from __future__ import annotations

import base64
import os
from typing import List, Optional

from pydantic import BaseModel, Field

from .claims import OMClaims, Quote, Unit

MODEL = os.environ.get("OMRC_MODEL", "claude-opus-5-5")


class ExtractedUnit(BaseModel):
    unit: str
    status: str = Field(description="RS for rent stabilized/regulated, FM for free market, VACANT, or COMM for commercial")
    current_rent: Optional[float] = Field(None, description="Monthly in-place rent")
    proforma_rent: Optional[float] = Field(None, description="Monthly pro forma / projected rent")
    legal_rent: Optional[float] = Field(None, description="DHCR legal regulated rent, if listed")


class ExtractedQuote(BaseModel):
    field: str = Field(description="Name of the field this quote supports")
    text: str = Field(description="Exact wording from the OM, under 40 words")
    page: Optional[int] = None


class ExtractedOM(BaseModel):
    address: Optional[str] = Field(None, description="Street address including borough, e.g. '95 Bergen Street, Brooklyn'")
    asking_price: Optional[float] = None
    stated_cap_rate: Optional[float] = Field(None, description="Headline cap rate as a decimal (5.5% -> 0.055)")
    stated_proforma_cap_rate: Optional[float] = None
    units_res: Optional[int] = None
    units_commercial: Optional[int] = None
    gross_sf: Optional[float] = None
    year_built: Optional[int] = None
    rs_units: Optional[int] = Field(None, description="Number of rent stabilized or regulated units")
    fm_units: Optional[int] = Field(None, description="Number of free market units")
    stated_tax_class: Optional[str] = Field(None, description="NYC tax class the OM states, e.g. '2A', '2B', '2'")
    gross_income_current: Optional[float] = Field(None, description="Annual current gross potential income")
    gross_income_proforma: Optional[float] = None
    vacancy_pct: Optional[float] = Field(None, description="Vacancy & credit loss as a decimal")
    real_estate_taxes: Optional[float] = Field(None, description="Annual real estate taxes in the current/in-place operating statement")
    total_expenses: Optional[float] = Field(None, description="Annual total operating expenses including taxes, current")
    noi_current: Optional[float] = None
    noi_proforma: Optional[float] = None
    rs_rent_growth: Optional[float] = Field(None, description="Annual rent growth assumed for stabilized units, decimal")
    fm_rent_growth: Optional[float] = None
    expense_growth: Optional[float] = None
    claims_deregulation_upside: bool = Field(False, description="True if the OM says stabilized units can be deregulated, destabilized, converted to market, or 'go market' on turnover")
    renovation_rent_bump: Optional[float] = Field(None, description="Monthly rent increase per stabilized unit claimed after renovation/IAI")
    air_rights_sf: Optional[float] = Field(None, description="Unused development rights / air rights claimed, in SF")
    mentions_tax_abatement: bool = Field(False, description="True if the OM mentions 421-a, J-51, or another tax exemption/abatement")
    abatement_expiry_disclosed: bool = Field(False, description="True only if the OM states when the tax benefit ends and models the higher taxes")
    rent_roll: List[ExtractedUnit] = Field(default_factory=list)
    quotes: List[ExtractedQuote] = Field(default_factory=list)


PROMPT = """You are an acquisitions analyst reading a New York City multifamily offering memorandum.
Extract the seller's claims exactly as the OM states them. Do not correct, estimate or infer
numbers the OM doesn't give: leave those fields empty. Use the in-place/current column for
current figures and the pro forma column for pro forma figures.

Include the full rent roll if one exists. Mark a unit RS if it is labeled rent stabilized,
regulated, RS, or similar; FM if free market or market; VACANT if vacant; COMM for retail/commercial.

For each of these fields, if the OM states it, add a quote with the exact wording and page:
asking_price, stated_cap_rate, rs_units, real_estate_taxes, total_expenses, noi_current,
rs_rent_growth, claims_deregulation_upside, renovation_rent_bump, air_rights_sf,
mentions_tax_abatement."""


class ExtractionError(RuntimeError):
    pass


def extract_claims(pdf_bytes: bytes, client=None) -> OMClaims:
    import anthropic

    client = client or anthropic.Anthropic()
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode()
    # Opus 5.5 can decline a request via safety classifiers; the server-side
    # fallback beta retries on another model automatically.
    resp = client.beta.messages.parse(
        model=MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "medium"},
        messages=[{
            "role": "user",
            "content": [
                {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": pdf_b64}},
                {"type": "text", "text": PROMPT},
            ],
        }],
        output_format=ExtractedOM,
    )
    if resp.stop_reason == "refusal":
        raise ExtractionError("The model declined to read this document.")
    if resp.stop_reason == "max_tokens":
        raise ExtractionError("The OM was too long to extract in one pass (output limit reached).")
    data: ExtractedOM = resp.parsed_output
    if data is None:
        raise ExtractionError("Could not parse the extraction result.")
    return to_claims(data)


def to_claims(data: ExtractedOM) -> OMClaims:
    d = data.model_dump()
    rent_roll = [Unit(**u) for u in d.pop("rent_roll")]
    quotes = [Quote(**q) for q in d.pop("quotes")]
    claims = OMClaims(**d)
    claims.rent_roll = rent_roll
    claims.quotes = quotes
    return claims
