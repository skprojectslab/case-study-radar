from bs4 import BeautifulSoup
from urllib.parse import urlsplit
from ..utils import absolute_url, clean_text, normalize_url
POSITIVE=("success","story","stories","case","client","customer","project","reference","referencer","kund","kunde","kundreferenser","cas-client","storie","successo","prosjekt","prosjekter")
GENERIC_TITLES={"home","homepage","careers","career","contact","contact us","privacy","privacy policy","terms","terms and conditions","sitemap","newsroom","success stories","client stories","cas client","cas clients","storie di successo","kundreferenser","referencer","prosjekter"}
def _path(url): return urlsplit(url).path.rstrip("/") or "/"
def _same_domain(a,b): return urlsplit(a).netloc.lower()==urlsplit(b).netloc.lower()
def _allowed_candidate(url,listing_url,cfg):
    if not _same_domain(url,listing_url) or url==normalize_url(listing_url): return False
    path=_path(url).lower(); detail_prefixes=cfg.get("detail_path_prefixes") or []
    if detail_prefixes: return any(path.startswith(p.rstrip("/").lower()) for p in detail_prefixes)
    prefixes=cfg.get("allowed_path_prefixes") or []
    if prefixes and not any(path.startswith(p.rstrip("/").lower()+"/") for p in prefixes): return False
    for fragment in cfg.get("blocked_path_fragments",[]): 
        if fragment.lower() in path: return False
    return True
def _france_candidate_links(soup,listing_url,cfg):
    seen=set()
    for a in soup.find_all("a",href=True):
        url=absolute_url(listing_url,a["href"])
        if not _allowed_candidate(url,listing_url,cfg) or url in seen: continue
        text=clean_text(a.get_text(" ",strip=True))
        if len(text)<6: continue
        seen.add(url); yield {"url":url,"anchor_text":text}
def candidate_links(html,listing_url,cfg):
    soup=BeautifulSoup(html,"html.parser")
    if str(cfg.get("market","")).strip().lower()=="france":
        yield from _france_candidate_links(soup,listing_url,cfg); return
    seen=set()
    for a in soup.find_all("a",href=True):
        url=absolute_url(listing_url,a["href"])
        if not _allowed_candidate(url,listing_url,cfg): continue
        text=clean_text(a.get_text(" ",strip=True))
        if len(text)<6: continue
        detail_prefixes=cfg.get("detail_path_prefixes") or []
        if not detail_prefixes:
            hay=(url+" "+text).lower()
            if not any(keyword in hay for keyword in POSITIVE): continue
        if url in seen: continue
        seen.add(url); yield {"url":url,"anchor_text":text}
def extract_detail(html,seed):
    soup=BeautifulSoup(html,"html.parser"); main=soup.find("main") or soup
    h1=soup.find("h1")
    if h1: title=clean_text(h1.get_text(" ",strip=True))
    else:
        meta=soup.select_one("meta[property='og:title']"); title=clean_text(meta.get("content","")) if meta else seed["anchor_text"]
    if title.lower() in GENERIC_TITLES or len(title)<6: return None
    main_text=clean_text(main.get_text(" ",strip=True))
    if len(main_text)<120: return None
    description=""
    for selector in ["meta[name='description']","meta[property='og:description']"]:
        meta=soup.select_one(selector)
        if meta and meta.get("content"): description=clean_text(meta.get("content")); break
    if str(seed.get("_market","")).strip().lower()=="netherlands" and description.lower()=="success story | sopra steria":
        description=""
    if not description:
        for p in main.find_all("p"):
            candidate=clean_text(p.get_text(" ",strip=True))
            if len(candidate)>=40: description=candidate; break
    published_date=""; time_el=soup.find("time")
    if time_el: published_date=clean_text(time_el.get("datetime") or time_el.get_text(" ",strip=True))
    categories=[]
    for selector in ["[class*='tag'] a","[class*='category'] a","[class*='taxonomy'] a","[rel='tag']"]:
        for el in soup.select(selector):
            value=clean_text(el.get_text(" ",strip=True))
            if value and value.lower() not in {x.lower() for x in categories}: categories.append(value)
    return {"title":title,"description":description,"published_date":published_date,"categories":categories,"client_name":""}
