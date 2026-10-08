from bs4 import BeautifulSoup
from urllib.parse import urlsplit

from ..utils import absolute_url, clean_text, normalize_url


POSITIVE = (
    "success",
    "story",
    "stories",
    "case",
    "client",
    "customer",
    "project",
    "reference",
    "referencer",
    "kund",
    "kunde",
    "kundreferenser",
    "cas-client",
    "storie",
    "successo",
    "prosjekt",
    "prosjekter",
)

GENERIC_TITLES = {
    "home",
    "homepage",
    "careers",
    "career",
    "contact",
    "contact us",
    "privacy",
    "privacy policy",
    "terms",
    "terms and conditions",
    "sitemap",
    "newsroom",
    "success stories",
    "client stories",
    "cas client",
    "cas clients",
    "storie di successo",
    "kundreferenser",
    "referencer",
    "prosjekter",
}

# Descriptions which are clearly generic CMS/site descriptions
# rather than a description of the individual case study.
GENERIC_DESCRIPTIONS = {
    "success story | sopra steria",
    "success stories | sopra steria",
    "client story | sopra steria",
    "client stories | sopra steria",
    "case study | sopra steria",
    "case studies | sopra steria",
}

# Known generic descriptions observed on the UK site.
# These should not be allowed to overwrite a meaningful paragraph.
SUSPICIOUS_DESCRIPTION_PHRASES = (
    "worked with a large public body since 2021",
    "successfully transition to an oracle fusion cloud",
    "chosen for an important strategic project",
)


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

    if prefixes:
        if not any(
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

        yield {
            "url": url,
            "anchor_text": text,
        }


def candidate_links(html, listing_url, cfg):
    soup = BeautifulSoup(html, "html.parser")

    if str(cfg.get("market", "")).strip().lower() == "france":
        yield from _france_candidate_links(
            soup,
            listing_url,
            cfg,
        )
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

        yield {
            "url": url,
            "anchor_text": text,
        }


def _json_ld_objects(soup):
    objects = []

    for script in soup.select("script[type='application/ld+json']"):
        raw = script.string or script.get_text()

        if not raw:
            continue

        try:
            import json

            data = json.loads(raw)

            if isinstance(data, list):
                objects.extend(data)
            elif isinstance(data, dict):
                objects.append(data)

        except Exception:
            continue

    return objects


def _extract_client_from_labelled_html(soup):
    """
    Conservative client extraction.

    Only accept a value when the page explicitly labels it as:
    Client / Customer / Kunde / Kund / Customer name etc.
    """

    labels = {
        "client",
        "customer",
        "client name",
        "customer name",
        "kunde",
        "kund",
        "kundnamn",
        "klient",
    }

    # Look through common definition-list/table structures.
    for el in soup.find_all(["dt", "th", "strong", "b", "span", "div"]):
        label = clean_text(el.get_text(" ", strip=True)).lower()

        if label not in labels:
            continue

        # Definition-list pattern: <dt>Client</dt><dd>...</dd>
        if el.name == "dt":
            nxt = el.find_next_sibling("dd")

            if nxt:
                value = clean_text(nxt.get_text(" ", strip=True))

                if 2 <= len(value) <= 150:
                    return value

        # Table pattern: <th>Client</th><td>...</td>
        if el.name == "th":
            nxt = el.find_next_sibling("td")

            if nxt:
                value = clean_text(nxt.get_text(" ", strip=True))

                if 2 <= len(value) <= 150:
                    return value

        # Generic parent with label + nearby value.
        parent = el.parent

        if parent:
            text = clean_text(parent.get_text(" ", strip=True))

            if text.lower().startswith(label):
                value = clean_text(text[len(label):].strip(" :-"))

                if 2 <= len(value) <= 150:
                    return value

    return ""


def _extract_client_from_json_ld(soup):
    """
    Conservative JSON-LD extraction.

    Only use explicit Organization/Person names where the page
    structure clearly identifies a client/customer relationship.
    """

    for obj in _json_ld_objects(soup):
        if not isinstance(obj, dict):
            continue

        for key in ("client", "customer"):
            value = obj.get(key)

            if isinstance(value, dict):
                name = clean_text(value.get("name", ""))

                if 2 <= len(name) <= 150:
                    return name

            elif isinstance(value, str):
                value = clean_text(value)

                if 2 <= len(value) <= 150:
                    return value

    return ""


def _extract_client(soup):
    client = _extract_client_from_labelled_html(soup)

    if client:
        return client

    return _extract_client_from_json_ld(soup)


def _extract_categories(soup):
    """
    Extremely conservative category extraction.

    Do NOT use broad class selectors such as:
      [class*='tag']
      [class*='category']

    because these can capture footer/social/navigation elements.
    """

    categories = []

    def add(value):
        value = clean_text(value)

        if not value:
            return

        if len(value) > 100:
            return

        if value.lower() in {
            "instagram",
            "facebook",
            "linkedin",
            "youtube",
            "twitter",
            "x",
        }:
            return

        if value.lower() not in {
            x.lower() for x in categories
        }:
            categories.append(value)

    # Explicit rel=tag is the safest HTML signal.
    for el in soup.select("[rel='tag']"):
        add(el.get_text(" ", strip=True))

    # Explicit metadata.
    for meta in soup.select("meta[name='keywords']"):
        value = meta.get("content", "")

        if value:
            for item in value.split(","):
                add(item)

    for meta in soup.select("meta[property='article:section']"):
        add(meta.get("content", ""))

    # JSON-LD keywords.
    for obj in _json_ld_objects(soup):
        if not isinstance(obj, dict):
            continue

        keywords = obj.get("keywords")

        if isinstance(keywords, str):
            for item in keywords.split(","):
                add(item)

        elif isinstance(keywords, list):
            for item in keywords:
                if isinstance(item, str):
                    add(item)

    return categories


def _is_suspicious_description(description):
    d = clean_text(description).lower()

    if not d:
        return True

    if d in GENERIC_DESCRIPTIONS:
        return True

    for phrase in SUSPICIOUS_DESCRIPTION_PHRASES:
        if phrase in d:
            return True

    return False


def _extract_description(soup, main):
    """
    Preserve the original stable behaviour:

    1. meta description
    2. og:description
    3. first meaningful paragraph

    We only reject the description when it is clearly generic/wrong.
    We do NOT score descriptions against the title because that caused
    hundreds of false UPDATED records.
    """

    candidates = []

    for selector in [
        "meta[name='description']",
        "meta[property='og:description']",
    ]:
        meta = soup.select_one(selector)

        if meta and meta.get("content"):
            candidates.append(
                clean_text(meta.get("content"))
            )

    for description in candidates:
        if not _is_suspicious_description(description):
            return description

    # If metadata is generic/wrong, use the first meaningful paragraph.
    for p in main.find_all("p"):
        candidate = clean_text(
            p.get_text(" ", strip=True)
        )

        if len(candidate) < 40:
            continue

        if candidate.lower() in GENERIC_DESCRIPTIONS:
            continue

        return candidate

    # Preserve whatever metadata exists if no better paragraph exists.
    if candidates:
        return candidates[0]

    return ""


def _extract_date(soup):
    """
    Conservative date extraction.

    Only explicit date metadata is used.
    """

    time_el = soup.find("time")

    if time_el:
        value = clean_text(
            time_el.get("datetime")
            or time_el.get_text(" ", strip=True)
        )

        if value:
            return value

    for selector in [
        "meta[property='article:published_time']",
        "meta[property='article:modified_time']",
        "meta[name='date']",
        "meta[name='publish-date']",
        "meta[name='publication-date']",
    ]:
        meta = soup.select_one(selector)

        if meta and meta.get("content"):
            value = clean_text(meta.get("content"))

            if value:
                return value

    return ""


def extract_detail(html, seed):
    soup = BeautifulSoup(html, "html.parser")

    main = soup.find("main") or soup

    # -------------------------
    # TITLE
    # -------------------------

    h1 = soup.find("h1")

    if h1:
        title = clean_text(
            h1.get_text(" ", strip=True)
        )
    else:
        meta = soup.select_one(
            "meta[property='og:title']"
        )

        title = (
            clean_text(meta.get("content", ""))
            if meta
            else seed["anchor_text"]
        )

    if title.lower() in GENERIC_TITLES or len(title) < 6:
        return None

    # -------------------------
    # MAIN CONTENT VALIDATION
    # -------------------------

    main_text = clean_text(
        main.get_text(" ", strip=True)
    )

    if len(main_text) < 120:
        return None

    # -------------------------
    # DESCRIPTION
    # -------------------------

    description = _extract_description(
        soup,
        main,
    )

    # Netherlands-specific protection
    if (
        str(seed.get("_market", "")).strip().lower()
        == "netherlands"
        and description.lower()
        == "success story | sopra steria"
    ):
        description = ""

        for p in main.find_all("p"):
            candidate = clean_text(
                p.get_text(" ", strip=True)
            )

            if len(candidate) >= 40:
                description = candidate
                break

    # -------------------------
    # DATE
    # -------------------------

    published_date = _extract_date(soup)

    # -------------------------
    # CLIENT
    # -------------------------

    client_name = _extract_client(soup)

    # -------------------------
    # CATEGORIES
    # -------------------------

    categories = _extract_categories(soup)

    return {
        "title": title,
        "description": description,
        "published_date": published_date,
        "categories": categories,
        "client_name": client_name,
    }
