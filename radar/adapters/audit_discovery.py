from bs4 import BeautifulSoup
from urllib.parse import urlsplit
from ..utils import absolute_url, clean_text, normalize_url

GENERIC_TITLES={"home","homepage","careers","career","contact","contact us","privacy","privacy policy","terms","terms and conditions","sitemap","newsroom","success stories","client stories","cas client","cas clients","storie di successo","kundreferenser","referencer","prosjekter"}

def _path(url): return urlsplit(url).path.rstrip("/") or "/"
def _same_domain(a,b): return urlsplit(a).netloc.lower()==urlsplit(b).netloc.lower()

def _is_detail(url, listing_url, cfg):
    if not _same_domain(url, listing_url): return False
    path=_path(url).lower(); listing=_path(listing_url).lower().rstrip("/")
    if path==listing: return False
    detail=cfg.get("detail_path_contains") or []
    if detail:
        return any(x.lower() in path for x in detail)
    prefixes=cfg.get("allowed_path_prefixes") or []
    if not any(path.startswith(p.rstrip("/").lower()+"/") for p in prefixes): return False
    for blocked in cfg.get("blocked_path_fragments",[]):
        if blocked.lower() in path: return False
    return True

def candidate_links(html, listing_url, cfg):
    soup=BeautifulSoup(html,"html.parser")
    seen=set()
    for a in soup.find_all("a",href=True):
        url=normalize_url(absolute_url(listing_url,a["href"]))
        if url in seen or not _is_detail(url,listing_url,cfg): continue
        text=clean_text(a.get_text(" ",strip=True))
        if len(text)<5: continue
        path=_path(url).lower()
        # Reject obvious utility links, filters and non-content paths.
        if any(x in path for x in ("/contact","/privacy","/terms","/sitemap","/careers","/karriere","/kontakt")): continue
        seen.add(url)
        yield {"url":url,"anchor_text":text}

def extract_detail(html,seed):
    soup=BeautifulSoup(html,"html.parser")
    main=soup.find("main") or soup
    h1=soup.find("h1")
    if h1: title=clean_text(h1.get_text(" ",strip=True))
    else:
        meta=soup.select_one("meta[property='og:title']")
        title=clean_text(meta.get("content","")) if meta else seed["anchor_text"]
    if not title or title.lower() in GENERIC_TITLES or len(title)<6: return None
    description=""
    for selector in ("meta[name='description']","meta[property='og:description']"):
        meta=soup.select_one(selector)
        if meta and meta.get("content"):
            description=clean_text(meta["content"]); break
    if not description:
        for p in main.find_all("p"):
            t=clean_text(p.get_text(" ",strip=True))
            if len(t)>=40: description=t; break
    published_date=""
    time_el=soup.find("time")
    if time_el: published_date=clean_text(time_el.get("datetime") or time_el.get_text(" ",strip=True))
    if not published_date:
        for meta_name in ("article:published_time","date","publish-date"):
            meta=soup.select_one(f"meta[property='{meta_name}'], meta[name='{meta_name}']")
            if meta and meta.get("content"):
                published_date=clean_text(meta["content"]); break
    if len(clean_text(main.get_text(" ",strip=True)))<150: return None
    return {"title":title,"description":description,"published_date":published_date,"categories":[],"client_name":""}
