from bs4 import BeautifulSoup
from urllib.parse import urlsplit
import json
import re

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


GENERIC_VALUES = {
    "client",
    "customer",
    "client name",
    "customer name",
    "organisation",
    "organization",
    "company",
    "partner",
    "sopra steria",
    "sopra steria next",
    "sopra steria in",
    "sopra steria benelux",
    "read more",
    "learn more",
    "see more",
    "details",
    "success story",
    "client story",
}


# Words which are useful for identifying explicit client/customer labels.
CLIENT_LABELS = {
    "client",
    "customer",
    "client name",
    "customer name",
    "our client",
    "the client",
    "organisation",
    "organization",
    "client organisation",
    "client organization",
    "customer organisation",
    "customer organization",
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

        if not _allowed_candidate(url, listing_url, cfg) or url in seen:
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

        yield {
            "url": url,
            "anchor_text": text,
        }


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

def _normalise_value(value):
    value = clean_text(value)

    if not value:
        return ""

    value = re.sub(r"\s+", " ", value).strip(" |•·:-")

    return value


def _is_generic_value(value):
    return value.strip().lower() in GENERIC_VALUES


def _add_unique(values, value):
    value = _normalise_value(value)

    if not value:
        return

    if _is_generic_value(value):
        return

    lowered = value.lower()

    if not any(existing.lower() == lowered for existing in values):
        values.append(value)


def _split_values(value):
    """
    Split metadata/category strings without aggressively splitting normal
    organisation names.
    """
    if not value:
        return []

    parts = re.split(r"\s*[|;,]\s*", value)

    return [
        _normalise_value(part)
        for part in parts
        if _normalise_value(part)
    ]


def _extract_json_ld(soup):
    """
    Return JSON-LD objects found on the page.

    This is deliberately tolerant because Sopra Steria pages can expose
    Article/WebPage metadata in different JSON-LD shapes.
    """
    objects = []

    for script in soup.select("script[type='application/ld+json']"):
        raw = script.string or script.get_text()

        if not raw:
            continue

        try:
            data = json.loads(raw)
        except Exception:
            continue

        if isinstance(data, list):
            objects.extend(data)

        elif isinstance(data, dict):
            if isinstance(data.get("@graph"), list):
                objects.extend(data["@graph"])
            else:
                objects.append(data)

    return objects


def _extract_categories(soup, json_ld):
    """
    Deterministic category/taxonomy extraction.

    Priority:
      1. Explicit category/tag/taxonomy/sector/expertise elements
      2. Meta keywords
      3. article:section
      4. JSON-LD keywords
    """

    categories = []

    # Explicit visible taxonomy/category structures.
    selectors = [
        "[class*='tag'] a",
        "[class*='tag'] span",
        "[class*='tag'] li",
        "[class*='category'] a",
        "[class*='category'] span",
        "[class*='category'] li",
        "[class*='taxonomy'] a",
        "[class*='taxonomy'] span",
        "[class*='taxonomy'] li",
        "[class*='sector'] a",
        "[class*='sector'] span",
        "[class*='sector'] li",
        "[class*='expertise'] a",
        "[class*='expertise'] span",
        "[class*='expertise'] li",
        "[rel='tag']",
    ]

    for selector in selectors:
        for el in soup.select(selector):
            value = clean_text(el.get_text(" ", strip=True))

            if not value:
                continue

            # Avoid accidentally treating very long blocks of page copy
            # as categories.
            if len(value) > 100:
                continue

            _add_unique(categories, value)

    # Meta keywords.
    for meta in soup.select("meta[name='keywords']"):
        raw = meta.get("content", "")

        for value in _split_values(raw):
            if len(value) <= 100:
                _add_unique(categories, value)

    # Article section.
    for meta in soup.select("meta[property='article:section']"):
        value = clean_text(meta.get("content", ""))

        if value:
            _add_unique(categories, value)

    # JSON-LD keywords.
    for obj in json_ld:
        keywords = obj.get("keywords") if isinstance(obj, dict) else None

        if isinstance(keywords, str):
            for value in _split_values(keywords):
                if len(value) <= 100:
                    _add_unique(categories, value)

        elif isinstance(keywords, list):
            for value in keywords:
                if isinstance(value, str) and len(value.strip()) <= 100:
                    _add_unique(categories, value)

    return categories


def _extract_client_from_labelled_fields(soup):
    """
    Look for explicit Client/Customer fields.

    We only accept values which appear structurally next to an explicit
    client/customer label. This avoids guessing clients from arbitrary text.
    """

    # Label + next sibling / parent structure.
    for label in soup.find_all(
        string=re.compile(
            r"^\s*(client|customer|client name|customer name|"
            r"our client|the client|organisation|organization)\s*:?\s*$",
            re.I,
        )
    ):
        parent = label.parent

        if not parent:
            continue

        # Same parent: e.g. <div><span>Client</span><span>ABC</span></div>
        children = list(parent.find_all(recursive=False))

        if children:
            for index, child in enumerate(children):
                child_text = clean_text(child.get_text(" ", strip=True))

                if child_text.lower().rstrip(":") in CLIENT_LABELS:
                    for next_child in children[index + 1:]:
                        value = clean_text(
                            next_child.get_text(" ", strip=True)
                        )

                        if value and not _is_generic_value(value):
                            if 2 <= len(value) <= 150:
                                return value

        # Next sibling.
        sibling = parent.find_next_sibling()

        if sibling:
            value = clean_text(sibling.get_text(" ", strip=True))

            if value and not _is_generic_value(value):
                if 2 <= len(value) <= 150:
                    return value

        # Parent text with a colon:
        parent_text = clean_text(parent.get_text(" ", strip=True))

        match = re.match(
            r"^(?:client|customer|client name|customer name|"
            r"our client|the client|organisation|organization)\s*:\s*(.+)$",
            parent_text,
            re.I,
        )

        if match:
            value = _normalise_value(match.group(1))

            if value and not _is_generic_value(value):
                if 2 <= len(value) <= 150:
                    return value

    return ""


def _extract_client_from_json_ld(json_ld):
    """
    Extract only strongly labelled client/customer information from JSON-LD.

    Do NOT treat author, publisher, creator, or generic organisation metadata
    as the client.
    """

    client_keys = {
        "client",
        "customer",
        "clientname",
        "customername",
        "client_name",
        "customer_name",
    }

    for obj in json_ld:
        if not isinstance(obj, dict):
            continue

        for key, value in obj.items():
            normalised_key = re.sub(r"[^a-z0-9]", "", key.lower())

            if normalised_key not in {
                re.sub(r"[^a-z0-9]", "", x)
                for x in client_keys
            }:
                continue

            if isinstance(value, str):
                candidate = _normalise_value(value)

                if (
                    candidate
                    and not _is_generic_value(candidate)
                    and 2 <= len(candidate) <= 150
                ):
                    return candidate

            elif isinstance(value, dict):
                candidate = _normalise_value(
                    value.get("name", "")
                )

                if (
                    candidate
                    and not _is_generic_value(candidate)
                    and 2 <= len(candidate) <= 150
                ):
                    return candidate

    return ""


def _extract_client_from_title(title):
    """
    Very conservative title-based extraction.

    We only use obvious organisation-name prefixes such as:
        'Yara: Developing...'
        'Equinor: ...'
        'Airbus - ...'

    We deliberately do NOT infer clients from titles such as:
        'Supporting millions of passengers...'
        'Transforming ...'
        'How ...'
        'Sopra Steria and X...'
    """

    if not title:
        return ""

    # Colon pattern: "Yara: ..."
    match = re.match(
        r"^([^:]{2,80}):\s+.+$",
        title,
    )

    if match:
        candidate = _normalise_value(match.group(1))

        if (
            candidate
            and candidate.lower() not in {
                "client success stories",
                "client stories",
                "success stories",
                "case study",
                "case studies",
                "sopra steria",
            }
            and not candidate.lower().startswith("sopra steria")
        ):
            return candidate

    # Hyphen pattern: "Airbus - Creating..."
    match = re.match(
        r"^([^-]{2,80})\s+-\s+.+$",
        title,
    )

    if match:
        candidate = _normalise_value(match.group(1))

        if (
            candidate
            and candidate.lower() not in {
                "client success stories",
                "client stories",
                "success stories",
                "case study",
                "case studies",
                "sopra steria",
            }
            and not candidate.lower().startswith("sopra steria")
        ):
            return candidate

    return ""


def _extract_client(soup, title, json_ld):
    """
    Client extraction priority:

      1. Explicit labelled HTML field
      2. Explicit JSON-LD client/customer field
      3. Very obvious organisation prefix in title

    Otherwise return blank.
    """

    client = _extract_client_from_labelled_fields(soup)

    if client:
        return client

    client = _extract_client_from_json_ld(json_ld)

    if client:
        return client

    return _extract_client_from_title(title)


def _extract_description(soup, main, title):
    """
    Extract the most useful deterministic description.

    Meta descriptions are preferred when they are clearly meaningful.
    Generic CMS descriptions are rejected.

    We also inspect the first few meaningful paragraphs rather than blindly
    taking the first <p>, because some Sopra Steria pages begin with generic
    navigation/introductory content.
    """

    generic_descriptions = {
        "success story | sopra steria",
        "client story | sopra steria",
        "client stories | sopra steria",
        "success stories | sopra steria",
        "sopra steria",
    }

    meta_candidates = []

    for selector in [
        "meta[name='description']",
        "meta[property='og:description']",
    ]:
        meta = soup.select_one(selector)

        if meta and meta.get("content"):
            value = clean_text(meta.get("content"))

            if value:
                meta_candidates.append(value)

    for candidate in meta_candidates:
        if candidate.lower() in generic_descriptions:
            continue

        if len(candidate) >= 40:
            return candidate

    # Paragraph fallback.
    paragraphs = []

    for p in main.find_all("p"):
        candidate = clean_text(p.get_text(" ", strip=True))

        if len(candidate) < 40:
            continue

        if candidate.lower() in generic_descriptions:
            continue

        if candidate not in paragraphs:
            paragraphs.append(candidate)

    if not paragraphs:
        return ""

    # Prefer a paragraph which contains a meaningful title word.
    title_words = {
        word.lower()
        for word in re.findall(r"[A-Za-zÀ-ÿ0-9]{4,}", title or "")
    }

    scored = []

    for paragraph in paragraphs[:10]:
        paragraph_words = {
            word.lower()
            for word in re.findall(
                r"[A-Za-zÀ-ÿ0-9]{4,}",
                paragraph,
            )
        }

        overlap = len(title_words.intersection(paragraph_words))

        scored.append(
            (
                overlap,
                -len(paragraph),
                paragraph,
            )
        )

    scored.sort(reverse=True)

    return scored[0][2]


# ---------------------------------------------------------------------------
# Detail extraction
# ---------------------------------------------------------------------------

def extract_detail(html, seed):
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main") or soup

    # ---------------------------------------------------------
    # TITLE
    # ---------------------------------------------------------

    h1 = soup.find("h1")

    if h1:
        title = clean_text(h1.get_text(" ", strip=True))
    else:
        meta = soup.select_one("meta[property='og:title']")

        if meta:
            title = clean_text(meta.get("content", ""))
        else:
            title = seed["anchor_text"]

    if title.lower() in GENERIC_TITLES or len(title) < 6:
        return None

    # ---------------------------------------------------------
    # MINIMUM CONTENT CHECK
    # ---------------------------------------------------------

    main_text = clean_text(
        main.get_text(" ", strip=True)
    )

    if len(main_text) < 120:
        return None

    # ---------------------------------------------------------
    # JSON-LD
    # ---------------------------------------------------------

    json_ld = _extract_json_ld(soup)

    # ---------------------------------------------------------
    # DESCRIPTION
    # ---------------------------------------------------------

    description = _extract_description(
        soup,
        main,
        title,
    )

    # Preserve the Netherlands-specific CMS correction.
    if (
        str(seed.get("_market", "")).strip().lower() == "netherlands"
        and description.lower() == "success story | sopra steria"
    ):
        description = ""

        for p in main.find_all("p"):
            candidate = clean_text(
                p.get_text(" ", strip=True)
            )

            if len(candidate) >= 40:
                description = candidate
                break

    # ---------------------------------------------------------
    # PUBLISHED DATE
    # ---------------------------------------------------------

    published_date = ""

    time_el = soup.find("time")

    if time_el:
        published_date = clean_text(
            time_el.get("datetime")
            or time_el.get_text(" ", strip=True)
        )

    # Additional deterministic metadata fallback.
    if not published_date:
        for selector in [
            "meta[property='article:published_time']",
            "meta[name='date']",
            "meta[name='publish-date']",
        ]:
            meta = soup.select_one(selector)

            if meta and meta.get("content"):
                published_date = clean_text(
                    meta.get("content")
                )

                if published_date:
                    break

    # ---------------------------------------------------------
    # CATEGORIES
    # ---------------------------------------------------------

    categories = _extract_categories(
        soup,
        json_ld,
    )

    # ---------------------------------------------------------
    # CLIENT
    # ---------------------------------------------------------

    client_name = _extract_client(
        soup,
        title,
        json_ld,
    )

    # ---------------------------------------------------------
    # RESULT
    # ---------------------------------------------------------

    return {
        "title": title,
        "description": description,
        "published_date": published_date,
        "categories": categories,
        "client_name": client_name,
    }
