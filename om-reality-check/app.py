"""OM Reality Check: Streamlit front end.

Run:  .venv/bin/streamlit run app.py
"""
from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from omrc import config
from omrc.analyze import analyze
from omrc.claims import OMClaims, Unit
from omrc.nyc_data import DataError
from omrc.profile import build_profile
from omrc.report import to_markdown

SAMPLE = Path(__file__).parent / "samples" / "sample_95_bergen.json"
BLUE, ORANGE, INK_MUTED = "#2a78d6", "#eb6834", "#52514e"
SEV_STYLE = {
    "high": ("🔴", "High"),
    "medium": ("🟠", "Medium"),
    "low": ("🟡", "Low"),
    "info": ("🔵", "Info"),
}

st.set_page_config(page_title="OM Reality Check", page_icon="🏢", layout="wide")


def money(x):
    return "n/a" if x is None else (f"-${-x:,.0f}" if x < 0 else f"${x:,.0f}")


def signed(x):
    """'-$34,958' so Streamlit colors the delta red/green correctly."""
    return f"-${abs(x):,.0f}" if x < 0 else f"+${x:,.0f}"


def md(text, target=None):
    """Markdown with literal dollar signs (Streamlit treats $...$ as LaTeX)."""
    (target or st).markdown(text.replace("$", r"\$"))


def short(x):
    if x is None:
        return "n/a"
    if abs(x) >= 1e6:
        return f"${x / 1e6:,.2f}M"
    return f"${x / 1e3:,.0f}k" if abs(x) >= 1e4 else f"${x:,.0f}"


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("🏢 OM Reality Check")
    st.caption("Audit a NYC multifamily offering memorandum against public records and current rent and tax law.")
    st.markdown(
        "**Checks against**\n"
        "- MapPLUTO (units, SF, year built, zoning)\n"
        "- DOF assessment roll and exemptions (421-a, J-51)\n"
        "- HPD and DOB/ECB violations\n"
        "- ACRIS deeds and mortgages\n"
        "- RGB Orders #57-58, HSTPA 2019, IAI caps\n"
        "- RGB Income & Expense Study benchmarks"
    )
    st.caption(f"Tax rates: {config.TAX_RATE_FISCAL_YEAR}. Not an appraisal, legal or zoning opinion.")

# ---------------------------------------------------------------------------
# Step 1: get claims
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Case studies: real OMs, run live against city data
# ---------------------------------------------------------------------------
EXAMPLES_DIR = Path(__file__).parent / "samples"
CASES = sorted((EXAMPLES_DIR / "real_oms").glob("*.json")) + [SAMPLE]


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def run_case(path_str: str):
    claims = OMClaims.from_dict(json.loads(Path(path_str).read_text()))
    return analyze(claims)


st.title("OM Reality Check")
st.markdown("Broker OMs are marketing documents. This tool checks one against NYC public records "
            "and current rent and tax law, flags what doesn't hold up, and rebuilds the NOI.")
st.header("Case studies")
st.caption("Three real Brooklyn offering memoranda posted publicly by a broker, plus one fictional OM. "
           "Each row is audited live against city data.")

with st.spinner("Auditing the case studies against NYC data..."):
    cases = []
    for path in CASES:
        try:
            cases.append((path, run_case(str(path))))
        except (DataError, ValueError) as e:
            st.warning(f"{path.name}: {e}")

rows = []
for path, au in cases:
    top = next((f for f in au.flags if f.severity in ("high", "medium")), None)
    rows.append({
        "Building": au.profile.address.title(),
        "OM": "Fictional" if path == SAMPLE else "Real (public PDF)",
        "Grade": au.grade,
        "Flags (high/med)": f"{len(au.high)} / {len(au.medium)}",
        f"OM NOI": money(au.uw.om_noi_basis),
        "Adjusted NOI": money(au.uw.adjusted_noi_basis),
        "Ask": short(au.claims.asking_price),
        "Value at OM's cap": short(au.uw.value_at_om_cap),
        "Top finding": top.title if top else "Clean",
    })
st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

cols = st.columns(len(cases) or 1)
for col, (path, au) in zip(cols, cases):
    label = au.profile.address.title().replace(" Street", " St").replace(" Avenue", " Ave")
    if col.button(f"Open {label}", key=f"open_{path.stem}", use_container_width=True):
        st.session_state.claims = au.claims
        st.session_state.audit = au
        st.session_state.scroll_to_report = True

# Deep link: ?case=721_henry_st opens that case study directly.
qcase = st.query_params.get("case")
if qcase and st.session_state.get("opened_case") != qcase:
    match = next(((pth, au) for pth, au in cases if pth.stem == qcase), None)
    if match:
        st.session_state.claims, st.session_state.audit = match[1].claims, match[1]
        st.session_state.opened_case = qcase
        st.session_state.scroll_to_report = True

# ---------------------------------------------------------------------------
# Step 1: your own OM
# ---------------------------------------------------------------------------
st.header("1 · Or audit your own OM")
tab_pdf, tab_manual = st.tabs(["Upload OM PDF", "Enter / import manually"])

with tab_pdf:
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    key = None if has_key else st.text_input(
        "Anthropic API key (used only for this session)", type="password",
        help="Claude reads the PDF and extracts the broker's claims with page-cited quotes.")
    pdf = st.file_uploader("Offering memorandum (PDF)", type=["pdf"])
    if pdf and st.button("Extract claims", type="primary"):
        from omrc.extract import ExtractionError, extract_claims
        import anthropic
        try:
            with st.spinner("Claude is reading the OM..."):
                client = anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()
                st.session_state.claims = extract_claims(pdf.getvalue(), client=client)
                st.session_state.pop("audit", None)
            st.success("Claims extracted. Review them below before running the audit.")
        except (ExtractionError, anthropic.APIError) as e:
            st.error(f"Extraction failed: {e}")

with tab_manual:
    up = st.file_uploader("Import claims JSON", type=["json"], key="json_up")
    if up and st.button("Load JSON"):
        st.session_state.claims = OMClaims.from_dict(json.load(up))
        st.session_state.pop("audit", None)
    if st.button("Start blank"):
        st.session_state.claims = OMClaims()
        st.session_state.pop("audit", None)

claims: OMClaims = st.session_state.get("claims")
if claims is None:
    st.info("Open a case study above, or load an OM.")
    st.stop()

# ---------------------------------------------------------------------------
# Step 2: review claims
# ---------------------------------------------------------------------------
st.header("2 · Review what the OM claims")
st.caption("Edit anything the extraction got wrong. Leave a field at 0 or blank if the OM doesn't say.")


def num(label, value, fmt="%.0f", step=1.0, help=None):
    v = st.number_input(label, value=float(value or 0), step=step, format=fmt, help=help)
    return v or None


with st.form("claims_form"):
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        address = st.text_input("Address (with borough)", claims.address or "")
        bbl = st.text_input("BBL (optional, overrides address)", claims.bbl or "")
        asking = num("Asking price", claims.asking_price, step=50_000.0)
        cap = num("Stated cap rate", claims.stated_cap_rate, fmt="%.4f", step=0.0025)
    with c2:
        units = num("Residential units", claims.units_res)
        rs_units = st.number_input("Rent-stabilized units", value=int(claims.rs_units or 0), step=1)
        gsf = num("Gross SF", claims.gross_sf, step=100.0)
        yb = num("Year built", claims.year_built)
    with c3:
        gpi = num("Gross income (current, annual)", claims.gross_income_current, step=1000.0)
        vac = num("Vacancy & credit loss", claims.vacancy_pct, fmt="%.3f", step=0.005)
        taxes = num("Real estate taxes", claims.real_estate_taxes, step=500.0)
        opex = num("Total expenses (incl. taxes)", claims.total_expenses, step=1000.0)
    with c4:
        noi = num("NOI (current)", claims.noi_current, step=1000.0)
        noi_pf = num("NOI (pro forma)", claims.noi_proforma, step=1000.0)
        rs_g = num("RS rent growth / yr", claims.rs_rent_growth, fmt="%.3f", step=0.005)
        reno = num("Renovation bump per RS unit ($/mo)", claims.renovation_rent_bump, step=25.0)
    c5, c6, c7 = st.columns(3)
    with c5:
        dereg = st.checkbox("OM claims RS units can go to market", claims.claims_deregulation_upside)
        abat = st.checkbox("OM discloses when tax abatement ends", claims.abatement_expiry_disclosed)
    with c6:
        air = num("Air rights claimed (SF)", claims.air_rights_sf, step=100.0)
    with c7:
        fm_g = num("Free-market rent growth / yr", claims.fm_rent_growth, fmt="%.3f", step=0.005)

    st.markdown("**Rent roll** (optional; status RS / FM / VACANT / COMM, rents monthly)")
    rr = pd.DataFrame([u.__dict__ for u in claims.rent_roll]) if claims.rent_roll else pd.DataFrame(
        columns=["unit", "status", "current_rent", "proforma_rent", "legal_rent"])
    rr = st.data_editor(rr, num_rows="dynamic", use_container_width=True,
                        column_config={"status": st.column_config.SelectboxColumn(
                            options=["RS", "FM", "VACANT", "COMM"])})
    run = st.form_submit_button("Run audit", type="primary")

if run:
    units_list = []
    for r in rr.to_dict("records"):
        if not r.get("unit") or pd.isna(r.get("unit")):
            continue
        clean = {k: (None if (isinstance(v, float) and pd.isna(v)) else v) for k, v in r.items()}
        units_list.append(Unit(unit=str(clean["unit"]), status=clean.get("status") or "FM",
                               current_rent=clean.get("current_rent"), proforma_rent=clean.get("proforma_rent"),
                               legal_rent=clean.get("legal_rent")))
    # Start from the loaded claims so fields the form doesn't show (pro forma income,
    # tax class, quotes...) survive the edit.
    claims = dataclasses.replace(
        claims,
        address=address or None, bbl=bbl or None, asking_price=asking, stated_cap_rate=cap,
        units_res=int(units) if units else None, rs_units=int(rs_units) if (rs_units or not units_list) else None,
        gross_sf=gsf, year_built=int(yb) if yb else None, gross_income_current=gpi, vacancy_pct=vac,
        real_estate_taxes=taxes, total_expenses=opex, noi_current=noi, noi_proforma=noi_pf,
        rs_rent_growth=rs_g, fm_rent_growth=fm_g, renovation_rent_bump=reno, air_rights_sf=air,
        claims_deregulation_upside=dereg, abatement_expiry_disclosed=abat, rent_roll=units_list,
    )
    st.session_state.claims = claims
    if not (claims.address or claims.bbl):
        st.error("Enter an address or BBL.")
        st.stop()
    try:
        with st.spinner("Pulling NYC public records..."):
            profile = build_profile(address=claims.address, bbl=claims.bbl)
        st.session_state.audit = analyze(claims, profile)
    except (DataError, ValueError) as e:
        st.error(str(e))
        st.stop()

audit = st.session_state.get("audit")
if audit is None:
    st.stop()

# ---------------------------------------------------------------------------
# Step 3: report
# ---------------------------------------------------------------------------
a, c, p, uw = audit, audit.claims, audit.profile, audit.uw
st.header(f"3 · Reality check: {p.address}")
st.caption(f"BBL {p.bbl} · {p.borough} · {p.bldg_class} · zoning {p.zoning}")
if c.source:
    st.caption(f"OM source: {c.source}")
if st.session_state.pop("scroll_to_report", False):
    import streamlit.components.v1 as components
    components.html("""<script>
      const h=[...window.parent.document.querySelectorAll('h2')].find(x=>x.innerText.includes('Reality check'));
      if(h) h.scrollIntoView({behavior:'smooth'});
    </script>""", height=0)

m1, m2, m3, m4 = st.columns(4)
m1.metric(f"Grade · {len(a.high)} high, {len(a.medium)} medium", a.grade)
om_noi = uw.om_noi_basis
m2.metric(f"Adjusted NOI ({uw.basis})", short(uw.adjusted_noi_basis),
          None if om_noi is None else f"{signed(uw.adjusted_noi_basis - om_noi)} vs OM", delta_color="normal")
m3.metric("Value at OM cap", short(uw.value_at_om_cap),
          None if a.price_gap is None else f"{signed(-a.price_gap)} vs ask", delta_color="normal")
cur = c.noi_current_or_estimate()
om_cap = f" (OM: {cur / c.asking_price:.2%})" if (c.asking_price and cur) else ""
m4.metric(f"In-place cap, adjusted{om_cap}",
          "n/a" if uw.adjusted_cap_on_ask is None else f"{uw.adjusted_cap_on_ask:.2%}")

left, right = st.columns([3, 2])
with left:
    st.subheader("Red flags")
    if not a.flags:
        st.success("No issues found against the public record.")
    for f in a.flags:
        icon, label = SEV_STYLE[f.severity]
        with st.expander(f"{icon} **{label}** · {f.title}", expanded=f.severity == "high"):
            md(f.detail)
            cols = st.columns(3)
            if f.om_value:
                md(target=cols[0], text=f"**OM:** {f.om_value}")
            if f.record_value:
                md(target=cols[1], text=f"**Record:** {f.record_value}")
            if f.noi_impact:
                md(target=cols[2], text=f"**NOI impact:** {money(f.noi_impact)}/yr")
            if f.om_quote:
                md(f"> OM says: *“{f.om_quote}”*")
            if f.source:
                st.caption(f"Source: {f.source}")

with right:
    st.subheader("Public record")
    md(
        f"- **{p.units_res}** residential units · **{p.bldg_area:,.0f}** SF · built **{p.year_built}**\n"
        f"- Lot {p.lot_area:,.0f} SF · built FAR {p.built_far:.2f} / allowed {p.resid_far:.2f}\n"
        f"- Owner: {p.owner}"
    )
    if p.likely_rent_stabilized:
        st.warning(("**Likely rent stabilized:** " + "; ".join(p.rs_reasons)).replace("$", r"\$"))
    if p.assessment:
        s = p.assessment
        md(f"- FY{s.roll_year} class **{s.tax_class}** · market value {money(s.market_value)} · "
                    f"est. tax **{money(s.est_annual_tax)}**")
    for e in p.exemptions:
        md(f"- {e.program} ({e.description}) {e.start_year}-{e.end_year} · saves ~{money(e.annual_tax_savings)}/yr")
    hpd = sum(p.hpd_open.values())
    md(f"- Open HPD violations: {hpd} (class C: {p.hpd_open.get('C', 0)}) · active ECB: {p.ecb_open_count}")
    if p.last_deed:
        md(f"- Last deed: {p.last_deed.recorded}, {money(p.last_deed.amount)}")
    if p.mortgages:
        m = p.mortgages[0]
        md(f"- Latest mortgage doc: {m.doc_type} {m.recorded}, {money(m.amount)}")
    for w in p.warnings:
        st.caption(f"⚠️ {w}")

    if uw.taxes:
        st.subheader("Projected property taxes")
        tdf = pd.DataFrame([{"Fiscal year": f"FY{t.fiscal_year}", "Tax": t.tax, "Note": t.note} for t in uw.taxes])
        chart = alt.Chart(tdf).mark_bar(color=BLUE, cornerRadiusTopLeft=4, cornerRadiusTopRight=4, size=28).encode(
            x=alt.X("Fiscal year:N", axis=alt.Axis(labelAngle=0, title=None)),
            y=alt.Y("Tax:Q", axis=alt.Axis(format="$,.0f", title=None, grid=True, gridOpacity=0.3)),
            tooltip=[alt.Tooltip("Fiscal year:N"), alt.Tooltip("Tax:Q", format="$,.0f"), alt.Tooltip("Note:N")],
        ).properties(height=220)
        st.altair_chart(chart, use_container_width=True)
        st.caption("Flat tax rate; assessment phase-in and exemption roll-off from the DOF roll.")

st.subheader("NOI: OM vs adjusted")
rows = [{"Year": y.year, "Series": "Adjusted", "NOI": y.noi} for y in uw.projection]
if c.noi_current is not None and c.noi_proforma is not None:
    n = len(uw.projection) - 1
    for y in range(n + 1):  # straight-line the OM from current to pro forma
        rows.append({"Year": y, "Series": "OM", "NOI": c.noi_current + (c.noi_proforma - c.noi_current) * y / n})
ndf = pd.DataFrame(rows)
line = alt.Chart(ndf).mark_line(strokeWidth=2, point=alt.OverlayMarkDef(size=64, filled=True)).encode(
    x=alt.X("Year:O", axis=alt.Axis(labelAngle=0)),
    y=alt.Y("NOI:Q", axis=alt.Axis(format="$,.0f", title=None, gridOpacity=0.3), scale=alt.Scale(zero=False)),
    color=alt.Color("Series:N", scale=alt.Scale(domain=["Adjusted", "OM"], range=[BLUE, ORANGE]),
                    legend=alt.Legend(orient="top", title=None)),
    tooltip=[alt.Tooltip("Series:N"), alt.Tooltip("Year:O"), alt.Tooltip("NOI:Q", format="$,.0f")],
).properties(height=260)
st.altair_chart(line, use_container_width=True)
if c.noi_current is not None and c.noi_proforma is not None:
    st.caption("OM line straight-lines its current NOI to its pro forma NOI.")

with st.expander("Adjusted 5-year projection and assumptions"):
    st.dataframe(pd.DataFrame([y.__dict__ for y in uw.projection]).set_index("year"), use_container_width=True)
    st.json(uw.assumptions)
    for note in uw.notes:
        st.caption(note)

st.download_button("Download memo (Markdown)", to_markdown(a), file_name=f"om_reality_check_{p.bbl}.md")
st.download_button("Download claims (JSON)", json.dumps(c.to_dict(), indent=2), file_name="om_claims.json")
