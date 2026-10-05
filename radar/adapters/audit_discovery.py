from bs4 import BeautifulSoup
from urllib.parse import urlsplit

from ..utils import absolute_url, clean_text, normalize_url

GENERIC_TITLES = {
    "home", "homepage", "careers", "career", "contact", "contact us",
    "privacy", "privacy policy", "terms", "terms and conditions",
    "sitemap", "newsroom", "success stories", "client stories",
    "cas client", "cas clients", "storie di successo",
    "kundreferenser", "referencer", "prosjekter",
}

# Exact detail-page patterns verified against the current Sopra Steria
# source structure. These are discovery guards, not language keywords.
DETAIL_PATHS = {
    "UK": ("/insights/client-success-stories/details/", "/insights/client-success-stories/"),
    "Germany": ("/newsroom/success-stories/details/",),
    "Belgium": ("/newsroom/success-stories/details/",),
    "Luxembourg": ("/newsroom/success-stories/details/",),
    "Netherlands": ("/newsroom/success-stories/details/",),
    "France": ("/espace-media/cas-client/details/",),
    "Sweden": ("/kundreferenser/",),
    "India": ("/insights/case-studies/details/",),
    "Norway": ("/prosjekter/details/",),
}

def _path(url):
    return urlsplit(url).path.rstrip("/") or "/"

def _same_domain(a, b):
    return urlsplit(a).netloc.lower() == urlsplit(b).netloc.lower()

def _is_real_detail_url(url, listing_url, cfg):
    if not _same_domain(url, listing_url):
        return False
    if url == normalize_url(listing_url):
        return False

    path = _path(url).lower()
    market = str(cfg.get("market", "")).strip()
    patterns = DETAIL_PATHS.get(market)

    if not patterns:
        return False

    for pattern in patterns:
        p = pattern.lower().rstrip("/")
        # UK has both direct story URLs and /details/ URLs.
        if path.startswith(p + "/") or path == p:
            # A direct listing URL must never become a candidate.
            if path == _path(listing_url).lower():
                return False
            return True

    return False

def _candidate_from_anchor(a, listing_url):
    url = absolute_url(listing_url, a.get("href", ""))
    text = clean_text(a.get_text(" ", strip=True))
    if not url or len(text) < 6:
        return None
    return {"url": url, "anchor_text": text}

def _heading_candidates(soup, listing_url, cfg):
    """Used for Denmark, whose case cards link to varied site paths."""
    seen = set()

    for heading in soup.find_all(["h2", "h3", "h4"]):
        title = clean_text(heading.get_text(" ", strip=True))
        if len(title) < 12 or title.lower() in GENERIC_TITLES:
            continue

        anchors = list(heading.find_all("a", href=True))
        if not anchors and heading.parent:
            anchors = list(heading.parent.find_all("a", href=True))

        # Look one level higher when the heading and link are siblings.
        if not anchors and heading.parent and heading.parent.parent:
            anchors = list(heading.parent.parent.find_all("a", href=True))

        for a in anchors[:3]:
            item = _candidate_from_anchor(a, listing_url)
            if not item:
                continue
            url = item["url"]
            path = _path(url).lower()

            if not _same_domain(url, listing_url):
                continue
            if url in seen:
                continue
            if "?" in url or "#" in url:
                continue
            if path in {
                _path(listing_url).lower(),
                "/hvad-kan-vi",
                "/hvem-hjaelper-vi",
                "/hvem-hjaelper-vi/offentlig-sektor",
            }:
                continue
            if any(x in path for x in (
                "/kontakt", "/contact", "/karriere", "/careers",
                "/privacy", "/terms", "/sitemap"
            )):
                continue

            seen.add(url)
            item["anchor_text"] = title
            yield item
            break

def candidate_links(html, listing_url, cfg):
    soup = BeautifulSoup(html, "html.parser")
    market = str(cfg.get("market", "")).strip()

    # France's listing URL is /services/conseil/nos-client-stories and
    # its detail pages use /espace-media/cas-client/details/.
    if market == "Denmark":
        yield from _heading_candidates(soup, listing_url, cfg)
        return

    seen = set()

    for a in soup.find_all("a", href=True):
        url = absolute_url(listing_url, a.get("href", ""))
        if not _is_real_detail_url(url, listing_url, cfg):
            continue
        if url in seen:
            continue

        item = _candidate_from_anchor(a, listing_url)
        if not item:
            continue

        # Ignore pagination/filter URLs and generic navigation.
        if "?" in url or "#" in url:
            continue

        seen.add(url)
        yield item

def extract_detail(html, seed):
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup

    h1 = soup.find("h1")
    if h1:
        title = clean_text(h1.get_text(" ", strip=True))
    else:
        meta = soup.select_one("meta[property='og:title']")
        title = clean_text(meta.get("content", "")) if meta else seed.get("anchor_text", "")

    if not title or title.lower() in GENERIC_TITLES or len(title) < 6:
        return None

    description = ""
    for selector in (
        "meta[name='description']",
        "meta[property='og:description']",
    ):
        meta = soup.select_one(selector)
        if meta and meta.get("content"):
            description = clean_text(meta.get("content"))
            break

    if not description:
        # Prefer a meaningful paragraph rather than requiring English
        # words such as client/challenge/result.
        for p in main.find_all("p"):
            candidate = clean_text(p.get_text(" ", strip=True))
            if len(candidate) >= 40:
                description = candidate
                break

    main_text = clean_text(main.get_text(" ", strip=True))
    if len(main_text) < 120:
        return None

    published_date = ""
    time_el = soup.find("time")
    if time_el:
        published_date = clean_text(
            time_el.get("datetime") or time_el.get_text(" ", strip=True)
        )

    # Some Sopra Steria pages expose the publication date in a visible
    # metadata string instead of <time>. Keep this deterministic.
    if not published_date:
        meta_date = soup.select_one(
            "meta[property='article:published_time'], "
            "meta[name='date'], meta[name='publishdate']"
        )
        if meta_date:
            published_date = clean_text(meta_date.get("content", ""))

    return {
        "title": title,
        "description": description,
        "published_date": published_date,
        "categories": [],
        "client_name": "",
    }
