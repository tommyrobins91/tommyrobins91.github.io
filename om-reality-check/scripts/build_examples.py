"""Re-run every example OM against live NYC data and save the reports.

    .venv/bin/python scripts/build_examples.py

Writes examples/<name>.md (full memo per OM) and examples/README.md (index).
"""
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from omrc.analyze import analyze  # noqa: E402
from omrc.claims import OMClaims  # noqa: E402
from omrc.report import to_markdown  # noqa: E402

CASES = sorted((ROOT / "samples" / "real_oms").glob("*.json")) + [ROOT / "samples" / "sample_95_bergen.json"]
OUT = ROOT / "examples"


def m(x):
    return "n/a" if x is None else (f"${x / 1e6:.2f}M" if abs(x) >= 1e6 else f"${x:,.0f}")


def main():
    OUT.mkdir(exist_ok=True)
    rows = []
    for path in CASES:
        a = analyze(OMClaims.from_dict(json.loads(path.read_text())))
        name = path.stem
        memo = to_markdown(a)
        if a.claims.source:
            memo = memo.replace("\n\n**Grade", f"\n\nOM source: {a.claims.source}\n\n**Grade", 1)
        (OUT / f"{name}.md").write_text(memo)
        top = [f.title for f in a.flags if f.severity in ("high", "medium")][:3]
        rows.append((name, a, top, path.parent.name == "real_oms"))
        print(f"{name}: grade {a.grade}, {len(a.flags)} flags")

    lines = [
        "# Example reports",
        f"Generated {date.today():%B %d, %Y} by `scripts/build_examples.py` against live NYC Open Data.",
        "",
        "| OM | Grade | OM NOI | Adjusted NOI | Ask | Value at OM's cap | Top findings |",
        "|---|:-:|--:|--:|--:|--:|---|",
    ]
    for name, a, top, real in rows:
        label = a.profile.address.title() + ("" if real else " *(fictional OM)*")
        lines.append(
            f"| [{label}]({name}.md) | {a.grade} | {m(a.uw.om_noi_basis)} ({a.uw.basis}) | {m(a.uw.adjusted_noi_basis)} "
            f"| {m(a.claims.asking_price)} | {m(a.uw.value_at_om_cap)} | {'; '.join(top)} |"
        )
    (OUT / "README.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
