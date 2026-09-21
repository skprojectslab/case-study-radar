import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


# ============================================================
# CASE STUDY RADAR — SOURCE AUDIT
# ============================================================

SOURCES = [

    {
        "market": "UK",
        "name": "Sopra Steria UK",
        "url": "https://www.soprasteria.co.uk/insights/client-success-stories",
    },

    {
        "market": "Germany",
        "name": "Sopra Steria Germany",
        "url": "https://www.soprasteria.de/newsroom/success-stories",
    },

    {
        "market": "Belgium",
        "name": "Sopra Steria Belgium",
        "url": "https://www.soprasteria.be/newsroom/success-stories",
    },

    {
        "market": "Denmark",
        "name": "Sopra Steria Denmark",
        "url": "https://www.soprasteria.dk/Referencer",
    },

    {
        "market": "Italy",
        "name": "Sopra Steria Italy",
        "url": "https://www.soprasteria.it/chi-siamo/storie-di-successo",
    },

    {
        "market": "Luxembourg",
        "name": "Sopra Steria Luxembourg",
        "url": "https://www.soprasteria.lu/newsroom/success-stories",
    },

    {
        "market": "Netherlands",
        "name": "Sopra Steria Netherlands",
        "url": "https://www.soprasteria.nl/newsroom/success-stories",
    },

    {
        "market": "France",
        "name": "Sopra Steria France",
        "url": "https://www.soprasteria.fr/espace-media/cas-client",
    },

    {
        "market": "Sweden",
        "name": "Sopra Steria Sweden",
        "url": "https://www.soprasteria.se/kundreferenser/",
    },

    {
        "market": "India",
        "name": "Sopra Steria India",
        "url": "https://www.soprasteria.in/insights#clientstories",
    },

    {
        "market": "Norway",
        "name": "Sopra Steria Norway",
        "url": "https://www.soprasteria.no/prosjekter",
    },

]


# ============================================================
# KEYWORDS USED TO IDENTIFY POSSIBLE CASE STUDY LINKS
# ============================================================

KEYWORDS = [

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

]


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def clean_text(text):

    if not text:
        return ""

    return re.sub(
        r"\s+",
        " ",
        text
    ).strip()


def looks_like_case_study_link(url):

    url_lower = url.lower()

    return any(
        keyword in url_lower
        for keyword in KEYWORDS
    )


def same_domain(base_url, test_url):

    base_domain = urlparse(base_url).netloc

    test_domain = urlparse(test_url).netloc

    return (
        base_domain == test_domain
    )


# ============================================================
# AUDIT ONE SOURCE
# ============================================================

def audit_source(page, source):

    market = source["market"]
    name = source["name"]
    url = source["url"]

    print()
    print("=" * 65)
    print(f"[{market}] {name}")
    print("=" * 65)
    print(f"URL: {url}")

    result = {
        "market": market,
        "name": name,
        "url": url,
        "status": "FAILED",
        "candidate_links": 0,
        "sample_titles": [],
        "dates_detected": False,
        "load_more_detected": False,
        "error": None,
    }

    try:

        response = page.goto(
            url,
            wait_until="networkidle",
            timeout=60000
        )

        page.wait_for_timeout(3000)

        status = response.status if response else "UNKNOWN"

        print(f"HTTP Status: {status}")

        html = page.content()

        soup = BeautifulSoup(
            html,
            "lxml"
        )

        title = clean_text(
            soup.title.get_text()
            if soup.title
            else ""
        )

        print(f"Page Title: {title}")

        # ----------------------------------------------------
        # GET ALL LINKS
        # ----------------------------------------------------

        all_links = []

        for a in soup.find_all("a"):

            href = a.get("href")

            if not href:
                continue

            full_url = urljoin(
                url,
                href
            )

            if not same_domain(
                url,
                full_url
            ):
                continue

            link_text = clean_text(
                a.get_text(" ", strip=True)
            )

            all_links.append({
                "url": full_url,
                "text": link_text
            })


        # ----------------------------------------------------
        # FIND POSSIBLE CASE STUDY LINKS
        # ----------------------------------------------------

        candidates = []

        seen_urls = set()

        for link in all_links:

            link_url = link["url"]

            link_text = link["text"]

            if link_url in seen_urls:
                continue

            if (
                looks_like_case_study_link(
                    link_url
                )
                or
                looks_like_case_study_link(
                    link_text
                )
            ):

                seen_urls.add(
                    link_url
                )

                candidates.append(
                    link
                )


        result["candidate_links"] = len(
            candidates
        )


        # ----------------------------------------------------
        # SAMPLE TITLES
        # ----------------------------------------------------

        sample_titles = []

        for item in candidates[:10]:

            text = item["text"]

            if (
                text
                and len(text) > 5
            ):

                sample_titles.append(
                    text
                )

        result["sample_titles"] = sample_titles


        # ----------------------------------------------------
        # DATE DETECTION
        # ----------------------------------------------------

        text_content = soup.get_text(
            " ",
            strip=True
        )

        date_patterns = [

            r"\b\d{1,2}\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b",

            r"\b\d{1,2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+\d{4}\b",

            r"\b\d{4}-\d{2}-\d{2}\b",

        ]

        for pattern in date_patterns:

            if re.search(
                pattern,
                text_content,
                re.IGNORECASE
            ):

                result[
                    "dates_detected"
                ] = True

                break


        # ----------------------------------------------------
        # LOAD MORE / PAGINATION DETECTION
        # ----------------------------------------------------

        page_text_lower = text_content.lower()

        load_more_words = [

            "load more",
            "show more",
            "view more",

            "next",

            "visa fler",
            "vis flere",

            "mehr laden",
            "mehr anzeigen",

            "voir plus",

            "carica altro",

        ]

        result[
            "load_more_detected"
        ] = any(

            word in page_text_lower

            for word in load_more_words

        )


        # ----------------------------------------------------
        # STATUS
        # ----------------------------------------------------

        result["status"] = "OK"

        print(
            f"Candidate case-study links: "
            f"{len(candidates)}"
        )

        print(
            f"Dates detected: "
            f"{'YES' if result['dates_detected'] else 'NO'}"
        )

        print(
            f"Load more / pagination detected: "
            f"{'YES' if result['load_more_detected'] else 'NO'}"
        )


        print()
        print("Sample candidate titles:")

        if sample_titles:

            for sample in sample_titles:

                print(
                    f"  • {sample}"
                )

        else:

            print(
                "  No link text samples found."
            )


    except Exception as e:

        result["error"] = str(e)

        print()
        print(
            f"ERROR: {e}"
        )


    return result


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 65)
    print("CASE STUDY RADAR — SOURCE AUDIT")
    print("=" * 65)

    results = []

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True
        )

        page = browser.new_page(
            viewport={
                "width": 1440,
                "height": 1200
            }
        )

        for source in SOURCES:

            result = audit_source(
                page,
                source
            )

            results.append(
                result
            )


        browser.close()


    # ========================================================
    # SUMMARY
    # ========================================================

    print()
    print()
    print("=" * 65)
    print("FINAL SUMMARY")
    print("=" * 65)

    working = [

        r for r in results

        if r["status"] == "OK"

    ]

    failed = [

        r for r in results

        if r["status"] != "OK"

    ]


    print(
        f"Sources tested: {len(results)}"
    )

    print(
        f"Working: {len(working)}"
    )

    print(
        f"Failed: {len(failed)}"
    )


    print()
    print("SOURCE RESULTS")
    print("-" * 65)


    for r in results:

        print()

        print(
            f"{r['market']}: "
            f"{r['status']}"
        )

        print(
            f"  Candidate links: "
            f"{r['candidate_links']}"
        )

        print(
            f"  Dates: "
            f"{'YES' if r['dates_detected'] else 'NO'}"
        )

        print(
            f"  Load more: "
            f"{'YES' if r['load_more_detected'] else 'NO'}"
        )

        if r["error"]:

            print(
                f"  Error: "
                f"{r['error']}"
            )


    print()
    print("=" * 65)
    print("AUDIT COMPLETE")
    print("=" * 65)


if __name__ == "__main__":

    main()