"""Build the portfolio site.

Run `python3 build.py` from the repo root. It writes index.html and
projects/<slug>.html from the PROJECTS list below and the case study
bodies in content/<slug>.html. Edit those, not the generated pages.

Writing rules: no em dashes, plain tone. Never publish owner names,
target lists, deal figures, loan data or ACG addresses.
"""

from html import escape
from pathlib import Path

ROOT = Path(__file__).parent
GH = "https://github.com/tommyrobins91"
SITE = "https://tommyrobins91.github.io"

CATEGORIES = [
    ("tools", "Data tools and automation",
     "Tools that replace a manual step in sourcing, market tracking or asset management."),
    ("research", "Investment research and underwriting",
     "Valuation, acquisitions and market research work, with the confidential numbers left out."),
    ("schack", "NYU Schack coursework",
     "Selected work from the MS in Real Estate, Real Estate Finance and Investment."),
]

# Order inside each category is the order shown on the site.
PROJECTS = [
    dict(slug="muskoka", cat="tools", feature=True,
         title="Muskoka Development Pipeline", date="October 2026", year="2026",
         blurb="Every planning application and building permit across Muskoka, Ontario on one map. "
               "The data was split across six municipalities and a district GIS, and no paid tracker covered it.",
         short="Planning applications and permits across six Ontario townships on one map",
         tags=["JavaScript", "ArcGIS REST", "Excel export"],
         demo=f"{SITE}/Muskoka-Dev-Pipeline/", repo=f"{GH}/Muskoka-Dev-Pipeline",
         img="muskoka.png"),
    dict(slug="distress-monitor", cat="tools",
         title="Florida industrial distress monitor", date="November 2026", year="2026",
         blurb="Scores private industrial owners on how likely they are to sell, using CMBS loan tapes, "
               "clerk of court records and parcel data, so off-market outreach starts with the best targets.",
         short="Ranks private industrial owners by likelihood to sell",
         tags=["Python", "Public records", "CMBS data"],
         repo=f"{GH}/Florida-Distress-Monitor", private=True,
         demo="demos/distress-monitor/index.html", img="distress-monitor.png", sample=True),
    dict(slug="sourcing-pipeline", cat="tools",
         title="Off-market sourcing pipeline", date="July 2026", year="2026",
         blurb="Turns a raw Reonomy export of 1,000+ properties into a filtered, CRM-ready call list of "
               "mom-and-pop owners. Run on Plant City, Lakeland, Orlando, Tampa and Jacksonville.",
         short="Reonomy export to a filtered, CRM-ready call list",
         tags=["Python", "pandas", "Airtable"],
         repo=f"{GH}/Off-Market-Sourcing-Pipeline", private=True,
         demo="demos/sourcing-pipeline/index.html", img="sourcing-pipeline.png", sample=True),
    dict(slug="multifamily", cat="tools",
         title="Multifamily rent roll monitor", date="October 2026", year="2026",
         blurb="Occupancy, loss-to-lease, unit mix and lease rollover across a 5-property, 240-unit portfolio, "
               "filterable by property. It found 68% of leases expiring within 12 months.",
         short="Occupancy, loss-to-lease and rollover dashboard for 240 units",
         tags=["JavaScript", "pandas", "Asset management"],
         demo=f"{SITE}/Multifamily-Rent-Roll-Monitor/", repo=f"{GH}/Multifamily-Rent-Roll-Monitor",
         img="multifamily.png"),
    dict(slug="reit-research", cat="research",
         title="Digital infrastructure REIT research", date="October 2026", year="2026",
         blurb="Sector coverage of AMT, EQIX and DLR for the NYU Schack REIT Fund. My Equinix pitch, valued on "
               "NAV, FFO/AFFO, DDM and DCF, was approved by the Investment Committee.",
         short="AMT, EQIX and DLR coverage; EQIX pitch approved by the IC",
         tags=["Valuation", "REITs", "Excel"],
         repo=f"{GH}/Digital-Infrastructure-REIT-Research",
         demo="demos/reit-valuation/index.html", img="reit-research.png", sample=True),
    dict(slug="underwriting", cat="research",
         title="Industrial acquisitions underwriting", date="2026", year="2026",
         blurb="50+ value-add industrial deals underwritten across Florida on a 39-tab acquisitions model, "
               "plus the scripts I built to repair, document and present the models faster.",
         short="50+ value-add industrial deals on a 39-tab model",
         tags=["Excel", "Python", "Acquisitions"],
         repo=f"{GH}/Industrial-Acquisitions-Underwriting", private=True,
         demo="demos/underwriting/index.html", img="underwriting.png", sample=True),
    dict(slug="northmark", cat="research",
         title="Northmark Intelligence", date="2026", year="2026",
         blurb="A Toronto research venture producing Canadian commercial real estate research for private "
               "equity clients: a GTA market brief, an AI adoption strategy deck and a residential comp tracker.",
         short="Canadian CRE research venture for private equity clients",
         tags=["Market research", "Strategy", "Canada"],
         repo=f"{GH}/tommyrobins91/tree/main/projects/northmark-intelligence", private=True,
         demo="demos/northmark-comps/index.html", img="northmark.png", sample=True),
    dict(slug="state-population", cat="schack",
         title="U.S. state population explorer", date="October 2026", year="2026",
         blurb="One CSV in, a full census briefing out. Every view moves together through 235 years of state "
               "growth, and the page rebuilds itself from any file in the same format.",
         short="One CSV in, an interactive census briefing out",
         tags=["JavaScript", "Census data", "NYU Schack"],
         demo="demos/state-population/", img="state-population.png"),
    dict(slug="schack-coursework", cat="schack",
         title="Development and finance coursework", date="2025 to 2027", year="2025-27",
         blurb="Transit-oriented development in Jamaica, Queens, an office-to-residential conversion on "
               "East 42nd Street, a CMBS investment committee memo, the StuyTown case and more.",
         short="Development, capital markets and valuation projects",
         tags=["Development", "Capital markets", "Valuation"],
         repo=f"{GH}/tommyrobins91/tree/main/projects/schack-development-coursework",
         img="coursework.png"),
]

# Projects shown on the site, in this order. Every entry in PROJECTS stays
# defined so a project can be brought back by adding its slug here.
SHOW = ["muskoka", "multifamily", "distress-monitor"]
ALL_PROJECTS = PROJECTS
PROJECTS = [p for slug in SHOW for p in ALL_PROJECTS if p["slug"] == slug]

TOOLS = [
    ("Modeling", ["Excel (DCF, NAV, FFO/AFFO, debt sizing)", "ARGUS Enterprise"]),
    ("Data", ["CoStar", "Reonomy", "Bloomberg", "Trepp", "Green Street", "County public records"]),
    ("Build", ["Python (pandas, openpyxl)", "JavaScript", "ArcGIS REST", "Airtable",
               "Claude for research and build work"]),
]

FOOT_NOTE = "Owner names, deal figures and client data are removed. Public demos use public records or sample data."


def page(title, desc, body, prefix=""):
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title>
<meta name="description" content="{escape(desc)}">
<meta property="og:title" content="{escape(title)}"><meta property="og:description" content="{escape(desc)}"><meta property="og:type" content="website">
<link rel="icon" href="{prefix}favicon.svg" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{prefix}style.css">
</head><body>
<header class="nav"><div class="wrap navin"><a class="brand" href="{prefix}index.html"><b>Tommy Robins</b> <span>Real Estate Data Tools</span></a>
<nav><a href="{prefix}index.html#projects">Projects</a><a href="{prefix}index.html#approach">Approach</a><a href="{prefix}index.html#tools">Tools</a><a href="{GH}" target="_blank" rel="noopener">GitHub</a></nav></div></header>
{body}
<footer><div class="wrap foot"><span><b>Tommy Robins</b> · New York, NY</span>
<span>{FOOT_NOTE}</span></div></footer>
</body></html>
"""


def ext(url):
    return "" if url.startswith(("demos/", "../")) else ' target="_blank" rel="noopener"'


def visual(p, prefix="", wide=False):
    w = " wide" if wide else ""
    if p.get("img"):
        return (f'<div class="shot{w}"><img src="{prefix}img/{p["img"]}" '
                f'alt="{escape(p["title"])} screenshot" loading="lazy"></div>')
    big, lab, sub = p["stat"]
    return (f'<div class="shot stat{w}"><div class="big">{big}</div>'
            f'<div class="lab">{escape(lab)}</div><div class="sub">{escape(sub)}</div></div>')


def demo_link(p, prefix=""):
    if not p.get("demo"):
        return ""
    url = p["demo"] if p["demo"].startswith("http") else prefix + p["demo"]
    return f'<a class="btn solid" href="{url}"{ext(url)}>Open the live demo</a>'


def card(p):
    href = f'projects/{p["slug"]}.html'
    cls = "card feature" if p.get("feature") else "card"
    badge = '<span class="pill">Live demo</span>' if p.get("demo") else ""
    return (f'<a class="{cls}" href="{href}">{visual(p)}<div class="txt"><div class="date">{p["date"]}</div>\n'
            f'<h3>{escape(p["title"])}</h3><p>{escape(p["blurb"])}</p>'
            f'<div class="row"><span class="cs">Read the case study →</span>{badge}</div></div></a>')


def status(p):
    if p.get("demo"):
        return '<span class="st live">Live demo</span>'
    return '<span class="st">Case study</span>'


def build_index():
    catname = {c[0]: c[1] for c in CATEGORIES}
    rows = "".join(
        f'<tr><td><a href="projects/{p["slug"]}.html">{escape(p["title"])}</a></td>'
        f'<td class="m hide">{escape(p["short"])}</td><td class="m hide">{catname[p["cat"]]}</td>'
        f'<td class="yr">{p["year"]}</td><td>{status(p)}</td></tr>'
        for p in PROJECTS)
    demos = sum(1 for p in PROJECTS if p.get("demo"))

    cats = [c for c in CATEGORIES if any(p["cat"] == c[0] for p in PROJECTS)]
    sections = []
    for i, (key, name, sub) in enumerate(cats, 1):
        ps = [p for p in PROJECTS if p["cat"] == key]
        feat = "".join(card(p) for p in ps if p.get("feature"))
        rest = [p for p in ps if not p.get("feature")]
        gcls = "grid" if len(rest) == 2 else "grid3"
        sections.append(
            f'<div class="cat" id="{key}">'
            + (f'<div class="cathead"><i>0{i}</i><h3>{name}</h3></div><p class="catsub">{sub}</p>' if len(cats) > 1 else "")
            + f'{feat}<div class="{gcls}">{"".join(card(p) for p in rest)}</div></div>')

    # The summary table only earns its space once there are more than a few projects.
    if len(PROJECTS) > 4:
        sub2 = "Everything in one list, then each project in detail: the problem, how it works and what it found."
        table = ('<table class="idx" style="margin-bottom:72px"><thead><tr><th>Project</th><th class="hide">What it does</th>'
                 f'<th class="hide">Area</th><th>Year</th><th>Status</th></tr></thead><tbody>{rows}</tbody></table>')
    else:
        sub2 = "Click any project for the case study and a live demo."
        table = ""

    tools = "".join(
        f'<div class="toolgrp"><h4>{g}</h4><div class="toolsl">{"".join(f"<span>{escape(t)}</span>" for t in ts)}</div></div>'
        for g, ts in TOOLS)

    body = f"""<main>
<section class="hero"><div class="wrap">
<div class="eyebrow">Tommy Robins · NYU Schack MSRE · Anchor Capital Group</div>
<h1>Data tools for real estate investing, <em>built from the deal side.</em></h1>
<p class="lede">I source and underwrite value-add industrial deals in Florida and study real estate finance at NYU Schack. These are tools I built with Claude to turn slow, manual steps into repeatable ones.</p>
<div class="stats"><div><b>{len(PROJECTS)}</b><span>projects</span></div><div><b>{demos}</b><span>live demos</span></div><div><b>50+</b><span>deals underwritten</span></div></div>
</div></section>
<section id="projects" class="sec"><div class="wrap">
<div class="phead2"><h2>Projects</h2><p class="sub2">{sub2}</p></div>
{table}{"".join(sections)}
</div></section>
<section id="approach" class="sec"><div class="wrap">
<h2>Approach</h2><p class="sub2">The rules I build by.</p>
<div class="steps">
<div><i>01</i><h4>Start from a real bottleneck</h4><p>Every tool here came from a step I was doing by hand at work or a problem someone in the market described to me. Finding motivated sellers is the bottleneck in off-market sourcing, so that's what the sourcing tools go after.</p></div>
<div><i>02</i><h4>Check what already exists</h4><p>Before building, I look for a product that already solves it. Muskoka got built because the paid trackers stop at Toronto and Vancouver.</p></div>
<div><i>03</i><h4>Show the source</h4><p>Figures link back to the filing, notice or record they came from, so anyone can check the number instead of trusting it.</p></div>
<div><i>04</i><h4>Keep private data private</h4><p>Real owner lists, deal numbers and loan data stay off the public site. Demos use public records or sample data.</p></div>
</div></div></section>
<section id="tools" class="sec"><div class="wrap">
<h2>Tools</h2><p class="sub2">What I use for models, data and builds.</p>
{tools}
</div></section></main>"""
    (ROOT / "index.html").write_text(page(
        "Tommy Robins | Real Estate Data Tools",
        "Real estate data tools, models and research built by Tommy Robins, NYU Schack MSRE.", body))


def build_case(i, p):
    nxt = PROJECTS[(i + 1) % len(PROJECTS)]
    tags = "".join(f'<span class="tag">{escape(t)}</span>' for t in p["tags"])
    acts = demo_link(p, "../")
    if p.get("repo"):
        acts += f'<a class="btn" href="{p["repo"]}" target="_blank" rel="noopener">View on GitHub</a>'
    content = (ROOT / "content" / f'{p["slug"]}.html').read_text().strip()
    hero = visual(p, "../", wide=True)
    if p.get("demo"):
        url = p["demo"] if p["demo"].startswith("http") else "../" + p["demo"]
        hero = f'<a class="heroimg" href="{url}"{ext(url)}>{hero}</a>'
    if p.get("sample"):
        acts += '<span class="snote">Runs on fictional sample data</span>'
    body = f"""<main class="case"><div class="wrap narrow">
<a class="back" href="../index.html#projects">← All projects</a>
<div class="date">{p["date"]}</div><h1 class="ctitle">{escape(p["title"])}</h1>
<p class="lede">{escape(p["blurb"])}</p><div class="tags">{tags}</div><div class="row act">{acts}</div></div>
<div class="wrap">{hero}</div>
<div class="wrap narrow prose">{content}
<a class="next" href="{nxt["slug"]}.html"><span>Next project</span>{escape(nxt["title"])} →</a></div></main>"""
    (ROOT / "projects" / f'{p["slug"]}.html').write_text(page(
        f'{p["title"]} | Tommy Robins', p["blurb"], body, "../"))


if __name__ == "__main__":
    (ROOT / "projects").mkdir(exist_ok=True)
    build_index()
    for i, p in enumerate(PROJECTS):
        build_case(i, p)
    # Remove pages for projects no longer shown so they aren't reachable from old links.
    keep = {f'{p["slug"]}.html' for p in PROJECTS}
    for f in (ROOT / "projects").glob("*.html"):
        if f.name not in keep:
            f.unlink()
    print(f"Built index.html and {len(PROJECTS)} case studies.")
