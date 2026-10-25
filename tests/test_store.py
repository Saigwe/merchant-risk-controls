import datetime as dt
import sys
from pathlib import Path

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import store  # noqa: E402
from workflow import Event, WorkflowError  # noqa: E402

DEC, NOV = dt.date(2025, 12, 1), dt.date(2025, 11, 1)
NOW = dt.datetime(2025, 12, 10, 9, 0)


@pytest.fixture
def con():
    c = duckdb.connect(":memory:")
    c.execute("create schema bronze")
    c.execute("create table bronze.users as select * from (values ('ana', 'analyst'), ('chk', 'checker')) t(user_id, role)")
    c.execute("create table bronze.period_locks as select date '2025-11-01' as period_month, "
              "timestamp '2025-12-05 18:00:00' as locked_at, 'controller' as locked_by")
    c.execute("""create table bronze.override_events (event_id bigint, override_id varchar, merchant_id varchar,
                 period_month date, action varchar, actor varchar, event_ts timestamp, reason varchar,
                 proposed_rating varchar)""")
    yield c
    c.close()


def propose(con, oid="OVR000001", merchant="M1", period=DEC, actor="ana", reason="Owner verified by video call"):
    return store.submit(con, Event(oid, merchant, period, "propose", actor, NOW, reason, "medium"))


def test_valid_flow_appends_events_in_order(con):
    assert propose(con) == 1
    assert store.submit(con, Event("OVR000001", "M1", DEC, "approve", "chk", NOW + dt.timedelta(hours=1))) == 2
    o = store.overrides(con)
    assert o.loc[0, "status"] == "approved" and o.loc[0, "decided_by"] == "chk"


def test_refused_event_writes_nothing(con):
    with pytest.raises(WorkflowError, match="locked"):
        propose(con, period=NOV)
    assert con.execute("select count(*) from bronze.override_events").fetchone()[0] == 0


def test_self_approval_refused_and_log_unchanged(con):
    store.submit(con, Event("OVR000001", "M1", DEC, "propose", "chk", NOW, "Checker proposing directly", "low"))
    with pytest.raises(WorkflowError, match="maker-checker"):
        store.submit(con, Event("OVR000001", "M1", DEC, "approve", "chk", NOW + dt.timedelta(hours=1)))
    assert con.execute("select count(*) from bronze.override_events").fetchone()[0] == 1


def test_second_live_override_for_same_merchant_month_refused(con):
    propose(con)
    with pytest.raises(WorkflowError, match="live override"):
        propose(con, oid="OVR000002")
    propose(con, oid="OVR000003", merchant="M2")  # another merchant is fine


def test_next_override_id_counts_existing(con):
    assert store.next_override_id(con) == "OVR000001"
    propose(con)
    assert store.next_override_id(con) == "OVR000002"
