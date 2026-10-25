"""Generate synthetic merchant risk data into DuckDB `bronze`.

- merchants               : ~20k merchants; some onboard during the year
- merchant_monthly_metrics: monthly signals (GMV, chargeback and refund rates, negative-balance days,
                            ownership change, expired KYC). A hidden risk state drifts month to month.
- users                   : analysts (makers) and checkers
- period_locks            : each month locks at 18:00 on the 5th of the next month; the last month stays open
- override_events         : the append-only audit log, built by replaying the app's own workflow rules
                            (app/workflow.py), so every generated event is one the app would accept

With --plant-violations (CI fixture), events that break each control are written straight to the log,
bypassing the rules, and listed in `fixture_planted_violations` so tests can prove dbt catches them.

Usage
    python ingestion/generate_risk_data.py --db warehouse/risk.duckdb
    python ingestion/generate_risk_data.py --db warehouse/fixture.duckdb --merchants 600 --plant-violations
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from workflow import Event, check, status_of  # noqa: E402

SEGMENTS = {"smb": (0.72, 9.0), "mid_market": (0.22, 11.0), "enterprise": (0.06, 13.0)}  # weight, mean log GMV
REASONS = {
    "high": ["Linked to a merchant terminated for fraud last quarter", "Card-network fraud alert received this month",
             "Beneficial owner appears on an adverse-media screen"],
    "medium": ["Chargebacks driven by a one-off fulfilment delay, now resolved",
               "New owner verified but monitoring for three months", "Seasonal refund spike, documented by the merchant"],
    "low": ["Chargeback ratio inflated by a single disputed bulk order", "KYC refreshed after the month-end extract",
            "Negative balance caused by a processor settlement delay"],
}


def month_starts(year: int) -> list[dt.date]:
    return [dt.date(year, m, 1) for m in range(1, 13)]


def make_merchants(rng, n: int, year: int) -> pd.DataFrame:
    seg = rng.choice(list(SEGMENTS), n, p=[v[0] for v in SEGMENTS.values()])
    new = rng.random(n) < 0.15
    onboard = np.where(
        new,
        pd.to_datetime([dt.date(year, int(m), 1) for m in rng.integers(1, 13, n)]) + pd.to_timedelta(rng.integers(0, 28, n), unit="D"),
        pd.Timestamp(year, 1, 1) - pd.to_timedelta(rng.integers(30, 2000, n), unit="D"),
    )
    return pd.DataFrame({
        "merchant_id": [f"M{i:06d}" for i in range(1, n + 1)],
        "segment": seg,
        "country_code": rng.choice(["US", "CA", "AU", "GB"], n, p=[0.6, 0.15, 0.1, 0.15]),
        "category": rng.choice(["restaurant", "grocery", "convenience", "retail", "pharmacy", "alcohol"], n,
                               p=[0.55, 0.15, 0.1, 0.1, 0.05, 0.05]),
        "onboarded_at": pd.to_datetime(onboard),
    })


def make_metrics(rng, merchants: pd.DataFrame, year: int) -> pd.DataFrame:
    n = len(merchants)
    risky = rng.random(n) < 0.06
    base_gmv = rng.lognormal(merchants["segment"].map({k: v[1] for k, v in SEGMENTS.items()}).to_numpy(), 0.7)
    gmv_prev = base_gmv.copy()
    rows = []
    for ms in month_starts(year):
        risky = np.where(risky, rng.random(n) > 0.10, rng.random(n) < 0.02)  # drift in and out of risk
        active = merchants["onboarded_at"].to_numpy() < np.datetime64(ms + pd.offsets.MonthEnd(0))
        spike = risky & (rng.random(n) < 0.15)
        gmv = np.round(gmv_prev * rng.lognormal(0, 0.15, n) * np.where(spike, rng.uniform(4, 8, n), 1.0), 2)
        orders = np.maximum(1, (gmv / rng.uniform(25, 45, n)).astype(int))
        cb_rate = np.where(risky, rng.gamma(4, 0.003, n), rng.gamma(2, 0.001, n))
        rows.append(pd.DataFrame({
            "merchant_id": merchants["merchant_id"], "period_month": ms, "gmv_usd": gmv, "orders": orders,
            "chargebacks": np.round(orders * cb_rate).astype(int),
            "refunds": np.round(orders * np.where(risky, rng.beta(4, 22, n), rng.beta(2, 45, n))).astype(int),
            "negative_balance_days": np.where(risky, rng.poisson(4, n), rng.poisson(0.2, n)),
            "ownership_changed": rng.random(n) < np.where(risky, 0.03, 0.003),
            "kyc_expired": rng.random(n) < np.where(risky, 0.10, 0.02),
        })[active])
        gmv_prev = np.where(spike, gmv_prev, gmv)
    return pd.concat(rows, ignore_index=True)


def make_users() -> pd.DataFrame:
    rows = [(f"analyst_{i}", "analyst") for i in range(1, 7)] + [(f"checker_{i}", "checker") for i in range(1, 4)]
    return pd.DataFrame(rows, columns=["user_id", "role"])


def make_locks(year: int) -> pd.DataFrame:
    rows = [(ms, dt.datetime(year + (ms.month == 12), ms.month % 12 + 1, 5, 18, 0), "controller_1")
            for ms in month_starts(year)[:-1]]
    return pd.DataFrame(rows, columns=["period_month", "locked_at", "locked_by"])


def make_events(rng, merchants: pd.DataFrame, metrics: pd.DataFrame, users: pd.DataFrame, locks: pd.DataFrame,
                year: int, per_month: int) -> pd.DataFrame:
    roles = dict(zip(users.user_id, users.role))
    lock_map = {r.period_month: r.locked_at.to_pydatetime() for r in locks.itertuples()}
    analysts = users.loc[users.role == "analyst", "user_id"].to_numpy()
    checkers = users.loc[users.role == "checker", "user_id"].to_numpy()
    events: list[Event] = []
    by_override: dict[str, list[Event]] = {}
    live: dict[tuple, list[str]] = {}

    def add(e: Event) -> None:
        key = (e.merchant_id, e.period_month)
        check(e, by_override.get(e.override_id, []), [o for o in live.get(key, []) if o != e.override_id],
              roles, lock_map)
        by_override.setdefault(e.override_id, []).append(e)
        events.append(e)
        live.setdefault(key, [])
        if status_of(by_override[e.override_id]) in ("proposed", "approved"):
            if e.override_id not in live[key]:
                live[key].append(e.override_id)
        elif e.override_id in live[key]:
            live[key].remove(e.override_id)

    seq = 0
    for ms in month_starts(year):
        lock = lock_map.get(ms)
        candidates = metrics.loc[metrics.period_month == ms, "merchant_id"].to_numpy()
        for merchant in rng.choice(candidates, per_month, replace=False):
            seq += 1
            oid = f"OVR{seq:06d}"
            rating = rng.choice(["low", "medium", "high"], p=[0.45, 0.30, 0.25])
            proposed_at = dt.datetime.combine(ms, dt.time(9)) + dt.timedelta(minutes=int(rng.integers(0, 30 * 24 * 60)))
            if lock and proposed_at >= lock - dt.timedelta(hours=72):
                proposed_at = lock - dt.timedelta(hours=int(rng.integers(72, 400)))
            maker = rng.choice(analysts)
            add(Event(oid, merchant, ms, "propose", maker, proposed_at, rng.choice(REASONS[rating]), rating))
            outcome = rng.choice(["approve", "reject", "withdraw", "pending"], p=[0.72, 0.18, 0.05, 0.05])
            if outcome == "pending" and lock:
                outcome = "approve"  # closed months are fully decided before the lock
            if outcome == "pending":
                continue
            decided_at = proposed_at + dt.timedelta(minutes=int(rng.integers(20, 48 * 60)))
            actor = maker if outcome == "withdraw" else rng.choice(checkers)
            reason = {"approve": None, "reject": "Evidence does not support changing the model rating",
                      "withdraw": "Proposed against the wrong merchant id"}[outcome]
            add(Event(oid, merchant, ms, outcome, actor, decided_at, reason, None))

    return events_frame(events)


def events_frame(events: list[Event]) -> pd.DataFrame:
    df = pd.DataFrame([e.__dict__ for e in events]).sort_values(["event_ts", "override_id"]).reset_index(drop=True)
    df.insert(0, "event_id", np.arange(1, len(df) + 1))
    return df


def plant_violations(events: pd.DataFrame, merchants: pd.DataFrame, locks: pd.DataFrame,
                     year: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Write events that break each control straight into the log (bypassing the app), plus an answer key.
    Each uses a merchant with no other overrides, so each planted case breaks exactly the controls listed."""
    open_month = dt.date(year, 12, 1)
    some = merchants.loc[~merchants["merchant_id"].isin(events["merchant_id"]), "merchant_id"].to_numpy()
    t = dt.datetime(year, 12, 20, 10, 0)
    lock = locks.iloc[0]
    rows, key = [], []

    def ov(oid, merchant, period, action, actor, ts, reason=None, rating=None):
        rows.append(dict(override_id=oid, merchant_id=merchant, period_month=period, action=action, actor=actor,
                         event_ts=ts, reason=reason, proposed_rating=rating))

    ov("BAD001", some[0], open_month, "propose", "checker_1", t, "Merchant explained the refund spike", "low")
    ov("BAD001", some[0], open_month, "approve", "checker_1", t + dt.timedelta(hours=1))
    key.append(("BAD001", "self_approval"))
    ov("BAD002", some[1], open_month, "propose", "analyst_1", t, "", "low")
    key.append(("BAD002", "missing_reason"))
    ov("BAD003", some[2], lock.period_month, "propose", "analyst_2", lock.locked_at + dt.timedelta(days=3),
       "Backdated change after the month closed", "high")
    key.append(("BAD003", "locked_period_edit"))
    ov("BAD004", some[3], open_month, "propose", "analyst_3", t, "Owner verified on a video call", "medium")
    ov("BAD004", some[3], open_month, "approve", "analyst_4", t + dt.timedelta(hours=2))
    key.append(("BAD004", "unauthorised_approver"))
    ov("BAD005", some[4], open_month, "propose", "analyst_5", t, "Fraud alert from the card network", "high")
    ov("BAD005", some[4], open_month, "approve", "checker_2", t + dt.timedelta(hours=1))
    ov("BAD006", some[4], open_month, "propose", "analyst_6", t + dt.timedelta(hours=3), "Second opinion: lower it", "low")
    ov("BAD006", some[4], open_month, "approve", "checker_3", t + dt.timedelta(hours=4))
    key.append(("BAD006", "duplicate_live_override"))

    planted = pd.DataFrame(rows)
    merged = pd.concat([events.drop(columns=["event_id"]), planted], ignore_index=True)
    merged = merged.sort_values(["event_ts", "override_id"]).reset_index(drop=True)
    merged.insert(0, "event_id", np.arange(1, len(merged) + 1))
    return merged, pd.DataFrame(key, columns=["override_id", "violation"])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="warehouse/risk.duckdb")
    ap.add_argument("--merchants", type=int, default=20000)
    ap.add_argument("--year", type=int, default=2025)
    ap.add_argument("--overrides-per-month", type=int, default=None)
    ap.add_argument("--plant-violations", action="store_true")
    ap.add_argument("--seed", type=int, default=202)
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    per_month = args.overrides_per_month or max(10, args.merchants // 160)
    merchants = make_merchants(rng, args.merchants, args.year)
    metrics = make_metrics(rng, merchants, args.year)
    users = make_users()
    locks = make_locks(args.year)
    events = make_events(rng, merchants, metrics, users, locks, args.year, per_month)
    tables = {"merchants": merchants, "merchant_monthly_metrics": metrics, "users": users,
              "period_locks": locks, "override_events": events}
    if args.plant_violations:
        tables["override_events"], tables["fixture_planted_violations"] = plant_violations(events, merchants, locks, args.year)

    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(args.db) as con:
        con.execute("create schema if not exists bronze")
        for name, df in tables.items():
            con.register("df", df)
            con.execute(f"create or replace table bronze.{name} as select * from df")
            con.unregister("df")
            print(f"bronze.{name:<26} {len(df):>9,} rows")


if __name__ == "__main__":
    main()
