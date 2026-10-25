"""Read workflow state from DuckDB and append events to the audit log, enforcing app/workflow.py.

Every write goes through `submit`, which checks the event against the controls and inserts it in one
transaction. Nothing is ever updated or deleted.
"""
from __future__ import annotations

import datetime as dt

import duckdb
import pandas as pd

from workflow import Event, check

LIVE = ("proposed", "approved")


def roles(con: duckdb.DuckDBPyConnection) -> dict[str, str]:
    return dict(con.execute("select user_id, role from bronze.users").fetchall())


def locks(con: duckdb.DuckDBPyConnection) -> dict[dt.date, dt.datetime]:
    return dict(con.execute("select period_month, locked_at from bronze.period_locks").fetchall())


def history(con: duckdb.DuckDBPyConnection, override_id: str) -> list[Event]:
    rows = con.execute(
        """select override_id, merchant_id, period_month, action, actor, event_ts, reason, proposed_rating
           from bronze.override_events where override_id = ? order by event_id""", [override_id]).fetchall()
    return [Event(*r) for r in rows]


def overrides(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """One row per override with its current status (latest event wins)."""
    return con.execute("""
        with p as (
            select override_id, merchant_id, period_month, actor as proposed_by, event_ts as proposed_at,
                   proposed_rating, reason
            from bronze.override_events where action = 'propose'
        ),
        last as (
            select override_id, action, actor, event_ts,
                   row_number() over (partition by override_id order by event_id desc) as rn
            from bronze.override_events
        )
        select p.*, case l.action when 'propose' then 'proposed' when 'approve' then 'approved'
                                  when 'reject' then 'rejected' else 'withdrawn' end as status,
               case when l.action <> 'propose' then l.actor end as decided_by
        from p join last l on l.override_id = p.override_id and l.rn = 1
        order by p.proposed_at desc
    """).df()


def live_for(con: duckdb.DuckDBPyConnection, merchant_id: str, period_month: dt.date, exclude: str) -> list[str]:
    o = overrides(con)
    mask = (o.merchant_id == merchant_id) & (o.period_month == pd.Timestamp(period_month)) \
        & o.status.isin(LIVE) & (o.override_id != exclude)
    return o.loc[mask, "override_id"].tolist()


def next_override_id(con: duckdb.DuckDBPyConnection) -> str:
    n = con.execute("select count(distinct override_id) from bronze.override_events").fetchone()[0]
    return f"OVR{n + 1:06d}"


def submit(con: duckdb.DuckDBPyConnection, event: Event) -> int:
    """Check `event` against every control and append it. Returns the new event_id; raises WorkflowError."""
    con.execute("begin transaction")
    try:
        check(event, history(con, event.override_id),
              live_for(con, event.merchant_id, event.period_month, event.override_id), roles(con), locks(con))
        event_id = con.execute("select coalesce(max(event_id), 0) + 1 from bronze.override_events").fetchone()[0]
        con.execute(
            """insert into bronze.override_events
               (event_id, override_id, merchant_id, period_month, action, actor, event_ts, reason, proposed_rating)
               values (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [event_id, event.override_id, event.merchant_id, event.period_month, event.action, event.actor,
             event.event_ts, event.reason, event.proposed_rating])
        con.execute("commit")
        return event_id
    except Exception:
        con.execute("rollback")
        raise
