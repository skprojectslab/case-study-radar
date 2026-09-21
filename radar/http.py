import requests
def get(url,timeout=30):
 r=requests.get(url,headers={"User-Agent":"CaseStudyRadar/2.0"},timeout=timeout); r.raise_for_status(); return r.text
