"""Regulatory constants and market benchmarks.

Every number here is a policy or market input that changes over time. Each one
carries its source so a reviewer can check it, and the rules engine cites these
sources in the report it produces. Update this file when the city or state
changes a rule; no other module hard-codes policy numbers.
"""
from __future__ import annotations

# --- NYC property tax rates (per $1 of taxable assessed value) ---------------
# FY2026 (Jul 2025 - Jun 2026) final rates, revised by City Council Oct 29, 2025.
# Source: NYC Dept. of Finance, "Property Tax Rates"
#   https://www.nyc.gov/site/finance/property/property-tax-rates.page
TAX_RATE_FISCAL_YEAR = "FY2026 (final)"
TAX_RATES = {
    "1": 0.19843,
    "2": 0.12439,
    "3": 0.11108,
    "4": 0.10848,
}

# Class 2 sub-classes 2A/2B/2C (4-10 units) and Class 1 have assessment caps:
# taxable AV can rise at most 8%/yr and 30% over 5 yrs. Larger Class 2 and Class 4
# phase market-value changes in over 5 years via "transitional" AV.
CAPPED_CLASSES = {"1", "1A", "1B", "1C", "1D", "2A", "2B", "2C"}
CAP_ANNUAL = 0.08
CAP_FIVE_YEAR = 0.30

# --- Rent Guidelines Board (rent-stabilized renewal increases) ---------------
# Source: RGB Order #57 (leases 10/1/2025-9/30/2026) and Order #58
# (leases 10/1/2026-9/30/2027, adopted June 25, 2026).
#   https://rentguidelinesboard.cityofnewyork.us/2026-27-apartment-loft-order-58/
RGB_ORDERS = [
    {"order": 58, "lease_start": "2026-10-01", "one_year": 0.000, "two_year": 0.000},
    {"order": 57, "lease_start": "2025-10-01", "one_year": 0.030, "two_year": 0.045},
    {"order": 56, "lease_start": "2024-10-01", "one_year": 0.0275, "two_year": 0.0525},
]
# Long-run average one-year guideline used for forward years we cannot know.
# Orders 52-58 one-year guidelines averaged ~2.0%.
RGB_FORWARD_ASSUMPTION = 0.020

# --- Rent stabilization coverage heuristics ---------------------------------
# Buildings with 6+ residential units built before Jan 1, 1974 are presumptively
# covered by the Emergency Tenant Protection Act / Rent Stabilization Law.
RS_MIN_UNITS = 6
RS_BUILT_BEFORE = 1974

# HSTPA (June 14, 2019) ended high-rent vacancy deregulation and the 20% vacancy
# bonus, and limited IAI increases. The FY2025 state budget (eff. Oct 17, 2024)
# raised the IAI cap to $30,000 per 15 years ($50,000 for units occupied 25+ yrs
# or registered vacant in 2022-2023/24). Increase = 1/168 (<=35 units) or
# 1/180 (>35 units) of cost, permanent.
# Source: NYS HCR Operational Bulletin 2024-2 and Fact Sheet #26.
#   https://hcr.ny.gov/apartment-iai-and-building-mci-improvements
HSTPA_DATE = "2019-06-14"
IAI_CAP_STANDARD = 30_000
IAI_CAP_ENHANCED = 50_000
IAI_DIVISOR_SMALL = 168  # buildings with 35 or fewer units
IAI_DIVISOR_LARGE = 180

# --- Exemption programs that imply / affect rent regulation -----------------
# DOF exemption code prefixes. Full descriptions are fetched live from NYC Open
# Data "Exemption Classification Codes" (myn9-hwsy); these prefixes tell the
# rules engine which programs matter for underwriting.
EXEMPTION_PROGRAMS = {
    "J51": {"prefixes": ["1920"], "requires_rs": True},
    "421A": {"prefixes": ["5110", "5113", "5114", "5116", "5117", "5118",
                          "5119", "5120", "5121", "5122", "5123"], "requires_rs": True},
    "421G": {"prefixes": ["1925"], "requires_rs": True},
    "467M": {"prefixes": ["5124", "5125", "5126", "5127", "5128", "5131"], "requires_rs": False},
    "485X": {"prefixes": ["5132", "5133", "5134", "5135", "5136", "5137"], "requires_rs": True},
    "420C": {"prefixes": ["1301"], "requires_rs": False},
    "ICIP": {"prefixes": ["1988"], "requires_rs": False},
}

# --- Operating expense benchmarks -------------------------------------------
# RGB Income & Expense Study (2026, covering calendar-2024 RPIE filings):
# citywide unadjusted cost-to-income ratio 63.6%; 66.3% for buildings that are
# 100% rent stabilized. Buyers' underwriting typically lands below RPIE-reported
# ratios (management fees, owner-specific costs), so we flag OMs that are more
# than FLAG_GAP points below a size/regulation-adjusted floor.
# Source: https://rentguidelinesboard.cityofnewyork.us/wp-content/uploads/2026/03/2026-IE-Study-Final.pdf
RGB_COST_TO_INCOME_ALL = 0.636
RGB_COST_TO_INCOME_100_RS = 0.663
# Conservative floors a lender/buyer would accept (opex / EGI).
EXPENSE_RATIO_FLOOR = {
    "rs_majority": 0.45,   # >50% of units rent stabilized
    "mixed": 0.38,
    "free_market": 0.32,
}
EXPENSE_FLAG_GAP = 0.05

# --- Underwriting defaults ---------------------------------------------------
DEFAULT_HOLD_YEARS = 5
DEFAULT_VACANCY = 0.03            # RS buildings in NYC run ~1-3% physical vacancy
DEFAULT_REPLACEMENT_RESERVE_PER_UNIT = 300
TOLERANCE_PCT = 0.05              # mismatch tolerance for SF / tax checks
