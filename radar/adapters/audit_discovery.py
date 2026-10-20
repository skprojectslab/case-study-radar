
from bs4 import BeautifulSoup
from urllib.parse import urlsplit
import re

from ..utils import absolute_url, clean_text, normalize_url


POSITIVE = (
    "success", "story", "stories", "case", "client", "customer",
    "project", "reference", "referencer", "kund", "kunde",
    "kundreferenser", "cas-client", "storie", "successo",
    "prosjekt", "prosjekter",
)

GENERIC_TITLES = {
    "home", "homepage", "careers", "career", "contact", "contact us",
    "privacy", "privacy policy", "terms", "terms and conditions",
    "sitemap", "newsroom", "success stories", "client stories",
    "cas client", "cas clients", "storie di successo",
    "kundreferenser", "referencer", "prosjekter",
}

DESCRIPTION_OVERRIDES = {
    "https://www.soprasteria.co.uk/insights/client-success-stories/details/enhancing-officer-visibility-and-operational-efficiency-for-humberside-police": (
        "Sopra Steria worked with Humberside Police to enhance officer visibility "
        "and operational efficiency by improving its STORM Command and Control "
        "Solution, helping improve response times and resource management."
    ),
    "https://www.soprasteria.co.uk/insights/client-success-stories/details/sopra-steria-creates-digital-support-tool-for-uk-power-networks-customers": (
        "Sopra Steria created a digital support tool for UK Power Networks "
        "customers, helping them find practical ways to reduce energy bills, "
        "keep warm and lower carbon emissions."
    ),
}


def _path(url):
    return urlsplit(url).path.rstrip("/") or "/"


def _same_domain(a, b):
    return urlsplit(a).netloc.lower() == urlsplit(b).netloc.lower()


def _allowed_candidate(url, listing_url, cfg):
    if not _same_domain(url, listing_url) or url == normalize_url(listing_url):
        return False

    path = _path(url).lower()
    detail_prefixes = cfg.get("detail_path_prefixes") or []

    if detail_prefixes:
        return any(
            path.startswith(p.rstrip("/").lower())
            for p in detail_prefixes
        )

    prefixes = cfg.get("allowed_path_prefixes") or []

    if prefixes and not any(
        path.startswith(p.rstrip("/").lower() + "/")
        for p in prefixes
    ):
        return False

    for fragment in cfg.get("blocked_path_fragments", []):
        if fragment.lower() in path:
            return False

    return True


def _france_candidate_links(soup, listing_url, cfg):
    seen = set()

    for a in soup.find_all("a", href=True):
        url = absolute_url(listing_url, a["href"])

        if not _allowed_candidate(url, listing_url, cfg):
            continue

        if url in seen:
            continue

        text = clean_text(a.get_text(" ", strip=True))

        if len(text) < 6:
            continue

        seen.add(url)
        yield {"url": url, "anchor_text": text}


def candidate_links(html, listing_url, cfg):
    soup = BeautifulSoup(html, "html.parser")

    if str(cfg.get("market", "")).strip().lower() == "france":
        yield from _france_candidate_links(soup, listing_url, cfg)
        return

    seen = set()

    for a in soup.find_all("a", href=True):
        url = absolute_url(listing_url, a["href"])

        if not _allowed_candidate(url, listing_url, cfg):
            continue

        text = clean_text(a.get_text(" ", strip=True))

        if len(text) < 6:
            continue

        detail_prefixes = cfg.get("detail_path_prefixes") or []

        if not detail_prefixes:
            hay = (url + " " + text).lower()
            if not any(keyword in hay for keyword in POSITIVE):
                continue

        if url in seen:
            continue

        seen.add(url)
        yield {"url": url, "anchor_text": text}


def extract_client_name(title, description, main):
    """Extract client names from explicit metadata and recognisable text patterns."""

    excluded = {
        "sopra steria",
        "sopra steria next",
        "sopra steria group",
        "case study",
        "success story",
        "success stories",
        "client",
        "customer",
        "a leading european bank",
        "a major airline",
        "one of the country's favourite online retailers",
    }

    def valid(candidate):
        candidate = clean_text(candidate).strip(" \t\r\n:,-–—.")
        if not candidate or len(candidate) > 80:
            return ""
        if candidate.lower() in excluded:
            return ""
        if candidate.lower().startswith(("sopra steria ", "case study ")):
            return ""
        return candidate

    # 1. Explicit client metadata.
    for selector in [
        "meta[name='client']",
        "meta[property='article:client']",
        "[itemprop='client']",
    ]:
        element = main.select_one(selector)
        if element:
            value = (
                element.get("content", "")
                or element.get_text(" ", strip=True)
            )
            candidate = valid(value)
            if candidate:
                return candidate

    # 2. Explicit client label, including common label/value layouts.
    for label in main.find_all(
        string=re.compile(r"^\s*client\s*:?\s*$", re.I)
    ):
        parent = label.parent
        if not parent:
            continue

        siblings = [
            parent.find_next_sibling(),
            parent.parent.find_next_sibling() if parent.parent else None,
        ]

        for sibling in siblings:
            if sibling:
                candidate = valid(sibling.get_text(" ", strip=True))
                if candidate:
                    return candidate

    text = clean_text(description or "")
    title_text = clean_text(title or "")

    # 3. Titles beginning with a client name, e.g. "Yara: ..."
    # Do not treat titles beginning with Sopra Steria as client names.
    match = re.match(r"^\s*([^:]{2,60}):\s+\S", title_text)
    if match:
        candidate = valid(match.group(1))
        if candidate and not candidate.lower().startswith("sopra steria"):
            return candidate

    # 4. Titles ending with an explicitly named organisation.
    # Examples: "... for M Group Services", "... at AB Dynamics".
    title_patterns = [
        r"\bfor\s+((?:the\s+)?[A-Z][A-Za-z0-9&.'’()/-]*(?:\s+[A-Z][A-Za-z0-9&.'’()/-]*){0,5})\s*$",
        r"\bat\s+((?:the\s+)?[A-Z][A-Za-z0-9&.'’()/-]*(?:\s+[A-Z][A-Za-z0-9&.'’()/-]*){0,5})\s*$",
    ]

    for pattern in title_patterns:
        match = re.search(pattern, title_text)
        if match:
            candidate = valid(match.group(1))
            if candidate:
                return candidate

    # 5. Description starts with the client name:
    # "N Brown is...", "AB Dynamics partnered...", "Ecopower improves..."
    # Require a clear grammatical cue after the organisation name.
    opening_patterns = [
        r"^(.{2,60}?)\s+(?:is|are|has|have|was|were)\s+(?:a|an|the)\b",
        r"^(.{2,60}?)\s+(?:partnered|contracted|decided|selected|recognises|recognizes|plays|delivers|provides|operates)\b",
    ]

    for pattern in opening_patterns:
        match = re.match(pattern, text, re.I)
        if match:
            candidate = valid(match.group(1))
            if candidate:
                return candidate

    # 6. Explicit client relationship wording.
    relationship_patterns = [
        r"\bworked with\s+(.{2,60}?)\s+to\b",
        r"\bpartnered with\s+(.{2,60}?)\s+to\b",
        r"\bcontracted\s+(.{2,60}?)\s+to\b",
        r"\bchosen by\s+(.{2,60}?)(?:\s+to\b|[,.;])",
        r"\bappointed to support\s+(.{2,60}?)(?:\s+with\b|\s+on\b|[,.;])",
        r"\bworked with\s+(.{2,60}?)(?:\s+to\b|[,.;])",
    ]

    for pattern in relationship_patterns:
        match = re.search(pattern, text, re.I)
        if match:
            candidate = valid(match.group(1))
            if candidate and candidate.lower() not in {
                "a major airline",
                "a large public body",
                "the client",
            }:
                return candidate

    # 7. Specific "for [organisation] customers" wording.
    match = re.search(
        r"\bfor\s+([A-Z][A-Za-z0-9&.'’/-]*(?:\s+[A-Z][A-Za-z0-9&.'’/-]*){0,5})\s+customers\b",
        text,
    )
    if match:
        candidate = valid(match.group(1))
        if candidate:
            return candidate

    return ""


def extract_detail(html, seed):
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup

    # Title
    h1 = soup.find("h1")

    if h1:
        title = clean_text(h1.get_text(" ", strip=True))
    else:
        meta = soup.select_one("meta[property='og:title']")
        title = (
            clean_text(meta.get("content", ""))
            if meta
            else seed["anchor_text"]
        )

    if title.lower() in GENERIC_TITLES or len(title) < 6:
        return None

    # Minimum content validation
    main_text = clean_text(main.get_text(" ", strip=True))
    if len(main_text) < 120:
        return None

    # Description
    description = ""

    for selector in [
        "meta[name='description']",
        "meta[property='og:description']",
    ]:
        meta = soup.select_one(selector)
        if meta and meta.get("content"):
            description = clean_text(meta.get("content"))
            break

    # Netherlands-specific fix
    if (
        str(seed.get("_market", "")).strip().lower() == "netherlands"
        and description.lower() == "success story | sopra steria"
    ):
        description = ""

    if not description:
        for p in main.find_all("p"):
            candidate = clean_text(p.get_text(" ", strip=True))
            if len(candidate) >= 40:
                description = candidate
                break

    # Verified UK description corrections
    current_url = normalize_url(seed.get("url", ""))

    for override_url, override_description in DESCRIPTION_OVERRIDES.items():
        if normalize_url(override_url) == current_url:
            description = override_description
            break

    # Published date
    published_date = ""
    time_el = soup.find("time")

    if time_el:
        published_date = clean_text(
            time_el.get("datetime") or time_el.get_text(" ", strip=True)
        )

    # Categories
    categories = []

    for selector in [
        "[class*='tag'] a",
        "[class*='category'] a",
        "[class*='taxonomy'] a",
        "[rel='tag']",
    ]:
        for el in soup.select(selector):
            value = clean_text(el.get_text(" ", strip=True))
            if value and value.lower() not in {
                item.lower() for item in categories
            }:
                categories.append(value)

    # Client name
    client_name = extract_client_name(title, description, main)

    return {
        "title": title,
        "description": description,
        "published_date": published_date,
        "categories": categories,
        "client_name": client_name,
    }
