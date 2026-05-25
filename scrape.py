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
    "appel à", "appel ouvert"  # French
]

# ─── RSS SOURCES ─────────────────────────────────────────────────────────────

RSS_FEEDS = [
    {
        "name": "Rhizome",
        "url": "https://rhizome.org/feed/",
        "filter": True  # filter by keywords
    },
    {
        "name": "Creative Applications",
        "url": "https://www.creativeapplications.net/feed/",
        "filter": True
    },
    {
        "name": "SFPC",
        "url": "https://sfpc.io/feed.xml",
        "filter": False  # everything from SFPC is relevant
    },
    {
        "name": "Residency Unlimited",
        "url": "https://residencyunlimited.org/feed/",
        "filter": False
    },
    {
        "name": "ResArtis",
        "url": "https://resartis.org/feed/",
        "filter": False
    },
    {
        "name": "Canada Council",
        "url": "https://canadacouncil.ca/rss/all",
        "filter": False
    },
    {
        "name": "Ars Electronica",
        "url": "https://ars.electronica.art/feed/",
        "filter": True
    },
]

# ─── SCRAPE TARGETS (no RSS) ──────────────────────────────────────────────────

SCRAPE_TARGETS = [
    {
        "name": "Eyebeam",
        "url": "https://www.eyebeam.org/opportunities/",
        "selector": "article, .opportunity, .post, h2, h3",
    },
    {
        "name": "InterAccess",
        "url": "https://interaccess.org/opportunities",
        "selector": "article, .views-row, h2, h3",
    },
    {
        "name": "Harbourfront Centre",
        "url": "https://harbourfrontcentre.com/opportunities/",
        "selector": "article, .opportunity, h2, h3",
    },
    {
        "name": "Gray Area",
        "url": "https://grayarea.org/opportunities/",
        "selector": "article, .opportunity, h2, h3",
    },
    {
        "name": "Onassis ONX",
        "url": "https://onassisusa.org/programs",
        "selector": "article, .program, h2, h3",
    },
    {
        "name": "transmediale",
        "url": "https://transmediale.de/en/calls",
        "selector": "article, .call, h2, h3",
    },
    {
        "name": "MUTEK",
        "url": "https://montreal.mutek.org/en/calls",
        "selector": "article, .call, h2, h3",
    },
    {
        "name": "Ontario Arts Council",
        "url": "https://www.arts.on.ca/grants",
        "selector": ".grant, article, h2, h3",
    },
    {
        "name": "Creative Capital",
        "url": "https://creative-capital.org/apply/",
        "selector": "article, .opportunity, h2, h3",
    },
    {
        "name": "La Gaite Lyrique",
        "url": "https://gaite-lyrique.net/appels-a-projets",
        "selector": "article, h2, h3",
    },
    {
        "name": "Blank100",
        "url": "https://blank100.com/opportunities/",
        "selector": "article, .opportunity, h2, h3",
    },
    {
        "name": "CAFE",
        "url": "https://www.callforentry.org/",
        "selector": ".opportunity, h2, h3, .listing",
    },
]

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def matches_keywords(text):
    text = text.lower()
    return any(kw in text for kw in KEYWORDS)

def clean(text):
    return re.sub(r'\s+', ' ', text).strip()

# ─── RSS FETCHER ──────────────────────────────────────────────────────────────

def fetch_rss():
    results = []
    for source in RSS_FEEDS:
        print(f"Fetching RSS: {source['name']}...")
        try:
            feed = feedparser.parse(source["url"])
            for entry in feed.entries[:20]:  # last 20 entries
                title = entry.get("title", "")
                summary = entry.get("summary", "")
                link = entry.get("link", "")
                published = entry.get("published", "")

                text = f"{title} {summary}"

                if source["filter"] and not matches_keywords(text):
                    continue

                results.append({
                    "source": source["name"],
                    "title": clean(title),
                    "url": link,
                    "excerpt": clean(BeautifulSoup(summary, "html.parser").get_text())[:200],
                    "published": published,
                    "type": "rss"
                })
        except Exception as e:
            print(f"  RSS error for {source['name']}: {e}")

    return results

# ─── PLAYWRIGHT SCRAPER ───────────────────────────────────────────────────────

async def scrape_target(page, target):
    results = []
    try:
        await page.goto(target["url"], wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)
        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")

        # try to find links with keyword-matching text
        links = soup.find_all("a", href=True)
        seen = set()

        for link in links:
            text = link.get_text(separator=" ", strip=True)
            href = link["href"]

            if len(text) < 10:
                continue
            if not matches_keywords(text):
                continue
            if href in seen:
                continue

            seen.add(href)

            # resolve relative URLs
            if href.startswith("/"):
                base = "/".join(target["url"].split("/")[:3])
                href = base + href

            results.append({
                "source": target["name"],
                "title": clean(text),
                "url": href,
                "excerpt": "",
                "published": "",
                "type": "scraped"
            })

        # fallback: grab headings if no links matched
        if not results:
            for tag in soup.find_all(["h2", "h3"]):
                text = tag.get_text(strip=True)
                if matches_keywords(text) and len(text) > 10:
                    results.append({
                        "source": target["name"],
                        "title": clean(text),
                        "url": target["url"],
                        "excerpt": "",
                        "published": "",
                        "type": "scraped"
                    })

    except Exception as e:
        print(f"  Scrape error for {target['name']}: {e}")

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
            print(f"  Found {len(items)} items")

        await browser.close()
    return results

# ─── DIGEST WRITER ────────────────────────────────────────────────────────────

def write_digest(all_results):
    os.makedirs("digest", exist_ok=True)
    filepath = f"digest/{DATE}.md"

    # deduplicate by URL
    seen_urls = set()
    unique = []
    for item in all_results:
        if item["url"] not in seen_urls:
            seen_urls.add(item["url"])
            unique.append(item)

    # group by source
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
                lines.append(f"> {item['excerpt'][:200]}")
            if item["published"]:
                lines.append(f"_published: {item['published']}_")
            lines.append("")
        lines.append("---\n")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\nDigest written: {filepath} ({len(unique)} items)")
    return filepath, len(unique)

# ─── MAIN ─────────────────────────────────────────────────────────────────────

async def main():
    print("=== open calls aggregator ===\n")

    rss_results = fetch_rss()
    print(f"\nRSS: {len(rss_results)} items\n")

    scraped_results = await fetch_scraped()
    print(f"\nScraped: {len(scraped_results)} items\n")

    all_results = rss_results + scraped_results
    filepath, count = write_digest(all_results)

    # write count to env for Telegram notification
    with open(os.environ.get("GITHUB_ENV", "/dev/null"), "a") as f:
        f.write(f"DIGEST_COUNT={count}\n")
        f.write(f"DIGEST_DATE={DATE}\n")

asyncio.run(main())
