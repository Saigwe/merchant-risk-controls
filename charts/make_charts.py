"""README charts from the gold marts. Usage: python charts/make_charts.py [--db warehouse/risk.duckdb] [--out docs/charts]"""
import argparse
from pathlib import Path

import duckdb
import matplotlib.dates as mdates

import style as st

ROOT = Path(__file__).resolve().parents[1]
ap = argparse.ArgumentParser()
ap.add_argument("--db", default=str(ROOT / "warehouse" / "risk.duckdb"))
ap.add_argument("--out", default=str(ROOT / "docs" / "charts"))
a = ap.parse_args()
OUT = Path(a.out)
con = duckdb.connect(a.db, read_only=True)

hits = con.execute("""select rule_id || '  ' || any_value(description), count(*) n
                      from gold.fct_rule_hits group by rule_id order by n desc""").fetchall()
f, ax = st.fig(8, 3.6)
SHORT = {"R01": "Chargebacks ≥ 0.9%", "R02": "Chargebacks ≥ 0.65% (early warning)", "R03": "Refunds ≥ 10% of orders",
         "R04": "Negative balance ≥ 5 days", "R05": "Onboarded < 90 days ago", "R06": "Ownership changed (3 months)",
         "R07": "KYC documents expired", "R08": "GMV up 300%+ on prior month"}
st.hbar(ax, [h[0][:3] + "  " + SHORT.get(h[0][:3], h[0][5:]) for h in hits], [h[1] for h in hits])
months = con.execute("select count(*) from (select distinct merchant_id, period_month from gold.fct_merchant_risk_score)").fetchone()[0]
st.head(ax, "Which scoring rules fire, and how often", f"Rule hits across {months:,} merchant-months; rules are held as data in a dbt seed", flush=True)
st.save(f, OUT / "rule_hits.png")

ov = con.execute("""select period_month, approved, rejected, withdrawn, pending, median_hours_to_decision
                    from gold.rpt_override_activity order by period_month""").fetchall()
x = [r[0] for r in ov]
f, ax = st.fig(8, 3.4)
bottom = [0] * len(ov)
for i, (lab, col) in enumerate([("Approved", st.S[0]), ("Rejected", st.S[1]), ("Withdrawn", st.S[3]), ("Pending", st.MUTED)]):
    vals = [r[1 + i] for r in ov]
    ax.bar(x, vals, width=20, bottom=bottom, color=col, label=lab, edgecolor=st.SURFACE, linewidth=1)
    bottom = [b + v for b, v in zip(bottom, vals)]
viol = con.execute("select count(*) from gold.rpt_control_violations").fetchone()[0]
ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
st.head(ax, f"Every override goes through maker-checker: {viol} control violations in the audit log",
        "Rating override proposals by month and decision", legend=True)
st.save(f, OUT / "override_decisions.png")
print(f"wrote charts to {OUT}")
