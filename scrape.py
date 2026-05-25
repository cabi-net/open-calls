import asyncio
import feedparser
import requests
import os
import re
from datetime import datetime, timezone
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")

KEYWORDS = [
    "open call", "open-call", "residency", "commission", "fellowship",
    "grant", "award", "application", "deadline", "opportunity", "prize",
    "appel à", "appel ouvert", "call for", "apply", "submissions",
    "internship", "volunteer", "job", "position"
]

TITLE_KEYWORDS = [
    "open call", "residency", "commission", "fellowship", "grant",
    "award", "call for", "opportunity", "prize", "appel", "position",
    "job", "hiring", "internship"
]

def matches_keywords(text):
    text = text.lower()
    return any(kw in text for kw in KEYWORDS)

def matches_title_keywords(text):
    text = text.lower()
    return any(kw in text for kw in TITLE_KEYWORDS)

def clean(text):
    return re.sub(r'\s+', ' ', text).strip()

# ─── RSS SOURCES ─────────────────────────────────────────────────────────────

RSS_FEEDS = [
    {
        "name": "Residency Unlimited",
        "url": "https://residencyunlimited.org/feed/",
        "title_only": True  # only match on title, not body
    },
    {
        "name": "ResArtis",
        "url": "https://resartis.org/feed/",
        "title_only": False
    },
    {
        "name": "Ars Electronica",
        "url": "https://ars.electronica.art/news/feed/",
        "title_only": True
    },
]

# ─── SCRAPE TARGETS ───────────────────────────────────────────────────────────

SCRAPE_TARGETS = [
    {"name": "Rhizome",             "url": "https://rhizome.org/community/",                        "wait": 3000},
    {"name": "Eyebeam",             "url": "https://www.eyebeam.org/opportunities/",                 "wait": 2000},
    {"name": "InterAccess",         "url": "https://interaccess.org/opportunities",                  "wait": 2000},
    {"name": "Harbourfront Centre", "url": "https://harbourfrontcentre.com/opportunities/",          "wait": 2000},
    {"name": "Gray Area",           "url": "https://grayarea.org/about/opportunities/",              "wait": 2000},
    {"name": "Onassis ONX",         "url": "https://onassisusa.org/programs",                        "wait": 3000},
    {"name": "transmediale",        "url": "https://transmediale.de/en/calls",                       "wait": 3000},
    {"name": "MUTEK",               "url": "https://montreal.mutek.org/en/calls",                    "wait": 2000},
    {"name": "Ontario Arts Council","url": "https://www.arts.on.ca/grants",                          "wait": 3000},
    {"name": "Canada Council",      "url": "https://canadacouncil.ca/funding/grants",                "wait": 3000},
    {"name": "Creative Capital",    "url": "https://creative-capital.org/apply/",                    "wait": 2000},
    {"name": "La Gaite Lyrique",    "url": "https://gaite-lyrique.net/appels-a-projets",             "wait": 3000},
    {"name": "SFPC",                "url": "https://sfpc.io/",                                       "wait": 2000},
    {"name": "Creative Applications","url": "https://www.creativeapplications.net/category/jobs/",   "wait": 2000},
    {"name": "Blank100",            "url": "https://blank100.com/opportunities/",                    "wait": 2000},
    {"name": "CAFE",                "url": "https://www.callforentry.org/festivals_unique_info.php", "wait": 3000},
]

# ─── RSS FETCHER ──────────────────────────────────────────────────────────────

def fetch_rss():
    results = []
    for source in RSS_FEEDS:
        print(f"Fetching RSS: {source['name']}...")
        try:
            feed = feedparser.parse(source["url"])
            count = 0
            for entry in feed.entries[:30]:
                title = entry.get("title", "")
                summary = entry.get("summary", "")
                link = entry.get("link", "")
                published = entry.get("published", "")

                if source.get("title_only"):
                    if not matches_title_keywords(title):
                        continue
                else:
                    if not matches_keywords(f"{title} {summary}"):
                        continue

                results.append({
                    "source": source["name"],
                    "title": clean(title),
                    "url": link,
                    "excerpt": clean(BeautifulSoup(summary, "html.parser").get_text())[:250],
                    "published": published,
                })
                count += 1
            print(f"  {count} items")
        except Exception as e:
            print(f"  RSS error for {source['name']}: {e}")
    return results

# ─── PLAYWRIGHT SCRAPER ───────────────────────────────────────────────────────

async def scrape_target(page, target):
    results = []
    name = target["name"]
    try:
        await page.goto(target["url"], wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(target.get("wait", 2000))
        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")
        seen = set()

        # Strategy 1: keyword-matching links
        for link in soup.find_all("a", href=True):
            text = link.get_text(separator=" ", strip=True)
            href = link["href"]

            if len(text) < 8 or len(text) > 200:
                continue
            if not matches_keywords(f"{text} {href}"):
                continue
            if href in seen:
                continue
            seen.add(href)

            if href.startswith("/"):
                base = "/".join(target["url"].split("/")[:3])
                href = base + href
            elif not href.startswith("http"):
                continue

            parent = link.parent
            excerpt = ""
            if parent:
                siblings = parent.find_next_siblings(["p", "div"], limit=1)
                if siblings:
                    excerpt = clean(siblings[0].get_text())[:200]

            results.append({
                "source": name,
                "title": clean(text),
                "url": href,
                "excerpt": excerpt,
                "published": "",
            })

        # Strategy 2: heading fallback
        if not results:
            for tag in soup.find_all(["h1", "h2", "h3"]):
                text = tag.get_text(strip=True)
                if matches_keywords(text) and 8 < len(text) < 200:
                    results.append({
                        "source": name,
                        "title": clean(text),
                        "url": target["url"],
                        "excerpt": "",
                        "published": "",
                    })

        if not results:
            print(f"  ⚠ 0 items — page may block scrapers or have no matching content")

    except Exception as e:
        print(f"  ✗ Error: {e}")

    return results

async def fetch_scraped():
    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        await page.set_extra_http_headers({"Accept-Language": "en-US,en;q=0.9"})

        for target in SCRAPE_TARGETS:
            print(f"Scraping: {target['name']}...")
            items = await scrape_target(page, target)
            results.extend(items)
            if items:
                print(f"  {len(items)} items")

        await browser.close()
    return results

# ─── DIGEST WRITER ────────────────────────────────────────────────────────────

def write_digest(all_results):
    os.makedirs("digest", exist_ok=True)
    filepath = f"digest/{DATE}.md"

    seen_urls = set()
    unique = []
    for item in all_results:
        url = item["url"]
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique.append(item)

    by_source = {}
    for item in unique:
        by_source.setdefault(item["source"], []).append(item)

    lines = [
        f"# open calls digest — {DATE}",
        f"\n_{len(unique)} opportunities across {len(by_source)} sources_\n",
        "---\n"
    ]

    for source, items in sorted(by_source.items()):
        lines.append(f"## {source}\n")
        for item in items:
            lines.append(f"**[{item['title']}]({item['url']})**")
            if item["excerpt"]:
                lines.append(f"> {item['excerpt']}")
            if item["published"]:
                lines.append(f"_published: {item['published']}_")
            lines.append("")
        lines.append("---\n")

    if os.path.exists(filepath):
        from datetime import datetime as dt
        ts = dt.now(timezone.utc).strftime("%H%M")
        catch_dir = "digest/catches"
        os.makedirs(catch_dir, exist_ok=True)
        filepath = f"{catch_dir}/{DATE}-{ts}.md"

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\n✓ Digest written: {filepath} ({len(unique)} items)")
    return filepath, len(unique)

# ─── MAIN ─────────────────────────────────────────────────────────────────────

async def main():
    print("=== open calls aggregator ===\n")

    rss_results = fetch_rss()
    print(f"\nRSS total: {len(rss_results)}\n")

    scraped_results = await fetch_scraped()
    print(f"\nScraped total: {len(scraped_results)}\n")

    all_results = rss_results + scraped_results
    filepath, count = write_digest(all_results)

    with open(os.environ.get("GITHUB_ENV", "/dev/null"), "a") as f:
        f.write(f"DIGEST_COUNT={count}\n")
        f.write(f"DIGEST_DATE={DATE}\n")

asyncio.run(main())