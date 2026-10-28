
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .http import get
from .utils import normalize_url, content_hash
from .adapters.audit_discovery import candidate_links, extract_detail


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CONFIG = ROOT / "config" / "sources.yaml"

MAX_WORKERS = 8
MAX_CANDIDATES_PER_SOURCE = 500

LISTING_TIMEOUT = (8, 30)
DETAIL_TIMEOUT = (5, 45)


def load(path, default):
    if not path.exists():
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def inspect_candidate(item):
    try:
        return (
            item,
            extract_detail(
                get(
                    item["url"],
                    timeout=DETAIL_TIMEOUT,
                    retries=4
                ),
                item
            ),
            None
        )
    except Exception as e:
        return item, None, str(e)


def run():
    sources = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    history = load(DATA / "history.json", {})

    current = {}
    errors = []
    run_at = datetime.now(timezone.utc).isoformat()

    for sid, cfg in sources.items():
        for listing in cfg["listing_urls"]:
            print(
                f"[{cfg['market']}] loading listing...",
                flush=True
            )

            try:
                html = get(
                    listing,
                    timeout=LISTING_TIMEOUT,
                    retries=3
                )
            except Exception as e:
                errors.append({
                    "source": sid,
                    "stage": "listing",
                    "url": listing,
                    "error": str(e)
                })

                print(
                    f"[{cfg['market']}] listing ERROR: {e}",
                    flush=True
                )
                continue

            seeds = list(
                candidate_links(
                    html,
                    listing,
                    cfg
                )
            )

            unique = {
                normalize_url(x["url"]): x
                for x in seeds
            }

            seeds = list(
                unique.values()
            )[:MAX_CANDIDATES_PER_SOURCE]

            print(
                f"[{cfg['market']}] candidates found: "
                f"{len(unique)}; checking: {len(seeds)}",
                flush=True
            )

            accepted = 0

            with ThreadPoolExecutor(
                max_workers=MAX_WORKERS
            ) as pool:

                futures = [
                    pool.submit(
                        inspect_candidate,
                        {**x, "_market": cfg["market"]}
                    )
                    for x in seeds
                ]

                for future in as_completed(futures):
                    seed, detail, error = future.result()

                    if error:
                        errors.append({
                            "source": sid,
                            "stage": "detail",
                            "url": seed["url"],
                            "error": error
                        })
                        continue

                    if not detail:
                        continue

                    url = normalize_url(seed["url"])

                    if url in current:
                        continue

                    r = {
                        "market": cfg["market"],
                        "source_id": sid,
                        "source_domain": cfg["domain"],
                        "source_url": listing,
                        "language": cfg["language"],
                        "title": detail["title"],
                        "description": detail["description"],
                        "url": url,
                        "canonical_url": url,
                        "categories": detail["categories"],
                        "published_date": detail["published_date"],
                        "client_name": detail["client_name"],
                        "first_seen": history.get(
                            url, {}
                        ).get(
                            "first_seen",
                            run_at
                        ),
                        "last_seen": run_at
                    }

                    r["content_hash"] = content_hash(r)

                    old = history.get(url)

                    if old is None:
                        r["status"] = "NEW"
                    else:
                        changed_fields = [
                            "title",
                            "description",
                            "published_date",
                            "categories",
                        ]

                        r["status"] = (
                            "UPDATED"
                            if any(
                                old.get(field, "") != r.get(field, "")
                                for field in changed_fields
                            )
                            else "EXISTING"
                        )

                    current[url] = r
                    accepted += 1

            print(
                f"[{cfg['market']}] accepted: {accepted}",
                flush=True
            )

    counts = {
        status: sum(
            r["status"] == status
            for r in current.values()
        )
        for status in (
            "NEW",
            "UPDATED",
            "EXISTING"
        )
    }

    summary = {
        "run_at": run_at,
        "sources": len(sources),
        "discovered": len(current),
        "new": counts["NEW"],
        "updated": counts["UPDATED"],
        "existing": counts["EXISTING"],
        "errors": len(errors)
    }

    assert (
        summary["new"]
        + summary["updated"]
        + summary["existing"]
        == summary["discovered"]
    )

    # Preserve the complete case-study history.
    save(
        DATA / "history.json",
        {**history, **current}
    )

    # Save the latest complete scrape.
    save(
        DATA / "current.json",
        list(current.values())
    )

    # Maintain a persistent change feed across daily runs.
    # Entries remain until data/changes.json is manually cleared.
    previous_feed = load(DATA / "changes.json", {})
    feed_by_key = {}

    for item in previous_feed.get("changes", []):
        record = item.get("record", {})

        key = normalize_url(
            record.get("canonical_url")
            or record.get("url", "")
        )

        if key:
            feed_by_key[key] = item

    for r in current.values():
        if r["status"] not in ("NEW", "UPDATED"):
            continue

        key = normalize_url(
            r.get("canonical_url")
            or r.get("url", "")
        )

        if not key:
            continue

        prior = feed_by_key.get(key)

        if prior:
            # Preserve the original feed-entry date while refreshing
            # the record and its latest change information.
            entry = {
                "type": r["status"],
                "market": r["market"],
                "detected_at": prior.get(
                    "detected_at",
                    run_at
                ),
                "last_changed_at": run_at,
                "record": r
            }
        else:
            entry = {
                "type": r["status"],
                "market": r["market"],
                "detected_at": run_at,
                "last_changed_at": run_at,
                "record": r
            }

        feed_by_key[key] = entry

    persistent_changes = sorted(
        feed_by_key.values(),
        key=lambda item: item.get(
            "last_changed_at",
            item.get("detected_at", "")
        ),
        reverse=True
    )

    save(
        DATA / "changes.json",
        {
            "summary": summary,
            "changes": persistent_changes,
            "errors": errors,
            "feed_updated_at": run_at
        }
    )

    # Save the audit summary by market.
    by = {}

    for r in current.values():
        market_summary = by.setdefault(
            r["market"],
            {
                "records": 0,
                "new": 0,
                "updated": 0,
                "existing": 0
            }
        )

        market_summary["records"] += 1
        market_summary[r["status"].lower()] += 1

    save(
        DATA / "audit.json",
        {
            "run_at": run_at,
            "summary": summary,
            "by_market": by
        }
    )

    print("FINAL SUMMARY", flush=True)
    print(
        json.dumps(summary, indent=2),
        flush=True
    )


if __name__ == "__main__":
    run()
