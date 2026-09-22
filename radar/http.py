import requests

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "CaseStudyRadar/2.2 (+deterministic research crawler)"})

def get(url, timeout=(2, 4)):
    r = SESSION.get(url, timeout=timeout)
    r.raise_for_status()
    return r.text
