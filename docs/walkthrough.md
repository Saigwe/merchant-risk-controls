# 3-minute walkthrough: Merchant Risk-Rating Controls

A timed script for a Loom recording of about 3 minutes (screen plus camera bubble, 1080p). Say it in your own words; the lines are a guide, not a teleprompter.

**Open these tabs before you press record:** Streamlit app running locally, README, dbt/seeds, dbt/models, GitHub Actions.

| Time | On screen | What to say |
|---|---|---|
| 0:00–0:20 | Portfolio card, then the README title | Risk ratings were being overridden through a spreadsheet upload: no sign-off, no locks, no history. This replaces it with maker-checker approvals, period locks and an audit log that dbt re-audits independently. It found 0 violations across 2,994 events. |
| 0:20–0:45 | README intro and the Data section | It rebuilds, on synthetic data, a control app I built for about 20k merchant accounts at a food-delivery marketplace. There I also fixed a model bug that overstated newly high-risk accounts about 3 times. No employer data is used. |
| 0:45–1:10 | The rules seed in `dbt/seeds` | Eight scoring rules live as data, so thresholds change without SQL, and every rating lists the rules behind it. |
| 1:10–1:35 | The Streamlit app: propose, refused self-approval, checker approval | Watch: I can't approve my own override. A different checker approves it with a reason, and the rating changes. |
| 1:35–2:00 | The audit model over the log | Controls are enforced twice: in the app, by 20 pytest tests, and again in SQL over the whole log. |
| 2:00–2:30 | The answer-key test and the newly-high-risk reconciliation | The test plants five kinds of breach and requires each to be caught. If the prior-month join silently fails, newly high-risk counts inflate 1.9 to 2.4 times, and now the build fails instead. |
| 2:30–2:45 | `docs/design_doc.md`, the options table | The decision I'd defend in an interview: Enforce controls in the app and audit them again in the warehouse, because anything that slips past the app still shows up when the warehouse re-checks the log. |
| 2:45–3:00 | Back to the README top | For a risk team, that means every rating can be explained and every change traced, and a broken report never reaches the committee. The repo, numbers and design doc are linked under the video. |

## Recording checklist
- Close email, chat and notifications. Zoom the browser to 125% so code is readable.
- Run `make fixture-all` once before recording, so CI-style output is fresh if you show it.
- Keep to one take per section; Loom lets you trim. Aim for 2:45 to 3:10.
- Show real numbers on screen as you say them; never estimate on camera.
- Say "synthetic" out loud wherever the README labels data as synthetic.

## After recording
1. Copy the Loom share link.
2. In `README.md`, replace the roadmap line with `- [x] [3-minute Loom walkthrough](<your Loom link>)` and add the link under the title.
3. Add the link to this project's card on saigwe.github.io.
