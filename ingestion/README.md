# Ingestion

`generate_risk_data.py` writes synthetic merchants, monthly risk signals, users, period locks and the
override audit log into `bronze`:

- **Full (default):** 20,000 merchants, Jan–Dec 2025, about 3 s.
- **CI:** `--merchants 600 --plant-violations`. This writes events that break each control straight into the log, plus an answer key (`fixture_planted_violations`).

Override history is built by replaying `app/workflow.py`, the same rules the app enforces, so every generated event is one the app would accept.
