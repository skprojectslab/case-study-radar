import json,yaml
from pathlib import Path
from datetime import datetime,timezone
from .http import get
from .utils import normalize_url,content_hash
from .adapters.audit_discovery import candidate_links,extract_detail
ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/"data"; CONFIG=ROOT/"config/sources.yaml"
def load(p,d):
 if not p.exists(): return d
 try:return json.loads(p.read_text(encoding="utf-8"))
 except:return d
def save(p,x): p.write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding="utf-8")
def run():
 sources=yaml.safe_load(CONFIG.read_text(encoding="utf-8")); history=load(DATA/"history.json",{}); current={}; errors=[]; run_at=datetime.now(timezone.utc).isoformat()
 for sid,cfg in sources.items():
  for listing in cfg["listing_urls"]:
   try: html=get(listing)
   except Exception as e: errors.append({"source":sid,"stage":"listing","error":str(e)}); continue
   for seed in candidate_links(html,listing):
    u=normalize_url(seed["url"])
    if u in current: continue
    try:
     d=extract_detail(get(u),seed)
     if not d: continue
     r={"market":cfg["market"],"source_id":sid,"source_domain":cfg["domain"],"source_url":listing,"language":cfg["language"],"title":d["title"],"description":d["description"],"url":u,"canonical_url":u,"categories":d["categories"],"published_date":d["published_date"],"client_name":d["client_name"],"first_seen":history.get(u,{}).get("first_seen",run_at),"last_seen":run_at}
     r["content_hash"]=content_hash(r); old=history.get(u); r["status"]="NEW" if old is None else ("UPDATED" if old.get("content_hash")!=r["content_hash"] else "EXISTING"); current[u]=r
    except Exception as e: errors.append({"source":sid,"url":u,"stage":"detail","error":str(e)})
 counts={s:sum(r["status"]==s for r in current.values()) for s in ["NEW","UPDATED","EXISTING"]}
 summary={"run_at":run_at,"sources":len(sources),"discovered":len(current),"new":counts["NEW"],"updated":counts["UPDATED"],"existing":counts["EXISTING"],"errors":len(errors)}
 save(DATA/"history.json",{**history,**current}); save(DATA/"current.json",list(current.values())); save(DATA/"changes.json",{"summary":summary,"changes":[{"type":r["status"],"market":r["market"],"record":r} for r in current.values() if r["status"]!="EXISTING"],"errors":errors})
 by={}
 for r in current.values():
  m=by.setdefault(r["market"],{"records":0,"new":0,"updated":0,"existing":0}); m["records"]+=1; m[r["status"].lower()]+=1
 save(DATA/"audit.json",{"run_at":run_at,"summary":summary,"by_market":by})
 print(json.dumps(summary,indent=2))
if __name__=="__main__":run()
