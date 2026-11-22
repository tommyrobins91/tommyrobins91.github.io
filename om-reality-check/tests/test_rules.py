"""Offline tests: a hand-built public record, no network."""
from datetime import date

from omrc.analyze import analyze
from omrc.claims import OMClaims, Unit
from omrc.profile import Assessment, Exemption, PropertyProfile, current_fiscal_year
from omrc.underwrite import max_iai_bump, project_taxes, rgb_growth_path


def profile(**kw):
    fy = current_fiscal_year()
    p = PropertyProfile(
        bbl="3000000001", address="1 TEST STREET", borough="Brooklyn", zoning="R6B",
        lot_area=2500, bldg_area=6000, res_area=6000, units_res=8, units_total=8,
        year_built=1910, floors=4, built_far=2.4, resid_far=2.0,
        assessment=Assessment(fy, "2B", 2_500_000, 1_125_000, 230_000, 230_000, 120_000, 110_000, 0.12439, 13_683),
        exemptions=[Exemption("1920", "J51", "J51", 1996, fy - 1996 + 2, fy + 2, 120_000, 14_927, True)],
    )
    for k, v in kw.items():
        setattr(p, k, v)
    return p


def rules_hit(audit):
    return {f.rule for f in audit.flags}


def test_clean_om_has_no_high_flags():
    c = OMClaims(units_res=8, gross_sf=6000, year_built=1910, rs_units=8, real_estate_taxes=14_000,
                 gross_income_current=200_000, vacancy_pct=0.03, total_expenses=100_000,
                 abatement_expiry_disclosed=True)
    a = analyze(c, profile())
    assert not a.high, [f.title for f in a.high]


def test_catches_the_classic_bad_om():
    c = OMClaims(units_res=9, gross_sf=7200, rs_units=2, real_estate_taxes=9_000,
                 gross_income_current=300_000, vacancy_pct=0.01, total_expenses=70_000,
                 rs_rent_growth=0.03, claims_deregulation_upside=True, renovation_rent_bump=800,
                 air_rights_sf=1500)
    hit = rules_hit(analyze(c, profile()))
    for rule in ["unit_count", "gross_sf", "rs_status", "deregulation_upside", "rs_rent_growth",
                 "renovation_bump", "tax_understated", "abatement_expiry", "expense_ratio", "air_rights", "vacancy"]:
        assert rule in hit, rule


def test_rs_status_inferred_from_age_and_units():
    assert profile().likely_rent_stabilized
    assert not profile(units_res=4, exemptions=[]).likely_rent_stabilized
    assert not profile(year_built=1990, exemptions=[]).likely_rent_stabilized


def test_iai_bump_matches_statute():
    assert round(max_iai_bump(20), 2) == round(30_000 / 168, 2)
    assert round(max_iai_bump(50), 2) == round(30_000 / 180, 2)


def test_rgb_path_uses_order_in_effect():
    assert rgb_growth_path(3, today=date(2026, 11, 22))[0] == 0.0     # Order 58 freeze
    assert rgb_growth_path(3, today=date(2026, 1, 15))[0] == 0.03     # Order 57


def test_tax_projection_drops_exemption_and_respects_cap():
    taxes = project_taxes(profile())
    assert taxes[0].exempt_av > 0
    assert any(t.exempt_av == 0 for t in taxes)
    # Class 2B cap: at most +30% taxable AV over 5 years
    assert taxes[5].taxable_av <= 230_000 * 1.30 + 1


def test_pro_forma_rs_rent_over_legal_max_is_flagged():
    c = OMClaims(units_res=8, rent_roll=[Unit("1", "RS", 1500, 3000), Unit("2", "FM", 3000, 3200)])
    assert "proforma_rs_rents" in rules_hit(analyze(c, profile()))


def test_preferential_rent_cannot_jump_to_legal_on_renewal():
    c = OMClaims(units_res=8, rs_units=8,
                 rent_roll=[Unit("4L", "RS", current_rent=1167, proforma_rent=1406, legal_rent=1406)])
    flag = next(f for f in analyze(c, profile()).flags if f.rule == "proforma_rs_rents")
    assert "preferential" in flag.detail
    assert round(flag.noi_impact) == -(1406 - 1167) * 12  # Order 58 = 0% renewal


def test_headline_cap_on_pro_forma_is_called_out():
    c = OMClaims(asking_price=2_150_000, stated_cap_rate=0.0781, noi_proforma=168_062, gross_income_proforma=229_929,
                 gross_income_current=162_516, vacancy_pct=0.03, total_expenses=54_969)
    a = analyze(c, profile())
    assert "cap_rate_basis" in rules_hit(a)
    assert a.uw.basis == "pro forma"


def test_recent_sale_is_flagged():
    from omrc.profile import Transaction
    recent = date.today().replace(day=1).isoformat()
    a = analyze(OMClaims(asking_price=2_400_000), profile(last_deed=Transaction("DEED", recent, 2_200_000)))
    assert "recent_sale" in rules_hit(a)


def test_partial_free_market_claim_asks_for_dhcr_history():
    c = OMClaims(units_res=8, rs_units=5)
    assert "rs_verify" in rules_hit(analyze(c, profile()))
