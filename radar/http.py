import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

SESSION=requests.Session()
SESSION.headers.update({"User-Agent":"CaseStudyRadar/2.3 (+deterministic research crawler)"})
_retry=Retry(total=2,connect=2,read=2,backoff_factor=0.8,status_forcelist=(429,500,502,503,504),allowed_methods=frozenset(["GET"]))
SESSION.mount("https://",HTTPAdapter(max_retries=_retry))
SESSION.mount("http://",HTTPAdapter(max_retries=_retry))

def get(url, timeout=(5,15)):
    r=SESSION.get(url,timeout=timeout)
    r.raise_for_status()
    return r.text
