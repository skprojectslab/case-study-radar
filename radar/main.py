import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import yaml
from .http import get
from .utils import normalize_url, content_hash
from .adapters.audit_discovery import candidate_links, extract_detail

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"data"
CONFIG=ROOT/"config"/"sources.yaml"
MAX_WORKERS=12
MAX_CANDIDATES_PER_SOURCE=15

def load(path, default):
    if not path.exists(): return default
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return default

def save(path,obj):
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding="utf-8")

def inspect_candidate(item):
    try: return item, extract_detail(get(item["url"]),item), None
    except Exception as e: return item,None,str(e)

def run():
    sources=yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    history=load(DATA/"history.json",{})
    current={}
    errors=[]
    run_at=datetime.now(timezone.utc).isoformat()

    for sid,cfg in sources.items():
        for listing in cfg["listing_urls"]:
            print(f"[{cfg['market']}] loading listing...",flush=True)
            try: html=get(listing,timeout=(2,8))
            except Exception as e:
                errors.append({"source":sid,"stage":"listing","url":listing,"error":str(e)})
                print(f"[{cfg['market']}] listing ERROR: {e}",flush=True)
                continue

            seeds=list(candidate_links(html,listing,cfg))
            unique={normalize_url(x["url"]):x for x in seeds}
            seeds=list(unique.values())[:MAX_CANDIDATES_PER_SOURCE]
            print(f"[{cfg['market']}] candidates found: {len(unique)}; checking: {len(seeds)}",flush=True)

            accepted=0
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
                futures=[pool.submit(inspect_candidate,x) for x in seeds]
                for future in as_completed(futures):
                    seed,detail,error=future.result()
                    if error:
                        errors.append({"source":sid,"stage":"detail","url":seed["url"],"error":error})
                        continue
                    if not detail: continue
                    url=normalize_url(seed["url"])
                    if url in current: continue
                    r={
                        "market":cfg["market"],"source_id":sid,"source_domain":cfg["domain"],
                        "source_url":listing,"language":cfg["language"],"title":detail["title"],
                        "description":detail["description"],"url":url,"canonical_url":url,
                        "categories":detail["categories"],"published_date":detail["published_date"],
                        "client_name":detail["client_name"],
                        "first_seen":history.get(url,{}).get("first_seen",run_at),"last_seen":run_at
                    }
                    r["content_hash"]=content_hash(r)
                    old=history.get(url)
                    r["status"]="NEW" if old is None else ("UPDATED" if old.get("content_hash")!=r["content_hash"] else "EXISTING")
                    current[url]=r
                    accepted+=1
            print(f"[{cfg['market']}] accepted: {accepted}",flush=True)

    counts={s:sum(r["status"]==s for r in current.values()) for s in ("NEW","UPDATED","EXISTING")}
    summary={"run_at":run_at,"sources":len(sources),"discovered":len(current),"new":counts["NEW"],"updated":counts["UPDATED"],"existing":counts["EXISTING"],"errors":len(errors)}
    assert summary["new"]+summary["updated"]+summary["existing"]==summary["discovered"]

    save(DATA/"history.json",{**history,**current})
    save(DATA/"current.json",list(current.values()))
    save(DATA/"changes.json",{"summary":summary,"changes":[{"type":r["status"],"market":r["market"],"record":r} for r in current.values() if r["status"]!="EXISTING"],"errors":errors})
    by={}
    for r in current.values():
        m=by.setdefault(r["market"],{"records":0,"new":0,"updated":0,"existing":0})
        m["records"]+=1
        m[r["status"].lower()]+=1
    save(DATA/"audit.json",{"run_at":run_at,"summary":summary,"by_market":by})
    print("FINAL SUMMARY",flush=True)
    print(json.dumps(summary,indent=2),flush=True)

if __name__=="__main__": run()
