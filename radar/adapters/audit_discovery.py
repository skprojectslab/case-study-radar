from bs4 import BeautifulSoup
from urllib.parse import urlsplit
from ..utils import absolute_url, clean_text, normalize_url

POSITIVE = ("success","story","stories","case","client","customer","project","reference","referencer","kund","kunde","kundreferenser","cas-client","storie","successo","prosjekt","prosjekter")
GENERIC_TITLES = {"home","homepage","careers","career","contact","contact us","privacy","privacy policy","terms","terms and conditions","sitemap","newsroom","success stories","client stories","cas client","cas clients","storie di successo","kundreferenser","referencer","prosjekter"}

def _path(url):
    return urlsplit(url).path.rstrip("/") or "/"

def _same_domain(a,b):
    return urlsplit(a).netloc.lower() == urlsplit(b).netloc.lower()

def _allowed_candidate(url, listing_url, cfg):
    if not _same_domain(url, listing_url) or url == normalize_url(listing_url):
        return False
    path=_path(url).lower()
    prefixes=cfg.get("allowed_path_prefixes") or []
    if prefixes and not any(path.startswith(p.rstrip("/").lower()+"/") for p in prefixes):
        return False
    for fragment in cfg.get("blocked_path_fragments", []):
        if fragment.lower() in path:
            return False
    return True

def candidate_links(html, listing_url, cfg):
    soup=BeautifulSoup(html,"html.parser")
    seen=set()
    for a in soup.find_all("a",href=True):
        url=absolute_url(listing_url,a["href"])
        if not _allowed_candidate(url,listing_url,cfg):
            continue
        text=clean_text(a.get_text(" ",strip=True))
        if len(text)<6:
            continue
        if not any(k in (url+" "+text).lower() for k in POSITIVE):
            continue
        if url in seen:
            continue
        seen.add(url)
        yield {"url":url,"anchor_text":text}

def extract_detail(html,seed):
    soup=BeautifulSoup(html,"html.parser")
    main=soup.find("main") or soup
    h1=soup.find("h1")
    if h1:
        title=clean_text(h1.get_text(" ",strip=True))
    else:
        meta=soup.select_one("meta[property='og:title']")
        title=clean_text(meta.get("content","")) if meta else seed["anchor_text"]
    if title.lower() in GENERIC_TITLES or len(title)<6:
        return None
    main_text=clean_text(main.get_text(" ",strip=True))
    if len(main_text)<250:
        return None
    text=main_text.lower()
    groups=[
        ["client","customer","kunde","kund","cliente","klient"],
        ["challenge","challenges","utmaning","défi","defi","sfida","uitdaging","udfordring","utfordring"],
        ["solution","lösning","soluzione","oplossing","løsning"],
        ["result","results","resultat","résultat","risultato","resultaat","resultater"],
        ["project","projet","progetto","projecten","projekt","prosjekt"]]
    if sum(any(w in text for w in g) for g in groups)<2:
        return None
    description=""
    for selector in ["meta[name='description']","meta[property='og:description']"]:
        meta=soup.select_one(selector)
        if meta and meta.get("content"):
            description=clean_text(meta["content"]); break
    if not description:
        p=main.find("p")
        if p: description=clean_text(p.get_text(" ",strip=True))
    t=soup.find("time")
    date=clean_text(t.get("datetime") or t.get_text(" ",strip=True)) if t else ""
    return {"title":title,"description":description,"published_date":date,"categories":[],"client_name":""}
