from bs4 import BeautifulSoup
from urllib.parse import urlsplit
from ..utils import absolute_url, clean_text, normalize_url
GENERIC_TITLES={"home","homepage","careers","career","contact","contact us","privacy","privacy policy","terms","terms and conditions","sitemap","newsroom","success stories","client stories","cas client","cas clients","storie di successo","kundreferenser","referencer","prosjekter"}
CARD_WORDS=("card","tile","teaser","story","project","reference","result","item","case")
SKIP_ANCESTORS=("nav","header","footer","aside","form")
def _path(url): return urlsplit(url).path.rstrip("/") or "/"
def _same_domain(a,b): return urlsplit(a).netloc.lower()==urlsplit(b).netloc.lower()
def _detail_prefixes(cfg): return [p.rstrip("/").lower()+"/" for p in (cfg.get("detail_path_prefixes") or [])]
def _is_detail(url,listing_url,cfg):
    if not _same_domain(url,listing_url) or url==normalize_url(listing_url): return False
    path=_path(url).lower()+"/"
    return any(path.startswith(p) for p in _detail_prefixes(cfg))
def _bad_container(node): return any(getattr(x,"name","") in SKIP_ANCESTORS for x in node.parents)
def _card_for_link(a):
    node=a
    for _ in range(6):
        if node is None or not getattr(node,"name",None) or node.name in SKIP_ANCESTORS: break
        text=clean_text(node.get_text(" ",strip=True))
        if len(text)<=1200:
            headings=node.find_all(["h1","h2","h3","h4","h5"],limit=3)
            paragraphs=node.find_all("p",limit=3)
            times=node.find_all("time",limit=2)
            attrs=" ".join(node.get("class") or [])+" "+str(node.get("id") or "")
            score=(2 if headings else 0)+(1 if paragraphs else 0)+(1 if times else 0)+(1 if any(w in attrs.lower() for w in CARD_WORDS) else 0)+(1 if len(clean_text(a.get_text(" ",strip=True)))>=10 else 0)
            if score>=2 and (headings or len(clean_text(a.get_text(" ",strip=True)))>=15): return node
        node=node.parent
    return None
def _extract_seed(a,card,listing_url):
    url=absolute_url(listing_url,a["href"])
    hs=card.find_all(["h1","h2","h3","h4","h5"],limit=5)
    title=clean_text(hs[0].get_text(" ",strip=True)) if hs else clean_text(a.get_text(" ",strip=True))
    if len(title)<6: return None
    t=card.find("time"); date=clean_text(t.get("datetime") or t.get_text(" ",strip=True)) if t else ""
    desc=""
    for p in card.find_all("p",limit=5):
        txt=clean_text(p.get_text(" ",strip=True))
        if len(txt)>=40: desc=txt; break
    return {"url":url,"anchor_text":title,"listing_title":title,"listing_description":desc,"listing_date":date}
def candidate_links(html,listing_url,cfg):
    soup=BeautifulSoup(html,"html.parser"); seen=set()
    for a in soup.find_all("a",href=True):
        url=absolute_url(listing_url,a["href"])
        if not _is_detail(url,listing_url,cfg) or url in seen or _bad_container(a): continue
        card=_card_for_link(a)
        if card is None: continue
        item=_extract_seed(a,card,listing_url)
        if item and item["url"] not in seen:
            seen.add(item["url"]); yield item
def extract_detail(html,seed):
    soup=BeautifulSoup(html,"html.parser"); main=soup.find("main") or soup; h1=soup.find("h1")
    if h1: title=clean_text(h1.get_text(" ",strip=True))
    else:
        meta=soup.select_one("meta[property='og:title']"); title=clean_text(meta.get("content","")) if meta else seed.get("anchor_text","")
    if title.lower() in GENERIC_TITLES or len(title)<6: return None
    if len(clean_text(main.get_text(" ",strip=True)))<120: return None
    desc=seed.get("listing_description","")
    for selector in ["meta[name='description']","meta[property='og:description']"]:
        meta=soup.select_one(selector)
        if meta and meta.get("content"): desc=clean_text(meta.get("content")); break
    if not desc:
        for p in main.find_all("p",limit=8):
            txt=clean_text(p.get_text(" ",strip=True))
            if len(txt)>=40: desc=txt; break
    t=soup.find("time"); date=clean_text(t.get("datetime") or t.get_text(" ",strip=True)) if t else seed.get("listing_date","")
    return {"title":title,"description":desc,"published_date":date,"categories":[],"client_name":""}
