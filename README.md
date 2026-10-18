# 2. Bundesliga 2026/27 — standalone dashboard

This repository contains an independent, mobile-first dashboard for the German **2. Bundesliga only**. It is separate from Bundesliga 1 and the other league projects.

## Current snapshot

- Result cutoff: **18 October 2026, 12:20 America/Sao_Paulo (BRT)**.
- 18 clubs; 34 matchdays; 306 DFL-listed fixtures.
- 72 confirmed final results (matchdays 1–8); 234 later fixtures have no scores.
- Computed played, W-D-L, goals for/against/difference and points match all 18 clubs on the current DFL table and ESPN's independent current table.
- `2bundesliga_2026_27_results_verified.csv` is the separate league dataset.
- `2bundesliga_2026_27_sources_validation.json` is the source log and saved official/independent table snapshots.
- `2bundesliga_2026_27_dashboard_template.html` and `build_2bundesliga_2026_27_dashboard.py` are the self-contained builder/validator.

## Refresh workflow (06:00 BRT updater)

1. Retrieve the current official DFL table and each relevant `Bundesliga 2` matchday page: https://www.bundesliga.com/en/2bundesliga/table and https://www.bundesliga.com/en/2bundesliga/matchday. The round-specific routes are stored in each CSV row.
2. Update only the 2. Bundesliga CSV rows. Enter a score only when the DFL matchday page confirms a final result. Keep unfinished or scheduled scores blank. Preserve official matchday assignment and update published reschedules/times only from DFL.
3. Refresh the official and independent table snapshots and source retrieval times in `2bundesliga_2026_27_sources_validation.json`; use ESPN's German 2. Bundesliga standings as the independent table check. If any comparison remains unresolved, stop before publication.
4. Run `python3 build_2bundesliga_2026_27_dashboard.py`. It validates all 306 unique pairings, nine fixtures per round, 18-club coverage, 17 home/17 away per team, score/status consistency, and the table against both snapshots, then deterministically writes `index.html`.
5. Commit/publish only after the script passes. Do not let the refresh process read or write Bundesliga 1 files, and do not infer unannounced individual dates from broad DFL round ranges.

No cron job is configured by this repository build.

## Dashboard controls

- League table with promotion/relegation zones and recent form.
- Club profiles with last five, overall/home/away splits and next fixture.
- Official results/fixtures filters by status, round and club.
- Season H2H selector, 1–X–2 / goal Poisson estimates, and eight Top-5 ranking categories with overall/home/away denominator cuts.
- Sources, cutoff, competition rules, methods and limitations.

The early-season projection is descriptive, highly uncertain, and not betting advice.
