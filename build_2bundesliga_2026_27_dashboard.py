#!/usr/bin/env python3
"""Validate and deterministically build the 2. Bundesliga 2026/27 dashboard.

No network requests are made. Update only from confirmed DFL matchday pages, then run:
  python3 build_2bundesliga_2026_27_dashboard.py
"""
from __future__ import annotations
import csv, json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
CSV_PATH = ROOT / "2bundesliga_2026_27_results_verified.csv"
META_PATH = ROOT / "2bundesliga_2026_27_sources_validation.json"
TEMPLATE_PATH = ROOT / "2bundesliga_2026_27_dashboard_template.html"
OUT_PATH = ROOT / "index.html"
with CSV_PATH.open(newline="", encoding="utf-8") as f:
    raw = list(csv.DictReader(f))
meta = json.loads(META_PATH.read_text(encoding="utf-8"))
template = TEMPLATE_PATH.read_text(encoding="utf-8")
if not raw or "__DATA__" not in template or "__META__" not in template:
    raise SystemExit("Missing CSV rows or template data placeholders")
required = {"round","date","date_range","kickoff_time","timezone","home","away","home_goals","away_goals","status","official_match_url"}
if required - set(raw[0]): raise SystemExit(f"CSV missing columns: {required-set(raw[0])}")
rows=[]
for source in raw:
    r=dict(source); r["round"]=int(r["round"])
    if not 1<=r["round"]<=34: raise SystemExit(f"Invalid round: {r}")
    if r["home"]==r["away"] or not r["home"] or not r["away"]: raise SystemExit(f"Invalid fixture: {r}")
    if r["status"] not in {"finished","scheduled"}: raise SystemExit(f"Invalid status: {r['status']}")
    if r["status"]=="finished":
        if not r["home_goals"].isdigit() or not r["away_goals"].isdigit(): raise SystemExit(f"Final score missing/invalid: {r}")
        r["home_goals"]=int(r["home_goals"]); r["away_goals"]=int(r["away_goals"])
        if min(r["home_goals"],r["away_goals"])<0: raise SystemExit(f"Negative score: {r}")
    elif r["home_goals"] or r["away_goals"]: raise SystemExit(f"Scheduled match must have blank score: {r}")
    # Add a BRT presentation time, preserving the official local time and zone.
    r["kickoff_brt"]=""
    if r["kickoff_time"]:
        if not r["date"] or r["timezone"]!="Europe/Berlin": raise SystemExit(f"Kickoff lacks date/timezone: {r}")
        dt=datetime.fromisoformat(r["date"]+"T"+r["kickoff_time"]).replace(tzinfo=ZoneInfo("Europe/Berlin"))
        r["kickoff_brt"]=dt.astimezone(ZoneInfo("America/Sao_Paulo")).strftime("%H:%M")
    # Disambiguate official date ranges with their season year; individual days remain unguessed.
    if r["date_range"]:
        year="2026" if any(mon in r["date_range"] for mon in ("Dec",)) else "2027"
        r["date_range"] += " " + year
    rows.append(r)
if len(rows)!=306 or meta["coverage"]["official_fixtures"]!=306: raise SystemExit(f"Expected 306 fixtures, got {len(rows)}")
if len({(r['round'],r['home'],r['away']) for r in rows})!=306: raise SystemExit("Duplicate fixture key")
clubs=sorted({r["home"] for r in rows}|{r["away"] for r in rows})
if len(clubs)!=18 or len(meta["standings_snapshot"])!=18: raise SystemExit("Expected 18 competition clubs and table rows")
for rnd in range(1,35):
    rr=[r for r in rows if r["round"]==rnd]
    if len(rr)!=9 or Counter([r["home"] for r in rr]+[r["away"] for r in rr])!=Counter(clubs): raise SystemExit(f"Round {rnd} has invalid schedule coverage")
for club in clubs:
    if sum(r["home"]==club for r in rows)!=17 or sum(r["away"]==club for r in rows)!=17: raise SystemExit(f"Invalid venue split: {club}")
finished=[r for r in rows if r["status"]=="finished"]
if len(finished)!=72 or meta["coverage"]["final_results"]!=len(finished): raise SystemExit(f"Expected 72 confirmed finals, found {len(finished)}")
if any(r["round"]>8 for r in finished) or any(r["round"]<=8 and r["status"]!="finished" for r in rows): raise SystemExit("Rounds 1–8 must be final; later rounds must have no score yet")
stats={c:{"MP":0,"W":0,"D":0,"L":0,"GF":0,"GA":0,"Pts":0} for c in clubs}
for r in finished:
    h,a=stats[r["home"]],stats[r["away"]]; hg,ag=r["home_goals"],r["away_goals"]
    h["MP"]+=1;a["MP"]+=1;h["GF"]+=hg;h["GA"]+=ag;a["GF"]+=ag;a["GA"]+=hg
    if hg>ag: h["W"]+=1;a["L"]+=1;h["Pts"]+=3
    elif ag>hg: a["W"]+=1;h["L"]+=1;a["Pts"]+=3
    else: h["D"]+=1;a["D"]+=1;h["Pts"]+=1;a["Pts"]+=1
ordered=sorted(clubs,key=lambda c:(-stats[c]["Pts"],-(stats[c]["GF"]-stats[c]["GA"]),-stats[c]["GF"],c))
computed=[]
for pos,c in enumerate(ordered,1):
    s=stats[c];computed.append({"club":c,"position":pos,**s,"GD":s["GF"]-s["GA"]})
# Validate the saved 12:11/12:20 BRT snapshots against the result-derived table.
# Later standings-page responses are separately logged because both lagged the Sunday finals.
recon=meta.get("result_reconciliation",{})
if recon.get("table_page_discrepancy",{}).get("reported_total_played_matches")!=len(finished): raise SystemExit("Current DFL table snapshot must equal the score-derived final count")
checks=recon.get("cross_checked_disputed_fixtures",[])
if len(checks)!=3: raise SystemExit("Expected three fixture-level discrepancy checks")
for item in checks:
    key=(int(item["round"]),item["home"],item["away"])
    found=[r for r in rows if (r["round"],r["home"],r["away"])==key]
    if len(found)!=1: raise SystemExit(f"Disputed fixture key missing or duplicated: {key}")
    row=found[0]
    score=f"{row['home_goals']}-{row['away_goals']}"
    if row["status"]!="finished" or score!=item["score"] or not item.get("official_match_url") or not item.get("independent_match_url"):
        raise SystemExit(f"Disputed fixture evidence does not match verified final row: {key}")
official={x["club"]:x for x in meta["standings_snapshot"]}
independent={x["club"]:x for x in meta["independent_table_snapshot"]}
if set(official)!=set(clubs) or set(independent)!=set(clubs): raise SystemExit("Official/independent table club set mismatch")
fields=["MP","W","D","L","GF","GA","GD","Pts"]
for c in clubs:
    vals={"MP":stats[c]["MP"],"W":stats[c]["W"],"D":stats[c]["D"],"L":stats[c]["L"],"GF":stats[c]["GF"],"GA":stats[c]["GA"],"GD":stats[c]["GF"]-stats[c]["GA"],"Pts":stats[c]["Pts"]}
    if any(vals[k]!=official[c][k] for k in fields): raise SystemExit(f"Score table differs from official DFL for {c}: {vals} vs {official[c]}")
    if any(vals[k]!=independent[c][k] for k in fields): raise SystemExit(f"Score table differs from ESPN for {c}: {vals} vs {independent[c]}")
if meta["validation"].get("status")!="PASS": raise SystemExit("Source log validation status is not PASS")
rows.sort(key=lambda r:(r["round"],r["date"] or r["date_range"],r["home"]))
data=json.dumps(rows,ensure_ascii=False,separators=(",",":" )).replace("</","<\\/")
metadata=json.dumps(meta,ensure_ascii=False,separators=(",",":" )).replace("</","<\\/")
page=template.replace("__DATA__",data).replace("__META__",metadata)
OUT_PATH.write_text(page,encoding="utf-8")
print(json.dumps({"output":str(OUT_PATH),"fixtures":len(rows),"confirmed_results":len(finished),"scheduled":len(rows)-len(finished),"clubs":len(clubs),"rounds":34,"saved_12_11_12_20_table_snapshots":"PASS 18/18 clubs against the 72-result dataset (historical snapshots; not the later stale standings response)","current_official_table":"PASS: current DFL live table reconciles with all 72 score-derived finals; the earlier 69-match response is retained as historical evidence","fixture_level_reconciliation":"PASS 3/3 disputed finals match unique CSV rows and DFL+ESPN source links","schedule":"PASS 306 unique fixtures, 9 per round, 17 home/away per club"},ensure_ascii=False,indent=2))
