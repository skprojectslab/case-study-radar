import time
import requests
SESSION=requests.Session()
SESSION.headers.update({"User-Agent":"CaseStudyRadar/2.3 (+deterministic research crawler)"})
def get(url, timeout=(5,20), retries=3):
    last=None
    for attempt in range(retries):
        try:
            r=SESSION.get(url,timeout=timeout); r.raise_for_status(); return r.text
        except requests.RequestException as e:
            last=e
            if attempt+1<retries: time.sleep(0.75*(attempt+1))
    raise last
