# DIN Mercado · 2. Bundesliga 2026/27

Standalone, mobile-first interactive panel for the German second division only. The existing GitHub Pages URL remains in this repository.

## Verified data pipeline

- Official DFL matchday pages provide the complete 306-fixture calendar, 34 rounds, official match IDs, current status, kickoff and scores.
- Only DFL `FINAL_WHISTLE` fixtures with both full-time goals are counted; live, postponed, cancelled and unstarted fixtures remain scoreless.
- The current DFL live table must match the result-derived table for all 18 clubs.
- Every final score is independently checked against an ESPN `STATUS_FULL_TIME` event; a separate table recomputed from ESPN scores must also match all 18 clubs.
- Any missing fixture, unknown status, API mismatch, score discrepancy or table disagreement stops the run before an update is committed.

## Automatic refresh

GitHub Actions is configured to run daily at **06:10 America/Sao_Paulo (09:10 UTC)** and supports manual dispatch. The first manual run is the end-to-end check before treating the schedule as proven: it retrieves every DFL matchday and the current table, cross-checks all finals against ESPN, rebuilds and validates the page, then commits only if every check passes. A failed check leaves the public page unchanged. Updates are committed to `main` in place, preserving the existing Pages URL.

The exact cutoff and result counts are regenerated in the metadata, validation report and page on each successful run. Collector dependencies are listed in `requirements.txt`.

## Local equivalent

```sh
python3 -m pip install -r requirements.txt
python3 refresh_2bundesliga.py
python3 build_2bundesliga_2026_27_dashboard.py
```

- Repository: `wildsonfranciscosilva1986-coder/2-bundesliga-2026-27-dashboard`
- Branch/path: `main` / root `index.html`
- Existing page: https://wildsonfranciscosilva1986-coder.github.io/2-bundesliga-2026-27-dashboard/

The 1-X-2 and goal estimates are descriptive, based on the current small sample, and are not calibrated predictions or betting advice.
