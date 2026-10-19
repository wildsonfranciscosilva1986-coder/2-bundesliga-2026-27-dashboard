#!/usr/bin/env python3
"""Fetch the complete official DFL 2. Bundesliga calendar/table and ESPN-check every final."""
from __future__ import annotations
import csv,json,re,unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.request import Request,urlopen
import requests
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parent
BASE='https://www.bundesliga.com/en/2bundesliga/matchday/2026-2027/{}'
TABLE_URL='https://www.bundesliga.com/en/2bundesliga/table'
ESPN='https://site.api.espn.com/apis/site/v2/sports/soccer/ger.2/scoreboard'
SEASON='DFL-SEA-0001KA';COMP='DFL-COM-000002';CUT=datetime.now(ZoneInfo('America/Sao_Paulo')).strftime('%Y-%m-%d %H:%M America/Sao_Paulo')
BERLIN=ZoneInfo('Europe/Berlin')
HEADERS={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36','Accept':'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8','Accept-Language':'en-US,en;q=0.9','Referer':'https://www.bundesliga.com/en/2bundesliga/','Origin':'https://www.bundesliga.com','Cache-Control':'no-cache'}

# Stable user-facing club names used by the existing panel.
CANON={'Bielefeld':'Arminia Bielefeld','Bochum':'Bochum','Braunschweig':'Eintracht Braunschweig','Darmstadt':'Darmstadt','Dresden':'Dynamo Dresden','FC Energie':'Energie Cottbus','Fürth':'Greuther Fürth','Hannover':'Hannover 96','Heidenheim':'Heidenheim','Hertha BSC':'Hertha Berlin','Kaiserslautern':'Kaiserslautern','Karlsruhe':'Karlsruhe','Kiel':'Holstein Kiel','Magdeburg':'Magdeburg','Nürnberg':'Nuremberg','Osnabrück':'VfL Osnabrück','St. Pauli':'St. Pauli','Wolfsburg':'Wolfsburg'}
ALIASES={'nurnberg':'Nuremberg','1 fc nurnberg':'Nuremberg','fc energie cottbus':'Energie Cottbus','energie cottbus':'Energie Cottbus','hertha bsc':'Hertha Berlin','hertha berlin':'Hertha Berlin','vfl bochum 1848':'Bochum','bochum':'Bochum','dsc arminia bielefeld':'Arminia Bielefeld','arminia bielefeld':'Arminia Bielefeld','1 fc heidenheim 1846':'Heidenheim','heidenheim':'Heidenheim','sv darmstadt 98':'Darmstadt','darmstadt 98':'Darmstadt','sg dynamo dresden':'Dynamo Dresden','dynamo dresden':'Dynamo Dresden','spvgg greuther furth':'Greuther Fürth','greuther furth':'Greuther Fürth','hannover 96':'Hannover 96','1 fc kaiserslautern':'Kaiserslautern','karlsruher sc':'Karlsruhe','holstein kiel':'Holstein Kiel','1 fc magdeburg':'Magdeburg','vfl osnabruck':'VfL Osnabrück','fc st pauli':'St. Pauli','vfl wolfsburg':'Wolfsburg','eintracht braunschweig':'Eintracht Braunschweig'}

def norm(s):
    s=unicodedata.normalize('NFKD',s or '').encode('ascii','ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+',' ',s).strip()

def parse_state(html):
    soup=BeautifulSoup(html,'html.parser');node=soup.find('script',id='ng-state')
    if not node or not node.string:raise RuntimeError('Official DFL page has no ng-state payload')
    return json.loads(node.string)

def get_page(url):
    response=requests.get(url,headers=HEADERS,timeout=45);response.raise_for_status();return response.text

def parse_matchday(rnd):
    url=BASE.format(rnd);state=parse_state(get_page(url));candidates=[]
    for key,value in state.items():
        if 'DFL-COM-000002' in key and 'matchesmatchday' in key and isinstance(value,list):
            if len(value)==9 and all(x.get('dflDatalibraryCompetitionId')==COMP and int(x.get('matchday',-1))==rnd for x in value):
                candidates.append(value)
    if len(candidates)!=1:raise RuntimeError(f'DFL matchday {rnd} data is missing/ambiguous; candidates={len(candidates)}')
    matches=candidates[0];rows=[]
    status_map={'FINAL_WHISTLE':'finished','PRE_MATCH':'scheduled','LIVE':'in_progress','FIRST_HALF':'in_progress','HALF_TIME':'in_progress','SECOND_HALF':'in_progress','EXTRA_TIME':'in_progress','PENALTY_SHOOTOUT':'in_progress','INTERRUPTED':'in_progress','POSTPONED':'postponed','CANCELLED':'cancelled','ABANDONED':'abandoned'}
    for m in matches:
        if m.get('dflDatalibrarySeasonId')!=SEASON or m.get('dflDatalibraryCompetitionId')!=COMP:raise RuntimeError(f'DFL competition/season mismatch: {m.get("matchId")}')
        raw_status=m.get('matchStatus','');status=status_map.get(raw_status)
        if not status:raise RuntimeError(f'Unknown DFL match status {raw_status!r} for {m.get("matchId")}')
        teams=m.get('teams',{});home_raw=teams.get('home',{}).get('nameShort','');away_raw=teams.get('away',{}).get('nameShort','')
        home=CANON.get(home_raw);away=CANON.get(away_raw)
        if not home or not away:raise RuntimeError(f'Unmapped DFL team name: {home_raw!r} / {away_raw!r}')
        score=m.get('score') or {}
        if status=='finished':
            hg=(score.get('home') or {}).get('fulltime');ag=(score.get('away') or {}).get('fulltime')
            if hg is None or ag is None or int(hg)<0 or int(ag)<0:raise RuntimeError(f'DFL FINAL_WHISTLE lacks score: {m.get("matchId")}')
            hg,ag=str(int(hg)),str(int(ag))
        else:hg=ag=''
        fixed=m.get('matchDateFixed') is True
        raw_kickoff=m.get('kickOff') or m.get('plannedKickOff')
        date='';kickoff='';date_range=''
        if fixed and raw_kickoff:
            dt=datetime.fromisoformat(raw_kickoff.replace('Z','+00:00')).astimezone(BERLIN)
            date=dt.strftime('%Y-%m-%d');kickoff=dt.strftime('%H:%M')
        else:
            rng=m.get('matchdayRange') or {};start=rng.get('start');end=rng.get('end')
            if start and end:
                sdt=datetime.fromisoformat(start.replace('Z','+00:00')).astimezone(BERLIN);edt=datetime.fromisoformat(end.replace('Z','+00:00')).astimezone(BERLIN)
                date_range=f'{sdt.strftime("%a %d %b")} – {edt.strftime("%a %d %b")}'
        slug=(m.get('slugs') or {}).get('slugLong','')
        match_url=f'{BASE.format(rnd)}/{slug}/liveticker' if slug else url
        rows.append({'round':rnd,'date':date,'date_range':date_range,'date_label':date_range or date,'kickoff_time':kickoff,'timezone':'Europe/Berlin','home':home,'away':away,'home_goals':hg,'away_goals':ag,'status':status,'official_match_url':match_url,'official_match_id':m.get('matchId',''),'dfl_status':raw_status})
    return {'url':url,'retrieved_at':CUT,'matches':matches},rows

with ThreadPoolExecutor(max_workers=5) as pool:
    futures=[pool.submit(parse_matchday,rnd) for rnd in range(1,35)]
    fetched=[f.result() for f in as_completed(futures)]
fetched.sort(key=lambda x:int(re.search(r'/([0-9]+)$',x[0]['url']).group(1)))
rows=[row for _,group in fetched for row in group]
if len(rows)!=306 or len({r['official_match_id'] for r in rows})!=306:raise RuntimeError(f'Expected 306 unique official fixtures; got {len(rows)}')
clubs=sorted({r['home'] for r in rows}|{r['away'] for r in rows})
if len(clubs)!=18:raise RuntimeError(f'Expected 18 clubs, found {len(clubs)}')
for rnd in range(1,35):
    rr=[r for r in rows if r['round']==rnd]
    if len(rr)!=9 or Counter([r['home'] for r in rr]+[r['away'] for r in rr])!=Counter(clubs):raise RuntimeError(f'DFL round {rnd} does not contain each of 18 clubs exactly once')
for team in clubs:
    if sum(r['home']==team or r['away']==team for r in rows)!=34:raise RuntimeError(f'{team} does not have 34 DFL fixture rows')
finished=[r for r in rows if r['status']=='finished'];counts={s:sum(r['status']==s for r in rows) for s in sorted({r['status'] for r in rows})}
if not finished:raise RuntimeError('No DFL FullTime results returned')

# The official DFL live table is parsed from its own table page ng-state.
table_url='https://www.bundesliga.com/en/2bundesliga/table';table_state=parse_state(get_page(table_url))
keys=[k for k in table_state if 'DFL-COM-000002' in k and k.endswith('/liveTable')]
if len(keys)!=1:raise RuntimeError(f'DFL current table payload missing/ambiguous: {keys}')
table_payload=table_state[keys[0]];entries=table_payload.get('entries') or []
if len(entries)!=18:raise RuntimeError(f'DFL live table must have 18 rows, got {len(entries)}')

def table_row(entry,position=None):
    club=CANON.get(entry['club']['nameShort'])
    if not club:raise RuntimeError(f'Unmapped DFL table club {entry["club"].get("nameShort")}')
    return {'club':club,'position':int(entry.get('rank',position or 0)),'MP':int(entry['gamesPlayed']),'W':int(entry['wins']),'D':int(entry['draws']),'L':int(entry['losses']),'GF':int(entry['goalsScored']),'GA':int(entry['goalsAgainst']),'GD':int(entry['goalDifference']),'Pts':int(entry['points'])}
official=sorted([table_row(x) for x in entries],key=lambda x:x['position'])
if {r['club'] for r in official}!=set(clubs):raise RuntimeError('Current DFL table roster differs from fixture schedule')

stats={t:{'MP':0,'W':0,'D':0,'L':0,'GF':0,'GA':0,'GD':0,'Pts':0} for t in clubs}
for r in finished:
    hg,ag=int(r['home_goals']),int(r['away_goals']);h,a=stats[r['home']],stats[r['away']]
    h['MP']+=1;a['MP']+=1;h['GF']+=hg;h['GA']+=ag;a['GF']+=ag;a['GA']+=hg
    if hg>ag:h['W']+=1;a['L']+=1;h['Pts']+=3
    elif ag>hg:a['W']+=1;h['L']+=1;a['Pts']+=3
    else:h['D']+=1;a['D']+=1;h['Pts']+=1;a['Pts']+=1
for s in stats.values():s['GD']=s['GF']-s['GA']
off={r['club']:r for r in official}
for team in clubs:
    diff={k:(stats[team][k],off[team][k]) for k in ['MP','W','D','L','GF','GA','GD','Pts'] if stats[team][k]!=off[team][k]}
    if diff:raise RuntimeError(f'DFL final-only table does not match current official table for {team}: {diff}')

# Build independent ESPN lookup for each official final and recompute ESPN's own table.
ESPN_ALIASES={norm(k):v for k,v in {**{x:x for x in clubs},'Nürnberg':'Nuremberg','1. FC Nürnberg':'Nuremberg','1 FC Nurnberg':'Nuremberg','FC Energie Cottbus':'Energie Cottbus','Energie Cottbus':'Energie Cottbus','Hertha BSC':'Hertha Berlin','VfL Bochum 1848':'Bochum','DSC Arminia Bielefeld':'Arminia Bielefeld','1. FC Heidenheim 1846':'Heidenheim','SV Darmstadt 98':'Darmstadt','SG Dynamo Dresden':'Dynamo Dresden','SpVgg Greuther Fürth':'Greuther Fürth','1. FC Kaiserslautern':'Kaiserslautern','Karlsruher SC':'Karlsruhe','Holstein Kiel':'Holstein Kiel','1. FC Magdeburg':'Magdeburg','VfL Osnabrück':'VfL Osnabrück','VfL Bochum':'Bochum','TSV Eintracht Braunschweig':'Eintracht Braunschweig','FC St. Pauli':'St. Pauli','VfL Wolfsburg':'Wolfsburg'}.items()}
# Include DFL short names and all aliases after normalization.
for k,v in CANON.items():ESPN_ALIASES[norm(k)]=v

all_dates=set()
for r in finished:
    d=datetime.strptime(r['date'],'%Y-%m-%d').date()
    for delta in (-1,0,1):all_dates.add((d+timedelta(days=delta)).strftime('%Y%m%d'))
def espn_day(day):
    url=ESPN+'?dates='+day
    req=Request(url,headers={'User-Agent':'Mozilla/5.0','Accept':'application/json'})
    with urlopen(req,timeout=40) as response:return day,url,json.loads(response.read())
events={};queried=[]
with ThreadPoolExecutor(max_workers=8) as pool:
    futures=[pool.submit(espn_day,d) for d in sorted(all_dates)]
    for future in as_completed(futures):
        day,url,payload=future.result();queried.append(day)
        for e in payload.get('events',[]):
            comp=e.get('competitions',[{}])[0];by={x.get('homeAway'):x for x in comp.get('competitors',[])};home,away=by.get('home',{}),by.get('away',{})
            hn=ESPN_ALIASES.get(norm(home.get('team',{}).get('displayName','')));an=ESPN_ALIASES.get(norm(away.get('team',{}).get('displayName','')))
            if not hn or not an:continue
            key=(hn,an);rec={'event_id':e.get('id',''),'status':comp.get('status',{}).get('type',{}).get('name',''),'home_goals':str(home.get('score','')),'away_goals':str(away.get('score','')),'url':url}
            if key not in events or (rec['status']=='STATUS_FULL_TIME' and events[key]['status']!='STATUS_FULL_TIME'):events[key]=rec
cross=[];missing=[];mismatch=[]
for r in finished:
    event=events.get((r['home'],r['away']))
    if not event:
        missing.append({'round':r['round'],'home':r['home'],'away':r['away'],'date':r['date']});continue
    same=event['status']=='STATUS_FULL_TIME' and event['home_goals']==str(r['home_goals']) and event['away_goals']==str(r['away_goals'])
    record={'round':r['round'],'official_match_id':r['official_match_id'],'home':r['home'],'official_home_goals':r['home_goals'],'espn_home_goals':event['home_goals'],'away':r['away'],'official_away_goals':r['away_goals'],'espn_away_goals':event['away_goals'],'espn_status':event['status'],'match':same,'espn_event_id':event['event_id'],'official_match_url':r['official_match_url'],'independent_match_url':event['url']}
    cross.append(record)
    if not same:mismatch.append(record)
if missing or mismatch:raise RuntimeError(json.dumps({'missing':missing,'mismatches':mismatch},ensure_ascii=False,indent=2))
espn_stats={t:{'MP':0,'W':0,'D':0,'L':0,'GF':0,'GA':0,'GD':0,'Pts':0} for t in clubs}
for r in cross:
    hg,ag=int(r['espn_home_goals']),int(r['espn_away_goals']);h,a=espn_stats[r['home']],espn_stats[r['away']]
    h['MP']+=1;a['MP']+=1;h['GF']+=hg;h['GA']+=ag;a['GF']+=ag;a['GA']+=hg
    if hg>ag:h['W']+=1;a['L']+=1;h['Pts']+=3
    elif ag>hg:a['W']+=1;h['L']+=1;a['Pts']+=3
    else:h['D']+=1;a['D']+=1;h['Pts']+=1;a['Pts']+=1
for s in espn_stats.values():s['GD']=s['GF']-s['GA']
for t in clubs:
    if stats[t]!=espn_stats[t]:raise RuntimeError(f'ESPN independently recomputed table mismatch for {t}: {stats[t]} vs {espn_stats[t]}')

# Persist only after every official/independent validation has succeeded.
meta={'competition':'2. Bundesliga','season':'2026/27','as_of':CUT,'result_cutoff':CUT,'official_table_captured':CUT,'independent_table_captured':CUT,'fixture_snapshot_retrieved':CUT,
 'coverage':{'teams':18,'rounds':34,'official_fixtures':306,'final_results':len(finished),'scheduled_fixtures':counts.get('scheduled',0),'completed_rounds':','.join(map(str,sorted({int(r['round']) for r in finished})))},
 'standings_snapshot':official,
 'independent_table_snapshot':[{'club':t,'position':i+1,**espn_stats[t]} for i,t in enumerate(sorted(clubs,key=lambda t:(-espn_stats[t]['Pts'],-espn_stats[t]['GD'],-espn_stats[t]['GF'],t)))],
 'sources':[{'name':'Official DFL 2. Bundesliga matchday pages','url_pattern':BASE,'matchdays_checked':34},{'name':'Official DFL current table','url':TABLE_URL,'clubs_checked':18},{'name':'Independent ESPN results','url':ESPN,'finished_scores_checked':len(cross),'identical_final_scores':len(cross),'mismatches':0}],
 'result_reconciliation':{'table_page_discrepancy':{'reported_total_played_matches':len(finished),'current_status':'Current DFL table matches all final-only results.'},'cross_checked_disputed_fixtures':[{'round':r['round'],'home':r['home'],'away':r['away'],'score':f"{r['official_home_goals']}-{r['official_away_goals']}",'official_match_url':r['official_match_url'],'independent_match_url':r['independent_match_url']} for r in cross]},
 'validation':{'status':'PASS','official_score_derived_table':'PASS 18/18','independent_score_derived_table':'PASS 18/18','final_scores_checked':len(cross),'schedule_integrity':'PASS 306 fixtures, 9 per round, every club once per round.'}}
meta['source_validation']={'status':'PASS','official_table_matches':18,'espn_table_matches':18,'espn_scores_checked':len(cross),'score_mismatches':0}

SNAP=ROOT/'source_snapshots';SNAP.mkdir(exist_ok=True)
for snapshot,rows_for_round in fetched:
    rnd=int(re.search(r'/([0-9]+)$',snapshot['url']).group(1))
    (SNAP/f'dfl_matchday_{rnd:02d}_latest.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(SNAP/'dfl_table_latest.json').write_text(json.dumps({'url':TABLE_URL,'retrieved_at':CUT,'entries':entries},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
with (ROOT/'2bundesliga_2026_27_results_verified.csv').open('w',encoding='utf-8',newline='') as f:
    fields=['round','date','date_range','kickoff_time','timezone','home','away','home_goals','away_goals','status','official_match_url','official_match_id']
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows([{k:r.get(k,'') for k in fields} for r in rows])
(ROOT/'2bundesliga_2026_27_sources_validation.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
with (SNAP/'espn_results_crosscheck_latest.json').open('w',encoding='utf-8') as f:json.dump({'source':ESPN,'cutoff':CUT,'checked':len(cross),'mismatches':mismatch,'missing':missing,'results':cross},f,ensure_ascii=False,indent=2)
validation={'competition':'2. Bundesliga 2026/27','cutoff':CUT,'official_fixture_slots':len(rows),'rounds':34,'clubs':len(clubs),'status_counts':counts,'final_results':len(finished),'scheduled':counts.get('scheduled',0),'official_table_reconciliation':{'all_stats_match':True,'clubs_compared':18,'mismatches':0},'independent_ESPN_scores':{'checked':len(cross),'exact_fulltime_matches':len(cross),'mismatches':0},'independent_ESPN_table':{'all_stats_match':True,'clubs_compared':18,'mismatches':0},'fixture_structure':'PASS: 306 unique fixtures, 9 per round, each club once per round.'}
(ROOT/'2bundesliga_2026_27_validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
text=[f"2. Bundesliga 2026/27 validation — cutoff {CUT}",f"Coverage: {len(rows)}/306 official fixtures; 34 rounds × 9; 18 clubs.",f"Statuses: {len(finished)} confirmed finals; {counts.get('scheduled',0)} scheduled.","Official DFL table reconciliation: PASS all 18 clubs across played, W-D-L, GF/GA/GD and points.",f"Independent ESPN final-score check: PASS {len(cross)}/{len(finished)} exact STATUS_FULL_TIME results.","Independent ESPN-derived table: PASS all 18 club vectors.","No future or nonfinal score is included."]
(ROOT/'2bundesliga_2026_27_validation.txt').write_text('\n'.join(text)+'\n',encoding='utf-8')
print(json.dumps({'cutoff':CUT,'fixtures':len(rows),'rounds':34,'clubs':len(clubs),'status_counts':counts,'finals':len(finished),'DFL_table':'18/18 PASS','ESPN_scores':f'{len(cross)}/{len(finished)} PASS','ESPN_table':'18/18 PASS'},ensure_ascii=False,indent=2))
