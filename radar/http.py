import time
import requests

HEADERS={"User-Agent":"CaseStudyRadar/2.4 (+deterministic research crawler)"}


def get(url, timeout=(5,20), retries=3):
    last=None
    for attempt in range(1,retries+1):
        try:
            r=requests.get(url,headers=HEADERS,timeout=timeout)
            r.raise_for_status()
            return r.text
        except requests.RequestException as e:
            last=e
            if attempt < retries:
                time.sleep(1.5 * attempt)
    raise last
