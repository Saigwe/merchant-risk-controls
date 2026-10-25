import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from workflow import Event, WorkflowError, check, status_of  # noqa: E402

JAN = dt.date(2025, 1, 1)
ROLES = {"ana": "analyst", "ben": "analyst", "chk": "checker", "chk2": "checker"}
LOCKS = {dt.date(2024, 12, 1): dt.datetime(2025, 1, 5, 18, 0)}
T0 = dt.datetime(2025, 1, 10, 9, 0)


def ev(action, actor, ts=T0, reason="customer documents verified", rating=None, period=JAN, oid="O1"):
    return Event(oid, "M1", period, action, actor, ts, reason, rating)


PROPOSAL = ev("propose", "ana", rating="medium")


def test_valid_propose_then_approve():
    check(PROPOSAL, [], [], ROLES, LOCKS)
    check(ev("approve", "chk", T0 + dt.timedelta(hours=2)), [PROPOSAL], [], ROLES, LOCKS)


@pytest.mark.parametrize("reason", [None, "", "   ", "too short"])
def test_propose_needs_a_reason(reason):
    with pytest.raises(WorkflowError, match="reason"):
        check(ev("propose", "ana", reason=reason, rating="high"), [], [], ROLES, LOCKS)


def test_propose_needs_a_valid_rating():
    with pytest.raises(WorkflowError, match="rating"):
        check(ev("propose", "ana", rating="critical"), [], [], ROLES, LOCKS)


def test_self_approval_is_refused_even_for_a_checker():
    own = ev("propose", "chk", rating="low")
    with pytest.raises(WorkflowError, match="maker-checker"):
        check(ev("approve", "chk"), [own], [], ROLES, LOCKS)


def test_analyst_cannot_approve():
    with pytest.raises(WorkflowError, match="only a checker"):
        check(ev("approve", "ben"), [PROPOSAL], [], ROLES, LOCKS)


def test_locked_period_refuses_any_action():
    dec = dt.date(2024, 12, 1)
    with pytest.raises(WorkflowError, match="locked"):
        check(ev("propose", "ana", ts=dt.datetime(2025, 1, 6), rating="high", period=dec), [], [], ROLES, LOCKS)


def test_action_before_lock_time_is_allowed():
    dec = dt.date(2024, 12, 1)
    check(ev("propose", "ana", ts=dt.datetime(2025, 1, 5, 17, 59), rating="high", period=dec), [], [], ROLES, LOCKS)


def test_second_live_override_for_same_month_is_refused():
    with pytest.raises(WorkflowError, match="live override"):
        check(ev("propose", "ben", rating="high", oid="O2"), [], ["O1"], ROLES, LOCKS)


def test_cannot_approve_twice_or_after_rejection():
    approved = [PROPOSAL, ev("approve", "chk")]
    with pytest.raises(WorkflowError, match="approved"):
        check(ev("approve", "chk2"), approved, [], ROLES, LOCKS)
    rejected = [PROPOSAL, ev("reject", "chk")]
    with pytest.raises(WorkflowError, match="rejected"):
        check(ev("approve", "chk2"), rejected, [], ROLES, LOCKS)


def test_only_proposer_can_withdraw():
    with pytest.raises(WorkflowError, match="only the proposer"):
        check(ev("withdraw", "ben"), [PROPOSAL], [], ROLES, LOCKS)
    check(ev("withdraw", "ana"), [PROPOSAL], [], ROLES, LOCKS)


def test_unknown_user_is_refused():
    with pytest.raises(WorkflowError, match="unknown user"):
        check(ev("propose", "mallory", rating="low"), [], [], ROLES, LOCKS)


def test_status_follows_the_last_event():
    assert status_of([]) is None
    assert status_of([PROPOSAL]) == "proposed"
    assert status_of([PROPOSAL, ev("approve", "chk")]) == "approved"
