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


GENERIC_CLIENT_VALUES = {
    "",
    "client",
    "customer",
    "client name",
    "customer name",
    "our client",
    "the client",
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
}


GENERIC_DESCRIPTIONS = {
    "success story | sopra steria",
    "client story | sopra steria",
    "client stories | sopra steria",
    "success stories | sopra steria",
    "sopra steria",
    "read more about our servicenow services.",
}


CLIENT_LABEL_PATTERN = re.compile(
    r"^\s*(client|customer|client name|customer name|"
    r"our client|the client|client organisation|client organization|"
    r"customer organisation|customer organization)\s*:?\s*$",
    re.IGNORECASE,
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
# Generic helpers
# ---------------------------------------------------------------------------

def _normalise_value(value):
    value = clean_text(value)

    if not value:
        return ""

    value = re.sub(r"\s+", " ", value)
    value = value.strip(" |•·:-")

    return value


def _is_generic_client(value):
    return _normalise_value(value).lower() in GENERIC_CLIENT_VALUES


def _add_unique(values, value):
    value = _normalise_value(value)

    if not value:
        return

    if len(value) > 100:
        return

    if value.lower() in {
        "instagram",
        "facebook",
        "linkedin",
        "twitter",
        "youtube",
        "x",
        "share",
        "follow us",
    }:
        return

    if not any(
        existing.lower() == value.lower()
        for existing in values
    ):
        values.append(value)


def _extract_json_ld(soup):
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
            graph = data.get("@graph")

            if isinstance(graph, list):
                objects.extend(graph)
            else:
                objects.append(data)

    return objects


# ---------------------------------------------------------------------------
# CLIENT
# ---------------------------------------------------------------------------

def _extract_client_from_labelled_html(soup):
    """
    Only extract a client when the page explicitly labels the value
    as Client / Customer.

    This intentionally does NOT infer a client from arbitrary page text.
    """

    # Case 1:
    # <div>
    #   <span>Client</span>
    #   <span>Example Ltd</span>
    # </div>
    for element in soup.find_all(string=CLIENT_LABEL_PATTERN):
        label = element.parent

        if not label:
            continue

        parent = label.parent

        if parent:
            children = list(parent.find_all(recursive=False))

            for index, child in enumerate(children):
                child_text = clean_text(
                    child.get_text(" ", strip=True)
                )

                if CLIENT_LABEL_PATTERN.match(child_text):
                    for following in children[index + 1:]:
                        value = _normalise_value(
                            following.get_text(" ", strip=True)
                        )

                        if (
                            value
                            and not _is_generic_client(value)
                            and 2 <= len(value) <= 150
                        ):
                            return value

            # Case 2:
            # <div>Client: Example Ltd</div>
            parent_text = clean_text(
                parent.get_text(" ", strip=True)
            )

            match = re.match(
                r"^(?:client|customer|client name|customer name|"
                r"our client|the client|client organisation|"
                r"client organization|customer organisation|"
                r"customer organization)\s*:\s*(.+)$",
                parent_text,
                re.IGNORECASE,
            )

            if match:
                value = _normalise_value(match.group(1))

                if (
                    value
                    and not _is_generic_client(value)
                    and 2 <= len(value) <= 150
                ):
                    return value

        # Case 3:
        # label followed by sibling
        sibling = label.find_next_sibling()

        if sibling:
            value = _normalise_value(
                sibling.get_text(" ", strip=True)
            )

            if (
                value
                and not _is_generic_client(value)
                and 2 <= len(value) <= 150
            ):
                return value

    return ""


def _extract_client_from_json_ld(json_ld):
    """
    Only use explicitly named client/customer properties.

    Do NOT treat author, publisher, creator or provider as the client.
    """

    valid_keys = {
        "client",
        "customer",
        "clientname",
        "customername",
        "client_name",
        "customer_name",
    }

    normalised_keys = {
        re.sub(r"[^a-z0-9]", "", key.lower())
        for key in valid_keys
    }

    for obj in json_ld:
        if not isinstance(obj, dict):
            continue

        for key, value in obj.items():
            key_normalised = re.sub(
                r"[^a-z0-9]",
                "",
                key.lower(),
            )

            if key_normalised not in normalised_keys:
                continue

            if isinstance(value, str):
                candidate = _normalise_value(value)

                if (
                    candidate
                    and not _is_generic_client(candidate)
                    and 2 <= len(candidate) <= 150
                ):
                    return candidate

            elif isinstance(value, dict):
                candidate = _normalise_value(
                    value.get("name", "")
                )

                if (
                    candidate
                    and not _is_generic_client(candidate)
                    and 2 <= len(candidate) <= 150
                ):
                    return candidate

    return ""


def _extract_client(soup, json_ld):
    """
    Conservative client extraction.

    Priority:
      1. Explicit Client/Customer HTML field
      2. Explicit JSON-LD client/customer field

    Deliberately NO title-based inference.
    """

    client = _extract_client_from_labelled_html(soup)

    if client:
        return client

    client = _extract_client_from_json_ld(json_ld)

    if client:
        return client

    return ""


# ---------------------------------------------------------------------------
# CATEGORIES
# ---------------------------------------------------------------------------

def _extract_categories(soup, json_ld):
    """
    Conservative category extraction.

    We deliberately avoid generic selectors such as:
        [class*='tag']
        [class*='category']
        [class*='sector']

    Those produced false positives such as "Instagram".

    Only explicit metadata is accepted here.
    """

    categories = []

    # Explicit HTML rel=tag is retained because it is semantically defined.
    for element in soup.select("[rel='tag']"):
        value = clean_text(
            element.get_text(" ", strip=True)
        )

        if 2 <= len(value) <= 100:
            _add_unique(categories, value)

    # Meta keywords are semantically explicit.
    for meta in soup.select("meta[name='keywords']"):
        raw = clean_text(meta.get("content", ""))

        if not raw:
            continue

        for value in re.split(r"\s*[|;,]\s*", raw):
            value = _normalise_value(value)

            if 2 <= len(value) <= 100:
                _add_unique(categories, value)

    # Article section is explicit metadata.
    for meta in soup.select("meta[property='article:section']"):
        value = clean_text(
            meta.get("content", "")
        )

        if 2 <= len(value) <= 100:
            _add_unique(categories, value)

    # JSON-LD keywords.
    for obj in json_ld:
        if not isinstance(obj, dict):
            continue

        keywords = obj.get("keywords")

        if isinstance(keywords, str):
            values = re.split(r"\s*[|;,]\s*", keywords)

            for value in values:
                value = _normalise_value(value)

                if 2 <= len(value) <= 100:
                    _add_unique(categories, value)

        elif isinstance(keywords, list):
            for value in keywords:
                if not isinstance(value, str):
                    continue

                value = _normalise_value(value)

                if 2 <= len(value) <= 100:
                    _add_unique(categories, value)

    return categories


# ---------------------------------------------------------------------------
# DESCRIPTION
# ---------------------------------------------------------------------------

def _title_tokens(title):
    return {
        word.lower()
        for word in re.findall(
            r"[A-Za-zÀ-ÿ0-9]{4,}",
            title or "",
        )
    }


def _description_quality(description, title):
    """
    Score a description based on whether it looks relevant to the title.

    This is deliberately deterministic.
    """

    description = clean_text(description)

    if not description:
        return -999

    lowered = description.lower()

    if lowered in GENERIC_DESCRIPTIONS:
        return -999

    if len(description) < 40:
        return -100

    if len(description) > 800:
        return -10

    title_words = _title_tokens(title)

    description_words = {
        word.lower()
        for word in re.findall(
            r"[A-Za-zÀ-ÿ0-9]{4,}",
            description,
        )
    }

    overlap = len(
        title_words.intersection(description_words)
    )

    score = overlap * 10

    # Prefer descriptions that actually describe the case study rather
    # than generic navigation/service copy.
    if "sopra steria" in lowered:
        score += 1

    if "worked with" in lowered:
        score += 2

    if "partnered with" in lowered:
        score += 2

    if "helped" in lowered:
        score += 1

    if "supports" in lowered:
        score += 1

    return score


def _extract_description(soup, main, title):
    """
    Collect candidate descriptions and choose the strongest relevant one.

    This is specifically designed to avoid the two UK cases where the
    generic meta description belonged to another page/template.
    """

    candidates = []

    # Meta descriptions.
    for selector in [
        "meta[name='description']",
        "meta[property='og:description']",
    ]:
        meta = soup.select_one(selector)

        if meta and meta.get("content"):
            value = clean_text(
                meta.get("content")
            )

            if value:
                candidates.append(
                    ("meta", value)
                )

    # First meaningful paragraphs.
    for paragraph in main.find_all("p"):
        value = clean_text(
            paragraph.get_text(" ", strip=True)
        )

        if len(value) < 40:
            continue

        if value.lower() in GENERIC_DESCRIPTIONS:
            continue

        if value not in [
            candidate[1]
            for candidate in candidates
        ]:
            candidates.append(
                ("paragraph", value)
            )

        # We don't need to inspect hundreds of paragraphs.
        if len(candidates) >= 25:
            break

    if not candidates:
        return ""

    scored = []

    for source, value in candidates:
        score = _description_quality(
            value,
            title,
        )

        # Paragraphs are preferred over meta descriptions when their
        # relevance is materially stronger.
        if source == "paragraph":
            score += 3

        scored.append(
            (
                score,
                source == "paragraph",
                value,
            )
        )

    scored.sort(
        key=lambda item: (
            item[0],
            item[1],
            -len(item[2]),
        ),
        reverse=True,
    )

    best_score, _, best_value = scored[0]

    if best_score <= 0:
        # Last-resort meaningful candidate.
        for _, value in candidates:
            if len(value) >= 40:
                return value

    return best_value


# ---------------------------------------------------------------------------
# DATE
# ---------------------------------------------------------------------------

def _extract_date(soup):
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
        "meta[name='date']",
        "meta[name='publish-date']",
        "meta[name='published-date']",
    ]:
        meta = soup.select_one(selector)

        if meta and meta.get("content"):
            value = clean_text(
                meta.get("content")
            )

            if value:
                return value

    return ""


# ---------------------------------------------------------------------------
# DETAIL EXTRACTION
# ---------------------------------------------------------------------------

def extract_detail(html, seed):
    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    main = soup.find("main") or soup

    # ---------------------------------------------------------
    # TITLE
    # ---------------------------------------------------------

    h1 = soup.find("h1")

    if h1:
        title = clean_text(
            h1.get_text(" ", strip=True)
        )
    else:
        meta = soup.select_one(
            "meta[property='og:title']"
        )

        if meta:
            title = clean_text(
                meta.get("content", "")
            )
        else:
            title = seed["anchor_text"]

    if (
        title.lower() in GENERIC_TITLES
        or len(title) < 6
    ):
        return None

    # ---------------------------------------------------------
    # MINIMUM CONTENT
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

    # Netherlands-specific correction retained.
    if (
        str(seed.get("_market", "")).strip().lower()
        == "netherlands"
        and description.lower()
        == "success story | sopra steria"
    ):
        description = ""

        for paragraph in main.find_all("p"):
            candidate = clean_text(
                paragraph.get_text(" ", strip=True)
            )

            if len(candidate) >= 40:
                description = candidate
                break

    # ---------------------------------------------------------
    # DATE
    # ---------------------------------------------------------

    published_date = _extract_date(soup)

    # ---------------------------------------------------------
    # CLIENT
    # ---------------------------------------------------------

    client_name = _extract_client(
        soup,
        json_ld,
    )

    # ---------------------------------------------------------
    # CATEGORIES
    # ---------------------------------------------------------

    categories = _extract_categories(
        soup,
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
