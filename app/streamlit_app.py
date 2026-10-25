"""Merchant risk-rating control app: review queue, maker-checker overrides, audit log and controls.

Run:  streamlit run app/streamlit_app.py      (warehouse path: RISK_DUCKDB_PATH, default warehouse/risk.duckdb)
Ratings come from the dbt gold layer; override actions are written to the audit log through store.submit,
which enforces app/workflow.py. Rebuild dbt to see approved overrides in the ratings.
"""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

import store
from workflow import RATINGS, Event, WorkflowError

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = os.environ.get("RISK_DUCKDB_PATH", str(ROOT / "warehouse" / "risk.duckdb"))

st.set_page_config(page_title="Merchant Risk Controls", layout="wide")

if not Path(DB_PATH).exists():
    st.error(f"No warehouse at {DB_PATH}. Run `make all` first.")
    st.stop()


def read(sql: str, params: list | None = None) -> pd.DataFrame:
    with duckdb.connect(DB_PATH, read_only=True) as con:
        return con.execute(sql, params or []).df()


def write(event: Event) -> None:
    with duckdb.connect(DB_PATH) as con:
        event_id = store.submit(con, event)
    st.success(f"Recorded event {event_id}: {event.action} on {event.override_id}.")


with duckdb.connect(DB_PATH, read_only=True) as con:
    user_roles = store.roles(con)
    lock_map = store.locks(con)

st.sidebar.title("Merchant Risk Controls")
user = st.sidebar.selectbox("Signed in as (demo)", sorted(user_roles), format_func=lambda u: f"{u} ({user_roles[u]})")
st.sidebar.caption("A real deployment takes identity from SSO; the selector stands in for it here.")
months = read("select distinct period_month from gold.fct_merchant_rating order by 1 desc")["period_month"]
open_month = months.iloc[0].date()
st.sidebar.markdown(f"**Open month:** {open_month:%B %Y}")
st.sidebar.markdown(f"**Locked months:** {len(lock_map)} (latest {max(lock_map):%b %Y})" if lock_map else "No locked months")

queue, propose, approvals, log, controls = st.tabs(["Review queue", "Propose override", "Approvals", "Audit log", "Controls"])

with queue:
    month = st.selectbox("Month", months, format_func=lambda d: d.strftime("%b %Y"))
    ratings = st.multiselect("Model rating", list(RATINGS), default=["high"])
    q = read("""select merchant_id, risk_score, model_rating, final_rating, rating_source, rules_fired
                from gold.fct_merchant_rating where period_month = ? order by risk_score desc""", [month])
    q = q[q["model_rating"].isin(ratings)]
    st.caption(f"{len(q):,} merchants. Rules are listed highest weight first.")
    st.dataframe(q.head(500), use_container_width=True, hide_index=True)
    rules = read("select rule_id, description, points from ref.risk_rules order by rule_id")
    with st.expander("Scoring rules (dbt seed risk_rules.csv)"):
        st.dataframe(rules, use_container_width=True, hide_index=True)

with propose:
    with st.form("propose"):
        merchant = st.text_input("Merchant id", placeholder="M000123")
        period = st.selectbox("Month", months, format_func=lambda d: d.strftime("%b %Y"))
        rating = st.radio("New rating", RATINGS, horizontal=True)
        reason = st.text_area("Reason (required, at least 10 characters)")
        if st.form_submit_button("Propose override"):
            with duckdb.connect(DB_PATH, read_only=True) as con:
                oid = store.next_override_id(con)
            try:
                write(Event(oid, merchant.strip(), period.date(), "propose", user, dt.datetime.now(), reason, rating))
            except WorkflowError as e:
                st.error(f"Refused: {e}")

with approvals:
    with duckdb.connect(DB_PATH, read_only=True) as con:
        pending = store.overrides(con)
    pending = pending[pending["status"] == "proposed"]
    st.caption(f"{len(pending)} override(s) waiting for a checker.")
    for row in pending.itertuples():
        with st.expander(f"{row.override_id} · {row.merchant_id} · {row.period_month:%b %Y} → {row.proposed_rating} "
                         f"(by {row.proposed_by})"):
            st.write(f"**Reason:** {row.reason}")
            note = st.text_input("Reason (required to reject or withdraw)", key=f"r-{row.override_id}")
            c1, c2, c3 = st.columns(3)
            for col, action in ((c1, "approve"), (c2, "reject"), (c3, "withdraw")):
                if col.button(action.title(), key=f"{action}-{row.override_id}"):
                    try:
                        write(Event(row.override_id, row.merchant_id, row.period_month.date(), action, user,
                                    dt.datetime.now(), note or None, None))
                    except WorkflowError as e:
                        st.error(f"Refused: {e}")

with log:
    st.caption("Append-only: every action is a new row; nothing is edited or deleted.")
    st.dataframe(read("""select event_id, event_ts, override_id, merchant_id, period_month, action, actor,
                                proposed_rating, reason
                         from bronze.override_events order by event_id desc limit 300"""),
                 use_container_width=True, hide_index=True)

with controls:
    v = read("select violation, count(*) as events from gold.rpt_control_violations group by 1")
    if v.empty:
        st.success("Audit: no event in the override log breaks a control (as of the last dbt build).")
    else:
        st.error("Audit found events that break a control.")
        st.dataframe(v, hide_index=True)
    st.subheader("Newly high-risk merchants per month")
    nh = read("select period_month, new_high, continuing_high, total_high from gold.rpt_new_high_risk order by 1")
    st.bar_chart(nh.set_index("period_month")[["new_high", "continuing_high"]])
    st.subheader("Override activity")
    st.dataframe(read("""select period_month, proposals, approved, rejected, withdrawn, pending, approval_rate,
                                median_hours_to_decision, override_share
                         from gold.rpt_override_activity order by 1 desc"""),
                 use_container_width=True, hide_index=True)
    st.subheader("Period locks")
    st.dataframe(read("select * from bronze.period_locks order by period_month desc"), hide_index=True)
