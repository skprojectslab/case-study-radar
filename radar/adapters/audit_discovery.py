from bs4 import BeautifulSoup
from ..utils import absolute_url,clean_text,normalize_url
POS=("success","story","stories","case","client","customer","project","reference","referencer","kund","kunde","kundreferenser","cas-client","storie","successo","prosjekt","prosjekter")
BLOCK=("/contact","/kontakt","/privacy","/terms","/legal","/cookies","/sitemap","/careers","/career","/jobs","/press","/publications","/about-us","/services/","/blog/")
GENERIC={"home","homepage","careers","contact","contact us","privacy","terms","sitemap","newsroom","success stories","client stories","cas client","storie di successo","kundreferenser","referencer","prosjekter"}
def candidate_links(html,listing):
 soup=BeautifulSoup(html,"html.parser"); seen=set()
 for a in soup.find_all("a",href=True):
  u=absolute_url(listing,a["href"]); p=u.lower()
  if u==normalize_url(listing) or u in seen or "://" not in u: continue
  if any(x in p for x in BLOCK): continue
  if u.split("/")[2].lower()!=listing.split("/")[2].lower(): continue
  t=clean_text(a.get_text(" ",strip=True))
  if len(t)<6 or not any(k in (p+" "+t.lower()) for k in POS): continue
  seen.add(u); yield {"url":u,"anchor_text":t}
def extract_detail(html,seed):
 soup=BeautifulSoup(html,"html.parser")
 h=soup.find("h1"); title=clean_text(h.get_text(" ",strip=True)) if h else seed["anchor_text"]
 if title.lower() in GENERIC or len(title)<6: return None
 main=soup.find("main") or soup
 text=clean_text(main.get_text(" ",strip=True)).lower()
 if len(text)<250: return None
 groups=[
 ["client","customer","kunde","kund","cliente","klient"],
 ["challenge","challenges","utmaning","défi","defi","sfida","uitdaging","udfordring","utfordring"],
 ["solution","lösning","soluzione","oplossing","løsning"],
 ["result","results","resultat","résultat","risultato","resultaat","resultater"],
 ["project","projet","progetto","projecten","projekt","prosjekt"]]
 if sum(any(w in text for w in g) for g in groups)<2: return None
 desc=""
 for s in ["meta[name='description']","meta[property='og:description']"]:
  m=soup.select_one(s)
  if m and m.get("content"): desc=clean_text(m["content"]); break
 if not desc:
  p=main.find("p")
  if p: desc=clean_text(p.get_text(" ",strip=True))
 t=soup.find("time"); date=clean_text(t.get("datetime") or t.get_text(" ",strip=True)) if t else ""
 return {"title":title,"description":desc,"published_date":date,"categories":[],"client_name":""}
