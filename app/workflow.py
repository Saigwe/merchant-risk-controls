"""Override workflow rules: the controls the approval app enforces before writing to the audit log.

An override changes a merchant's risk rating for one month. The rules:
- Maker-checker: an analyst or checker proposes; a *different* user with the checker role approves or rejects.
- A reason of at least 10 characters is required to propose, reject or withdraw.
- Period locks: once a month is locked, no event for that month is accepted.
- One live override per merchant and month: a new proposal is refused while another is proposed or approved.
- Only the proposer can withdraw, and only while it is still proposed.

The log is append-only: every action is a new event, nothing is updated or deleted. dbt re-checks the
same rules independently over the whole log (rpt_control_violations), so a write that bypassed the app
would still be caught.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

RATINGS = ("low", "medium", "high")
ACTIONS = ("propose", "approve", "reject", "withdraw")
MIN_REASON = 10


class WorkflowError(ValueError):
    """An action that breaks a control. The message says which one."""


@dataclass(frozen=True)
class Event:
    override_id: str
    merchant_id: str
    period_month: dt.date
    action: str
    actor: str
    event_ts: dt.datetime
    reason: str | None = None
    proposed_rating: str | None = None


def status_of(history: list[Event]) -> str | None:
    """Current status of one override from its events: proposed, approved, rejected, withdrawn, or None."""
    final = {"propose": "proposed", "approve": "approved", "reject": "rejected", "withdraw": "withdrawn"}
    return final[history[-1].action] if history else None


def check(event: Event, history: list[Event], live_for_period: list[str], roles: dict[str, str],
          locks: dict[dt.date, dt.datetime]) -> None:
    """Raise WorkflowError if `event` breaks a control.

    history         : earlier events of the same override, oldest first
    live_for_period : ids of other overrides for the same merchant and month that are proposed or approved
    roles           : user id -> role (analyst, checker)
    locks           : period month -> time it was locked
    """
    if event.action not in ACTIONS:
        raise WorkflowError(f"unknown action {event.action!r}")
    role = roles.get(event.actor)
    if role is None:
        raise WorkflowError(f"unknown user {event.actor!r}")
    locked_at = locks.get(event.period_month)
    if locked_at is not None and event.event_ts >= locked_at:
        raise WorkflowError(f"period {event.period_month:%Y-%m} is locked (since {locked_at:%Y-%m-%d %H:%M})")

    reason = (event.reason or "").strip()
    current = status_of(history)

    if event.action == "propose":
        if history:
            raise WorkflowError("override already exists; start a new one")
        if event.proposed_rating not in RATINGS:
            raise WorkflowError(f"rating must be one of {RATINGS}")
        if len(reason) < MIN_REASON:
            raise WorkflowError(f"a reason of at least {MIN_REASON} characters is required")
        if live_for_period:
            raise WorkflowError(f"merchant already has a live override for this month: {live_for_period[0]}")
        return

    if current != "proposed":
        raise WorkflowError(f"override is {current or 'not proposed'}; only a proposed override can be {event.action}d")
    proposer = history[0].actor

    if event.action in ("approve", "reject"):
        if role != "checker":
            raise WorkflowError("only a checker can approve or reject")
        if event.actor == proposer:
            raise WorkflowError("maker-checker: you can't approve or reject your own proposal")
        if event.action == "reject" and len(reason) < MIN_REASON:
            raise WorkflowError(f"a reason of at least {MIN_REASON} characters is required to reject")
        return

    if event.action == "withdraw":
        if event.actor != proposer:
            raise WorkflowError("only the proposer can withdraw")
        if len(reason) < MIN_REASON:
            raise WorkflowError(f"a reason of at least {MIN_REASON} characters is required to withdraw")
