import hashlib,json,re
from urllib.parse import urljoin,urlsplit,urlunsplit,parse_qsl,urlencode
def clean_text(x): return re.sub(r"\s+"," ",x or "").strip()
def normalize_url(url):
 p=urlsplit(url); q=[(k,v) for k,v in parse_qsl(p.query) if not k.lower().startswith(("utm_","fbclid","gclid"))]
 path=re.sub(r"/{2,}","/",p.path or "/")
 if path!="/" and path.endswith("/"): path=path[:-1]
 return urlunsplit((p.scheme.lower(),p.netloc.lower(),path,urlencode(q),""))
def absolute_url(base,href): return normalize_url(urljoin(base,href))
def content_hash(r):
 x={k:r.get(k,"") for k in ["title","description","client_name","published_date","categories"]}
 return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
