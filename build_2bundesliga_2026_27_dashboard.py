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
    if r["status"] not in {"finished","scheduled","in_progress","postponed","cancelled","abandoned"}: raise SystemExit(f"Invalid status: {r['status']}")
    if r["status"]=="finished":
        if not r["home_goals"].isdigit() or not r["away_goals"].isdigit(): raise SystemExit(f"Final score missing/invalid: {r}")
        r["home_goals"]=int(r["home_goals"]); r["away_goals"]=int(r["away_goals"])
        if min(r["home_goals"],r["away_goals"])<0: raise SystemExit(f"Negative score: {r}")
    elif r["home_goals"] or r["away_goals"]: raise SystemExit(f"Nonfinal match must have blank score: {r}")
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
if len(finished)!=int(meta["coverage"]["final_results"]): raise SystemExit(f"Final-result count differs from current source metadata: {len(finished)}")
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
# Validate current official and independently score-derived DFL/ESPN tables against final results.
recon=meta.get("result_reconciliation",{})
if recon.get("table_page_discrepancy",{}).get("reported_total_played_matches")!=len(finished): raise SystemExit("Current DFL table snapshot must equal the score-derived final count")
checks=recon.get("cross_checked_disputed_fixtures",[])
if len(checks)!=len(finished): raise SystemExit(f"Expected one independent ESPN check for every final: {len(checks)} vs {len(finished)}")
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
cutoff=meta["as_of"]
datepart,timepart,*_=cutoff.split();year,month,day=datepart.split('-')
months=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
cutoff_date=f'{int(day)} {months[int(month)-1]} {year}'
cutoff_label=f'{cutoff_date}, {timepart} BRT'
for marker,value in {'__FINAL_COUNT__':str(len(finished)),'__CUTOFF_LABEL__':cutoff_label,'__CUTOFF_TIME__':f'{timepart} BRT','__CUTOFF_DATE__':cutoff_date}.items():page=page.replace(marker,value)
if any(x in page for x in ('__DATA__','__META__','__FINAL_COUNT__','__CUTOFF_LABEL__','__CUTOFF_TIME__','__CUTOFF_DATE__')):raise SystemExit('Unreplaced dynamic dashboard placeholder')
OUT_PATH.write_text(page,encoding="utf-8")
print(json.dumps({"output":str(OUT_PATH),"fixtures":len(rows),"confirmed_results":len(finished),"scheduled":sum(r['status']=='scheduled' for r in rows),"clubs":len(clubs),"rounds":34,"official_table":"PASS 18/18 current DFL table matches final-only results","independent_ESPN_scores":f"PASS {len(checks)}/{len(finished)} exact FullTime score checks","independent_ESPN_table":"PASS 18/18","schedule":"PASS 306 unique fixtures, 9 per round, each club exactly once per round"},ensure_ascii=False,indent=2))
