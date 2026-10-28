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

MAX_WORKERS=8
MAX_CANDIDATES_PER_SOURCE=500

LISTING_TIMEOUT=(8,30)
DETAIL_TIMEOUT=(5,45)

def load(path,default):
    if not path.exists(): return default
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return default

def save(path,obj):
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding="utf-8")

def inspect_candidate(item):
    try:
        return item,extract_detail(
            get(
                item["url"],
                timeout=DETAIL_TIMEOUT,
                retries=4
            ),
            item
        ),None
    except Exception as e:
        return item,None,str(e)

def run():
    sources=yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    history=load(DATA/"history.json",{})
    current={}; errors=[]
    run_at=datetime.now(timezone.utc).isoformat()

    for sid,cfg in sources.items():
        for listing in cfg["listing_urls"]:
            print(f"[{cfg['market']}] loading listing...",flush=True)

            try:
                html=get(
                    listing,
                    timeout=LISTING_TIMEOUT,
                    retries=3
                )
            except Exception as e:
                errors.append({
                    "source":sid,
                    "stage":"listing",
                    "url":listing,
                    "error":str(e)
                })
                print(
                    f"[{cfg['market']}] listing ERROR: {e}",
                    flush=True
                )
                continue

            seeds=list(
                candidate_links(
                    html,
                    listing,
                    cfg
                )
            )

            unique={
                normalize_url(x["url"]):x
                for x in seeds
            }

            seeds=list(
                unique.values()
            )[:MAX_CANDIDATES_PER_SOURCE]

            print(
                f"[{cfg['market']}] candidates found: "
                f"{len(unique)}; checking: {len(seeds)}",
                flush=True
            )

            accepted=0

            with ThreadPoolExecutor(
                max_workers=MAX_WORKERS
